from datetime import datetime, timezone
from pathlib import Path

import orjson
from flask import Response, g, request
from flask_smorest import Blueprint, abort

from src.api import tracking
from src.api.auth import require_token
from src.api.filters import FilterError, build_where, parse_aggregators
from src.db import DB_PATH, aggregate_marches, count_marches, get_cursor, query_marches
from src.db import schema as duckdb_schema
from src.utils import logger
from src.utils.data import DATA_SCHEMA

bp = Blueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="API privée colibre — accès tabulaire aux marchés publics.",
)

MAX_PAGE_SIZE = 200


def _parse_pagination():
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "50"))
    except ValueError:
        abort(400, message="page et page_size doivent être des entiers")
    if page < 1:
        abort(400, message="page doit être >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        abort(
            400,
            message=f"page_size doit être dans [1, {MAX_PAGE_SIZE}]",
        )
    return page, page_size


def _parse_columns():
    raw = request.args.get("columns")
    if not raw:
        return None
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = [c for c in cols if c not in duckdb_schema]
    if unknown:
        abort(400, message=f"Colonnes inconnues : {unknown}")
    return cols


def _build_links(page, page_size, total):
    base = request.path
    qs = request.args.to_dict(flat=False)
    qs.pop("page", None)

    def url_for(p):
        from urllib.parse import urlencode

        params = [(k, v) for k, vs in qs.items() for v in vs]
        params.append(("page", str(p)))
        return f"{base}?{urlencode(params)}"

    prev_url = url_for(page - 1) if page > 1 else None
    next_url = None
    if total is None or page * page_size < total:
        next_url = url_for(page + 1)
    return {"prev": prev_url, "next": next_url}


@bp.after_request
def _track_consumption(response):
    token_id = getattr(g, "token_id", None)
    if token_id is not None:
        tracking.enqueue_counter_update(token_id)
        tracking.enqueue_matomo_event(
            token_id=token_id,
            path=request.path,
            query_string=request.query_string.decode("utf-8", errors="replace"),
            status_code=response.status_code,
            user_agent=request.headers.get("User-Agent", ""),
        )
    return response


@bp.route("/health")
def health():
    """Sonde de santé, sans authentification.

    Interroge réellement DuckDB : un 200 statique resterait vert avec une base
    absente ou corrompue. Expose aussi la fraîcheur des données, car
    `_ensure_database` rattrape un rebuild raté en réutilisant la base
    existante — l'app démarre alors normalement, en servant des données
    périmées sans que rien ne le signale.
    """
    try:
        get_cursor().execute("SELECT 1 FROM decp LIMIT 1").fetchone()
        construites_le = datetime.fromtimestamp(
            Path(DB_PATH).stat().st_mtime, tz=timezone.utc
        )
    except Exception:
        logger.exception("Sonde /health : DuckDB injoignable")
        return {"status": "error"}, 503

    age_heures = (datetime.now(timezone.utc) - construites_le).total_seconds() / 3600
    return {
        "status": "ok",
        "donnees": {
            "construites_le": construites_le.isoformat(),
            "age_heures": round(age_heures, 1),
        },
    }


@bp.route("/schema")
def schema():
    """Liste des champs disponibles dans le dataset DECP (format TableSchema)."""
    return {"fields": list(DATA_SCHEMA.values())}


@bp.route("/data")
@bp.doc(
    security=[{"BearerAuth": []}],
    parameters=[
        {
            "name": "page",
            "in": "query",
            "schema": {"type": "integer", "default": 1, "minimum": 1},
            "description": "Numéro de page (commence à 1).",
        },
        {
            "name": "page_size",
            "in": "query",
            "schema": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
            "description": "Nombre de résultats par page (max 200).",
        },
        {
            "name": "columns",
            "in": "query",
            "schema": {"type": "string"},
            "description": "Liste de colonnes à retourner, séparées par des virgules (ex: `id,acheteur_id,montant`). Par défaut : toutes.",
        },
        {
            "name": "count_results",
            "in": "query",
            "schema": {"type": "string", "enum": ["true", "false"], "default": "true"},
            "description": "Inclure le total (`COUNT(*)`) dans `meta`. Mettre `false` pour accélérer la requête. Ignoré en mode agrégation.",
        },
        # Objet free-form : OpenAPI n'a pas de nom de paramètre variable, et un
        # nom littéral `<colonne>__<opérateur>` amenait Swagger UI à envoyer le
        # placeholder comme nom réel (`?%3Ccolonne%3E__%3Cop%C3%A9rateur%3E=...`)
        # → 400. Avec `style: form` + `explode: true`, Swagger UI affiche un
        # champ JSON clé/valeur et sérialise `?colonne__op=valeur`. Le `name`
        # n'apparaît jamais dans l'URL, il sert juste d'étiquette.
        #
        # `additionalProperties: true` plutôt que `{"type": "string"}` : Swagger
        # UI exige du JSON valide dans ce champ (le YAML est refusé avant même
        # l'envoi), autant y autoriser les nombres nus et `null` — qui sérialise
        # en `col__groupby=`, la forme courte des drapeaux d'agrégation.
        {
            "name": "filtres",
            "in": "query",
            "style": "form",
            "explode": True,
            "schema": {"type": "object", "additionalProperties": True},
            "example": {
                "acheteur_id__contains": "VILLE",
                "montant__greater": 1000000,
            },
            "description": (
                "Filtres et agrégations dynamiques, saisis ici en JSON "
                '`{"<colonne>__<opérateur>": <valeur>}` — chaque paire '
                "devient un paramètre `?<colonne>__<opérateur>=<valeur>` de "
                "l'URL (voir les colonnes via `/schema`). Les nombres se "
                "passent sans guillemets, et les drapeaux sans valeur "
                "(`groupby`, `count`, `sum`, ...) s'écrivent `null`.\n\n"
                "**Filtres** (`<colonne>__<op>=<valeur>`) :\n"
                "- `exact` : égal à la valeur\n"
                "- `differs` : différent de la valeur (null-safe, `IS DISTINCT FROM`)\n"
                "- `contains` / `notcontains` : contient / ne contient pas "
                "(insensible à la casse ; sur `objet`, aussi aux accents, aux "
                "ligatures œ/æ et à l'apostrophe typographique)\n"
                "- `startswith` : commence par (préfixe, insensible à la casse "
                "et, sur `objet`, aux accents, ligatures et apostrophes "
                "typographiques, ex. `codeCPV__startswith=72`)\n"
                "- `in` / `notin` : dans / hors d'une liste séparée par des virgules\n"
                "- `less` / `greater` : ≤ / ≥\n"
                "- `strictly_less` / `strictly_greater` : < / >\n"
                "- `isnull` / `isnotnull` : valeur nulle / non nulle (sans valeur)\n"
                "- `sort` : tri, valeur `asc` ou `desc`\n\n"
                "**Agrégation** (drapeaux sans valeur, ex. `acheteur_departement_code__groupby&montant__sum`) :\n"
                "- `groupby` : regroupe sur la colonne\n"
                "- `count`, `sum`, `avg`, `min`, `max` : agrège la colonne ; "
                "la colonne de sortie est nommée `colonne__count`, `colonne__sum`, "
                "`colonne__avg`, `colonne__min`, `colonne__max`\n\n"
                "En mode agrégation, la réponse contient des lignes groupées, "
                "`columns` est interdit et `meta` ne contient pas `total`. "
                "`sort` peut être appliqué sur une colonne `groupby` (ex. `acheteur_departement_code__sort=asc`) ; "
                "il n'est pas supporté sur les alias d'agrégats (ex. `uid__count__sort=desc` → 400).\n\n"
                "Exemples d'URL : `acheteur_id__contains=VILLE`, `montant__greater=10000`, "
                "`acheteur_departement_code__groupby&montant__sum`, "
                "`acheteur_departement_code__groupby&uid__count&acheteur_departement_code__sort=asc`.\n\n"
                "Les mêmes, saisis dans ce champ :\n"
                '- `{"acheteur_id__contains": "VILLE", "montant__greater": 10000}`\n'
                '- `{"acheteur_departement_code__groupby": null, "montant__sum": null}`\n'
                '- `{"acheteur_departement_code__groupby": null, "uid__count": null, '
                '"acheteur_departement_code__sort": "asc"}`'
            ),
        },
    ],
)
@require_token
def data():
    """Récupère des marchés publics filtrés, triés ou agrégés.

    Filtres en query string : `<colonne>__<opérateur>=<valeur>`.
    Opérateurs de filtre : exact, differs, contains, notcontains, startswith,
    in, notin, less, greater, strictly_less, strictly_greater, isnull,
    isnotnull, sort.

    Agrégation (drapeaux sans valeur) : `<colonne>__groupby`,
    `<colonne>__count|sum|avg|min|max`. Les colonnes agrégées sont nommées
    `<colonne>__<opérateur>`. `columns` est interdit avec une agrégation et
    `meta` ne contient alors pas `total`. `sort` est supporté sur les colonnes
    `groupby` ; non supporté sur les alias d'agrégats (→ 400).

    Paramètres réservés : page (défaut 1), page_size (défaut 50, max 200),
    columns (csv), count_results (true|false ; mettre false pour économiser
    le COUNT(*)).

    Exemple d'agrégation :
    `?acheteur_departement_code__groupby&uid__count&montant__sum`
    """
    page, page_size = _parse_pagination()
    columns = _parse_columns()
    count_results = request.args.get("count_results", "true").lower() != "false"

    args = list(request.args.items(multi=True))
    try:
        agg = parse_aggregators(args, duckdb_schema)
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        abort(400, message=str(e), errors={"field": e.field})

    if agg is not None:
        if columns:
            abort(
                400,
                message="`columns` ne peut pas être combiné avec une agrégation",
            )
        df = aggregate_marches(
            select_sql=agg.select_sql,
            where_sql=where_sql,
            params=params,
            group_by=agg.group_by_sql,
            order_by=order_sql or None,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        # Si la page est partielle, on connaît le total exact ; sinon on ne sait pas.
        agg_total = (
            (page - 1) * page_size + df.height if df.height < page_size else None
        )
        return Response(
            orjson.dumps(
                {
                    "data": df.to_dicts(),
                    "meta": {"page": page, "page_size": page_size},
                    "links": _build_links(page, page_size, agg_total),
                }
            ),
            mimetype="application/json",
        )

    df = query_marches(
        where_sql=where_sql,
        params=params,
        columns=columns,
        order_by=order_sql,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    total = count_marches(where_sql, params) if count_results else None
    meta = {"page": page, "page_size": page_size}
    if total is not None:
        meta["total"] = total

    return Response(
        orjson.dumps(
            {
                "data": df.to_dicts(),
                "meta": meta,
                "links": _build_links(page, page_size, total),
            }
        ),
        mimetype="application/json",
    )
