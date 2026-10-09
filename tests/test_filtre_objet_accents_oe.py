"""#147 : les filtres sur « objet » ignorent casse, accents et ligatures œ/æ.

Les requêtes sont exécutées pour de vrai dans un DuckDB en mémoire : on vérifie
quelles lignes sont retournées, pas le SQL généré.
"""

import duckdb
import polars as pl
import pytest

from src.utils.query_ast import Condition, ast_to_sql
from src.utils.table_sql import dashboard_filters_to_sql, tokenize_text_filter

SCHEMA = pl.Schema({"objet": pl.String, "acheteur_nom": pl.String})

OBJETS = [
    "Maîtrise d'œuvre",
    "maitrise d'œuvre",
    "maîtrise d'oeuvre",
    "MAÎTRISE D'ŒUVRE",
    "Travaux de voirie",
    "Éclairage public",
]
MAITRISE_D_OEUVRE = OBJETS[:4]


@pytest.fixture
def con():
    connexion = duckdb.connect(":memory:")
    connexion.execute(
        "CREATE TABLE decp (objet VARCHAR, acheteur_nom VARCHAR, "
        'titulaire_nom VARCHAR, "dateNotification" DATE)'
    )
    connexion.executemany(
        "INSERT INTO decp VALUES (?, 'NIMES METROPOLE', 'FREJUS SARL', "
        "DATE '2025-06-01')",
        [(objet,) for objet in OBJETS] + [(None,), ("",)],
    )
    return connexion


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
def test_contains_retrouve_toutes_les_graphies(con, saisie):
    where, params = tokenize_text_filter("objet", saisie)

    assert _objets(con, where, params) == sorted(MAITRISE_D_OEUVRE)


def test_contains_saisie_accentuee_retrouve_valeur_non_accentuee(con):
    where, params = tokenize_text_filter("objet", "éclairage")

    assert _objets(con, where, params) == ["Éclairage public"]


def test_contains_joker_et_phrase_gardent_leur_semantique(con):
    where, params = tokenize_text_filter("objet", "maitrise+d'oeuvre")
    assert _objets(con, where, params) == sorted(MAITRISE_D_OEUVRE)

    where, params = tokenize_text_filter("objet", "eclairage*")
    assert _objets(con, where, params) == ["Éclairage public"]

    where, params = tokenize_text_filter("objet", "*voirie")
    assert _objets(con, where, params) == ["Travaux de voirie"]


def test_contains_ne_retourne_ni_null_ni_vide(con):
    where, params = tokenize_text_filter("objet", "e")

    assert None not in _objets(con, where, params)
    assert "" not in _objets(con, where, params)


def test_not_contains_exclut_toutes_les_graphies(con):
    where, params = ast_to_sql(Condition("objet", "notContains", "maitrise"), SCHEMA)

    restant = _objets(con, f"objet IS NOT NULL AND ({where})", params)
    assert restant == ["", "Travaux de voirie", "Éclairage public"]


def test_starts_with_ignore_accents_et_ligatures(con):
    where, params = ast_to_sql(
        Condition("objet", "startsWith", "maitrise d'oe"), SCHEMA
    )

    assert _objets(con, where, params) == sorted(MAITRISE_D_OEUVRE)


def test_ends_with_ignore_accents_et_ligatures(con):
    where, params = ast_to_sql(Condition("objet", "endsWith", "d'oeuvre"), SCHEMA)

    assert _objets(con, where, params) == sorted(MAITRISE_D_OEUVRE)


def test_equals_reste_exact(con):
    where, params = ast_to_sql(Condition("objet", "eq", "Maîtrise d'œuvre"), SCHEMA)

    assert _objets(con, where, params) == ["Maîtrise d'œuvre"]


def test_observatoire_filtre_objet_ignore_accents_et_ligatures(con):
    where, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_marche_objet="maitrise d'oeuvre"
    )
    assert _objets(con, where, params) == sorted(MAITRISE_D_OEUVRE)


@pytest.mark.parametrize(
    "colonne, saisie", [("acheteur_nom", "Nîmes"), ("titulaire_nom", "fréjus")]
)
def test_noms_stockes_sans_accents_saisie_desaccentuee(con, colonne, saisie):
    """acheteur_nom/titulaire_nom sont stockés sans accents (#138) : seule la
    saisie est normalisée, et une saisie accentuée retrouve la valeur."""
    where, params = tokenize_text_filter(colonne, saisie)

    nb = con.execute(f"SELECT count(*) FROM decp WHERE {where}", params).fetchone()[0]
    assert nb == con.execute("SELECT count(*) FROM decp").fetchone()[0]

    where, params = tokenize_text_filter(colonne, "absent")
    assert (
        con.execute(f"SELECT count(*) FROM decp WHERE {where}", params).fetchone()[0]
        == 0
    )
