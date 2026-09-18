"""Tests d'intégration du drag & drop des cards de l'observatoire (issue #107)."""


def test_observatoire_card_order_dans_les_tables_admin():
    """La table observatoire_card_order est auto-découverte par l'admin."""
    from src.admin.tables import all_tables
    from src.migrations import apply_pending

    apply_pending()

    assert "observatoire_card_order" in all_tables()


def test_anonyme_pas_de_marqueur_ni_de_draggable(dash_duo):
    """Sans abonnement : pas de marqueur, donc aucune card n'est déplaçable.

    C'est tout le gating : `cards_drag_marker` n'est rendu que pour les
    abonné·es, et observatoire-dragdrop.js ne pose `draggable` que sur le
    parent d'un marqueur.
    """
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/observatoire")

    dash_duo.wait_for_element(".observatoire-card", timeout=20)

    assert (
        dash_duo.driver.find_elements("css selector", "[data-observatoire-cards]") == []
    ), "le marqueur de drag ne doit pas être rendu pour un anonyme"

    cards = dash_duo.driver.find_elements("css selector", ".observatoire-card")
    assert cards, "les cards doivent être rendues même sans abonnement"
    for card in cards:
        assert card.get_attribute("draggable") in (None, "false")

    assert dash_duo.get_logs() == []


def test_cards_portent_leur_card_id_en_classe(dash_duo):
    """Chaque card rendue porte `observatoire-card--<card_id>`."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/observatoire")

    dash_duo.wait_for_element(".observatoire-card--resume", timeout=20)

    classes = [
        c.get_attribute("class")
        for c in dash_duo.driver.find_elements("css selector", ".observatoire-card")
    ]
    assert any("observatoire-card--top-acheteurs" in c for c in classes)
    assert any("observatoire-card--sources-donnees" in c for c in classes)
