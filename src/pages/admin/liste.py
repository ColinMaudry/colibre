import dash_bootstrap_components as dbc
from dash import Input, Output, callback, ctx, html, no_update, register_page
from dash.exceptions import PreventUpdate
from flask_login import current_user

from src.admin.db import log_action
from src.admin.guard import is_admin
from src.admin.tables import all_tables, get_rows, set_cell
from src.figures import client_grid
from src.pages.admin._shell import not_admin

register_page(
    __name__,
    path="/admin",
    title="Panneau admin | colibre",
    name="Admin",
    description="Panneau d'administration interne.",
)

DEFAULT_TABLE = "users"


def _columns_for(table: str) -> list[dict]:
    cfg = all_tables()[table]
    defs = []
    for col in cfg.columns:
        col_def = {
            "field": col,
            "headerName": col,
            "editable": col in cfg.editable_columns,
        }
        if col in cfg.dropdowns:
            col_def |= {
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": list(cfg.dropdowns[col])},
            }
        defs.append(col_def)
    return defs


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            html.Div(id="admin-alerts"),
            dbc.Select(
                id="admin-table-select",
                options=[{"label": name, "value": name} for name in all_tables()],
                value=DEFAULT_TABLE,
                className="mb-3",
                style={"maxWidth": "300px"},
            ),
            client_grid(
                "admin-table",
                _columns_for(DEFAULT_TABLE),
                get_rows(DEFAULT_TABLE),
                page_size=20,
                defaultColDef={
                    "sortable": True,
                    "filter": True,
                    "floatingFilter": True,
                    "resizable": True,
                    "minWidth": 120,
                },
            ),
        ],
        fluid=True,
        className="py-4",
    )


@callback(
    Output("admin-table", "rowData"),
    Output("admin-table", "columnDefs"),
    Output("admin-alerts", "children"),
    Input("admin-table-select", "value"),
    Input("admin-table", "cellValueChanged"),
    prevent_initial_call=True,
)
def _update_table(selected_table, cell_changes):
    # Les callbacks Dash sont des endpoints serveur globaux (/_dash-update-component)
    # invocables indépendamment du layout rendu : la garde is_admin() de layout()
    # ne protège QUE l'affichage. Sans ce contrôle, n'importe qui (y compris un
    # anonyme) pourrait lire/écrire toute la base via ce callback. Voir issue #110.
    if not is_admin():
        raise PreventUpdate

    if ctx.triggered_id == "admin-table-select":
        return get_rows(selected_table), _columns_for(selected_table), None

    if not cell_changes:
        return no_update, no_update, None
    change = cell_changes[-1]
    column, old_value, new_value = change["colId"], change["oldValue"], change["value"]
    if old_value == new_value:
        return no_update, no_update, None

    cfg = all_tables()[selected_table]
    row = change["data"]
    try:
        set_cell(selected_table, row[cfg.pk], column, new_value)
    except ValueError as exc:
        # La cellule affiche encore la valeur refusée : on relit la base.
        return (
            get_rows(selected_table),
            no_update,
            dbc.Alert(str(exc), color="danger", dismissable=True),
        )

    log_action(
        current_user.email,
        f"edit_{selected_table}",
        cfg.target_user_id(row),
        f"{column}: {old_value!r} → {new_value!r}",
    )
    return (
        no_update,
        no_update,
        dbc.Alert("Modification enregistrée.", color="success", dismissable=True),
    )
