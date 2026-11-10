"""#147 : les filtres sur « objet » ignorent casse, accents, ligatures œ/æ et
apostrophe typographique.

Les requêtes sont exécutées pour de vrai dans un DuckDB en mémoire
(fixture `con_objets`) : on vérifie quelles lignes sont retournées, pas le SQL
généré.
"""

import polars as pl
import pytest

from src.utils.query_ast import Condition, ast_to_sql
from src.utils.table_sql import dashboard_filters_to_sql
from src.utils.text_query import analyser, en_sql

SCHEMA = pl.Schema({"objet": pl.String, "acheteur_nom": pl.String})

AUTRES = ["Travaux de voirie", "Éclairage public"]


def _objets(con, where, params):
    rows = con.execute(
        f"SELECT objet FROM decp WHERE {where} ORDER BY objet", params
    ).fetchall()
    return sorted(r[0] for r in rows)


@pytest.mark.parametrize(
    "saisie",
    [
        "maîtrise d'œuvre",
        "maitrise d'oeuvre",
        "MAÎTRISE D'OEUVRE",
        "maîtrise d'oeuvre",
        "maitrise d'œuvre",
    ],
)
def test_contains_retrouve_toutes_les_graphies(con_objets, objets_maitrise, saisie):
    where, params = en_sql(analyser(saisie, True), "objet")

    assert _objets(con_objets, where, params) == objets_maitrise


@pytest.mark.parametrize("saisie", ["d'oeuvre", "d’oeuvre", "d’œuvre"])
def test_contains_apostrophes_droite_et_typographique_equivalentes(
    con_objets, objets_maitrise, saisie
):
    where, params = en_sql(analyser(saisie, True), "objet")

    assert _objets(con_objets, where, params) == objets_maitrise


def test_contains_saisie_accentuee_retrouve_valeur_non_accentuee(con_objets):
    where, params = en_sql(analyser("éclairage", True), "objet")

    assert _objets(con_objets, where, params) == ["Éclairage public"]


def test_contains_joker_et_phrase_gardent_leur_semantique(con_objets, objets_maitrise):
    where, params = en_sql(analyser('"maitrise d\'oeuvre"', True), "objet")
    assert _objets(con_objets, where, params) == objets_maitrise

    where, params = en_sql(analyser("eclairage*", True), "objet")
    assert _objets(con_objets, where, params) == ["Éclairage public"]

    where, params = en_sql(analyser("*voirie", True), "objet")
    assert _objets(con_objets, where, params) == ["Travaux de voirie"]


def test_contains_ne_retourne_ni_null_ni_vide(con_objets):
    where, params = en_sql(analyser("e", True), "objet")

    assert None not in _objets(con_objets, where, params)
    assert "" not in _objets(con_objets, where, params)


def test_saisie_vide_ou_espaces_retourne_tout_sauf_null_et_vide(
    con_objets, objets_maitrise
):
    where, params = en_sql(analyser("   ", True), "objet")

    assert _objets(con_objets, where, params) == sorted([*objets_maitrise, *AUTRES])


def test_not_contains_exclut_toutes_les_graphies(con_objets):
    where, params = ast_to_sql(
        Condition("objet", "notContains", "maitrise"), SCHEMA, operateurs=True
    )

    restant = _objets(con_objets, f"objet IS NOT NULL AND ({where})", params)
    assert restant == sorted(["", *AUTRES])


def test_starts_with_ignore_accents_et_ligatures(con_objets, objets_maitrise):
    where, params = ast_to_sql(
        Condition("objet", "startsWith", "maitrise d'oe"), SCHEMA, operateurs=True
    )

    assert _objets(con_objets, where, params) == objets_maitrise


def test_ends_with_ignore_accents_et_ligatures(con_objets, objets_maitrise):
    where, params = ast_to_sql(
        Condition("objet", "endsWith", "d'oeuvre"), SCHEMA, operateurs=True
    )

    assert _objets(con_objets, where, params) == objets_maitrise


def test_starts_with_et_ends_with_apostrophe_typographique(con_objets, objets_maitrise):
    where, params = ast_to_sql(
        Condition("objet", "startsWith", "maitrise d’oe"), SCHEMA, operateurs=True
    )
    assert _objets(con_objets, where, params) == objets_maitrise

    where, params = ast_to_sql(
        Condition("objet", "endsWith", "d’oeuvre"), SCHEMA, operateurs=True
    )
    assert _objets(con_objets, where, params) == objets_maitrise


def test_equals_reste_exact(con_objets):
    where, params = ast_to_sql(
        Condition("objet", "eq", "Maîtrise d'œuvre"), SCHEMA, operateurs=True
    )

    assert _objets(con_objets, where, params) == ["Maîtrise d'œuvre"]


def test_observatoire_filtre_objet_ignore_accents_et_ligatures(
    con_objets, objets_maitrise
):
    where, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_objet="maitrise d'oeuvre",
        operateurs=True,
    )

    assert _objets(con_objets, where, params) == objets_maitrise


@pytest.mark.parametrize(
    "colonne, saisie",
    [
        ("acheteur_nom", "Nîmes"),
        ("acheteur_nom", "nimes"),
        ("acheteur_nom", "NIMES"),
        ("acheteur_nom", "nîmes métropole"),
        ("titulaire_nom", "Fréjus"),
        ("titulaire_nom", "fréjus"),
        ("titulaire_nom", "FREJUS"),
    ],
)
def test_filtre_nom_insensible_a_la_casse_et_aux_accents(con_objets, colonne, saisie):
    """#150 : les noms sont stockés en casse normale avec accents ; « nimes »,
    « Nîmes » et « NIMES » retournent les mêmes lignes."""
    where, params = en_sql(analyser(saisie, True), colonne)

    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert (
        nb
        == con_objets.execute(
            "SELECT count(*) FROM decp WHERE acheteur_nom IS NOT NULL"
        ).fetchone()[0]
    )

    where, params = en_sql(analyser("absent", True), colonne)
    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert nb == 0


def test_starts_with_et_ends_with_sur_les_noms(con_objets):
    where, params = ast_to_sql(
        Condition("acheteur_nom", "startsWith", "Nîmes"), SCHEMA, operateurs=True
    )
    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert nb == 9

    where, params = ast_to_sql(
        Condition("acheteur_nom", "endsWith", "MÉTROPOLE"), SCHEMA, operateurs=True
    )
    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert nb == 9


def test_equals_sur_les_noms_reste_exact(con_objets):
    where, params = ast_to_sql(
        Condition("acheteur_nom", "eq", "Nimes Metropole"), SCHEMA, operateurs=True
    )

    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert nb == 0

    where, params = ast_to_sql(
        Condition("acheteur_nom", "eq", "Nîmes Métropole"), SCHEMA, operateurs=True
    )
    nb = con_objets.execute(
        f"SELECT count(*) FROM decp WHERE {where}", params
    ).fetchone()[0]
    assert nb == 9
