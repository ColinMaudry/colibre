"""Le thème doit faire partie de la clé des caches mémoïsés des cards (#118).

Sans ça, deux visiteurs consultant les mêmes filtres avec des thèmes
différents (l'un clair, l'autre abonné en sombre) se partageraient les mêmes
figures en cache — l'un des deux recevrait des graphiques de la mauvaise
palette.
"""

import pytest

from src.theme import CLAIR, SOMBRE


@pytest.fixture(scope="module")
def flask_app():
    """Flask app minimale avec SimpleCache pour que @cache.memoize()
    fonctionne en test (même pattern que tests/test_grid.py)."""
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


@pytest.fixture
def observatoire_mod():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import observatoire

    return observatoire


@pytest.fixture
def tableau_mod():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau

    return tableau


def _fake_build_dashboard_cards(calls):
    def fake(dff, **kwargs):
        theme = kwargs.get("theme")
        calls.append(kwargs)
        return f"cards-{theme}"

    return fake


def test_observatoire_meme_theme_meme_filtre_un_seul_calcul(
    observatoire_mod, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        observatoire_mod, "prepare_dashboard_data", lambda **kw: "dff-stub"
    )
    monkeypatch.setattr(
        observatoire_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtres = (("acheteur_nom", "ACME"),)
    r1 = observatoire_mod._compute_dashboard_children(filtres, CLAIR, False)
    r2 = observatoire_mod._compute_dashboard_children(filtres, CLAIR, False)

    assert len(calls) == 1
    assert r1 == r2 == "cards-clair"


def test_observatoire_changement_de_theme_meme_filtre_deux_calculs(
    observatoire_mod, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        observatoire_mod, "prepare_dashboard_data", lambda **kw: "dff-stub"
    )
    monkeypatch.setattr(
        observatoire_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtres = (("acheteur_nom", "ACME"),)
    r_clair = observatoire_mod._compute_dashboard_children(filtres, CLAIR, False)
    r_sombre = observatoire_mod._compute_dashboard_children(filtres, SOMBRE, False)

    assert len(calls) == 2
    assert r_clair == "cards-clair"
    assert r_sombre == "cards-sombre"


def test_observatoire_build_dashboard_cards_recoit_le_theme(
    observatoire_mod, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        observatoire_mod, "prepare_dashboard_data", lambda **kw: "dff-stub"
    )
    monkeypatch.setattr(
        observatoire_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtres = (("acheteur_nom", "ACME"),)
    observatoire_mod._compute_dashboard_children(filtres, SOMBRE, False)

    assert calls[-1]["theme"] == SOMBRE


def test_tableau_meme_theme_meme_filtre_un_seul_calcul(tableau_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(tableau_mod, "filtermodel_to_ast", lambda fm, schema: "ast")
    monkeypatch.setattr(
        tableau_mod, "ast_to_sql", lambda ast, schema, *, operateurs: ("1=1", [])
    )
    monkeypatch.setattr(tableau_mod, "query_marches", lambda **kw: "dff-stub")
    monkeypatch.setattr(
        tableau_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtre_json = tableau_mod._normalize_filter_model(
        {"acheteur_nom": {"filterType": "text", "type": "contains", "filter": "ACME"}}
    )
    r1 = tableau_mod._cards_pour_filtre(filtre_json, CLAIR, False)
    r2 = tableau_mod._cards_pour_filtre(filtre_json, CLAIR, False)

    assert len(calls) == 1
    assert r1 == r2 == "cards-clair"


def test_tableau_changement_de_theme_meme_filtre_deux_calculs(tableau_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(tableau_mod, "filtermodel_to_ast", lambda fm, schema: "ast")
    monkeypatch.setattr(
        tableau_mod, "ast_to_sql", lambda ast, schema, *, operateurs: ("1=1", [])
    )
    monkeypatch.setattr(tableau_mod, "query_marches", lambda **kw: "dff-stub")
    monkeypatch.setattr(
        tableau_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtre_json = tableau_mod._normalize_filter_model(
        {"acheteur_nom": {"filterType": "text", "type": "contains", "filter": "ACME"}}
    )
    r_clair = tableau_mod._cards_pour_filtre(filtre_json, CLAIR, False)
    r_sombre = tableau_mod._cards_pour_filtre(filtre_json, SOMBRE, False)

    assert len(calls) == 2
    assert r_clair == "cards-clair"
    assert r_sombre == "cards-sombre"


def test_tableau_build_dashboard_cards_recoit_le_theme(tableau_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(tableau_mod, "filtermodel_to_ast", lambda fm, schema: "ast")
    monkeypatch.setattr(
        tableau_mod, "ast_to_sql", lambda ast, schema, *, operateurs: ("1=1", [])
    )
    monkeypatch.setattr(tableau_mod, "query_marches", lambda **kw: "dff-stub")
    monkeypatch.setattr(
        tableau_mod, "build_dashboard_cards", _fake_build_dashboard_cards(calls)
    )

    filtre_json = tableau_mod._normalize_filter_model(
        {"acheteur_nom": {"filterType": "text", "type": "contains", "filter": "ACME"}}
    )
    tableau_mod._cards_pour_filtre(filtre_json, SOMBRE, False)

    assert calls[-1]["theme"] == SOMBRE
