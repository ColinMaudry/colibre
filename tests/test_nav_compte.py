"""Menu déroulant « Mon compte » de la navbar globale (issue #133).

Cliquer sur « Mon compte » ouvre la liste des sections plutôt que de changer de
page : les sections de l'espace abonné deviennent atteignables en un clic depuis
n'importe où.

Le menu et la barre latérale de l'espace compte partagent la même source de
vérité (`visible_sections`), donc les mêmes entrées, filtrées par l'accès.
"""

import dash_bootstrap_components as dbc

import src.app as app_module
from src.pages import _compte_shell as shell


def _fake_user(authenticated: bool):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    return user


def _menu(monkeypatch, *, has_subscription: bool):
    monkeypatch.setattr(app_module, "current_user", _fake_user(True))
    monkeypatch.setattr(
        shell, "current_user_has_subscription", lambda: has_subscription
    )
    return app_module._auth_nav(None)


def test_mon_compte_ouvre_un_menu_au_lieu_de_naviguer(monkeypatch):
    """Le cœur de l'issue : le libellé déclenche un menu, il ne navigue plus."""
    menu = _menu(monkeypatch, has_subscription=True)
    assert isinstance(menu, dbc.DropdownMenu)
    assert menu.label == "Espace abonné"


def test_menu_liste_toutes_les_sections_pour_un_abonne(monkeypatch):
    rendu = str(_menu(monkeypatch, has_subscription=True))
    for href in (
        "/compte/vues",
        "/compte/roadmap",
        "/compte/mcp",
        "/compte/abonnement",
        "/compte/admin",
    ):
        assert href in rendu


def test_menu_masque_les_sections_reservees_sans_acces(monkeypatch):
    """Mêmes entrées que la barre latérale : pas de section grisée."""
    rendu = str(_menu(monkeypatch, has_subscription=False))
    assert "/compte/abonnement" in rendu
    assert "/compte/admin" in rendu
    for href in ("/compte/vues", "/compte/roadmap", "/compte/mcp"):
        assert href not in rendu


def test_menu_contient_la_deconnexion(monkeypatch):
    rendu = str(_menu(monkeypatch, has_subscription=True))
    assert "Déconnexion" in rendu
    assert "/auth/logout" in rendu


def test_index_csrf_du_menu_distinct_de_celui_de_la_barre_laterale(monkeypatch):
    """Deux formulaires de déconnexion coexistent dans l'espace compte.

    Le remplissage se fait par motif (`{"type": "csrf-input", "index": ALL}`,
    src/app.py) : deux champs partageant un index se marcheraient dessus.
    """
    rendu = str(_menu(monkeypatch, has_subscription=True))
    assert "navbar-logout" in rendu
    assert "sidebar-logout" not in rendu


def test_visiteur_anonyme_garde_le_lien_connexion(monkeypatch):
    monkeypatch.setattr(app_module, "current_user", _fake_user(False))
    rendu = str(app_module._auth_nav(None))
    assert "Espace" in rendu
    assert "abonné" in rendu
    assert "/connexion" in rendu
    assert "Mon compte" not in rendu


def test_lien_connexion_porte_la_page_courante_en_next(monkeypatch):
    """Cliquer sur « Connexion » depuis /tableau doit ramener l'utilisateur
    sur /tableau après connexion, pas sur la page par défaut."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(False))
    rendu = str(app_module._auth_nav(None, "/tableau"))
    assert "/connexion?next=/tableau" in rendu


def test_lien_connexion_omet_next_depuis_une_page_d_authentification(monkeypatch):
    """Revenir sur /inscription après connexion n'aurait aucun sens."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(False))
    rendu = str(app_module._auth_nav(None, "/inscription"))
    assert "next=" not in rendu


def test_barre_laterale_garde_son_propre_bouton_de_deconnexion(monkeypatch):
    """Non-régression : l'espace compte n'a rien perdu au passage."""
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)
    rendu = str(shell._nav("abonnement"))
    assert "Déconnexion" in rendu
    assert "sidebar-logout" in rendu
