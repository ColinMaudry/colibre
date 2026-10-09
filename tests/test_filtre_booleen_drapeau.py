"""Le drapeau `operateurs` (abonné) active la syntaxe booléenne de bout en
bout : grille, export, et clés des caches mémoïsés des cards (#97)."""

from src.theme import CLAIR
from tests.test_theme_cache import (  # noqa: F401  (fixtures partagées)
    flask_app,
    observatoire_mod,
    reset_cache,
    tableau_mod,
)

FM = {"objet": {"filterType": "text", "type": "contains", "filter": "test OU zzzznope"}}


def test_grille_applique_le_ou_pour_un_abonne():
    from src.utils.grid import fetch_grid_page

    assert fetch_grid_page(FM, None, 0, 20, operateurs=True)[1] == 1
    assert fetch_grid_page(FM, None, 0, 20, operateurs=False)[1] == 0


def test_export_coherent_avec_la_grille():
    from src.utils.grid import export_dataframe

    assert export_dataframe(FM, None, [], operateurs=True).height == 1
    assert export_dataframe(FM, None, [], operateurs=False).height == 0


def test_cache_des_cards_distingue_le_drapeau(tableau_mod, monkeypatch):  # noqa: F811
    params_vus = []

    def faux_query_marches(**kw):
        params_vus.append(list(kw["params"]))
        return "dff-stub"

    monkeypatch.setattr(tableau_mod, "query_marches", faux_query_marches)
    monkeypatch.setattr(tableau_mod, "build_dashboard_cards", lambda dff, **kw: "cards")

    filtre_json = tableau_mod._normalize_filter_model(FM)
    tableau_mod._cards_pour_filtre(filtre_json, CLAIR, True)
    tableau_mod._cards_pour_filtre(filtre_json, CLAIR, False)

    assert len(params_vus) == 2
    assert params_vus[0] != params_vus[1]


def test_cache_de_l_observatoire_distingue_le_drapeau(
    observatoire_mod,  # noqa: F811
    monkeypatch,
):
    drapeaux = []

    def faux_prepare(columns=None, *, operateurs, **filter_params):
        drapeaux.append(operateurs)
        return "dff-stub"

    monkeypatch.setattr(observatoire_mod, "prepare_dashboard_data", faux_prepare)
    monkeypatch.setattr(
        observatoire_mod, "build_dashboard_cards", lambda dff, **kw: "cards"
    )

    filtres = (("dashboard_marche_objet", "test OU zzzznope"),)
    observatoire_mod._compute_dashboard_children(filtres, CLAIR, True)
    observatoire_mod._compute_dashboard_children(filtres, CLAIR, False)

    assert drapeaux == [True, False]
