"""Tests de la préférence de thème clair / sombre par utilisateur (#118)."""

import pytest


@pytest.fixture(autouse=True)
def _table_creee():
    """La table vient de la migration 0016 ; on s'assure qu'elle existe."""
    from src.migrations import apply_pending

    apply_pending()


def _fake_user(authenticated: bool, user_id: int = 1):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = user_id
    return user


def test_get_theme_returns_clair_for_new_user():
    from src.theme import CLAIR, get_theme

    assert get_theme(999) == CLAIR


def test_save_and_get_theme():
    from src.theme import SOMBRE, get_theme, save_theme

    save_theme(42, SOMBRE)

    assert get_theme(42) == SOMBRE


def test_save_theme_upserts():
    import src.auth.db as auth_db
    from src.theme import CLAIR, SOMBRE, get_theme, save_theme

    save_theme(1, SOMBRE)
    save_theme(1, CLAIR)

    assert get_theme(1) == CLAIR
    count = (
        auth_db.get_conn()
        .execute("SELECT COUNT(*) FROM user_preferences WHERE user_id = ?", (1,))
        .fetchone()[0]
    )
    assert count == 1


def test_save_theme_invalide_leve_et_n_ecrit_rien():
    from src.theme import SOMBRE, get_theme, save_theme

    save_theme(2, SOMBRE)

    with pytest.raises(ValueError):
        save_theme(2, "bleu")

    # L'écriture invalide n'a rien changé : la valeur précédente est toujours là.
    assert get_theme(2) == SOMBRE


def test_current_theme_hors_contexte_flask_est_clair():
    from src.theme import CLAIR, current_theme

    assert current_theme() == CLAIR


def test_current_theme_visiteur_non_connecte_est_clair(monkeypatch):
    import src.theme as theme
    from src.app import app

    monkeypatch.setattr(theme, "current_user", _fake_user(False))

    with app.server.test_request_context("/"):
        assert theme.current_theme() == theme.CLAIR


def test_current_theme_connecte_sombre_non_abonne_est_clair(monkeypatch):
    import src.theme as theme
    from src.app import app
    from src.pages import _compte_shell as shell

    theme.save_theme(10, theme.SOMBRE)
    monkeypatch.setattr(theme, "current_user", _fake_user(True, 10))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: False)

    with app.server.test_request_context("/"):
        assert theme.current_theme() == theme.CLAIR


def test_current_theme_connecte_sombre_abonne_est_sombre(monkeypatch):
    """Cas positif qui ancre les négatifs : sans lui, une fonction qui renvoie
    toujours CLAIR passerait aussi les autres tests de current_theme()."""
    import src.theme as theme
    from src.app import app
    from src.pages import _compte_shell as shell

    theme.save_theme(11, theme.SOMBRE)
    monkeypatch.setattr(theme, "current_user", _fake_user(True, 11))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)

    with app.server.test_request_context("/"):
        assert theme.current_theme() == theme.SOMBRE


def test_current_theme_connecte_abonne_sans_preference_est_clair(monkeypatch):
    import src.theme as theme
    from src.app import app
    from src.pages import _compte_shell as shell

    monkeypatch.setattr(theme, "current_user", _fake_user(True, 12))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)

    with app.server.test_request_context("/"):
        assert theme.current_theme() == theme.CLAIR
