import os

from flask import Blueprint, redirect, request, session
from flask_login import current_user

from src.api import tokens_db

ia_account_bp = Blueprint("ia_account", __name__)

_LABEL_MAX = 100


def _has_active_subscription() -> bool:
    # Réutilise la vérification canonique (gère TOUS_ABONNES).
    from src.pages._compte_shell import current_user_has_subscription

    return current_user_has_subscription()


def _guard():
    """Renvoie une redirection si l'accès est refusé, sinon None."""
    if not current_user.is_authenticated:
        return redirect("/connexion?next=/compte/ia")
    if not _has_active_subscription():
        return redirect("/compte/abonnement")
    return None


@ia_account_bp.route("/compte/ia/creer", methods=["POST"])
def creer():
    denied = _guard()
    if denied is not None:
        return denied
    label = (request.form.get("label") or "").strip()[:_LABEL_MAX] or "Sans nom"
    token, _ = tokens_db.create_token(
        os.environ["USERS_DB_PATH"], label, user_id=current_user.id, kind="mcp"
    )
    session["mcp_new_token"] = token
    return redirect("/compte/ia")


@ia_account_bp.route("/compte/ia/revoquer/<int:token_id>", methods=["POST"])
def revoquer(token_id):
    denied = _guard()
    if denied is not None:
        return denied
    tokens_db.revoke_user_token(os.environ["USERS_DB_PATH"], token_id, current_user.id)
    return redirect("/compte/ia")
