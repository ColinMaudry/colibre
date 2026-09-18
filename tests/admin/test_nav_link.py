"""Lien « Administration » de la navbar globale.

Il occupe son propre créneau (`admin-nav-slot`) plutôt que de partager celui de
l'authentification : les `dbc.NavItem` rendent des `<li>`, et deux `<li>` dans
le même `<div>` s'empileraient verticalement. Deux `<div>` frères, eux, sont
deux éléments flex côte à côte dans `navbar-nav`.

Le lien n'est qu'un raccourci : la page `/admin` revérifie `is_admin()` de son
côté (cf. test_callback_guard.py). Le masquer n'est donc pas la protection,
seulement l'ergonomie.
"""

import src.app as app_module


def test_lien_admin_absent_pour_non_admin(monkeypatch):
    monkeypatch.setattr(app_module, "is_admin", lambda: False)
    assert app_module._admin_nav(None) is None


def test_lien_admin_present_pour_admin(monkeypatch):
    monkeypatch.setattr(app_module, "is_admin", lambda: True)
    item = app_module._admin_nav(None)
    assert item is not None
    rendu = str(item)
    assert "Administration" in rendu
    assert "/admin" in rendu


def test_creneau_admin_est_apres_celui_de_connexion():
    """« à droite de Connexion/★★★ » : la navbar étant en flex, l'ordre des
    créneaux dans le layout est l'ordre affiché."""
    rendu = str(app_module.navbar)
    assert rendu.index("auth-nav-slot") < rendu.index("admin-nav-slot")
