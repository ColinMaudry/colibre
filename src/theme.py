"""Préférence de thème clair / sombre, par utilisateur (#118).

Les lignes de `user_preferences` (migration 0016) sont créées paresseusement,
au premier usage du switch ; l'absence de ligne vaut « clair ». Le mode sombre
est réservé aux abonné·es : le droit est vérifié à la lecture, dans
`current_theme()`, si bien qu'à la fin d'un abonnement l'affichage repasse en
clair tout en conservant la préférence pour un éventuel réabonnement.
"""

from datetime import datetime, timezone

from flask import has_request_context
from flask_login import current_user

from src.auth.db import get_conn

CLAIR = "clair"
SOMBRE = "sombre"
THEMES = (CLAIR, SOMBRE)


def get_theme(user_id: int) -> str:
    """Thème enregistré par l'utilisateur, CLAIR s'il n'en a jamais choisi."""
    row = (
        get_conn()
        .execute("SELECT theme FROM user_preferences WHERE user_id = ?", (user_id,))
        .fetchone()
    )
    return row[0] if row else CLAIR


def save_theme(user_id: int, theme: str) -> None:
    """Enregistre (ou remplace) le thème choisi par l'utilisateur."""
    if theme not in THEMES:
        raise ValueError(f"Thème inconnu : {theme!r}")
    now = datetime.now(timezone.utc).isoformat()
    get_conn().execute(
        "INSERT INTO user_preferences (user_id, theme, updated_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET theme = ?, updated_at = ?",
        (user_id, theme, now, theme, now),
    )


def current_theme() -> str:
    """Thème à appliquer à la requête en cours.

    SOMBRE seulement pour un·e abonné·e connecté·e qui l'a choisi. Hors
    requête (tests, import de module) : CLAIR.
    """
    if not has_request_context() or not current_user.is_authenticated:
        return CLAIR
    # Import local : les pages sont découvertes après le chargement de src.app.
    from src.pages._compte_shell import current_user_has_subscription

    if not current_user_has_subscription():
        return CLAIR
    return get_theme(current_user.id)
