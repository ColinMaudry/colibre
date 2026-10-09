# src/mcp/queries.py
import os
import re
from typing import Literal

from src.api.filters import OPERATORS, FilterError, build_where
from src.db import aggregate_marches, count_marches, query_marches
from src.db import schema as duckdb_schema
from src.mcp.serialization import to_json_records
from src.utils.data import DATA_SCHEMA, DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org

PAGE_SIZE = 50
# Même borne que l'API REST (src/api/routes.py.MAX_PAGE_SIZE).
MAX_PAGE_SIZE = 1000
TOP_N = 10
ORG_FRAMES = {"acheteur": DF_ACHETEURS, "titulaire": DF_TITULAIRES}

# Colonnes renvoyées par rechercher_marches (sortie ciblée, pas SELECT *).
MARCHES_COLUMNS = [
    "uid",
    "objet",
    "montant",
    "dateNotification",
    "codeCPV",
    "acheteur_id",
    "acheteur_nom",
    "acheteur_departement_code",
    "titulaire_id",
    "titulaire_nom",
]

# Colonnes sélectionnables par le client : le schéma de référence (présent en
# base) uni aux colonnes du défaut, pour que tout le défaut reste re-sélectionnable
# même si une colonne enrichie (ex. acheteur_nom) est absente de DATA_SCHEMA.
_FILTRABLES = tuple(name for name in DATA_SCHEMA if name in duckdb_schema)
SELECTABLE_COLUMNS = tuple(dict.fromkeys((*MARCHES_COLUMNS, *_FILTRABLES)))

# Enum exposé dans le schéma du tool (UX : liste fermée pour l'agent/le client).
ColonneMarche = Literal[SELECTABLE_COLUMNS]

# (param nommé, colonne decp, opérateur du moteur de filtres API).
# `greater` = >=, `less` = <=, `contains` = LIKE %v%, `exact` = =.
_NAMED_FILTERS = [
    ("acheteur_id", "acheteur_id", "exact"),
    ("titulaire_id", "titulaire_id", "exact"),
    ("cpv", "codeCPV", "startswith"),
    ("objet_contient", "objet", "contains"),
    ("montant_min", "montant", "greater"),
    ("montant_max", "montant", "less"),
    ("date_min", "dateNotification", "greater"),
    ("date_max", "dateNotification", "less"),
    ("departement", "acheteur_departement_code", "exact"),
]


def describe_schema() -> dict:
    """Schéma des marchés (même source que /schema de l'API REST).

    Limité aux colonnes réellement filtrables via filtres_avances (présentes
    dans la table DuckDB). L'agrégation (groupby/sum/...) n'est pas supportée
    ici : c'est une fonctionnalité de l'API REST /data.
    """
    colonnes = {
        name: {
            "type": field.get("type"),
            "titre": field.get("title"),
            "description": field.get("description"),  # inclut les énumérations
        }
        for name, field in DATA_SCHEMA.items()
        if name in duckdb_schema  # exclut la colonne virtuelle "marche"
    }
    return {
        "colonnes_filtrables": colonnes,
        "colonnes_retournees": [*MARCHES_COLUMNS, "lien"],
        "colonnes_disponibles": list(SELECTABLE_COLUMNS),
        "operateurs": sorted(OPERATORS),
        "filtres_nommes": {p: f"{c}__{o}" for p, c, o in _NAMED_FILTERS},
    }


def build_where_args(
    named: dict, filtres_avances: dict | None
) -> list[tuple[str, str]]:
    """Traduit les paramètres nommés + filtres avancés en tuples (col__op, valeur)."""
    args: list[tuple[str, str]] = []
    for param, col, op in _NAMED_FILTERS:
        value = named.get(param)
        if value is not None:
            args.append((f"{col}__{op}", str(value)))
    if filtres_avances:
        for key, value in filtres_avances.items():
            args.append((key, str(value)))
    return args


def search_marches(
    *,
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    filtres_avances: dict | None = None,
    colonnes: list[str] | None = None,
) -> dict:
    """Recherche paginée de marchés. Même sémantique de filtres que l'API REST."""
    named = {
        "acheteur_id": acheteur_id,
        "titulaire_id": titulaire_id,
        "cpv": cpv,
        "objet_contient": objet_contient,
        "montant_min": montant_min,
        "montant_max": montant_max,
        "date_min": date_min,
        "date_max": date_max,
        "departement": departement,
    }
    args = build_where_args(named, filtres_avances)
    try:
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        return {"error": str(e), "champ": e.field}

    if colonnes is None:
        out_columns = list(MARCHES_COLUMNS)
    else:
        invalid = [c for c in colonnes if c not in SELECTABLE_COLUMNS]
        if invalid:
            return {"error": f"colonne inconnue: {invalid[0]}", "champ": invalid[0]}
        # uid toujours présent (clé primaire + nécessaire au lien) ; dédoublonne
        # toute la liste (un client peut répéter une colonne malgré l'enum, ce
        # qui produirait des noms de colonnes dupliqués au SELECT).
        out_columns = list(dict.fromkeys(["uid", *colonnes]))

    page = max(1, int(page))
    page_size = int(page_size)
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        return {
            "error": f"page_size doit être dans [1, {MAX_PAGE_SIZE}]",
            "champ": "page_size",
        }
    offset = (page - 1) * page_size
    order_by = order_sql or '"dateNotification" DESC, "uid" DESC'
    df = query_marches(
        where_sql,
        params,
        columns=out_columns,
        order_by=order_by,
        limit=page_size,
        offset=offset,
    )
    total = count_marches(where_sql, params)
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    marches = to_json_records(df)
    for marche in marches:
        marche["lien"] = f"{base}/marches/{marche['uid']}"
    return {
        "meta": {"page": page, "page_size": page_size, "total": total},
        "marches": marches,
    }


def _extract_plain_text(html_str: str) -> str:
    """Extract plain text from HTML link, e.g. '<a...>123</a>' -> '123'."""
    match = re.search(r">([^<]+)<", html_str)
    return match.group(1) if match else html_str


def search_organisations(
    query: str, org_type: str = "acheteur", limite: int = 20
) -> list[dict]:
    """Recherche des organisations par nom, résout un nom -> id."""
    if org_type not in ORG_FRAMES:
        raise ValueError(
            f"type invalide: {org_type!r} (attendu 'acheteur' ou 'titulaire')"
        )
    df = search_org(ORG_FRAMES[org_type], query, org_type, track=False).head(limite)
    return [
        {
            "id": _extract_plain_text(r[f"{org_type}_id"]),
            "nom": _extract_plain_text(r[f"{org_type}_nom"]),
            "departement": r.get("Département"),
        }
        for r in df.to_dicts()
    ]


def _org_identite(org_type: str, org_id: str) -> dict:
    df = query_marches(
        where_sql=f'"{org_type}_id" = ?',
        params=[org_id],
        columns=[
            f"{org_type}_id",
            f"{org_type}_nom",
            f"{org_type}_departement_nom",
            f"{org_type}_commune_nom",
        ],
        limit=1,
    )
    if df.height == 0:
        return {"id": org_id, "nom": None, "departement": None, "commune": None}
    r = df.row(0, named=True)
    return {
        "id": org_id,
        "nom": r[f"{org_type}_nom"],
        "departement": r[f"{org_type}_departement_nom"],
        "commune": r[f"{org_type}_commune_nom"],
    }


def compute_org_stats(org_type: str, org_id: str) -> dict:
    """Statistiques agrégées d'un acheteur ou titulaire."""
    if org_type not in ORG_FRAMES:
        raise ValueError(
            f"type invalide: {org_type!r} (attendu 'acheteur' ou 'titulaire')"
        )
    other = "titulaire" if org_type == "acheteur" else "acheteur"
    where_sql = f'"{org_type}_id" = ?'
    params = [org_id]
    identite = _org_identite(org_type, org_id)

    totals = aggregate_marches(
        select_sql='COUNT("uid") AS nb, COALESCE(SUM("montant"), 0) AS montant_total',
        where_sql=where_sql,
        params=params,
    )
    nb = int(totals["nb"][0])
    if nb == 0:
        return {
            "identite": identite,
            "nb_marches": 0,
            "montant_total": 0.0,
            "repartition_annuelle": [],
            f"top_{other}s": [],
            "top_cpv": [],
        }

    annuelle = aggregate_marches(
        select_sql=(
            "CAST(date_part('year', \"dateNotification\") AS INTEGER) AS annee, "
            'COUNT("uid") AS nb_marches, '
            'COALESCE(SUM("montant"), 0) AS montant_total'
        ),
        where_sql=where_sql,
        params=params,
        group_by="date_part('year', \"dateNotification\")",
        order_by="annee",
    )
    top_other = aggregate_marches(
        select_sql=(
            f'"{other}_id" AS id, any_value("{other}_nom") AS nom, '
            'COUNT("uid") AS nb_marches, '
            'COALESCE(SUM("montant"), 0) AS montant_total'
        ),
        where_sql=where_sql,
        params=params,
        group_by=f'"{other}_id"',
        order_by="nb_marches DESC",
        limit=TOP_N,
    )
    top_cpv = aggregate_marches(
        select_sql='"codeCPV" AS cpv, COUNT("uid") AS nb_marches',
        where_sql=where_sql,
        params=params,
        group_by='"codeCPV"',
        order_by="nb_marches DESC",
        limit=TOP_N,
    )
    return {
        "identite": identite,
        "nb_marches": nb,
        "montant_total": float(totals["montant_total"][0]),
        "repartition_annuelle": to_json_records(annuelle),
        f"top_{other}s": to_json_records(top_other),
        "top_cpv": to_json_records(top_cpv),
    }
