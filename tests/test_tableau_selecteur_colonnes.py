"""Le sélecteur de colonnes du Tableau, de bout en bout.

Aucun test ne le couvrait, alors que l'issue #139 a déplacé le moment où ses
cases sont alimentées (ouverture de la modale, et non plus toute écriture du
store). Ce fichier vérifie que le parcours complet fonctionne toujours.
"""

import time

from dash.testing.composite import DashComposite
from selenium.webdriver.common.by import By

CASES = "#tableau_column_list .ag-row .ag-selection-checkbox input"
TOUT_COCHER = "#tableau_column_list .ag-header-select-all input"
RECHERCHE = "input[id*='column-search'][id*='tableau']"


def _entetes_de_la_grille(dash_duo) -> set[str]:
    cellules = dash_duo.driver.find_elements(
        By.CSS_SELECTOR, "#tableau_grid .ag-header-cell-text"
    )
    return {c.text for c in cellules if c.text}


def _nom_de_la_ligne(case) -> str:
    ligne = case.find_element(By.XPATH, "./ancestor::div[contains(@class,'ag-row ')]")
    return ligne.find_element(By.CSS_SELECTOR, ".ag-cell[col-id='name']").text


def _etat_des_cases(dash_duo) -> dict[str, bool]:
    """{nom de la colonne: cochée ?} pour les lignes affichées du sélecteur."""
    return {
        _nom_de_la_ligne(c): c.is_selected()
        for c in dash_duo.driver.find_elements(By.CSS_SELECTOR, CASES)
    }


def _charger_le_tableau(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)


def _ouvrir_la_modale(dash_duo: DashComposite):
    dash_duo.driver.find_element(By.ID, "tableau_columns_open").click()
    dash_duo.wait_for_element(CASES, timeout=8)
    time.sleep(1)  # laisse le callback d'ouverture peupler les cases


def test_ouvrir_la_modale_coche_les_colonnes_affichees(dash_duo: DashComposite):
    """Le cœur du changement de #139 : les cases sont peuplées à l'ouverture.
    Si elles restaient vides, l'utilisateur croirait n'avoir aucune colonne
    affichée et décocherait dans le vide."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)

    _ouvrir_la_modale(dash_duo)

    cochees = [
        c
        for c in dash_duo.driver.find_elements(By.CSS_SELECTOR, CASES)
        if c.is_selected()
    ]

    assert cochees, "aucune case cochée : les cases n'ont pas été alimentées"


def test_decocher_une_colonne_la_retire_de_la_grille(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/tableau")
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)
    avant = _entetes_de_la_grille(dash_duo)
    assert avant, "aucun en-tête lu avant l'action"

    _ouvrir_la_modale(dash_duo)
    driver = dash_duo.driver

    cible = None
    for case in driver.find_elements(By.CSS_SELECTOR, CASES):
        if not case.is_selected():
            continue
        nom = _nom_de_la_ligne(case)
        if nom in avant:
            cible = (case, nom)
            break
    assert cible is not None, f"aucune case cochée ne correspond aux en-têtes {avant}"

    case, nom = cible
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", case)
    case.click()
    time.sleep(1.5)
    driver.find_element(By.ID, "tableau_columns_close").click()
    time.sleep(1.5)

    assert nom not in _entetes_de_la_grille(dash_duo), (
        f"la colonne « {nom} » est toujours affichée après avoir été décochée"
    )


def _filtrer(dash_duo, texte: str):
    champ = dash_duo.driver.find_element(By.CSS_SELECTOR, RECHERCHE)
    champ.clear()
    if texte:
        champ.send_keys(texte)
    else:
        # clear() ne déclenche pas d'événement input côté React.
        champ.send_keys("x")
        champ.send_keys("\ue003")  # retour arrière
    time.sleep(1)


def test_la_recherche_filtre_les_colonnes(dash_duo: DashComposite):
    _charger_le_tableau(dash_duo)
    _ouvrir_la_modale(dash_duo)
    toutes = _etat_des_cases(dash_duo)
    assert "Montant attribué" in toutes and len(toutes) > 5

    _filtrer(dash_duo, "Montant attribu")

    filtrees = _etat_des_cases(dash_duo)
    assert "Montant attribué" in filtrees
    assert 0 < len(filtrees) < len(toutes), (
        f"le filtre n'a pas réduit la liste : {len(filtrees)} / {len(toutes)}"
    )


def test_tout_cocher_avec_un_filtre_ne_coche_que_les_lignes_filtrees(
    dash_duo: DashComposite,
):
    _charger_le_tableau(dash_duo)
    _ouvrir_la_modale(dash_duo)
    avant = _etat_des_cases(dash_duo)
    assert any(avant.values()) and not all(avant.values()), (
        "il faut des cases cochées et d'autres non pour que le test parle"
    )

    _filtrer(dash_duo, "titulaire")
    filtrees = set(_etat_des_cases(dash_duo))
    assert filtrees and len(filtrees) < len(avant)
    assert not all(avant[n] for n in filtrees), "tout est déjà coché dans le filtre"

    case = dash_duo.driver.find_element(By.CSS_SELECTOR, TOUT_COCHER)
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", case
    )
    case.click()
    time.sleep(1)
    apres_filtre = _etat_des_cases(dash_duo)
    assert all(apres_filtre.values()), f"lignes filtrées non cochées : {apres_filtre}"

    _filtrer(dash_duo, "")
    apres = _etat_des_cases(dash_duo)
    assert len(apres) == len(avant)
    for nom, coche in apres.items():
        attendu = True if nom in filtrees else avant[nom]
        assert coche == attendu, f"« {nom} » : {coche}, attendu {attendu}"


def test_ouvrir_puis_fermer_la_modale_ne_change_pas_les_colonnes(
    dash_duo: DashComposite,
):
    """Poser selectedRows à l'ouverture fait réémettre la sélection par AG
    Grid : si cet écho réécrivait le store (sélection partielle ou vide au
    montage dans la modale), les colonnes changeraient sans action de
    l'utilisateur."""
    _charger_le_tableau(dash_duo)
    driver = dash_duo.driver
    avant = _entetes_de_la_grille(dash_duo)
    assert len(avant) > 2, "aucun en-tête lu avant l'action"
    store_avant = driver.execute_script(
        "return localStorage.getItem('tableau-hidden-columns');"
    )

    _ouvrir_la_modale(dash_duo)
    assert any(_etat_des_cases(dash_duo).values()), "les cases n'ont pas été peuplées"
    driver.find_element(By.ID, "tableau_columns_close").click()
    time.sleep(1.5)
    assert _entetes_de_la_grille(dash_duo) == avant

    driver.refresh()
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=10)
    time.sleep(1)

    assert _entetes_de_la_grille(dash_duo) == avant
    assert (
        driver.execute_script("return localStorage.getItem('tableau-hidden-columns');")
        == store_avant
    )
