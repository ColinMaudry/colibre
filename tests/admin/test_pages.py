import uuid

from dash.testing.composite import DashComposite
from dash.testing.wait import until
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from werkzeug.security import generate_password_hash

from src.auth import db as auth_db
from src.subscriptions import db as sub_db

PASSWORD = "s3cretpass!"


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@ex.fr"


def _make_verified_user(email: str) -> int:
    auth_db.init_schema()
    uid = auth_db.create_user(email, generate_password_hash(PASSWORD))
    auth_db.set_email_verified(uid)
    return uid


def _cleanup_user(user_id: int) -> None:
    conn = auth_db.get_conn()
    conn.execute("DELETE FROM admin_actions WHERE target_user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriber_state WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    # tests/users.test.sqlite est committé dans git et partagé pour toute la
    # session Selenium (USERS_DB_PATH fixé globalement dans pyproject.toml).
    # Les DELETE seuls laissent le fichier byte-diffé : sqlite_sequence
    # (compteur AUTOINCREMENT) n'est jamais remis à zéro par un DELETE.
    conn.execute(
        "UPDATE sqlite_sequence SET seq = 0 "
        "WHERE name IN ('users', 'subscriptions', 'admin_actions')"
    )
    # Au-delà du compteur AUTOINCREMENT, SQLite ne remet jamais à zéro les
    # octets laissés par un DELETE dans une page devenue vide (page b-tree
    # de admin_actions/subscriptions) : ils restent tels quels sur le
    # disque, hors de toute zone logiquement lue, mais rendent le fichier
    # byte-diffé malgré un contenu logique identique (vérifié via
    # PRAGMA integrity_check + iterdump). VACUUM reconstruit le fichier
    # à partir des données vivantes uniquement et produit un layout de
    # pages déterministe (vérifié empiriquement : deux runs avec des
    # données aléatoires différentes produisent un fichier strictement
    # identique octet à octet après VACUUM). C'est donc la façon fiable
    # de retrouver l'état canonique committé après avoir touché ces tables.
    conn.execute("VACUUM")


def _row_index_of(dash_duo: DashComposite, email: str):
    """row-index AG Grid de la ligne dont la cellule email vaut `email`."""
    for cell in dash_duo.driver.find_elements(
        "css selector", "#admin-table .ag-cell[col-id='email']"
    ):
        if cell.text == email:
            row = cell.find_element("xpath", "ancestor::div[@row-index][1]")
            return row.get_attribute("row-index")
    return None


def _email_verified(user_id: int):
    return (
        auth_db.get_conn()
        .execute("SELECT email_verified FROM users WHERE id = ?", (user_id,))
        .fetchone()[0]
    )


def _login(dash_duo: DashComposite, email: str):
    dash_duo.driver.get(dash_duo.server_url + "/connexion")
    dash_duo.wait_for_element("input[name=email]", timeout=8).send_keys(email)
    dash_duo.driver.find_element("css selector", "input[name=password]").send_keys(
        PASSWORD
    )
    dash_duo.driver.find_element("css selector", "button[type=submit]").click()
    # Attendre la fin de la redirection post-login. Sans ça, un driver.get()
    # immédiat part en concurrence avec la navigation encore en vol, qui
    # atterrit après et l'écrase : le test se retrouve sur /compte/abonnement
    # au lieu de sa cible. On teste la sortie de /connexion plutôt que la page
    # d'arrivée, qui dépend de TOUS_ABONNES (cf. src/auth/routes.py).
    until(lambda: "/connexion" not in dash_duo.driver.current_url, timeout=8)


def test_admin_anonymous_gets_404(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/admin")
    dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)


def test_admin_non_admin_gets_404(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    monkeypatch.setenv("ADMIN_EMAIL", "admin-only@ex.fr")
    email = _unique_email("regular")
    uid = _make_verified_user(email)
    try:
        dash_duo.start_server(app)
        _login(dash_duo, email)
        # Cet utilisateur n'a pas d'abonnement : une connexion réussie
        # redirige vers /compte/abonnement (voir _post_login_url dans
        # src/auth/routes.py). Ça confirme que le login a bien réussi avant
        # de vérifier /admin (sinon ce test serait indiscernable de
        # test_admin_anonymous_gets_404 en cas de régression du login).
        dash_duo.wait_for_text_to_equal("h2", "Abonnement", timeout=8)
        assert "/connexion" not in dash_duo.driver.current_url

        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)
    finally:
        _cleanup_user(uid)


def test_admin_full_flow(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    admin_email = _unique_email("admin")
    monkeypatch.setenv("ADMIN_EMAIL", admin_email)
    admin_uid = _make_verified_user(admin_email)

    target_email = _unique_email("target")
    target_uid = _make_verified_user(target_email)
    sub_db.init_schema()
    _handle, sub_id = sub_db.create_pending(target_uid, "cust-e2e", "simple", 20.0)
    sub_db.set_status(sub_id, "active")

    try:
        dash_duo.start_server(app)
        _login(dash_duo, admin_email)

        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert target_email in dash_duo.driver.page_source  # table users, par défaut

        # Éditeur select (email_verified) sur la ligne de l'utilisateur cible.
        until(lambda: _row_index_of(dash_duo, target_email) is not None, timeout=8)
        row_index = _row_index_of(dash_duo, target_email)
        verified_cell = dash_duo.driver.find_element(
            "css selector",
            f"#admin-table .ag-row[row-index='{row_index}'] "
            ".ag-cell[col-id='email_verified']",
        )
        assert verified_cell.text == "1"
        verified_cell.click()
        # L'éditeur select s'ouvre replié : un clic déplie la liste.
        dash_duo.wait_for_element(
            "#admin-table .ag-cell-inline-editing .ag-picker-field-wrapper", timeout=8
        ).click()
        dash_duo.wait_for_element(".ag-select-list .ag-list-item", timeout=8)
        option_0 = next(
            item
            for item in dash_duo.driver.find_elements(
                "css selector", ".ag-select-list .ag-list-item"
            )
            if item.text.strip() == "0"
        )
        option_0.click()
        dash_duo.wait_for_text_to_equal(
            "#admin-alerts .alert-success", "Modification enregistrée.", timeout=8
        )
        until(lambda: _email_verified(target_uid) == 0, timeout=8)

        select = Select(dash_duo.wait_for_element("#admin-table-select", timeout=8))
        select.select_by_value("subscriptions")
        prix_selector = "#admin-table .ag-row[row-index='0'] .ag-cell[col-id='prix_ht']"
        dash_duo.wait_for_element(prix_selector, timeout=8)
        # Attendre que l'alerte de l'édition précédente soit effacée par la
        # bascule de table, pour ne pas lire l'ancienne alerte de succès.
        until(
            lambda: not dash_duo.driver.find_elements(
                "css selector", "#admin-alerts .alert-success"
            ),
            timeout=8,
        )

        # Un clic simple entre en édition (singleClickEdit).
        dash_duo.driver.find_element("css selector", prix_selector).click()
        dash_duo.wait_for_element(
            f"{prix_selector}.ag-cell-inline-editing input", timeout=8
        )
        active_input = dash_duo.driver.switch_to.active_element
        active_input.send_keys(Keys.CONTROL, "a")
        active_input.send_keys("30")
        active_input.send_keys(Keys.TAB)

        dash_duo.wait_for_text_to_equal(
            "#admin-alerts .alert-success", "Modification enregistrée.", timeout=8
        )

        row = sub_db.get_current(target_uid)
        assert row["prix_ht"] == 30.0

        select = Select(
            dash_duo.driver.find_element("css selector", "#admin-table-select")
        )
        select.select_by_value("admin_actions")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert "edit_subscriptions" in dash_duo.driver.page_source
        assert "prix_ht" in dash_duo.driver.page_source
    finally:
        _cleanup_user(target_uid)
        _cleanup_user(admin_uid)
