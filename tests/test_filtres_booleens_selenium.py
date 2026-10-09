"""Filtres booléens (#97) de bout en bout : la pastille montre l'expression
réellement appliquée, corrigée pour un·e abonné·e, accompagnée du bandeau
d'opérateurs pour un compte sans abonnement.

La base de test n'a qu'une ligne : la grille sera vide, seules les pastilles
comptent.
"""

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

from tests._selenium_compte import ouvrir_le_tableau, se_connecter

CHAMP_OBJET = '.ag-floating-filter[col-id="objet"] input'


def _saisir_objet(dash_duo: DashComposite, texte: str):
    """Ramène le champ dans le viewport (défilement horizontal du tableau)
    avant la saisie, comme `_filter_input_in_view` de test_main.py."""
    dash_duo.wait_for_element(CHAMP_OBJET, timeout=10)
    champ = dash_duo.find_element(CHAMP_OBJET)
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", champ
    )
    champ.send_keys(texte)


def test_abonne_voit_la_correction(dash_duo: DashComposite, compte_abonne):
    from src.app import app

    dash_duo.start_server(app)
    se_connecter(dash_duo)
    ouvrir_le_tableau(dash_duo)

    _saisir_objet(dash_duo, "(béton OU")

    dash_duo.wait_for_contains_text(
        "#tableau-filter-pills",
        "contient béton (parenthèse manquante, OU orphelin)",
        timeout=10,
    )
    pastilles = dash_duo.driver.find_elements(
        By.CSS_SELECTOR, "#tableau-filter-pills .filter-pill-warning"
    )
    assert len(pastilles) == 1


def test_non_abonne_voit_le_bandeau(dash_duo: DashComposite, compte_sans_abonnement):
    from src.app import app
    from src.utils.filter_pills import BANNIERE_OPERATEURS

    dash_duo.start_server(app)
    se_connecter(dash_duo)
    ouvrir_le_tableau(dash_duo)

    _saisir_objet(dash_duo, "béton OU ciment")

    dash_duo.wait_for_element(
        "#tableau-filter-pills .filter-pills-banniere", timeout=10
    )
    dash_duo.wait_for_contains_text(
        "#tableau-filter-pills .filter-pills-banniere", BANNIERE_OPERATEURS, timeout=10
    )
