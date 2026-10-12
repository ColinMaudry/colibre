from urllib.parse import urlparse

from markupsafe import escape

from src.subscriptions.db import has_access
from src.utils import TOUS_ABONNES


def subscription_ok(user_id: int) -> bool:
    return bool(TOUS_ABONNES or has_access(user_id))


def render_subscription_required() -> str:
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        "<title>Abonnement requis — colibre</title></head><body>"
        "<h1>Abonnement requis</h1>"
        "<p>Le connecteur IA colibre nécessite un abonnement actif.</p>"
        '<p><a href="/compte/abonnement">Gérer mon abonnement</a></p>'
        "</body></html>"
    )


def render_consent(
    client_name: str, redirect_uri: str, scope: str, csrf_token: str = ""
) -> str:
    host = urlparse(redirect_uri).netloc or redirect_uri
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        "<title>Autoriser l'accès — colibre</title></head><body>"
        f"<h1>Autoriser {escape(client_name)} ?</h1>"
        f"<p><strong>{escape(client_name)}</strong> demande à lire les données "
        "colibre en votre nom via le connecteur IA.</p>"
        f"<p>Vous serez redirigé vers <strong>{escape(host)}</strong>.</p>"
        '<form method="post">'
        f'<input type="hidden" name="csrf_token" value="{escape(csrf_token)}">'
        '<button name="confirm" value="yes" type="submit">Autoriser</button> '
        '<button name="confirm" value="no" type="submit">Refuser</button>'
        "</form></body></html>"
    )
