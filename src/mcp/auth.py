import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from src.api import tokens_db
from src.mcp import usage
from src.mcp.oauth import metadata, store
from src.subscriptions.db import has_access
from src.utils import TOUS_ABONNES


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


def _resource_metadata_url() -> str:
    return f"{_base()}/.well-known/oauth-protected-resource/_mcp"


def _unauthorized():
    resp = jsonify({"error": "unauthorized", "message": "Jeton absent ou invalide."})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = (
        f'Bearer realm="colibre-mcp", resource_metadata="{_resource_metadata_url()}"'
    )
    return resp


def _forbidden():
    resp = jsonify(
        {
            "error": "no_active_subscription",
            "message": "Un abonnement colibre actif est requis pour le connecteur IA.",
        }
    )
    resp.status_code = 403
    return resp


def _expired(iso_ts: str) -> bool:
    return datetime.fromisoformat(iso_ts) < datetime.now(timezone.utc)


def _authorize_static(db_path, token):
    row = tokens_db.get_token_by_plaintext(db_path, token)
    if row is None or row["revoked_at"] is not None or row["kind"] != "mcp":
        return None, None
    return row["user_id"], ("static", row["id"])


def _authorize_oauth(db_path, token):
    row = store.get_token_by_access(db_path, token)
    if row is None or row["revoked_at"] is not None:
        return None, None
    if _expired(row["access_expires_at"]):
        return None, None
    if row["resource"] != metadata.mcp_resource(_base()):
        return None, None
    return row["user_id"], ("oauth", row["id"])


def _authenticate_mcp():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return _unauthorized()
    token = header[len("Bearer ") :].strip()
    if not token:
        return _unauthorized()

    db_path = os.environ["USERS_DB_PATH"]
    if token.startswith("colibre_"):
        user_id, meta = _authorize_static(db_path, token)
    else:
        user_id, meta = _authorize_oauth(db_path, token)

    if meta is None:
        return _unauthorized()
    if user_id is None:
        return _forbidden()
    if not (TOUS_ABONNES or has_access(user_id)):
        return _forbidden()

    if request.method == "POST":
        # Les GET ne font qu'ouvrir/rouvrir le flux SSE (immédiatement refermé
        # par dash.mcp) : un client MCP standard les répète en boucle tant que
        # la connexion reste ouverte côté serveur. Ne compter l'usage que sur
        # les vrais appels JSON-RPC (POST) évite de polluer mcp_usage et les
        # compteurs de jeton avec ce bruit de reconnexion.
        kind, token_id = meta
        if kind == "static":
            tokens_db.increment_usage(db_path, token_id)
        else:
            store.increment_usage(db_path, token_id)
        usage.record(db_path, user_id, token_id, kind)
    return None


def init_mcp_auth(server: Flask) -> None:
    """Enregistre le garde d'authentification du serveur MCP (/_mcp)."""

    @server.before_request
    def _guard_mcp():
        if request.path == "/_mcp" or request.path.startswith("/_mcp/"):
            return _authenticate_mcp()
        return None
