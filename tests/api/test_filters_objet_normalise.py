"""#147 : l'API REST et le MCP filtrent « objet » sans tenir compte des accents,
ligatures œ/æ ni de l'apostrophe typographique.

`build_where` est exécuté pour de vrai dans le DuckDB en mémoire `con_objets`
(cf. tests/conftest.py).
"""

import polars as pl
import pytest

from src.api.filters import build_where
from src.mcp.queries import build_where_args

SCHEMA = pl.Schema({"objet": pl.String, "acheteur_nom": pl.String})

AUTRES = ["Travaux de voirie", "Éclairage public"]


def _objets(con, args):
    where, params, _ = build_where(args, SCHEMA)
    rows = con.execute(
        f"SELECT objet FROM decp WHERE {where} ORDER BY objet", params
    ).fetchall()
    return sorted((r[0] for r in rows), key=lambda objet: (objet is None, objet or ""))


@pytest.mark.parametrize(
    "saisie", ["maitrise d'oeuvre", "MAÎTRISE D’ŒUVRE", "maîtrise d’oeuvre"]
)
def test_objet_contains_retrouve_toutes_les_graphies(
    con_objets, objets_maitrise, saisie
):
    assert _objets(con_objets, [("objet__contains", saisie)]) == objets_maitrise


def test_objet_notcontains_exclut_les_graphies_et_les_null(con_objets):
    restant = _objets(con_objets, [("objet__notcontains", "maitrise")])

    assert restant == sorted(["", *AUTRES])


def test_objet_startswith(con_objets, objets_maitrise):
    assert (
        _objets(con_objets, [("objet__startswith", "maitrise d'oe")]) == objets_maitrise
    )


def test_objet_exact_reste_exact(con_objets):
    assert _objets(con_objets, [("objet__exact", "Maîtrise d'œuvre")]) == [
        "Maîtrise d'œuvre"
    ]


def test_autre_colonne_non_normalisee(con_objets):
    # acheteur_nom n'est pas normalisé côté API : la saisie accentuée ne
    # retrouve pas « NIMES METROPOLE ».
    assert _objets(con_objets, [("acheteur_nom__contains", "Nîmes")]) == []
    assert len(_objets(con_objets, [("acheteur_nom__contains", "NIMES")])) == 9


def test_mcp_objet_contient_equivaut_a_objet_contains(con_objets, objets_maitrise):
    args = build_where_args({"objet_contient": "maitrise d'oeuvre"}, None)

    assert _objets(con_objets, args) == objets_maitrise
