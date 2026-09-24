import polars as pl
from dash.testing.composite import DashComposite
from selenium.webdriver import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


def _wait_input_value(dash_duo, element: WebElement, expected: str, timeout=8) -> None:
    """Attend qu'un input atteigne la valeur attendue. La restauration de la
    persistance des filtres est asynchrone après rechargement de page : sous
    charge, lire la valeur immédiatement renvoie une chaîne vide."""
    WebDriverWait(dash_duo.driver, timeout).until(
        lambda _d: element.get_attribute("value") == expected
    )


def _filter_input_in_view(dash_duo, selector, timeout=6) -> WebElement:
    """Attend la présence d'un input de filtre du marches_table et le ramène
    dans le viewport. Le tableau a un défilement horizontal : sous charge
    (suite complète), la colonne ciblée peut être hors écran, ce qui fait échouer
    send_keys avec ElementNotInteractableException alors que l'élément est
    pourtant rendu et visible."""
    dash_duo.wait_for_element(selector, timeout=timeout)
    el: WebElement = dash_duo.find_element(selector)
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el
    )
    return el


def test_001_logo_and_search(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)
    assert dash_duo.find_element(".logo > h1").text == "colibre"

    for org_type in ["acheteur", "titulaire"]:
        name = f"{org_type.upper()} 1"
        search_bar: WebElement = dash_duo.find_element("#search")

        dash_duo.clear_input(search_bar)

        search_bar.send_keys(name)
        search_bar.send_keys(Keys.ENTER)

        dash_duo.wait_for_element(
            f"#results_{org_type}_datatable .ag-center-cols-container .ag-row",
            timeout=4,
        )
        result_rows = dash_duo.find_elements(
            f"#results_{org_type}_datatable .ag-center-cols-container .ag-row"
        )

        assert len(result_rows) == 1, "The search should return only one result"
        assert dash_duo.find_element(
            f'#results_{org_type}_datatable .ag-cell[col-id="{org_type}_nom"]'
        ).text.startswith(name), (
            f"The search result should have the right {org_type} name"
        )


def test_002_filter_persistence(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # /tableau utilise AG Grid (dash-ag-grid) depuis #41 ; sa persistance de
    # filtres/colonnes est couverte par persistence=True et
    # persisted_props=["filterModel", "columnState"] configurés dans la fabrique
    # ag_grid() de src/figures.py, et a été vérifiée manuellement via un navigateur
    # réel (Task 12 du plan #41).
    #
    # Les fiches acheteur/titulaire utilisent désormais elles aussi AG Grid
    # (src/utils/entity_grid.py). Chaque grille a un id pattern-matching
    # {"type": "<org>-grid", "entity_id": ..., "year": ...} : la persistance
    # (localStorage, persisted_props=["filterModel"]) est donc scopée par fiche
    # (et année) — on ne peut pas s'attendre à ce qu'un filtre saisi sur une
    # fiche survive à la navigation vers une AUTRE fiche, seulement à un
    # rechargement de la MÊME URL. C'est ce que ce test vérifie ci-dessous, sur
    # la colonne "objet" (filtre texte AG Grid, sans ambiguïté de format
    # contrairement à un filtre de date).

    def filter_input_selector(container_id: str) -> str:
        return f'#{container_id} div[col-id="objet"] .ag-floating-filter-input input'

    def open_page_and_get_filter_input(page: str, container_id: str) -> WebElement:
        dash_duo.wait_for_page(f"{dash_duo.server_url}/{page}")
        return _filter_input_in_view(dash_duo, filter_input_selector(container_id))

    for page, container_id in [
        ("acheteurs/123", "acheteur-grid-container"),
        ("titulaires/345", "titulaire-grid-container"),
    ]:
        filter_input = open_page_and_get_filter_input(page, container_id)
        filter_input.send_keys(
            "zzz_no_match"
        )  # valeur quelconque, on teste la persistance
        # Attendre que le filtre soit réellement appliqué (la grille se vide :
        # "zzz_no_match" ne matche aucun "objet") AVANT de re-naviguer. Sinon, on
        # peut quitter la page avant que le callback de filtre ait écrit la
        # persistance → la valeur n'est pas restaurée à la ré-ouverture.
        dash_duo.wait_for_no_elements(
            f"#{container_id} .ag-center-cols-container .ag-row"
        )
        filter_input = open_page_and_get_filter_input(page, container_id)
        _wait_input_value(dash_duo, filter_input, "zzz_no_match")
        assert filter_input.get_attribute("value") == "zzz_no_match"


def test_003_tableau_download(dash_duo: DashComposite):
    from src.app import app
    from src.pages.acheteur import download_acheteur_data
    from src.pages.tableau import download_data
    from src.pages.titulaire import download_titulaire_data

    # Juste pour instancier l'app
    print(app.server.name)

    # /tableau : sans filtre, le bouton renvoie désormais vers le CSV complet
    # de data.gouv.fr au lieu de générer un fichier (#142) — un filterModel
    # non vide est donc nécessaire ici pour exercer la génération réelle,
    # comme avant cette bascule.
    filtre = {"objet": {"filterType": "text", "type": "contains", "filter": "Objet"}}

    outputs = [
        download_data(1, filtre, None),
        download_acheteur_data(1, "/acheteurs/123", "2025", "ACHETEUR 1"),
        download_titulaire_data(1, "/titulaires/345", "2025", "TITULAIRE 1"),
    ]
    for output in outputs:
        assert isinstance(output, dict)
        for f in ["content", "filename", "type", "base64"]:
            assert f in output
        assert isinstance(output["content"], str) and len(output["content"]) > 100
        assert isinstance(output["filename"], str) and output["filename"].startswith(
            "decp_"
        )
        assert output["type"] is None
        assert output["base64"] is True


def test_004_add_links_observatoire_acheteur():
    from src.utils.table import add_links

    dff = pl.DataFrame(
        {
            "acheteur_id": ["123"],
            "acheteur_nom": ["ACHETEUR 1"],
        }
    )
    result = add_links(dff)
    nom_value = result["acheteur_nom"][0]
    id_value = result["acheteur_id"][0]

    # acheteur_nom should contain detail link + observatoire link
    assert "/acheteurs/123" in nom_value
    assert "ACHETEUR 1" in nom_value
    assert "/observatoire?acheteur_id=123" in nom_value
    assert "📊" in nom_value

    # acheteur_id should NOT contain observatoire link
    assert "/observatoire" not in id_value


def test_005_add_links_observatoire_titulaire():
    from src.utils.table import add_links

    dff = pl.DataFrame(
        {
            "titulaire_id": ["345"],
            "titulaire_nom": ["TITULAIRE 1"],
            "titulaire_typeIdentifiant": ["SIRET"],
        }
    )
    result = add_links(dff)
    nom_value = result["titulaire_nom"][0]
    id_value = result["titulaire_id"][0]

    # titulaire_nom should contain detail link + observatoire link
    assert "/titulaires/345" in nom_value
    assert "TITULAIRE 1" in nom_value
    assert "/observatoire?titulaire_id=345" in nom_value
    assert "📊" in nom_value

    # titulaire_id should NOT contain observatoire link
    assert "/observatoire" not in id_value


def test_006_observatoire_url_to_input(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=123")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "123", (
        "acheteur_id input should be populated from URL param"
    )


def test_007_observatoire_share_url(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=123")
    dash_duo.wait_for_element("#observatoire-share-url", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    share_url_input = dash_duo.find_element("#observatoire-share-url")
    share_url_value = share_url_input.get_attribute("value")

    assert "acheteur_id=123" in share_url_value, (
        f"Share URL should contain acheteur_id param, got: {share_url_value}"
    )


def test_008_search_to_observatoire(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # Search for an acheteur
    search_bar = dash_duo.find_element("#search")
    search_bar.send_keys("ACHETEUR 1")
    search_bar.send_keys(Keys.ENTER)

    dash_duo.wait_for_element(
        "#results_acheteur_datatable .ag-center-cols-container .ag-row", timeout=4
    )

    # Find the observatoire link in acheteur_nom column
    observatoire_link = dash_duo.find_element(
        '#results_acheteur_datatable .ag-cell[col-id="acheteur_nom"] a[href*="observatoire"]'
    )
    assert "📊" in observatoire_link.text

    # Click the observatoire link
    observatoire_link.click()

    # Wait for observatoire page to load
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time

    time.sleep(1)  # Allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "123", (
        "acheteur_id input should be populated after navigating from search"
    )


def test_009_observatoire_filter_persistence(dash_duo: DashComposite):
    import time

    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # Clear localStorage to start from a clean state
    dash_duo.driver.execute_script("localStorage.clear()")

    # Navigate to observatoire without URL params
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    # Set the acheteur_id text input; press Enter to trigger the debounced save callback
    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    dash_duo.clear_input(acheteur_input)
    acheteur_input.send_keys("123")
    acheteur_input.send_keys(Keys.ENTER)

    time.sleep(0.3)  # allow the save callback to write to localStorage

    # Navigate away
    dash_duo.wait_for_page(f"{dash_duo.server_url}/")

    # Navigate back without URL params
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)
    time.sleep(0.5)  # allow restore callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "123", (
        "acheteur_id should be restored from localStorage after navigating back"
    )

    # Also verify URL params still override localStorage
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=123")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)
    time.sleep(0.5)

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "123", (
        "URL param acheteur_id should override the value stored in localStorage"
    )


def test_011_observatoire_multi_param_url(dash_duo: DashComposite):
    import time

    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # Navigate with multiple filter params
    dash_duo.wait_for_page(
        f"{dash_duo.server_url}/observatoire?annee=2024&acheteur_id=12345678901234&montant_min=10000"
    )
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    time.sleep(1)  # Allow callback chain to complete

    # Verify acheteur_id input
    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "12345678901234", (
        "acheteur_id input should be populated from URL param"
    )

    # Verify montant_min input
    montant_input = dash_duo.find_element("#dashboard_montant_min")
    montant_value = montant_input.get_attribute("value")
    assert montant_value in ("10000", "10000.0"), (
        f"montant_min input should be populated from URL param, got: {montant_value}"
    )


def test_012_get_distance_histogram_returns_graph():
    from dash import dcc

    from src.figures import get_distance_histogram

    lff = pl.LazyFrame({"titulaire_distance": [1, 10, 100, 500, 1000]})
    result = get_distance_histogram(lff)
    assert isinstance(result, dcc.Graph)


def test_013_get_distance_histogram_handles_nulls():
    from dash import dcc

    from src.figures import get_distance_histogram

    lff = pl.LazyFrame({"titulaire_distance": [None, None, 50]})
    result = get_distance_histogram(lff)
    assert isinstance(result, dcc.Graph)


def test_014_get_distance_histogram_all_nulls():
    from dash import dcc

    from src.figures import get_distance_histogram

    lff = pl.LazyFrame({"titulaire_distance": pl.Series([], dtype=pl.Int64)})
    result = get_distance_histogram(lff)

    assert isinstance(result, dcc.Graph)


def test_015_org_pages_filter_date(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=4)

    # /tableau utilise AG Grid depuis #41 ; le filtrage de sa colonne date est
    # couvert par les tests unitaires de compilation SQL dans
    # tests/test_query_ast.py (ex. test_date_range_uses_between) et a été
    # vérifié manuellement (Task 12 du plan #41).
    #
    # Les fiches acheteur/titulaire utilisent elles aussi AG Grid désormais
    # (src/utils/entity_grid.py). La colonne dateNotification y est un filtre
    # AG Grid de type "agDateColumnFilter", dont le floating filter est un
    # <input type="date"> natif du navigateur : peu fiable à piloter via
    # Selenium (send_keys/click interceptés selon le focus du picker natif).
    # On vérifie donc ici qu'UN filtre de colonne (texte, "objet") vide bien
    # la grille scopée à la fiche, sur le même principe que le test historique
    # (valeur ne correspondant à aucune ligne). Le filtrage par date reste
    # couvert au niveau SQL par tests/test_query_ast.py.
    for page, container_id in [
        ("acheteurs/123", "acheteur-grid-container"),
        ("titulaires/345", "titulaire-grid-container"),
    ]:
        dash_duo.wait_for_page(f"{dash_duo.server_url}/{page}")
        filter_input = (
            f'#{container_id} div[col-id="objet"] .ag-floating-filter-input input'
        )
        filter_cell_result = f"#{container_id} .ag-center-cols-container .ag-row"
        _filter_input: WebElement = _filter_input_in_view(dash_duo, filter_input)
        _filter_input.send_keys("zzz_no_match")  # un "objet" qui n'existe pas
        # Le filtrage est asynchrone (debounce du filtre texte AG Grid) : attendre
        # la mise à jour de la grille plutôt que de lire les lignes immédiatement
        # (sinon on lit l'état pré-filtre).
        dash_duo.wait_for_no_elements(filter_cell_result, timeout=4)


def test_016_search_button_matches_input_height():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages.recherche import layout

    search_input, search_button = layout().children[1].children

    assert search_input.style["height"] == search_button.style["height"], (
        "Le bouton de recherche doit avoir la même hauteur que le champ de "
        "recherche pour ne pas déborder en bas"
    )
