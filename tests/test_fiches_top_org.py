"""Les tops des fiches sont paginés côté serveur (#142, suite de #141).

Avant : tout le classement partait au navigateur (jusqu'à ~2 Mo). Désormais
la grille est en modèle infinite et son datasource est scopé à la fiche.
"""

import dash_ag_grid as dag
import pytest


def _trouver_grille(node):
    if isinstance(node, dag.AgGrid):
        return node
    enfants = getattr(node, "children", None)
    if enfants is None:
        return None
    if not isinstance(enfants, (list, tuple)):
        enfants = [enfants]
    for enfant in enfants:
        trouve = _trouver_grille(enfant)
        if trouve is not None:
            return trouve
    return None


@pytest.mark.parametrize(
    "module,fonction,org_type",
    [
        ("acheteur", "get_top_titulaires", "titulaire"),
        ("titulaire", "get_top_acheteurs", "acheteur"),
    ],
)
def test_la_fiche_rend_une_grille_infinite_sans_donnees(module, fonction, org_type):
    import importlib

    from src.app import app  # noqa: F401  (instancie Dash avant les pages)

    page = importlib.import_module(f"src.pages.{module}")
    grille = _trouver_grille(getattr(page, fonction)("/x/123", None))

    assert grille is not None, "aucune grille rendue"
    assert grille.rowModelType == "infinite"
    assert grille.rowData is None  # plus aucun classement embarqué
    assert grille.id["type"] == "top-org-grid"
    assert grille.id["context"] == module
    assert grille.id["org_type"] == org_type


@pytest.mark.parametrize(
    "module,fonction",
    [("acheteur", "get_top_titulaires"), ("titulaire", "get_top_acheteurs")],
)
def test_changer_de_fiche_change_le_scope(module, fonction):
    """L'id doit varier avec la fiche et l'année, sinon React réutilise la
    grille et AG Grid ne redemande pas ses lignes."""
    import importlib

    from src.app import app  # noqa: F401

    page = importlib.import_module(f"src.pages.{module}")
    scopes = {
        _trouver_grille(getattr(page, fonction)(url, annee)).id["scope"]
        for url, annee in [("/x/1", None), ("/x/2", None), ("/x/1", "2025")]
    }
    assert len(scopes) == 3


@pytest.mark.parametrize(
    "module,fonction,scope_attr,org_type",
    [
        ("acheteur", "get_top_titulaires_rows", "_acheteur_scope", "titulaire"),
        ("titulaire", "get_top_acheteurs_rows", "_titulaire_scope", "acheteur"),
    ],
)
def test_le_datasource_est_scope_a_la_fiche(
    monkeypatch, module, fonction, scope_attr, org_type
):
    import importlib

    from src.app import app  # noqa: F401

    page = importlib.import_module(f"src.pages.{module}")
    monkeypatch.setattr(page, scope_attr, lambda *_: ("titulaire_id = ?", ["T1"]))

    recu = {}

    def faux_fetch(org, where_sql, params, request, extra_columns=(), *, operateurs):
        recu.update(
            org=org, where_sql=where_sql, params=params, extra=list(extra_columns)
        )
        return {"rowData": [], "rowCount": 0}

    monkeypatch.setattr(page, "fetch_top_org_page", faux_fetch)
    monkeypatch.setattr(page, "current_user_has_subscription", lambda: False)

    request = {"startRow": 0, "endRow": 10, "filterModel": None, "sortModel": None}
    getattr(page, fonction)(request, "/x/123", None)

    assert recu["org"] == org_type
    assert recu["where_sql"] == "titulaire_id = ?"
    assert recu["params"] == ["T1"]
    assert recu["extra"] == ["titulaire_distance"]
