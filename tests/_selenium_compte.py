"""Aides Selenium partagées : connexion par le vrai formulaire et ouverture du
Tableau. Les fixtures de compte (`compte_abonne`, `compte_sans_abonnement`)
sont dans `tests/conftest.py`."""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

EMAIL = "mode-observatoire@test.local"
MOT_DE_PASSE = "motdepasse-de-test-137"


def se_connecter(dash_duo: DashComposite):
    dash_duo.wait_for_page(f"{dash_duo.server_url}/connexion")
    dash_duo.wait_for_element("input[name='email']", timeout=8)
    dash_duo.driver.find_element(By.CSS_SELECTOR, "input[name='email']").send_keys(
        EMAIL
    )
    champ_mdp = dash_duo.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
    champ_mdp.send_keys(MOT_DE_PASSE)
    champ_mdp.submit()
    time.sleep(2)


def ouvrir_le_tableau(dash_duo: DashComposite):
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-root", timeout=10)
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)
