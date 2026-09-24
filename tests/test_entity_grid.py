import dash_ag_grid as dag

import src.app  # noqa: F401  # instancie l'app → schema chargé
from src.db import query_marches
from src.utils.entity_grid import (
    build_entity_grid,
    clear_sort,
    entity_grid_column_defs,
    entity_scope,
    export_entity_dataframe,
    fetch_entity_page,
    grid_type,
)


def _an_acheteur_id():
    return query_marches("TRUE", (), columns=["acheteur_id"])["acheteur_id"][0]


def test_entity_scope_acheteur():
    where, params = entity_scope("acheteur", "S123", None)
    assert where == "acheteur_id = ?"
    assert params == ["S123"]


def test_entity_scope_titulaire_requires_siret():
    where, params = entity_scope("titulaire", "S123", None)
    assert "titulaire_id = ?" in where
    assert "titulaire_typeIdentifiant = 'SIRET'" in where
    assert params == ["S123"]


def test_entity_scope_with_year_adds_bound_param():
    where, params = entity_scope("acheteur", "S123", "2025")
    assert 'YEAR("dateNotification") = ?' in where
    assert params == ["S123", 2025]


def test_entity_scope_toutes_les_annees_no_year_filter():
    where, params = entity_scope("acheteur", "S123", "Toutes les années")
    assert "YEAR" not in where
    assert params == ["S123"]


def test_fetch_entity_page_is_scoped():
    ach = _an_acheteur_id()
    request = {"startRow": 0, "endRow": 50, "filterModel": None, "sortModel": None}
    response, total, total_unique = fetch_entity_page("acheteur", ach, None, request)
    assert total > 0
    assert total_unique > 0
    assert response["rowCount"] == total
    assert len(response["rowData"]) <= 50
    # Toutes les lignes appartiennent à l'acheteur scopé.
    assert all(str(r["acheteur_id"]).find(str(ach)) != -1 for r in response["rowData"])


def test_fetch_entity_page_none_request():
    from dash import no_update

    out = fetch_entity_page("acheteur", "S123", None, None)
    assert out == (no_update, no_update, no_update)


def test_export_entity_dataframe_scoped():
    ach = _an_acheteur_id()
    df = export_entity_dataframe("acheteur", ach, None, None, None)
    assert df.height > 0
    assert set(df["acheteur_id"].to_list()) == {ach}


def test_clear_sort_preserves_width_and_order():
    column_state = [
        {"colId": "objet", "width": 400, "sort": "asc", "sortIndex": 0},
        {"colId": "montant", "width": 150, "sort": "desc", "sortIndex": 1},
    ]
    cleared = clear_sort(column_state)
    assert all(c["sort"] is None and c["sortIndex"] is None for c in cleared)
    assert cleared[0]["width"] == 400 and cleared[0]["colId"] == "objet"
    assert cleared[1]["width"] == 150


def test_clear_sort_empty():
    assert clear_sort(None) == []


def test_entity_grid_column_defs_applies_persisted_layout():
    defs = entity_grid_column_defs(
        hidden_columns=[], column_state=[{"colId": "montant", "width": 999}]
    )
    by_field = {d["field"]: d for d in defs}
    assert by_field["montant"]["width"] == 999


def test_build_entity_grid_has_pattern_matching_id_and_filter_only_persistence():
    grid = build_entity_grid("acheteur", "S123", "Toutes les années", [], None)
    assert isinstance(grid, dag.AgGrid)
    assert grid.id == {
        "type": "acheteur-grid",
        "entity_id": "S123",
        "year": "Toutes les années",
    }
    assert list(grid.persisted_props) == ["filterModel"]


def test_grid_type():
    assert grid_type("acheteur") == "acheteur-grid"
    assert grid_type("titulaire") == "titulaire-grid"


def test_register_entity_grid_callbacks_registered_via_page_import():
    """Les callbacks de grille entité sont enregistrés (une fois) à l'import
    des pages acheteur/titulaire — pas de double enregistrement."""
    import dash

    from src.app import app  # importe les pages → register_entity_grid_callbacks

    # Tant que l'app n'a pas été servie, les callbacks enregistrés via le
    # décorateur global `dash.callback` vivent dans
    # dash._callback.GLOBAL_CALLBACK_MAP ; ils ne migrent vers
    # app.callback_map qu'à la première requête (_setup_server). On inspecte
    # donc les deux registres pour ne pas dépendre de l'ordre des tests
    # (voir tests/test_csrf_architecture.py pour le même motif).
    callback_keys = set(dash._callback.GLOBAL_CALLBACK_MAP) | set(app.callback_map)
    # Le store columnState partagé est piloté par un callback enregistré.
    assert any("entity-grid-columns-state.data" in k for k in callback_keys)


def _get_meta_callback(org_type):
    """Récupère la fonction _meta non décorée (closure de
    register_entity_grid_callbacks), pour la tester directement sans passer
    par le cycle de requête Dash."""
    import dash

    from src.app import app  # importe les pages → register_entity_grid_callbacks

    registres = list(dash._callback.GLOBAL_CALLBACK_MAP.values()) + list(
        app.callback_map.values()
    )
    for entree in registres:
        fn = entree.get("callback")
        if fn is None:
            continue
        wrapped = getattr(fn, "__wrapped__", None)
        if wrapped is not None and wrapped.__name__ == "_meta":
            # Chaque org_type a sa propre closure ; on la distingue par l'id
            # du store total qu'elle consomme en entrée.
            if any(
                spec.get("id") == f"{org_type}-total"
                for spec in entree.get("inputs") or []
            ):
                return wrapped
    raise AssertionError(f"_meta introuvable pour {org_type}")


def test_meta_ignore_le_format_et_ne_desactive_jamais_au_dela_de_zero():
    """get_button_properties renvoie désormais 4 valeurs ; _meta (bouton
    d'export filtré) doit absorber le format sans le répercuter, et ne plus
    jamais désactiver le bouton au-delà de 0 ligne (#142)."""
    meta_acheteur = _get_meta_callback("acheteur")

    nb_rows, disabled, texte, titre = meta_acheteur(200_001, 5)

    assert disabled is False
    assert "lignes" in nb_rows
    assert texte == "Télécharger au format CSV"
    assert titre
