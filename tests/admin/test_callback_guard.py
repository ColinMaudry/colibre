"""Régression issue #110 : le callback admin est un endpoint serveur global
(/_dash-update-component), invocable indépendamment du layout. Il DOIT revérifier
is_admin() lui-même, sinon un non-admin (voire un anonyme) lit/écrit toute la base.

Ces tests appellent le callback directement (sans navigateur) : la garde s'exécute
avant tout accès au `ctx`/à la base, donc un non-admin ne doit rien pouvoir faire.
"""

import pytest
from dash.exceptions import PreventUpdate

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.pages.admin import liste


def test_update_table_read_path_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(liste, "is_admin", lambda: False)
    # Chemin lecture (sélection d'une table) : ne doit RIEN renvoyer.
    with pytest.raises(PreventUpdate):
        liste._update_table("users", [])


def test_update_table_write_path_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(liste, "is_admin", lambda: False)
    # Chemin écriture (édition de cellule simulée, format cellValueChanged AG Grid 35).
    cell_changes = [
        {
            "rowIndex": 0,
            "rowId": "1",
            "colId": "email",
            "oldValue": "victime@b.fr",
            "value": "a@b.fr",
            "data": {"id": 1, "email": "a@b.fr"},
        }
    ]
    with pytest.raises(PreventUpdate):
        liste._update_table("users", cell_changes)


def test_update_table_allows_admin(monkeypatch):
    # Avec is_admin() vrai, la garde ne bloque pas : sans cellValueChanged exploitable,
    # le callback renvoie 3 valeurs (pas de PreventUpdate).
    monkeypatch.setattr(liste, "is_admin", lambda: True)

    class _Ctx:
        triggered_id = "autre-composant"

    monkeypatch.setattr(liste, "ctx", _Ctx)
    result = liste._update_table("users", None)
    assert len(result) == 3
