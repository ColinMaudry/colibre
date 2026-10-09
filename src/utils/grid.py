"""Datasource server-side pour AG Grid (infinite row model)."""

import polars as pl

from src.db import count_marches, count_unique_marches, query_marches, schema
from src.figures import DATA_SCHEMA
from src.utils.cache import cache
from src.utils.query_ast import ast_to_sql, filtermodel_to_ast, sort_model_to_sql
from src.utils.table import postprocess_page


@cache.memoize()
def _cached_count(where_sql: str, params: tuple) -> int:
    """Cache le COUNT(*) sur (where_sql, params).

    AG Grid envoie une requête par bloc de défilement infini ; pour un même
    filtre, tous les blocs partagent le même (where_sql, params) et donc le
    même total — inutile de recompter un COUNT(*) sur ~1,5M lignes à chaque
    bloc chargé.
    """
    return count_marches(where_sql, params)


@cache.memoize()
def _cached_unique_count(where_sql: str, params: tuple) -> int:
    """Cache le COUNT(DISTINCT uid) sur (where_sql, params), même raison que
    `_cached_count`."""
    return count_unique_marches(where_sql, params)


def fetch_grid_page(
    filter_model,
    sort_model,
    start_row: int,
    end_row: int,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
    *,
    operateurs: bool,
) -> tuple[list[dict], int, int]:
    """Renvoie (row_data, total_count, total_unique_count) pour un bloc [start_row, end_row)."""
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, filter_params = ast_to_sql(ast, schema, operateurs=operateurs)
    where_sql = f"({base_where_sql}) AND ({filter_sql})"
    params = [*base_params, *filter_params]

    order_by = sort_model_to_sql(sort_model, schema) or None
    total = _cached_count(where_sql, tuple(params))
    total_unique = _cached_unique_count(where_sql, tuple(params))

    limit = max(0, end_row - start_row)
    page = query_marches(
        where_sql=where_sql,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=start_row,
    )
    page = postprocess_page(page)
    rows = page.to_dicts()
    # Numéro de ligne absolu (position dans les résultats filtrés/triés),
    # ajouté sous le lien loupe : repère visuel pendant le défilement infini
    # de la grille. Calculé ici plutôt que dans postprocess_page car il dépend
    # de `start_row`, propre au chargement par bloc de l'AG Grid.
    for i, row in enumerate(rows):
        row["marche"] = (
            f'{row["marche"]}<div class="marche-row-number">{start_row + i + 1}</div>'
        )
    return rows, total, total_unique


def export_dataframe(
    filter_model,
    sort_model,
    hidden_columns,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
    *,
    operateurs: bool,
) -> pl.DataFrame:
    """Renvoie les lignes filtrées/triées pour l'export Excel.

    Colonnes masquées exclues, valeurs brutes (non post-traitées HTML).
    `base_where_sql`/`base_params` scopent l'export à un sous-ensemble (ex. un
    acheteur/titulaire) — combinés en `(base) AND (filtre)`, comme
    `fetch_grid_page`. Par défaut `TRUE` → comportement inchangé pour tableau.py.
    """
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, filter_params = ast_to_sql(ast, schema, operateurs=operateurs)
    where_sql = f"({base_where_sql}) AND ({filter_sql})"
    params = [*base_params, *filter_params]
    order_by = sort_model_to_sql(sort_model, schema) or None
    visible = [c for c in schema.names() if c not in set(hidden_columns or [])]
    return query_marches(
        where_sql=where_sql,
        params=params,
        columns=visible,
        order_by=order_by,
    )


_LINK_COLUMNS = {
    "marche",
    "uid",
    "acheteur_id",
    "acheteur_nom",
    "titulaire_id",
    "titulaire_nom",
    "sourceDataset",
}

# Colonnes oui/non (cf. `booleans_to_strings` dans src.db) : valeur très
# courte, pas besoin de place.
_BOOLEAN_LIKE_COLUMNS = {
    "attributionAvance",
    "marcheInnovant",
    "sousTraitanceDeclaree",
    "considerationsSociales",
    "considerationsEnvironnementales",
}

# Codes/identifiants qui ne suivent pas le pattern de suffixe `_id`/`_code`
# (ex. codeCPV, idAccordCadre) mais restent des valeurs courtes.
_SHORT_CODE_COLUMNS = {
    "codeCPV",
    "lieuExecution_typeCode",
}

# Colonnes "nom" qui ne suivent pas le suffixe `_nom` (ex. sourceDataset).
_WIDE_LABEL_COLUMNS = {"objet", "uid"}

# Colonnes avec infobulle systématique sur les cellules (valeur complète au
# survol, pas seulement quand le texte est tronqué).
_CELL_TOOLTIP_COLUMNS = {
    "procedure",
    "considerationsSociales",
    "considerationsEnvironnementales",
    "objet",
    "ccag",
    "modalitesExecution",
    "acheteur_nom",
    "titulaire_nom",
    "acheteur_id",
    "titulaire_id",
}


def _filter_for(col_type) -> str:
    if col_type.is_numeric():
        return "agNumberColumnFilter"
    if col_type == pl.Date:
        return "agDateColumnFilter"
    return "agTextColumnFilter"


def _column_width(col: str, col_type) -> dict:
    """Largeur par défaut selon la nature de la colonne.

    Sert de base à l'affichage initial (pas de columnSize="responsiveSizeToFit",
    cf. ag_grid() : les colonnes ne s'étirent/compressent pas automatiquement).
    Pas de maxWidth ici : resizable=True (defaultColDef) doit pouvoir élargir
    librement une colonne à la souris, sans plafond artificiel.
    """
    if col == "montant":
        return {"width": 150}
    if col_type == pl.Date:
        return {"width": 220}
    if col_type.is_numeric():
        return {"width": 150}
    if col in _BOOLEAN_LIKE_COLUMNS:
        return {"width": 110}
    if col in _SHORT_CODE_COLUMNS or col.endswith(("_code")):
        return {"width": 180}
    if col in _WIDE_LABEL_COLUMNS or col.endswith("_nom"):
        return {"width": 350}
    return {"width": 190}


def grid_column_defs(hidden_columns=None):
    """columnDefs dérivés du schéma DuckDB.

    'marche' (colonne loupe ajoutée par postprocess_page) est placée en tête.
    """
    hidden = set(hidden_columns or [])
    defs = [
        {
            "field": "marche",
            "headerName": "",
            "cellRenderer": "markdown",
            "filter": False,
            "sortable": False,
            "maxWidth": 60,
            "pinned": "left",
        }
    ]
    for col in schema.names():
        meta = DATA_SCHEMA.get(col, {})
        col_type = schema[col]
        col_def = {
            "field": col,
            "headerName": meta.get("title", col),
            "filter": _filter_for(col_type),
            "floatingFilter": True,
            "sortable": True,
            "hide": col in hidden,
        }
        if meta.get("description"):
            # Texte brut (pas de markdown) : le renderer "markdown" côté
            # dash-ag-grid n'est enregistré que comme cellRenderer, pas
            # comme tooltipComponent — posé sur un en-tête, il retombe sur
            # le rendu natif d'AG Grid, qui affiche la chaîne telle quelle
            # (donc "**gras**" apparaissait littéralement avec les astérisques).
            col_def["headerTooltip"] = f"""{meta.get("title", col)} ({col})

                {meta["description"]}"""
        if col in _LINK_COLUMNS:
            col_def["cellRenderer"] = "markdown"
        if col in _CELL_TOOLTIP_COLUMNS:
            # Valeur complète en infobulle. Pour les colonnes-liens
            # (_LINK_COLUMNS), la cellule contient du HTML (<a href=...>) :
            # on pointe vers la copie texte brut posée par add_links() dans
            # src.utils.table plutôt que d'afficher ce balisage tel quel.
            col_def["tooltipField"] = f"{col}_tooltip" if col in _LINK_COLUMNS else col
        if col in ["objet", "acheteur_nom", "titulaire_nom"]:
            # autoHeight n'est pas supporté avec rowModelType="infinite" (la
            # grille doit pouvoir calculer la position des lignes non
            # chargées, donc une hauteur de ligne fixe) : cf. ag_grid(),
            # rowHeight fixe côté dashGridOptions plutôt qu'autoHeight ici.
            col_def["wrapText"] = True
        col_def.update(_column_width(col, col_type))
        defs.append(col_def)
    return defs


def apply_persisted_layout(
    defs: list[dict], column_state: list[dict] | None
) -> list[dict]:
    """Réapplique la largeur et l'ordre des colonnes personnalisés par
    l'utilisateur (columnState restauré via la persistance AG Grid) par-dessus
    des columnDefs fraîchement régénérés par grid_column_defs(), qui eux
    ignorent tout état précédent et ne portent que la largeur par défaut et
    l'ordre du schéma.

    Sans ça, tout changement de columnDefs (à chaque chargement de page ou
    changement de colonnes affichées) écrase silencieusement le
    redimensionnement/réordonnancement fait par l'utilisateur, cf. #47.
    """
    if not column_state:
        return defs
    order = {col["colId"]: i for i, col in enumerate(column_state)}
    widths = {col["colId"]: col["width"] for col in column_state if col.get("width")}
    for col_def in defs:
        field = col_def["field"]
        if field in widths:
            col_def["width"] = widths[field]
    # Colonnes déjà connues dans leur ordre persisté, colonnes nouvelles
    # (ex. ajout au schéma, jamais vues dans columnState) à la fin dans
    # leur ordre par défaut.
    defs.sort(key=lambda d: order.get(d["field"], len(order)))
    return defs
