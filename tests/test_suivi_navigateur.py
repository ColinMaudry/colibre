"""Suivi Matomo côté navigateur : le relais pousse dans `window._paq`."""

import time

import pytest
from dash.testing.composite import DashComposite
from selenium.webdriver import Keys
from selenium.webdriver.support.ui import WebDriverWait

from tests._selenium_compte import ouvrir_le_tableau as _ouvrir_le_tableau
from tests._selenium_compte import se_connecter as _se_connecter
from tests.helpers import appels_paq, installer_espion_paq

# Anti-rebond de 3 s des filtres de grille, plus une marge.
_ATTENTE_ANTI_REBOND = 4


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


def _demarrer(dash_duo: DashComposite, chemin: str) -> None:
    from src.app import app

    installer_espion_paq(dash_duo.driver)
    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + chemin)


def _saisir_filtre_objet(dash_duo: DashComposite, conteneur: str, texte: str) -> None:
    champ = f'{conteneur} .ag-floating-filter[col-id="objet"] input'
    dash_duo.wait_for_element(champ, timeout=15)
    el = dash_duo.find_element(champ)
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el
    )
    el.send_keys(texte)


def _filtres_envoyes(dash_duo: DashComposite) -> list[list]:
    return [a for a in appels_paq(dash_duo.driver, "trackEvent") if a[2] == "filtres"]


def test_serialiser_filtres_js(dash_duo: DashComposite):
    _demarrer(dash_duo, "/tableau")
    dash_duo.wait_for_element("#tableau_grid .ag-root", timeout=15)
    serialiser = "return window.colibreSuivi.serialiserFiltres(arguments[0]);"
    objet = {"filterType": "text", "type": "contains", "filter": "voirie"}
    montant = {"filterType": "number", "type": "greaterThan", "filter": 10000}

    dans_l_ordre = dash_duo.driver.execute_script(
        serialiser, {"objet": objet, "montant": montant}
    )
    dans_l_autre_ordre = dash_duo.driver.execute_script(
        serialiser, {"montant": montant, "objet": objet}
    )
    assert dans_l_ordre == 'montant > 10000 | objet contient "voirie"'
    assert dans_l_autre_ordre == dans_l_ordre

    entre = {"filterType": "number", "type": "inRange", "filter": 1, "filterTo": 10}
    assert (
        dash_duo.driver.execute_script(serialiser, {"montant": entre})
        == "montant entre 1 et 10"
    )

    combine = {
        "filterType": "text",
        "operator": "AND",
        "conditions": [
            {"filterType": "text", "type": "contains", "filter": "a"},
            {"filterType": "text", "type": "contains", "filter": "b"},
        ],
    }
    assert (
        dash_duo.driver.execute_script(serialiser, {"objet": combine})
        == 'objet (contient "a" ET contient "b")'
    )

    long = {"filterType": "text", "type": "contains", "filter": "x" * 600}
    tronquee = dash_duo.driver.execute_script(serialiser, {"objet": long})
    assert len(tronquee) == 500
    assert tronquee.endswith("…")


def test_filtre_saisi_dans_le_tableau_envoie_un_evenement(dash_duo: DashComposite):
    _demarrer(dash_duo, "/tableau")
    _saisir_filtre_objet(dash_duo, "#tableau_grid", "voirie")
    time.sleep(_ATTENTE_ANTI_REBOND)
    assert _filtres_envoyes(dash_duo) == [
        ["trackEvent", "Tableau", "filtres", 'objet contient "voirie"', 1]
    ]


def test_filtre_saisi_dans_une_fiche_envoie_un_evenement(dash_duo: DashComposite):
    _demarrer(dash_duo, "/acheteurs/123")
    _saisir_filtre_objet(dash_duo, "#acheteur-grid-container", "voirie")
    time.sleep(_ATTENTE_ANTI_REBOND)
    assert _filtres_envoyes(dash_duo) == [
        ["trackEvent", "Acheteur", "filtres", 'objet contient "voirie"', 1]
    ]


def test_vue_partagee_et_filtre_d_url_n_envoient_rien(dash_duo: DashComposite):
    _demarrer(dash_duo, "/tableau?acheteur_id=123")
    dash_duo.wait_for_contains_text(
        "#tableau-filter-pills", "SIRET acheteur", timeout=15
    )
    time.sleep(_ATTENTE_ANTI_REBOND)
    assert _filtres_envoyes(dash_duo) == []


def test_filtre_puis_reinitialisation_rapide_n_envoie_rien(dash_duo: DashComposite):
    modele = 'return dash_ag_grid.getApi("tableau_grid").getFilterModel();'
    _demarrer(dash_duo, "/tableau")
    _saisir_filtre_objet(dash_duo, "#tableau_grid", "voirie")
    # Le filtre flottant applique la saisie après son propre délai : attendre
    # qu'il soit dans la grille, sinon il serait appliqué après la réinitialisation.
    WebDriverWait(dash_duo.driver, 2).until(lambda d: d.execute_script(modele))
    dash_duo.find_element("#btn-tableau-reset").click()
    WebDriverWait(dash_duo.driver, 2).until(lambda d: d.execute_script(modele) == {})
    time.sleep(_ATTENTE_ANTI_REBOND)
    assert _filtres_envoyes(dash_duo) == []


def _evenements(dash_duo: DashComposite, action: str) -> list[list]:
    return [a for a in appels_paq(dash_duo.driver, "trackEvent") if a[2] == action]


@pytest.mark.usefixtures("compte_abonne")
def test_bascule_manuelle_du_mode_envoie_un_evenement(dash_duo: DashComposite):
    from src.app import app

    installer_espion_paq(dash_duo.driver)
    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    dash_duo.find_element("#tableau-mode-observatoire").click()
    WebDriverWait(dash_duo.driver, 4).until(lambda d: _evenements(dash_duo, "mode"))
    assert _evenements(dash_duo, "mode") == [
        ["trackEvent", "Tableau", "mode", "observatoire"]
    ]

    # Le rechargement restaure le mode mémorisé : ce n'est pas un geste.
    dash_duo.driver.refresh()
    dash_duo.wait_for_element(".ag-root", timeout=10)
    dash_duo.wait_for_element("#tableau-mode-wrapper.mode-observatoire", timeout=10)
    time.sleep(2)
    assert _evenements(dash_duo, "mode") == []


def test_restauration_du_mode_sans_abonnement_n_envoie_rien(dash_duo: DashComposite):
    _demarrer(dash_duo, "/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=10)
    dash_duo.driver.execute_script(
        "window.localStorage.setItem('tableau-mode-observatoire-persiste', 'true');"
    )
    dash_duo.driver.refresh()
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)
    time.sleep(2)
    assert _evenements(dash_duo, "mode") == []


@pytest.mark.usefixtures("compte_abonne")
def test_deplacement_d_une_tuile_envoie_un_evenement(dash_duo: DashComposite):
    from src.app import app

    installer_espion_paq(dash_duo.driver)
    # Le drag & drop n'est armé que sur un écran d'au moins 768 px de large.
    dash_duo.driver.set_window_size(1400, 1000)
    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element("[data-observatoire-cards]", timeout=20)
    WebDriverWait(dash_duo.driver, 10).until(
        lambda d: d.execute_script(
            "return document.querySelector('[data-observatoire-cards]')"
            ".parentElement.dataset.dragEnabled === 'true';"
        )
    )
    premiere = dash_duo.driver.execute_script(
        """
        const liste = document.querySelector("[data-observatoire-cards]").parentElement;
        const cards = Array.from(liste.children)
            .filter((el) => el.classList.contains("observatoire-card"));
        const [source, cible] = cards;
        const dt = new DataTransfer();
        const lancer = (el, type) => el.dispatchEvent(
            new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt})
        );
        lancer(source, "dragstart");
        lancer(cible, "dragover");
        lancer(cible, "drop");
        lancer(source, "dragend");
        return Array.from(source.classList)
            .find((c) => c.startsWith("observatoire-card--"))
            .slice("observatoire-card--".length);
        """
    )
    assert _evenements(dash_duo, "tuile_deplacee") == [
        ["trackEvent", "Observatoire", "tuile_deplacee", premiere, 2]
    ]
