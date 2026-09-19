"""Grille AG Grid de la page admin (issue #141).

Remplace le dash_table.DataTable : édition inline (texte + listes déroulantes),
pagination cliente par 20 lignes, alertes de succès/échec.
"""

from unittest.mock import Mock, patch

import dash_ag_grid as dag
from dash import no_update


def _find_grid(node, grid_id):
    """Retourne le composant d'id `grid_id` dans l'arbre du layout, ou None."""
    if getattr(node, "id", None) == grid_id:
        return node
    for child in getattr(node, "children", None) or []:
        found = _find_grid(child, grid_id)
        if found is not None:
            return found
    return None


def _fake_ctx(triggered_id):
    return type("Ctx", (), {"triggered_id": triggered_id})


def test_layout_has_admin_table_grid_paginated_by_20(users_db_path, monkeypatch):
    import src.app  # noqa: F401 — register_page() exige une app instanciée
    from src.pages.admin import liste

    monkeypatch.setattr(liste, "is_admin", lambda: True)

    grid = _find_grid(liste.layout(), "admin-table")

    assert isinstance(grid, dag.AgGrid)
    assert grid.dashGridOptions["pagination"] is True
    assert grid.dashGridOptions["paginationPageSize"] == 20


def test_columns_for_editable_only_on_declared_editable_columns():
    from src.pages.admin.liste import _columns_for

    defs = {d["field"]: d for d in _columns_for("users")}

    assert defs["email"]["editable"] is True
    assert defs["id"]["editable"] is False


def test_columns_for_dropdown_uses_ag_select_cell_editor():
    from src.admin.tables import all_tables
    from src.pages.admin.liste import _columns_for

    cfg = all_tables()["users"]
    defs = {d["field"]: d for d in _columns_for("users")}
    col_def = defs["email_verified"]

    assert col_def["cellEditor"] == "agSelectCellEditor"
    assert col_def["cellEditorParams"]["values"] == list(
        cfg.dropdowns["email_verified"]
    )


def test_update_table_switches_table_returns_rows_and_columns(
    users_db_path, monkeypatch
):
    from src.admin.tables import get_rows
    from src.pages.admin import liste

    monkeypatch.setattr(liste, "is_admin", lambda: True)
    monkeypatch.setattr(liste, "ctx", _fake_ctx("admin-table-select"))

    row_data, column_defs, alert = liste._update_table("subscriptions", None)

    assert row_data == get_rows("subscriptions")
    assert column_defs == liste._columns_for("subscriptions")
    assert alert is None


def test_update_table_valid_edit_calls_set_cell_and_log_action(
    users_db_path, monkeypatch
):
    from src.auth import db as auth_db
    from src.pages.admin import liste

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    monkeypatch.setattr(liste, "is_admin", lambda: True)
    monkeypatch.setattr(liste, "ctx", _fake_ctx("admin-table"))
    set_cell_mock = Mock()
    log_action_mock = Mock()
    monkeypatch.setattr(liste, "set_cell", set_cell_mock)
    monkeypatch.setattr(liste, "log_action", log_action_mock)

    cell_changes = [
        {
            "rowIndex": 0,
            "rowId": str(uid),
            "colId": "siret",
            "oldValue": None,
            "value": "12345678900011",
            "data": {"id": uid, "email": "a@ex.fr", "siret": "12345678900011"},
        }
    ]

    admin_user = type("U", (), {"email": "admin@ex.fr"})()
    with patch.object(liste, "current_user", admin_user):
        row_data, column_defs, alert = liste._update_table("users", cell_changes)

    set_cell_mock.assert_called_once_with("users", uid, "siret", "12345678900011")
    log_action_mock.assert_called_once()
    assert row_data is no_update
    assert column_defs is no_update
    assert alert.color == "success"


def test_update_table_rejected_edit_reverts_rowdata_from_db(users_db_path, monkeypatch):
    from src.admin.tables import get_rows
    from src.auth import db as auth_db
    from src.pages.admin import liste

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    auth_db.set_siret(uid, "ANCIEN")

    monkeypatch.setattr(liste, "is_admin", lambda: True)
    monkeypatch.setattr(liste, "ctx", _fake_ctx("admin-table"))

    def _raise(*_args, **_kwargs):
        raise ValueError("refusé")

    monkeypatch.setattr(liste, "set_cell", _raise)

    cell_changes = [
        {
            "rowIndex": 0,
            "rowId": str(uid),
            "colId": "siret",
            "oldValue": "ANCIEN",
            "value": "INVALIDE",
            "data": {"id": uid, "email": "a@ex.fr", "siret": "INVALIDE"},
        }
    ]

    row_data, column_defs, alert = liste._update_table("users", cell_changes)

    assert column_defs is no_update
    assert alert.color == "danger"
    assert row_data == get_rows("users")
    sirets = {row["id"]: row["siret"] for row in row_data}
    assert sirets[uid] == "ANCIEN"
