"""Persistance de l'ordre des cards de l'observatoire, par utilisateur (#107).

L'ordre est une simple liste de `card_id` sérialisée en JSON dans la table
`observatoire_card_order` (migration 0015). Un seul ordre par utilisateur,
partagé par la page /observatoire et le mode observatoire du Tableau : les
deux affichent exactement les mêmes cards.
"""

import json
from datetime import datetime, timezone

from src.auth.db import get_conn

#: Ordre par défaut des cards fixes, dans l'ordre produit par
#: `build_dashboard_cards`. Les cartes géographiques (`carte-<code>`) sont
#: dynamiques et n'y figurent pas.
DEFAULT_CARD_ORDER = [
    "resume",
    "cat-acheteur",
    "cat-entreprise",
    "type-achat",
    "considerations",
    "distance",
    "top-acheteurs",
    "top-titulaires",
    "sources-donnees",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_card_order(user_id: int) -> list[str] | None:
    """Ordre enregistré par l'utilisateur, ou None s'il n'en a jamais choisi."""
    row = (
        get_conn()
        .execute(
            "SELECT card_order FROM observatoire_card_order WHERE user_id = ?",
            (user_id,),
        )
        .fetchone()
    )
    if row is None:
        return None
    return json.loads(row[0])


def save_card_order(user_id: int, order: list[str]) -> None:
    """Enregistre (ou remplace) l'ordre choisi par l'utilisateur."""
    payload = json.dumps(order)
    now = _now()
    get_conn().execute(
        "INSERT INTO observatoire_card_order (user_id, card_order, updated_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET card_order = ?, updated_at = ?",
        (user_id, payload, now, payload, now),
    )
