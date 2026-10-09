import os
import time
from datetime import datetime, timezone

from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7591 import ClientRegistrationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge

from src.mcp.oauth import metadata, store
from src.utils import DEVELOPMENT

ACCESS_TTL = 3600  # 1 h
REFRESH_TTL = 5184000  # 60 j

if DEVELOPMENT:
    # authlib refuse tout URI non-https (InsecureTransportError), y compris
    # http://colibre.fr utilisé par le client de test Flask (pas de TLS local).
    # Comportement identique à SESSION_COOKIE_SECURE = not DEVELOPMENT dans
    # src/auth/setup.py : ne s'applique jamais en production (DEVELOPMENT=false).
    os.environ.setdefault("AUTHLIB_INSECURE_TRANSPORT", "1")


def _db() -> str:
    return os.environ["USERS_DB_PATH"]


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _expired(iso_ts: str) -> bool:
    return datetime.fromisoformat(iso_ts) < datetime.now(timezone.utc)


class _Client:
    def __init__(self, row: dict):
        self.client_id = row["client_id"]
        self.client_metadata = row["client_metadata"]

    def get_client_id(self):
        return self.client_id

    def get_default_redirect_uri(self):
        uris = self.client_metadata.get("redirect_uris") or []
        return uris[0] if uris else None

    def get_allowed_scope(self, scope):
        if not scope:
            return ""
        allowed = set((self.client_metadata.get("scope") or "").split())
        return " ".join(s for s in scope.split() if s in allowed)

    def check_redirect_uri(self, redirect_uri):
        return redirect_uri in (self.client_metadata.get("redirect_uris") or [])

    def check_client_secret(self, client_secret):
        return False  # client public

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type == "code"

    def check_grant_type(self, grant_type):
        return grant_type in ("authorization_code", "refresh_token")


def query_client(client_id):
    row = store.get_client(_db(), client_id)
    return _Client(row) if row else None


def save_token(token, request):
    resource = (
        request.form.get("resource")
        or request.args.get("resource")
        or metadata.mcp_resource(_base())
    )
    now = time.time()
    store.save_token(
        _db(),
        access_token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        client_id=request.client.get_client_id(),
        user_id=int(request.user),
        scope=token.get("scope", ""),
        resource=resource,
        access_expires_at=_iso(now + token.get("expires_in", ACCESS_TTL)),
        refresh_expires_at=_iso(now + REFRESH_TTL),
    )


class _AuthCode:
    def __init__(self, row: dict):
        self._row = row
        self._raw_code = None
        self.user_id = row["user_id"]
        self.code_challenge = row["code_challenge"]
        self.code_challenge_method = row["code_challenge_method"]

    def get_redirect_uri(self):
        return self._row["redirect_uri"]

    def get_scope(self):
        return self._row["scope"] or ""


class _Token(dict):
    """Wraps an ``oauth_tokens`` row (a plain dict from ``store``) so it also
    satisfies authlib's TokenMixin-ish protocol (``check_client``/
    ``get_scope``) needed by RefreshTokenGrant/RevocationEndpoint, while
    still supporting the dict-style ``row["..."]`` access used elsewhere in
    this module (e.g. ``credential["user_id"]``, ``token["id"]``).
    """

    def check_client(self, client):
        return self["client_id"] == client.get_client_id()

    def get_scope(self):
        return self["scope"] or ""


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code, request):
        store.save_code(
            _db(),
            code,
            client_id=request.client.get_client_id(),
            user_id=int(request.user),
            redirect_uri=request.payload.redirect_uri,
            code_challenge=request.payload.data.get("code_challenge"),
            code_challenge_method=request.payload.data.get("code_challenge_method"),
            scope=request.scope,
            resource=request.payload.data.get("resource")
            or metadata.mcp_resource(_base()),
            expires_at=_iso(time.time() + 300),
        )

    def query_authorization_code(self, code, client):
        row = store.get_code(_db(), code)
        if (
            row
            and row["client_id"] == client.get_client_id()
            and not _expired(row["expires_at"])
        ):
            obj = _AuthCode(row)
            obj._raw_code = code
            return obj
        return None

    def delete_authorization_code(self, authorization_code):
        # code_challenge est unique par code ; on supprime par le hash côté store
        # via le code d'origine reconstruit impossible → on stocke le code clair
        # dans l'objet. Ici authorization_code provient de query ; on supprime par
        # la ligne complète.
        store.delete_code(_db(), authorization_code._raw_code)

    def authenticate_user(self, authorization_code):
        return authorization_code.user_id


class RefreshTokenGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True  # rotation

    def authenticate_refresh_token(self, refresh_token):
        from src.mcp.oauth.consent import subscription_ok

        row = store.get_token_by_refresh(_db(), refresh_token)
        if not row or row["revoked_at"] is not None:
            return None
        if row["refresh_expires_at"] and _expired(row["refresh_expires_at"]):
            return None
        # Re-vérifie l'abonnement au refresh ici (pas dans authenticate_user) :
        # authlib traite un authenticate_refresh_token → None comme
        # InvalidGrantError (invalid_grant), alors qu'un authenticate_user →
        # None y devient InvalidRequestError (invalid_request). Claude exige
        # invalid_grant pour redéclencher le flux OAuth quand l'abonnement
        # est perdu.
        if not subscription_ok(row["user_id"]):
            return None
        return _Token(row)

    def authenticate_user(self, credential):
        return credential["user_id"]

    def revoke_old_credential(self, credential):
        store.revoke_token(_db(), credential["id"])


class _RegistrationEndpoint(ClientRegistrationEndpoint):
    def authenticate_token(self, request):
        # DCR ouverte (client public) : pas de jeton d'enregistrement requis.
        return True

    def resolve_public_key(self, request):
        return None

    def generate_client_info(self, request):
        # authlib génère toujours un client_secret, même pour un client public.
        # Nos clients s'authentifient en "none" au token endpoint ; or un client
        # qui renvoie ce secret (oh-my-pi le fait dès qu'il le reçoit) est
        # rejeté par authenticate_none → invalid_client. RFC 7591 §3.2.1 : le
        # secret est OPTIONNEL, on ne l'émet donc pas.
        info = super().generate_client_info(request)
        info.pop("client_secret", None)
        info.pop("client_secret_expires_at", None)
        return info

    def get_server_metadata(self):
        return metadata.authorization_server_metadata(_base())

    def save_client(self, client_info, client_metadata, request):
        client_id = client_info["client_id"]
        store.create_client(_db(), client_id, dict(client_metadata))
        return _Client(
            {"client_id": client_id, "client_metadata": dict(client_metadata)}
        )


class _RevocationEndpoint(RevocationEndpoint):
    # Clients publics (DCR, pas de secret) : authentification "none", comme
    # pour les grants authorization_code/refresh_token ci-dessus.
    CLIENT_AUTH_METHODS = ["none"]

    def query_token(self, token_string, token_type_hint):
        row = store.get_token_by_access(
            _db(), token_string
        ) or store.get_token_by_refresh(_db(), token_string)
        return _Token(row) if row else None

    def revoke_token(self, token, request):
        store.revoke_token(_db(), token["id"])


def create_authorization_server(app) -> AuthorizationServer:
    # authlib n'émet un refresh_token que si ce flag est activé (défaut: False) ;
    # requis puisque RefreshTokenGrant est enregistré ci-dessous et que le scope
    # "offline_access" (DCR) suppose l'émission d'un refresh_token.
    app.config.setdefault("OAUTH2_REFRESH_TOKEN_GENERATOR", True)
    server = AuthorizationServer(app, query_client=query_client, save_token=save_token)
    server.register_grant(AuthorizationCodeGrant, [CodeChallenge(required=True)])
    server.register_grant(RefreshTokenGrant)
    server.register_endpoint(_RegistrationEndpoint)
    server.register_endpoint(_RevocationEndpoint)
    return server
