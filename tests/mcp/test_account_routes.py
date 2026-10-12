import pytest
from flask import Flask


@pytest.fixture
def account_client(monkeypatch, tmp_path):
    from src.api import tokens_db
    from src.auth import db as auth_db
    from src.auth.setup import init_auth
    from src.mcp.account import ia_account_bp
    from src.subscriptions import db as sub_db

    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    auth_db.reset_conn_for_tests()

    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    init_auth(app)  # login manager + CSRF (désactivé) + schéma auth
    sub_db.init_schema()
    db_path = tmp_path / "users.test.sqlite"
    tokens_db.init_schema(db_path)
    app.register_blueprint(ia_account_bp)

    yield app, db_path
    auth_db.reset_conn_for_tests()


def _login(app, uid):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client


def _subscribed_uid():
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    uid = auth_db.create_user("sub@ex.fr", "hash")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    return uid


def test_creer_generates_mcp_token_for_subscriber(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)

    resp = client.post("/compte/ia/creer", data={"label": "Claude portable"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/ia")

    with client.session_transaction() as sess:
        assert sess.get("mcp_new_token", "").startswith("colibre_")

    rows = tokens_db.list_user_tokens(db_path, uid, "mcp")
    assert [r["label"] for r in rows] == ["Claude portable"]
    assert rows[0]["kind"] == "mcp"
    assert rows[0]["user_id"] == uid


def test_revoquer_own_token(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)
    token, tid = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")

    resp = client.post(f"/compte/ia/revoquer/{tid}")
    assert resp.status_code == 302
    assert tokens_db.get_token_by_plaintext(db_path, token)["revoked_at"] is not None


def test_revoquer_other_users_token_is_noop(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)
    other_token, other_id = tokens_db.create_token(
        db_path, "y", user_id=99999, kind="mcp"
    )

    resp = client.post(f"/compte/ia/revoquer/{other_id}")
    assert resp.status_code == 302
    assert tokens_db.get_token_by_plaintext(db_path, other_token)["revoked_at"] is None


def test_creer_blocked_without_subscription(account_client):
    from src.api import tokens_db
    from src.auth import db as auth_db

    app, db_path = account_client
    uid = auth_db.create_user("nosub@ex.fr", "hash")  # pas d'abonnement
    client = _login(app, uid)

    resp = client.post("/compte/ia/creer", data={"label": "x"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/abonnement")
    assert tokens_db.list_user_tokens(db_path, uid, "mcp") == []


def test_creer_blocked_when_anonymous(account_client):
    app, db_path = account_client
    resp = app.test_client().post("/compte/ia/creer", data={"label": "x"})
    assert resp.status_code == 302
    assert "/connexion" in resp.headers["Location"]
