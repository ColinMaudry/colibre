"""Les filtres de colonne des grilles AG Grid ne s'appliquent qu'à la
validation (Entrée), pas à chaque caractère tapé.

Les pastilles de filtre reflètent le filterModel réellement appliqué : leur
apparition prouve que la grille a refiltré.
"""

import time

from selenium.webdriver.common.keys import Keys

import src.app  # noqa: F401  # instancie l'app → register_page()

CHAMP = '#acheteur-grid-container .ag-floating-filter[col-id="objet"] input'
PASTILLE = "#acheteur-filter-pills .filter-pill-body"


def test_filtre_flottant_applique_seulement_apres_entree(dash_duo):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(dash_duo.server_url + "/acheteurs/123")
    dash_duo.wait_for_element(CHAMP, timeout=15)
    champ = dash_duo.find_element(CHAMP)

    champ.send_keys("test")
    # Largement au-delà du debounce natif d'AG Grid (500 ms).
    time.sleep(2)
    assert not dash_duo.find_elements(PASTILLE)

    champ.send_keys(Keys.ENTER)
    dash_duo.wait_for_contains_text(
        "#acheteur-filter-pills", "contient test", timeout=10
    )
