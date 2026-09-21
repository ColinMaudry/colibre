"""Le mode observatoire vu par le navigateur : le corps de la grille disparaît,
son en-tête reste visible et actionnable.

Les assertions sur le texte de style.css ne prouvent pas que les sélecteurs
visent quelque chose. Ici on applique la classe et on regarde le DOM réel.
"""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By


def _charger_le_tableau(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=8)
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)


def test_le_corps_de_la_grille_est_visible_hors_mode_observatoire(
    dash_duo: DashComposite,
):
    """Contrôle négatif : sans la classe, le corps est bien affiché — sinon le
    test suivant passerait pour de mauvaises raisons."""
    _charger_le_tableau(dash_duo)

    corps = dash_duo.driver.find_element(By.CSS_SELECTOR, ".ag-body")

    assert corps.is_displayed()


def test_la_classe_masque_le_corps_et_conserve_len_tete(dash_duo: DashComposite):
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    enveloppe = driver.find_element(By.ID, "tableau-grid-wrapper")
    hauteur_avec_lignes = enveloppe.size["height"]

    driver.execute_script(
        "document.getElementById('tableau-mode-wrapper')"
        ".className = 'tableau-mode mode-observatoire';"
    )
    time.sleep(0.3)

    assert not driver.find_element(By.CSS_SELECTOR, ".ag-body").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, ".ag-header").is_displayed()
    # Les filtres flottants restent atteignables pour affiner la sélection.
    assert driver.find_element(By.CSS_SELECTOR, ".ag-floating-filter").is_displayed()
    assert enveloppe.size["height"] < hauteur_avec_lignes


def test_lentete_reste_defilable_horizontalement(dash_duo: DashComposite):
    """Les colonnes débordent de la largeur de l'écran même avec le choix par
    défaut. Sans barre de défilement, les filtres des colonnes de droite
    deviendraient inatteignables en mode observatoire — or c'est justement là
    qu'on veut pouvoir affiner sans quitter le mode."""
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    driver.execute_script(
        "document.getElementById('tableau-mode-wrapper')"
        ".className = 'tableau-mode mode-observatoire';"
    )
    time.sleep(0.3)

    entete = driver.find_element(By.CSS_SELECTOR, ".ag-header-viewport")
    deborde = driver.execute_script(
        "return arguments[0].scrollWidth > arguments[0].clientWidth;", entete
    )
    assert deborde, "l'en-tête ne déborde pas : le test ne prouverait rien"

    barre = driver.find_element(By.CSS_SELECTOR, ".ag-body-horizontal-scroll")
    assert barre.is_displayed()

    # La barre pilote bien le défilement de l'en-tête.
    driver.execute_script(
        "document.querySelector('.ag-body-horizontal-scroll-viewport')"
        ".scrollLeft = 300;"
    )
    time.sleep(0.4)
    assert driver.execute_script("return arguments[0].scrollLeft;", entete) > 0


def test_changer_de_colonnes_en_mode_observatoire_garde_len_tete_complet(
    dash_duo: DashComposite,
):
    """Masquer le corps de la grille ne doit pas casser la virtualisation
    horizontale d'AG Grid.

    Avec `display: none` sur `.ag-body`, son viewport tombe à une largeur nulle.
    AG Grid s'en sert pour décider combien de colonnes rendre : à la
    régénération des columnDefs (décocher une colonne dans « Colonnes »), il en
    conclut qu'une seule tient et n'affiche plus qu'un en-tête. Le rechargement
    de la page corrigeait l'affichage, ce qui rendait le défaut déroutant.
    """
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    driver.execute_script(
        "document.getElementById('tableau-mode-wrapper')"
        ".className = 'tableau-mode mode-observatoire';"
    )
    time.sleep(0.5)
    entetes_avant = _entetes_de_la_grille(driver)
    assert len(entetes_avant) > 2, "il faut plusieurs colonnes pour que le test parle"

    driver.find_element(By.ID, "tableau_columns_open").click()
    cases = "#tableau_column_list .ag-row .ag-selection-checkbox input"
    dash_duo.wait_for_element(cases, timeout=8)
    time.sleep(1)
    cochees = [
        c for c in driver.find_elements(By.CSS_SELECTOR, cases) if c.is_selected()
    ]
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cochees[0])
    cochees[0].click()
    time.sleep(1.5)
    driver.find_element(By.ID, "tableau_columns_close").click()
    time.sleep(2)

    entetes_apres = _entetes_de_la_grille(driver)

    assert len(entetes_apres) == len(entetes_avant) - 1, (
        f"en-têtes attendus : {len(entetes_avant) - 1}, obtenus : {entetes_apres}"
    )


def _entetes_de_la_grille(driver) -> list[str]:
    cellules = driver.find_elements(
        By.CSS_SELECTOR, "#tableau_grid .ag-header-cell-text"
    )
    return [c.text for c in cellules if c.text]
