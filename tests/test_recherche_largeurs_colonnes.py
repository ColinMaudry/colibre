"""Largeurs fixes des colonnes des grilles de résultats de recherche.

Les deux grilles (acheteurs et titulaires) sont construites par la même
fonction : les largeurs doivent s'appliquer aux deux, par position de colonne,
quel que soit le préfixe de l'identifiant et du nom.

Ces tests vérifient le câblage, pas les valeurs : les largeurs sont un réglage
visuel que l'on ajuste à l'œil, et les figer ici ferait échouer la suite à
chaque retouche. Ils lisent donc `_RESULT_COLUMN_WIDTHS` et contrôlent que
chaque colonne reçoit bien la sienne.
"""

import polars as pl
import pytest

import src.app  # noqa: F401  # instancie Dash avant l'import de la page
from src.pages.recherche import _RESULT_COLUMN_WIDTHS, _result_column_defs


def _resultats(org_type: str) -> pl.DataFrame:
    """Colonnes renvoyées par `search_org`, dans leur ordre d'affichage."""
    return pl.DataFrame(
        {
            f"{org_type}_id": ["12345678900011"],
            f"{org_type}_nom": ["ORGANISATION 1"],
            "Département": ["Paris (75)"],
            "Marchés": [12],
        }
    )


@pytest.mark.parametrize("org_type", ["acheteur", "titulaire"])
def test_chaque_colonne_recoit_sa_largeur(org_type):
    defs = {d["field"]: d for d in _result_column_defs(_resultats(org_type))}

    assert defs[f"{org_type}_id"]["width"] == _RESULT_COLUMN_WIDTHS["_id"]
    assert defs[f"{org_type}_nom"]["width"] == _RESULT_COLUMN_WIDTHS["_nom"]
    assert defs["Département"]["width"] == _RESULT_COLUMN_WIDTHS["Département"]
    assert defs["Marchés"]["width"] == _RESULT_COLUMN_WIDTHS["Marchés"]


@pytest.mark.parametrize("org_type", ["acheteur", "titulaire"])
def test_aucune_colonne_sans_largeur(org_type):
    """Une colonne oubliée s'étirerait et décalerait les autres."""
    defs = _result_column_defs(_resultats(org_type))

    assert all("width" in d for d in defs), [
        d["field"] for d in defs if "width" not in d
    ]


def test_les_largeurs_sont_des_entiers_positifs():
    """Garde-fou sur le réglage lui-même : une valeur nulle ou négative
    ferait disparaître une colonne sans que rien d'autre ne le signale."""
    assert all(
        isinstance(largeur, int) and largeur > 0
        for largeur in _RESULT_COLUMN_WIDTHS.values()
    )


def test_colonne_inconnue_reste_sans_largeur_imposee():
    """Une colonne hors des quatre attendues ne doit pas hériter d'une
    largeur arbitraire : elle garde le comportement par défaut d'AG Grid."""
    defs = {
        d["field"]: d
        for d in _result_column_defs(pl.DataFrame({"colonne_inattendue": ["x"]}))
    }

    assert "width" not in defs["colonne_inattendue"]
