"""Menu déroulant « Mon compte » de la navbar globale (issue #133).

Cliquer sur « Mon compte » ouvre la liste des sections plutôt que de changer de
page : les sections de l'espace abonné deviennent atteignables en un clic depuis
n'importe où.

Le menu et la barre latérale de l'espace compte partagent la même source de
vérité (`visible_sections`), donc les mêmes entrées, filtrées par l'accès.
"""

import dash_bootstrap_components as dbc
import pytest
from dash import html
from dash.exceptions import PreventUpdate

import src.app as app_module
from src.pages import _compte_shell as shell
from src.theme import CLAIR, SOMBRE


def _fake_user(authenticated: bool, user_id: int = 1):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = user_id
    return user


def _menu(monkeypatch, *, has_subscription: bool, theme: str = CLAIR):
    monkeypatch.setattr(app_module, "current_user", _fake_user(True))
    monkeypatch.setattr(
        shell, "current_user_has_subscription", lambda: has_subscription
    )
    monkeypatch.setattr(app_module, "get_theme", lambda user_id: theme)
    return app_module._auth_nav(None)


def _find_switch(menu):
    """Cherche le `dbc.Switch` id="theme-switch" dans les enfants du menu.

    Renvoie (index dans menu.children, composant) ou (None, None). On
    parcourt la structure des composants plutôt que `str(menu)`, pour
    pouvoir vérifier la valeur `value` du switch.
    """
    for i, child in enumerate(menu.children):
        if isinstance(child, html.Div):
            for sub in child.children:
                if isinstance(sub, dbc.Switch) and getattr(sub, "id", None) == (
                    "theme-switch"
                ):
                    return i, sub
    return None, None


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


def test_switch_theme_present_et_sombre_pour_un_abonne_en_mode_sombre(monkeypatch):
    """Le switch reflète le thème enregistré : SOMBRE -> value=True (#118)."""
    menu = _menu(monkeypatch, has_subscription=True, theme=SOMBRE)
    idx, switch = _find_switch(menu)
    assert switch is not None
    assert switch.value is True


def test_switch_theme_present_et_clair_pour_un_abonne_en_mode_clair(monkeypatch):
    """Le switch reflète le thème enregistré : CLAIR -> value=False (#118)."""
    menu = _menu(monkeypatch, has_subscription=True, theme=CLAIR)
    idx, switch = _find_switch(menu)
    assert switch is not None
    assert switch.value is False


def test_switch_theme_absent_pour_un_non_abonne(monkeypatch):
    """Réservé aux abonné·es : masqué plutôt que grisé (#118, comme #133)."""
    menu = _menu(monkeypatch, has_subscription=False)
    rendu = str(menu)
    # Assertion positive : le menu s'est bien rendu (déconnexion présente),
    # ce n'est pas un rendu vide qui expliquerait l'absence du switch.
    assert "Déconnexion" in rendu
    idx, switch = _find_switch(menu)
    assert switch is None
    assert "theme-switch" not in rendu


def test_switch_theme_place_avant_le_separateur(monkeypatch):
    menu = _menu(monkeypatch, has_subscription=True, theme=SOMBRE)
    idx_switch, switch = _find_switch(menu)
    assert switch is not None
    idx_divider = next(
        i
        for i, child in enumerate(menu.children)
        if isinstance(child, dbc.DropdownMenuItem) and getattr(child, "divider", False)
    )
    assert idx_switch < idx_divider


def test_enregistrer_theme_sombre_pour_un_abonne(monkeypatch):
    """Cas positif (ancre) : la valeur reçue diffère du thème enregistré, donc
    le nouveau garde-fou de #118 ne doit pas empêcher la sauvegarde."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(True, user_id=42))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)
    monkeypatch.setattr(app_module, "get_theme", lambda user_id: CLAIR)
    appels = []
    monkeypatch.setattr(
        app_module,
        "save_theme",
        lambda user_id, theme: appels.append((user_id, theme)),
    )
    resultat = app_module._enregistrer_theme(True)
    assert appels == [(42, SOMBRE)]
    assert resultat == SOMBRE


def test_enregistrer_theme_clair_pour_un_abonne(monkeypatch):
    """Cas positif (ancre) : la valeur reçue diffère du thème enregistré, donc
    le nouveau garde-fou de #118 ne doit pas empêcher la sauvegarde."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(True, user_id=42))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)
    monkeypatch.setattr(app_module, "get_theme", lambda user_id: SOMBRE)
    appels = []
    monkeypatch.setattr(
        app_module,
        "save_theme",
        lambda user_id, theme: appels.append((user_id, theme)),
    )
    resultat = app_module._enregistrer_theme(False)
    assert appels == [(42, CLAIR)]
    assert resultat == CLAIR


def test_enregistrer_theme_non_abonne_ne_sauvegarde_pas_et_previent(monkeypatch):
    """Le switch n'est affiché qu'aux abonné·es, mais le droit est revérifié
    ici : un callback déclenché à la main pour un non-abonné ne doit ni
    sauvegarder ni recharger la page."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(True, user_id=42))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: False)
    appels = []
    monkeypatch.setattr(
        app_module,
        "save_theme",
        lambda user_id, theme: appels.append((user_id, theme)),
    )
    with pytest.raises(PreventUpdate):
        app_module._enregistrer_theme(True)
    assert appels == []


def test_enregistrer_theme_valeur_inchangee_previent_sans_sauvegarder(monkeypatch):
    """Bug #118 : `_auth_nav` remonte `dbc.Switch(value=get_theme(...))` à
    chaque re-rendu du menu (changement de page), et Dash déclenche le
    callback lié à un composant nouvellement inséré même sans clic, malgré
    `prevent_initial_call=True` (celui-ci ne couvre que le tout premier
    chargement de l'app, pas la (re)monte ultérieure d'un composant). Sans
    garde-fou, chaque changement de page réécrit la même valeur en base et
    déclenche le rechargement côté client (boucle infinie).

    Ici la valeur reçue égale le thème déjà enregistré : rien à sauvegarder,
    donc `PreventUpdate` doit être levée avant tout appel à `save_theme`."""
    monkeypatch.setattr(app_module, "current_user", _fake_user(True, user_id=42))
    monkeypatch.setattr(shell, "current_user_has_subscription", lambda: True)
    monkeypatch.setattr(app_module, "get_theme", lambda user_id: SOMBRE)
    appels = []
    monkeypatch.setattr(
        app_module,
        "save_theme",
        lambda user_id, theme: appels.append((user_id, theme)),
    )
    with pytest.raises(PreventUpdate):
        app_module._enregistrer_theme(True)
    assert appels == []
