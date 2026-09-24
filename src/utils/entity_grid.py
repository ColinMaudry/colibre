"""Logique de grille AG Grid scopée à une entité (acheteur/titulaire).

Factorise ce qui est commun aux pages acheteur.py et titulaire.py :
- scope SQL (WHERE acheteur_id/titulaire_id + année),
- datasource server-side (réutilise fetch_grid_page du Lot 1),
- export Excel filtré (réutilise export_dataframe),
- columnDefs + réapplication de la disposition persistée,
- fabrique de grille à id pattern-matching (persistance filterModel par fiche).

Les callbacks Dash sont enregistrés par register_entity_grid_callbacks()
(cf. module séparé de wiring) ; ici, seules des fonctions pures testables.
"""

from dash import (
    ALL,
    MATCH,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    no_update,
    set_props,
)

from src.figures import (
    AG_GRID_LOCALE_FR,  # noqa: F401  (réexport pratique)
    ag_grid,
)
from src.utils.grid import (
    apply_persisted_layout,
    export_dataframe,
    fetch_grid_page,
    grid_column_defs,
)

_TOUTES = "Toutes les années"


def grid_type(org_type: str) -> str:
    """Valeur de la clé `type` de l'id pattern-matching de la grille."""
    return f"{org_type}-grid"


def entity_scope(org_type: str, entity_id: str, year) -> tuple[str, list]:
    """WHERE SQL + params liés scopant les requêtes à cette entité (+ année).

    Reproduit _acheteur_scope/_titulaire_scope des pages, unifié par org_type.
    """
    if org_type == "titulaire":
        where_sql = "titulaire_id = ? AND titulaire_typeIdentifiant = 'SIRET'"
    else:
        where_sql = "acheteur_id = ?"
    params: list = [entity_id]
    if year and year != _TOUTES:
        where_sql += ' AND YEAR("dateNotification") = ?'
        params.append(int(year))
    return where_sql, params


def _sort_model_from_column_state(column_state) -> list:
    """Extrait le sortModel AG Grid d'un columnState (comme tableau.download_data)."""
    return [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or [])
        if c.get("sort")
    ]


def entity_grid_column_defs(hidden_columns, column_state) -> list[dict]:
    """columnDefs du schéma DECP + disposition (largeur/ordre) persistée."""
    defs = grid_column_defs(hidden_columns)
    return apply_persisted_layout(defs, column_state)


def fetch_entity_page(org_type, entity_id, year, request) -> tuple:
    """Datasource server-side scopé pour la grille entité.

    Renvoie ({"rowData": ..., "rowCount": total}, total, total_unique).
    """
    if request is None:
        return no_update, no_update, no_update
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    rows, total, total_unique = fetch_grid_page(
        request.get("filterModel") or None,
        request.get("sortModel") or None,
        request.get("startRow", 0),
        request.get("endRow", 100),
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )
    return {"rowData": rows, "rowCount": total}, total, total_unique


def export_entity_dataframe(org_type, entity_id, year, filter_model, column_state):
    """DataFrame filtré/trié (état courant de la grille) pour l'export Excel."""
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    sort_model = _sort_model_from_column_state(column_state)
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    return export_dataframe(
        filter_model,
        sort_model,
        hidden_columns,
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )


def clear_sort(column_state) -> list[dict]:
    """columnState avec le tri effacé (sort/sortIndex à None), largeur/ordre/
    épinglage préservés. Approche #47-safe de tableau.reset_view."""
    return [{**col, "sort": None, "sortIndex": None} for col in (column_state or [])]


def build_entity_grid(org_type, entity_id, year, hidden_columns, column_state):
    """Grille AG Grid à id pattern-matching, scopée à (entité, année).

    L'id inclut entity_id + year → une entrée localStorage de filterModel par
    fiche/année (persistance native scopée). columnState n'est PAS persisté
    nativement (géré par un store global partagé) : persisted_props=["filterModel"].
    """
    grid_id = {
        "type": grid_type(org_type),
        "entity_id": entity_id,
        "year": year or _TOUTES,
    }
    defs = entity_grid_column_defs(hidden_columns, column_state)
    return ag_grid(grid_id, defs, persisted_props=["filterModel"])


def register_entity_grid_callbacks(org_type: str) -> None:
    """Enregistre les callbacks de grille pour la page org_type (acheteur/titulaire).

    Appelée une fois par page. Utilise des closures sur org_type ; toute la
    logique délègue aux fonctions pures ci-dessus (testées en Task 4).
    """
    gtype = grid_type(org_type)

    # 1) Datasource server-side. Une seule sortie MATCH (getRowsResponse de la
    #    grille pattern-matching) : Dash INTERDIT de mélanger une sortie MATCH
    #    avec des sorties fixes (« MATCH wildcards must be on the same keys for
    #    all Outputs », erreur du dev-renderer en mode debug). Les stores totaux
    #    (id fixes) sont donc alimentés impérativement via dash.set_props.
    @callback(
        Output({"type": gtype, "entity_id": MATCH, "year": MATCH}, "getRowsResponse"),
        Input({"type": gtype, "entity_id": MATCH, "year": MATCH}, "getRowsRequest"),
        prevent_initial_call=True,
    )
    def _get_rows(request):
        gid = ctx.triggered_id  # {"type", "entity_id", "year"}
        if request is None or gid is None:
            return no_update
        if request.get("filterModel") and request.get("startRow", 0) == 0:
            import json

            from src.utils.tracking import track_search

            track_search(json.dumps(request["filterModel"]), org_type)
        response, total, total_unique = fetch_entity_page(
            org_type, gid["entity_id"], gid["year"], request
        )
        set_props(f"{org_type}-total", {"data": total})
        set_props(f"{org_type}-total-unique", {"data": total_unique})
        return response

    # 2) (Re)construit la grille au changement de fiche (URL), d'année, ou de
    #    colonnes masquées. Le remontage réinitialise le filterModel (accepté
    #    au changement de fiche/année) ; pour les colonnes masquées voir §3bis.
    @callback(
        Output(f"{org_type}-grid-container", "children"),
        Input(f"{org_type}_url", "pathname"),
        Input(f"{org_type}_year", "value"),
        State(f"{org_type}-hidden-columns", "data"),
        State("entity-grid-columns-state", "data"),
    )
    def _build_grid(pathname, year, hidden_columns, column_state):
        from src.utils.table import get_default_hidden_columns

        entity_id = (pathname or "").split("/")[-1]
        if hidden_columns is None:
            hidden_columns = get_default_hidden_columns(org_type)
        return build_entity_grid(
            org_type, entity_id, year, hidden_columns, column_state
        )

    # 3) Persiste columnState (largeur/ordre/tri/visibilité) dans le store global
    #    partagé. Input MATCH (grille) → Output fixe (store). Autorisé Dash 4.4.
    @callback(
        Output("entity-grid-columns-state", "data", allow_duplicate=True),
        Input({"type": gtype, "entity_id": MATCH, "year": MATCH}, "columnState"),
        prevent_initial_call=True,
    )
    def _persist_column_state(column_state):
        return column_state or no_update

    # 3bis) Colonnes masquées → columnDefs in-place (préserve le filtre courant,
    #       contrairement au remontage). Input fixe → Output ALL (grille unique).
    @callback(
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "columnDefs"),
        Input(f"{org_type}-hidden-columns", "data"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _apply_hidden_columns(hidden_columns, column_states):
        from src.utils.table import get_default_hidden_columns

        if hidden_columns is None:
            hidden_columns = get_default_hidden_columns(org_type)
        # ALL → listes (une entrée par grille présente, ici 0 ou 1).
        return [
            entity_grid_column_defs(hidden_columns, cs) for cs in (column_states or [])
        ]

    # 4) Reset : efface filtres ET tris (columnState avec sort=None). Bouton fixe
    #    → grille ALL.
    @callback(
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "filterModel"),
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        Input(f"btn-{org_type}-reset", "n_clicks"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _reset(_n, column_states):
        cleared = [clear_sort(cs) for cs in (column_states or [])]
        return [{} for _ in cleared], cleared

    # 5) Export filtré (état courant de la grille). Bouton fixe → Download fixe,
    #    lit filterModel/columnState de la grille via ALL (state).
    @callback(
        Output(f"{org_type}-download-filtered-data", "data"),
        Input(f"btn-download-filtered-data-{org_type}", "n_clicks"),
        State(f"{org_type}_url", "pathname"),
        State(f"{org_type}_year", "value"),
        State(f"{org_type}_nom", "children"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "filterModel"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _download_filtered(_n, pathname, year, nom, filter_models, column_states):
        import datetime as _dt

        from src.utils.table import write_styled_excel

        entity_id = (pathname or "").split("/")[-1]
        filter_model = (filter_models or [None])[0]
        column_state = (column_states or [None])[0]
        if filter_model:
            import json

            from src.utils.tracking import track_search

            track_search(json.dumps(filter_model), f"{org_type} download")
        df = export_entity_dataframe(
            org_type, entity_id, year, filter_model, column_state
        )

        def to_bytes(buffer):
            write_styled_excel(df, buffer)

        date = _dt.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        label = nom if isinstance(nom, str) else org_type
        return dcc.send_bytes(to_bytes, filename=f"decp_filtrées_{label}_{date}.xlsx")

    # 6) Meta : "X marchés (Y lignes)" + état du bouton d'export filtré (seuil 65k).
    @callback(
        Output(f"{org_type}_nb_rows", "children"),
        Output(f"btn-download-filtered-data-{org_type}", "disabled"),
        Output(f"btn-download-filtered-data-{org_type}", "children"),
        Output(f"btn-download-filtered-data-{org_type}", "title"),
        Input(f"{org_type}-total", "data"),
        Input(f"{org_type}-total-unique", "data"),
    )
    def _meta(total, total_unique):
        from src.utils.frontend import get_button_properties
        from src.utils.table import format_number

        total = total or 0
        total_unique = total_unique or 0
        nb_rows = (
            f"{format_number(total_unique) or 0} marchés "
            f"({format_number(total) or 0} lignes)"
        )
        # Le format (xlsx/csv) n'est pas utilisé ici : l'export filtré de
        # cette grille reste hors du périmètre de la bascule CSV (#142).
        disabled, children, title, _format = get_button_properties(total)
        return nb_rows, disabled, children, title
