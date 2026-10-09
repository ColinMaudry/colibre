"""Suivi Matomo côté navigateur : le relais pousse dans `window._paq`."""

from dash.testing.composite import DashComposite
from selenium.webdriver import Keys
from selenium.webdriver.support.ui import WebDriverWait

from tests.helpers import appels_paq, installer_espion_paq


def _rechercher(dash_duo: DashComposite, texte: str) -> None:
    dash_duo.wait_for_element("#search", timeout=8)
    champ = dash_duo.find_element("#search")
    champ.send_keys(texte)
    champ.send_keys(Keys.ENTER)
    dash_duo.wait_for_element("#search_results h3", timeout=8)


def test_recherche_accueil_pousse_un_trackSiteSearch(dash_duo: DashComposite):
    from src.app import app

    installer_espion_paq(dash_duo.driver)
    dash_duo.start_server(app)
    _rechercher(dash_duo, "ACHETEUR 1")
    WebDriverWait(dash_duo.driver, 8).until(lambda d: appels_paq(d, "trackSiteSearch"))
    (appel,) = appels_paq(dash_duo.driver, "trackSiteSearch")
    assert appel[1:3] == ["ACHETEUR 1", "accueil"]


def test_recherche_sans_traqueur_ne_leve_pas(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    _rechercher(dash_duo, "ACHETEUR 1")
    erreurs = [e for e in dash_duo.get_logs() or [] if e["level"] == "SEVERE"]
    assert erreurs == []
