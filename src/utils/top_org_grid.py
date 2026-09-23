"""Grilles « Top acheteurs / Top titulaires » paginées côté serveur (#142).

Les tops étaient des AG Grid client-side : tout le classement agrégé partait
au navigateur (jusqu'à 33 Mo dans l'observatoire, d'où une troncature à 100
lignes qui rendait le filtre trompeur). Ici, chaque page est agrégée, filtrée
et triée par DuckDB, et seules les lignes affichées transitent.

Ce module ne contient que des fonctions pures + la fabrique de grille ; les
callbacks de datasource vivent dans les pages, qui savent reconstruire leur
périmètre SQL (cf. src/utils/entity_grid.py, même découpage).
"""

import polars as pl
from dash import no_update

from src.db import aggregate_marches, count_aggregate, schema
from src.utils import logger
from src.utils.cache import cache
from src.utils.query_ast import ast_to_sql, filtermodel_to_ast
from src.utils.table import add_links

#: Nom de la colonne agrégée, affichée telle quelle dans la grille.
AGG_COLUMN = "Attributions"
_AGG_SQL = "COUNT(*)"

#: Opérateurs du filtre numérique AG Grid → SQL. `inRange` est traité à part
#: (deux valeurs), `blank`/`notBlank` n'ont pas de sens sur un COUNT(*).
_NUM_OPS = {
    "equals": "=",
    "notEqual": "<>",
    "lessThan": "<",
    "lessThanOrEqual": "<=",
    "greaterThan": ">",
    "greaterThanOrEqual": ">=",
}


def group_columns(org_type: str, extra_columns=()) -> list[str]:
    """Colonnes du GROUP BY (hors agrégat), dans l'ordre d'affichage.

    `titulaire_typeIdentifiant` est nécessaire à `add_links`, qui ne pose un
    lien vers la fiche que pour les SIRET. Les colonnes absentes du schéma
    sont écartées : tests/test.parquet n'en porte qu'un sous-ensemble.
    """
    cols = [f"{org_type}_id", f"{org_type}_nom"]
    if org_type == "titulaire":
        cols.append("titulaire_typeIdentifiant")
    cols += [c for c in extra_columns if c not in cols]
    return [c for c in cols if c in schema.names()]


def _to_number(value):
    """Convertit en nombre sans tronquer (AG Grid autorise une décimale sur
    un filtre numérique : `int()` tronquerait silencieusement 5.5 en 5, ce
    qui fausserait le filtre sans avertissement). Rend un `int` quand la
    valeur est entière, pour garder les paramètres liés usuels (`[5]`)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        logger.warning(
            f"Filtre {AGG_COLUMN} : valeur non numérique ignorée ({value!r})"
        )
        return None
    return int(number) if number.is_integer() else number


def _having_leaf(cond: dict) -> tuple[str, list]:
    op = cond.get("type")
    if op == "inRange":
        low, high = _to_number(cond.get("filter")), _to_number(cond.get("filterTo"))
        if low is None or high is None:
            return "", []
        return f"{_AGG_SQL} BETWEEN ? AND ?", [low, high]
    sql_op = _NUM_OPS.get(op)
    value = _to_number(cond.get("filter"))
    if sql_op is None or value is None:
        if sql_op is None:
            logger.warning(f"Filtre {AGG_COLUMN} : opérateur ignoré ({op!r})")
        return "", []
    return f"{_AGG_SQL} {sql_op} ?", [value]


def _having_sql(spec: dict | None) -> tuple[str, list]:
    """Traduit le filtre AG Grid de la colonne agrégée en clause HAVING.

    `filtermodel_to_ast` ne peut pas s'en charger : il valide les colonnes
    contre le schéma DECP, or `Attributions` n'existe qu'après agrégation.
    """
    if not spec:
        return "", []
    conditions = spec.get("conditions")
    if conditions is None:  # forme dépréciée condition1/condition2, ou unitaire
        conditions = [
            c for c in (spec.get("condition1"), spec.get("condition2")) if c
        ] or [spec]
    joiner = " OR " if spec.get("operator") == "OR" else " AND "

    fragments, params = [], []
    for cond in conditions:
        sql, cond_params = _having_leaf(cond)
        if sql:
            fragments.append(f"({sql})")
            params.extend(cond_params)
    return (joiner.join(fragments), params) if fragments else ("", [])


def top_org_filter_sql(
    filter_model, org_type: str, extra_columns=()
) -> tuple[str, list, str, list]:
    """(where_sql, where_params, having_sql, having_params) pour un filterModel.

    Les colonnes non agrégées passent par l'AST partagé (`filtermodel_to_ast`
    + `ast_to_sql`), qui gère notamment le désaccentuage des noms (#138). La
    colonne agrégée part en HAVING. Toute autre clé est ignorée : seules les
    colonnes du GROUP BY sont filtrables.
    """
    model = dict(filter_model or {})
    agg_spec = model.pop(AGG_COLUMN, None)

    allowed = set(group_columns(org_type, extra_columns))
    for column in [c for c in model if c not in allowed]:
        logger.warning(f"Filtre top ignoré (colonne hors périmètre) : {column!r}")
        model.pop(column)

    where_sql, where_params = ast_to_sql(filtermodel_to_ast(model, schema), schema)
    having_sql, having_params = _having_sql(agg_spec)
    return where_sql, where_params, having_sql, having_params


def top_org_sort_sql(sort_model, org_type: str, extra_columns=()) -> str:
    """Clause ORDER BY, avec l'id en dernier critère (pagination stable).

    Sans ce départage, deux organisations à égalité peuvent changer d'ordre
    d'une page à l'autre et apparaître deux fois ou pas du tout.
    """
    allowed = set(group_columns(org_type, extra_columns)) | {AGG_COLUMN}
    fragments = []
    for item in sort_model or []:
        column = item.get("colId")
        if column not in allowed:
            logger.warning(f"Tri top ignoré (colonne inconnue) : {column!r}")
            continue
        direction = "DESC" if item.get("sort") == "desc" else "ASC"
        fragments.append(f'"{column}" {direction}')

    if not fragments:
        fragments.append(f'"{AGG_COLUMN}" DESC')
    fragments.append(f'"{org_type}_id" ASC')
    return ", ".join(fragments)


def _select_and_group(org_type: str, extra_columns=()) -> tuple[str, str]:
    """Fragments SELECT et GROUP BY partagés par le COUNT et la page."""
    group_by = ", ".join(f'"{c}"' for c in group_columns(org_type, extra_columns))
    return f'{group_by}, {_AGG_SQL} AS "{AGG_COLUMN}"', group_by


@cache.memoize()
def _cached_top_count(select_sql, where_sql, params, group_by, having) -> int:
    """COUNT des groupes, mémoïsé sur la requête.

    AG Grid redemande le total à chaque bloc ; pour un même filtre tous les
    blocs partagent la même requête (cf. `_cached_count` dans
    src/utils/grid.py, même raison).
    """
    return count_aggregate(
        select_sql=select_sql,
        where_sql=where_sql,
        params=params,
        group_by=group_by,
        having=having,
    )


def _rows_with_links(dff: pl.DataFrame) -> list[dict]:
    """Lignes prêtes pour la grille : textes non nuls, liens HTML posés.

    Seules les colonnes texte sont castées : `Attributions` et
    `titulaire_distance` restent numériques, pour que la grille les affiche
    et les aligne comme des nombres.

    `add_links` pose aussi un lien sur les colonnes `*_id` (même comportement
    que `postprocess_page` pour la grille détail) ; on restitue leur valeur
    brute après coup, l'identifiant devant rester exploitable tel quel (clé
    de ligne, dédoublonnage de pagination) — le lien vers la fiche est déjà
    porté par la colonne `*_nom`.
    """
    if dff.height == 0:
        return []
    texte = [c for c, dtype in dff.schema.items() if dtype == pl.String]
    dff = dff.with_columns([pl.col(c).fill_null("") for c in texte])
    id_columns = [c for c in dff.columns if c.endswith("_id")]
    bruts = dff.select(id_columns)
    dff = add_links(dff)
    if id_columns:
        dff = dff.with_columns([bruts.get_column(c).alias(c) for c in id_columns])
    return dff.to_dicts()


def fetch_top_org_page(org_type, where_sql, params, request, extra_columns=()):
    """Datasource server-side d'une grille top, scopée par (where_sql, params).

    Renvoie {"rowData": ..., "rowCount": <nombre de groupes>}, ou `no_update`
    si AG Grid n'a pas (encore) envoyé de requête.
    """
    if request is None:
        return no_update

    select_sql, group_by = _select_and_group(org_type, extra_columns)
    filter_sql, filter_params, having_sql, having_params = top_org_filter_sql(
        request.get("filterModel"), org_type, extra_columns
    )
    scoped_where = f"({where_sql}) AND ({filter_sql})"
    query_params = [*params, *filter_params, *having_params]

    total = _cached_top_count(
        select_sql, scoped_where, tuple(query_params), group_by, having_sql or None
    )

    start = int(request.get("startRow", 0))
    end = int(request.get("endRow", start))
    dff = aggregate_marches(
        select_sql=select_sql,
        where_sql=scoped_where,
        params=query_params,
        group_by=group_by,
        having=having_sql or None,
        order_by=top_org_sort_sql(request.get("sortModel"), org_type, extra_columns),
        limit=max(0, end - start),
        offset=start,
    )
    return {"rowData": _rows_with_links(dff), "rowCount": total}
