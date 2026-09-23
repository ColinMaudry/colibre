"""Les grilles top reçoivent réellement leurs lignes du datasource (#142).

Les tests unitaires vérifient la requête et la grille séparément ; seul un
test de bout en bout montre que le callback pattern-matching est bien
dispatché. Il tourne en debug=True (dev-renderer), qui valide la cohérence
des wildcards MATCH — la même erreur avait fait échouer la grille entité (#41).
"""

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.db import query_marches


def _an_acheteur_id():
    return query_marches("TRUE", (), columns=["acheteur_id"])["acheteur_id"][0]


def test_top_titulaires_de_la_fiche_affiche_des_lignes(dash_duo):
    from src.app import app

    ach = _an_acheteur_id()

    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + f"/acheteurs/{ach}")

    dash_duo.wait_for_element(
        "#top10_titulaires .ag-center-cols-container .ag-row", timeout=15
    )

    match_errors = [
        entry
        for entry in (dash_duo.get_logs() or [])
        if "MATCH" in str(entry.get("message", ""))
    ]
    assert not match_errors, f"Erreur dev-renderer MATCH : {match_errors}"


def test_top_acheteurs_de_l_observatoire_affiche_des_lignes(dash_duo):
    from src.app import app

    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + "/observatoire")

    dash_duo.wait_for_element("#cards .ag-center-cols-container .ag-row", timeout=20)
