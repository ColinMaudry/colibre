"""Les sélecteurs de colonnes d'acheteur, titulaire et observatoire (#139).

Aucun n'était couvert, alors que le déclencheur de leurs cases vient de
changer. On vérifie le point qui casserait si le changement était mauvais :
les cases sont peuplées à l'ouverture de la modale.
"""

import time

import pytest
from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

# (url, id du bouton d'ouverture, id des cases)
PAGES = [
    ("/acheteurs/123", "acheteur_columns_open", "acheteur_column_list"),
    ("/titulaires/345", "titulaire_columns_open", "titulaire_column_list"),
]


@pytest.mark.parametrize("chemin,bouton,cases", PAGES)
def test_ouvrir_la_modale_coche_les_colonnes_affichees(
    dash_duo: DashComposite, chemin, bouton, cases
):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}{chemin}")
    dash_duo.wait_for_element(f"#{bouton}", timeout=10)
    cible = dash_duo.driver.find_element(By.ID, bouton)
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", cible
    )
    time.sleep(0.5)
    cible.click()
    selecteur = f"#{cases} .ag-row .ag-selection-checkbox input"
    dash_duo.wait_for_element(selecteur, timeout=8)
    time.sleep(1)

    cochees = [
        c
        for c in dash_duo.driver.find_elements(By.CSS_SELECTOR, selecteur)
        if c.is_selected()
    ]

    assert cochees, "aucune case cochée : les cases n'ont pas été alimentées"


def test_observatoire_ouvrir_la_modale_coche_les_colonnes(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    # Le sélecteur vit dans le tiroir de prévisualisation des données.
    dash_duo.wait_for_element("#btn-observatoire-preview", timeout=15)
    dash_duo.driver.find_element(By.ID, "btn-observatoire-preview").click()
    dash_duo.wait_for_element("#observatoire-preview-columns-open", timeout=10)
    dash_duo.driver.find_element(By.ID, "observatoire-preview-columns-open").click()
    selecteur = "#observatoire_preview_column_list .ag-row .ag-selection-checkbox input"
    dash_duo.wait_for_element(selecteur, timeout=8)
    time.sleep(1)

    cochees = [
        c
        for c in dash_duo.driver.find_elements(By.CSS_SELECTOR, selecteur)
        if c.is_selected()
    ]

    assert cochees, "aucune case cochée : les cases n'ont pas été alimentées"
