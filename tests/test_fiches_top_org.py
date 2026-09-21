"""Les « Top titulaires »/« Top acheteurs » des fiches ne sont pas tronqués (#141).

get_top_org_ag_grid tronque à 100 lignes par défaut (pour l'observatoire). Sur
les fiches, toutes les organisations doivent rester dans la grille : son filtre
texte doit trouver celles au-delà du 100e rang.
"""

import dash_ag_grid as dag
import polars as pl
import pytest

NB_ORGS = 150


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


def _marches(org_type: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "uid": [f"m{i}" for i in range(NB_ORGS)],
            f"{org_type}_id": [f"{i:014d}" for i in range(NB_ORGS)],
            f"{org_type}_nom": [f"Organisation {i}" for i in range(NB_ORGS)],
            "titulaire_distance": [i for i in range(NB_ORGS)],
            "titulaire_typeIdentifiant": ["SIRET"] * NB_ORGS,
        }
    )


@pytest.mark.parametrize(
    "module,fonction,scope,org_type",
    [
        ("acheteur", "get_top_titulaires", "_acheteur_scope", "titulaire"),
        ("titulaire", "get_top_acheteurs", "_titulaire_scope", "acheteur"),
    ],
)
def test_la_fiche_montre_toutes_les_organisations(
    monkeypatch, module, fonction, scope, org_type
):
    import importlib

    from src.app import app  # noqa: F401  (instancie Dash avant les pages)

    page = importlib.import_module(f"src.pages.{module}")
    monkeypatch.setattr(page, scope, lambda *_: ("1 = 1", []))
    monkeypatch.setattr(page, "query_marches", lambda *_: _marches(org_type))

    grille = _trouver_grille(getattr(page, fonction)("/x/123", None))

    assert grille is not None, "aucune grille rendue"
    assert len(grille.rowData) == NB_ORGS
    noms = " ".join(row[f"{org_type}_nom"] for row in grille.rowData)
    assert f"Organisation {NB_ORGS - 1}<" in noms
