import pytest
from flask import Flask


@pytest.fixture
def oauth_app(monkeypatch, tmp_path):
    from src.mcp.oauth import routes, store

    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "u.sqlite"))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    store.init_schema(tmp_path / "u.sqlite")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    routes.init_oauth(app)
    return app


def test_protected_resource_wellknown(oauth_app):
    resp = oauth_app.test_client().get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"


def test_protected_resource_wellknown_mcp_suffix(oauth_app):
    resp = oauth_app.test_client().get("/.well-known/oauth-protected-resource/_mcp")
    assert resp.status_code == 200
    assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"


def test_as_metadata_and_openid(oauth_app):
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ):
        resp = oauth_app.test_client().get(path)
        assert resp.status_code == 200
        assert resp.get_json()["code_challenge_methods_supported"] == ["S256"]


def test_dynamic_client_registration(oauth_app):
    resp = oauth_app.test_client().post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
            "token_endpoint_auth_method": "none",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert "client_id" in body
    # Client public (auth "none") : aucun secret ne doit être émis, sinon les
    # clients qui le renvoient à /oauth/token (oh-my-pi) sont rejetés en
    # invalid_client par l'authentification "none".
    assert "client_secret" not in body
    assert "client_secret_expires_at" not in body
