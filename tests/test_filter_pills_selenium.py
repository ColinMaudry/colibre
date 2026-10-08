"""Pastilles des filtres appliqués (#148), dans le navigateur.

Serveur en debug=True (dev-renderer) : valide aussi la cohérence des motifs
ALL/MATCH des callbacks des pastilles, comme test_entity_grid_datasource.
"""

from selenium.webdriver.support.ui import WebDriverWait

import src.app  # noqa: F401  # instancie l'app → register_page()

_ACTIF = """
const a = document.activeElement;
const cellule = a && a.closest('.ag-floating-filter');
return cellule ? [a.tagName, cellule.getAttribute('col-id')] : null;
"""


def _demarrer(dash_duo, chemin):
    from src.app import app

    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + chemin)


def test_tableau_pastille_du_filtre_org_puis_suppression(dash_duo):
    _demarrer(dash_duo, "/tableau?acheteur_id=123")

    dash_duo.wait_for_contains_text(
        "#tableau-filter-pills", "SIRET acheteur", timeout=15
    )
    assert "= 123" in dash_duo.find_element("#tableau-filter-pills").text

    dash_duo.find_element("#tableau-filter-pills .filter-pill-remove").click()

    WebDriverWait(dash_duo.driver, 10).until(
        lambda _d: not dash_duo.find_elements("#tableau-filter-pills .filter-pill")
    )
    # Plus aucun filtre : le téléchargement repasse sur le CSV complet.
    dash_duo.wait_for_contains_text(
        "#btn-download-data", "Télécharger toutes les données", timeout=10
    )


def test_tableau_clic_pastille_colonne_masquee_affiche_et_focus(dash_duo):
    # acheteur_id est masquée par défaut dans le Tableau.
    _demarrer(dash_duo, "/tableau?acheteur_id=123")
    dash_duo.wait_for_element("#tableau-filter-pills .filter-pill-body", timeout=15)
    assert not dash_duo.find_elements(
        '#tableau_grid .ag-floating-filter[col-id="acheteur_id"]'
    )

    dash_duo.find_element("#tableau-filter-pills .filter-pill-body").click()

    WebDriverWait(dash_duo.driver, 15).until(
        lambda d: d.execute_script(_ACTIF) == ["INPUT", "acheteur_id"]
    )


def test_fiche_acheteur_pastille_et_suppression(dash_duo):
    _demarrer(dash_duo, "/acheteurs/123")
    champ = '#acheteur-grid-container .ag-floating-filter[col-id="objet"] input'
    dash_duo.wait_for_element(champ, timeout=15)
    dash_duo.find_element(champ).send_keys("test")

    dash_duo.wait_for_contains_text(
        "#acheteur-filter-pills", "contient test", timeout=10
    )
    dash_duo.find_element("#acheteur-filter-pills .filter-pill-remove").click()

    WebDriverWait(dash_duo.driver, 10).until(
        lambda _d: not dash_duo.find_elements("#acheteur-filter-pills .filter-pill")
    )
    assert dash_duo.find_element(champ).get_attribute("value") == ""
