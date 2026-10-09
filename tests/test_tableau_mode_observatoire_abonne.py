"""Le mode observatoire de bout en bout, avec une session réellement abonnée.

Couvre la chaîne que les tests unitaires ne voient pas : interrupteur →
callback clientside → callback serveur → cards. La session est ouverte par le
vrai formulaire de connexion, et `TOUS_ABONNES` ouvre les fonctionnalités
d'abonné sans passer par la base d'abonnements — comme en production pendant
la période d'accès gratuit.
"""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

from tests._selenium_compte import ouvrir_le_tableau as _ouvrir_le_tableau
from tests._selenium_compte import se_connecter as _se_connecter


def test_linterrupteur_souvre_a_une_session_abonnee(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)

    interrupteur = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire")

    assert interrupteur.is_enabled()


def test_la_bascule_affiche_les_cards_du_filtre_courant(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    champ = driver.find_element(
        By.CSS_SELECTOR, ".ag-floating-filter-input input[aria-label*='acheteur']"
    )
    champ.send_keys("ACHETEUR")
    time.sleep(2)

    driver.find_element(By.ID, "tableau-mode-observatoire").click()
    dash_duo.wait_for_element("#tableau-observatoire-cards .card", timeout=15)

    cards = driver.find_element(By.ID, "tableau-observatoire-cards")
    titres = [t.text for t in cards.find_elements(By.CSS_SELECTOR, ".card-title")]

    assert "Résumé" in titres
    # Le corps de la grille a bien laissé la place, l'en-tête est resté.
    assert not driver.find_element(By.CSS_SELECTOR, ".ag-body").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, ".ag-header").is_displayed()


def test_sans_filtre_la_bascule_invite_a_en_poser_un(
    dash_duo: DashComposite, compte_abonne
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    driver.find_element(By.ID, "tableau-mode-observatoire").click()
    time.sleep(3)

    cards = driver.find_element(By.ID, "tableau-observatoire-cards")

    assert "Appliquez au moins un filtre" in cards.text


def test_un_compte_sans_acces_garde_linterrupteur_ferme(
    dash_duo: DashComposite, compte_sans_abonnement
):
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)

    interrupteur = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire")
    enveloppe = dash_duo.driver.find_element(By.ID, "tableau-mode-observatoire-wrapper")

    assert not interrupteur.is_enabled()
    assert (
        enveloppe.get_attribute("title") == "Fonctionnalité accessible en vous abonnant"
    )


# dcc.Store(storage_type="local") range sa donnée sous son id, sans préfixe.
CLE_LOCALSTORAGE = "tableau-mode-observatoire-persiste"


def test_le_mode_observatoire_persiste_apres_rechargement(
    dash_duo: DashComposite, compte_abonne
):
    """Un abonné qui bascule en mode visualisations, puis recharge la page,
    retrouve le mode visualisations sans action de sa part."""
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    # Bascule en mode observatoire (sans filtre → message d'invitation, mais le
    # mode est actif).
    driver.find_element(By.ID, "tableau-mode-observatoire").click()
    time.sleep(2)

    # Le localStorage contient bien true.
    valeur = driver.execute_script(
        f"return window.localStorage.getItem('{CLE_LOCALSTORAGE}');"
    )
    assert valeur == "true"

    # Rechargement : le mode doit être restauré côté client.
    driver.get(f"{dash_duo.server_url}/tableau")
    _ouvrir_le_tableau(dash_duo)

    wrapper = driver.find_element(By.ID, "tableau-mode-wrapper")
    assert "mode-observatoire" in wrapper.get_attribute("class")


def test_un_ex_abonne_ne_restaurateur_pas_le_mode_observatoire(
    dash_duo: DashComposite, compte_sans_abonnement
):
    """Un non-abonné dont le localStorage contient `true` (choix mémorisé avant
    l'expiration de l'abonnement) ne doit pas se retrouver bloqué en mode
    visualisations : l'interrupteur étant désactivé, la restauration renvoie
    False et les lignes restent visibles."""
    from src.app import app

    dash_duo.start_server(app)
    _se_connecter(dash_duo)
    _ouvrir_le_tableau(dash_duo)
    driver = dash_duo.driver

    # Injecte le choix mémorisé comme si l'utilisateur l'avait fait en étant
    # abonné, puis recharge.
    driver.execute_script(f"window.localStorage.setItem('{CLE_LOCALSTORAGE}', 'true');")
    driver.get(f"{dash_duo.server_url}/tableau")
    _ouvrir_le_tableau(dash_duo)

    wrapper = driver.find_element(By.ID, "tableau-mode-wrapper")
    assert "mode-observatoire" not in wrapper.get_attribute("class")
