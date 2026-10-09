from unittest.mock import patch

import pytest

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.pages.tableau import get_rows_tableau, reset_view
from src.utils import grid as grid_module
from src.utils.grid import (
    apply_persisted_layout,
    export_dataframe,
    fetch_grid_page,
    grid_column_defs,
)


@pytest.fixture(scope="module")
def flask_app():
    """Minimal Flask app with SimpleCache so @cache.memoize() works in tests
    (même pattern que tests/test_table.py)."""
    from flask import Flask

    from src.utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    from src.utils.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            pass
        yield


def test_column_defs_have_field_and_filter():
    defs = grid_column_defs(hidden_columns=[])
    by_field = {d["field"]: d for d in defs}
    assert "objet" in by_field
    # filtre texte par défaut
    assert by_field["objet"]["filter"] == "agTextColumnFilter"
    # montant est numérique
    assert by_field["montant"]["filter"] == "agNumberColumnFilter"
    # headerTooltip présent (définition de colonne)
    assert "headerTooltip" in by_field["objet"]


def test_column_defs_hidden_flag():
    defs = grid_column_defs(hidden_columns=["objet"])
    by_field = {d["field"]: d for d in defs}
    assert by_field["objet"]["hide"] is True


def test_fetch_grid_page_returns_rows_and_count():
    rows, total, total_unique = fetch_grid_page(None, None, 0, 20)
    assert isinstance(rows, list)
    assert isinstance(total, int)
    assert total >= len(rows)
    assert total_unique <= total

    if rows:
        # postprocess_page ajoute une colonne 'marche' avec un lien
        assert "marche" in rows[0]


def test_fetch_grid_page_filter_reduces_count():
    _, total_all, _ = fetch_grid_page(None, None, 0, 1)
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    rows, total_filtered, _ = fetch_grid_page(fm, None, 0, 20)
    assert total_filtered <= total_all
    assert rows == [] and total_filtered == 0


def test_fetch_grid_page_offset_slicing():
    rows, _, _ = fetch_grid_page(None, None, 0, 5)
    assert len(rows) <= 5


def test_export_dataframe_excludes_hidden_columns():
    df = export_dataframe(None, None, hidden_columns=["objet"])
    assert "objet" not in df.columns


def test_export_dataframe_sans_colonne_technique():
    df = export_dataframe(None, None, hidden_columns=[])
    assert "objet_normalise" not in df.columns


def test_export_dataframe_applies_filter():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    df = export_dataframe(fm, None, hidden_columns=[])
    assert df.height == 0


def test_export_dataframe_applies_base_scope():
    """base_where_sql restreint l'export à un sous-ensemble (ex. un acheteur),
    en plus du filterModel — utilisé par acheteur.py/titulaire.py (#41)."""
    # Récupère un acheteur_id présent dans le jeu de test.
    unscoped = export_dataframe(None, None, hidden_columns=[])
    assert unscoped.height > 0
    an_acheteur = unscoped["acheteur_id"][0]

    scoped = export_dataframe(
        None,
        None,
        hidden_columns=[],
        base_where_sql="acheteur_id = ?",
        base_params=(an_acheteur,),
    )
    assert scoped.height > 0
    assert scoped.height <= unscoped.height
    assert set(scoped["acheteur_id"].to_list()) == {an_acheteur}


def test_get_rows_tableau_tracks_search_once_per_filter_not_per_scroll_block():
    """Régression revue finale #41 : AG Grid envoie une getRowsRequest par bloc
    de défilement infini, avec le même filterModel tant que le filtre ne
    change pas. track_search ne doit être appelé qu'une fois par filtre (au
    premier bloc, startRow == 0), pas une fois par bloc défilé."""
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "route"}}
    with patch("src.pages.tableau.track_search") as mocked:
        get_rows_tableau({"filterModel": fm, "startRow": 0, "endRow": 100})
        get_rows_tableau({"filterModel": fm, "startRow": 100, "endRow": 200})
        get_rows_tableau({"filterModel": fm, "startRow": 200, "endRow": 300})
    mocked.assert_called_once()


def test_fetch_grid_page_caches_count_across_scroll_blocks(flask_app, monkeypatch):
    """Régression revue finale #41 : count_marches ne doit être appelé qu'une
    fois pour des blocs de défilement successifs partageant le même
    where_sql/params (même filtre, start_row différent)."""
    call_count = {"n": 0}
    real_count_marches = grid_module.count_marches

    def counting_count_marches(where_sql, params):
        call_count["n"] += 1
        return real_count_marches(where_sql, params)

    monkeypatch.setattr(grid_module, "count_marches", counting_count_marches)

    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "route"}}
    with flask_app.app_context():
        _, total1, _ = fetch_grid_page(fm, None, 0, 20)
        _, total2, _ = fetch_grid_page(fm, None, 20, 40)
        _, total3, _ = fetch_grid_page(fm, None, 40, 60)

    assert call_count["n"] == 1
    assert total1 == total2 == total3


def test_reset_view_clears_filter_and_sort():
    """Régression : le bouton Réinitialiser ('Supprime tous les filtres et les
    tris') ne remettait à zéro que filterModel, jamais le tri (#41)."""
    column_state = [{"colId": "objet", "sort": "asc", "sortIndex": 0, "width": 200}]
    filter_model, new_column_state = reset_view(1, column_state)
    assert filter_model == {}
    assert new_column_state == [
        {"colId": "objet", "sort": None, "sortIndex": None, "width": 200}
    ]


def test_reset_view_preserves_column_width():
    """Le bouton Réinitialiser ne doit remettre à zéro que les filtres et les
    tris, pas la largeur (ni le pinning/ordre) des colonnes."""
    column_state = [
        {"colId": "objet", "sort": "asc", "sortIndex": 0, "width": 350, "hide": True},
        {
            "colId": "montant",
            "sort": None,
            "sortIndex": None,
            "width": 120,
            "hide": False,
        },
    ]
    _, new_column_state = reset_view(1, column_state)
    assert [c["width"] for c in new_column_state] == [350, 120]
    assert [c["hide"] for c in new_column_state] == [True, False]
    assert all(c["sort"] is None and c["sortIndex"] is None for c in new_column_state)


def test_apply_persisted_layout_restores_width_and_order():
    """Régression : la largeur et l'ordre des colonnes choisis par
    l'utilisateur étaient perdus au rechargement de la page, écrasés par les
    columnDefs régénérés par apply_hidden_columns à chaque chargement (#47)."""
    defs = [
        {"field": "marche", "width": 60},
        {"field": "objet", "minWidth": 360},
        {"field": "montant", "width": 150},
        {"field": "acheteur_nom", "width": 200},
    ]
    # L'utilisateur a redimensionné "montant" et déplacé "acheteur_nom" avant "objet"
    column_state = [
        {"colId": "marche", "width": 60},
        {"colId": "acheteur_nom", "width": 200},
        {"colId": "objet", "width": 500},
        {"colId": "montant", "width": 320},
    ]
    result = apply_persisted_layout(defs, column_state)
    assert [d["field"] for d in result] == [
        "marche",
        "acheteur_nom",
        "objet",
        "montant",
    ]
    assert next(d for d in result if d["field"] == "montant")["width"] == 320
    # "objet" n'a pas de clé "width" dans columnDefs (minWidth seulement, cf.
    # grid_column_defs) : columnState en fournit une, elle doit être reprise.
    assert next(d for d in result if d["field"] == "objet")["width"] == 500


def test_apply_persisted_layout_places_unknown_columns_last():
    """Une colonne absente du columnState persisté (jamais vue par
    l'utilisateur, ex. ajout au schéma) doit rester à la fin plutôt que de
    faire planter le tri."""
    defs = [
        {"field": "marche", "width": 60},
        {"field": "objet", "minWidth": 360},
        {"field": "nouvelle_colonne", "width": 130},
    ]
    column_state = [
        {"colId": "objet", "width": 400},
        {"colId": "marche", "width": 60},
    ]
    result = apply_persisted_layout(defs, column_state)
    assert [d["field"] for d in result] == ["objet", "marche", "nouvelle_colonne"]


def test_apply_persisted_layout_noop_without_prior_state():
    """Premier chargement (jamais de columnState persisté) : columnDefs
    inchangés, pas d'erreur sur None/[]."""
    defs = [{"field": "marche", "width": 60}, {"field": "objet", "minWidth": 360}]
    assert apply_persisted_layout(defs, None) == defs
    assert apply_persisted_layout(defs, []) == defs
