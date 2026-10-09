import duckdb
import pytest

from src.utils.text_normalization import (
    normalize_text,
    normalize_text_sql,
    normalized_target,
    normalized_term,
)


def test_normalize_text_exemples():
    assert normalize_text("Maîtrise d’œuvre") == "Maitrise d'oeuvre"
    assert normalize_text("ÉCOLE ŒUVRE ÆON") == "ECOLE OEUVRE AEON"
    assert normalize_text("français garçon") == "francais garcon"
    # La casse est conservée : c'est l'ILIKE qui l'ignore.
    assert normalize_text("Éclairage") == "Eclairage"


def test_normalize_text_forme_decomposee():
    assert normalize_text("e\u0301cole") == "ecole"


def test_normalize_text_chaine_vide_et_non_latin():
    assert normalize_text("") == ""
    assert normalize_text("東京 😀") == "東京 😀"


ECHANTILLON = [
    "é è ê ë à ç î ï ô ù û ü ñ",
    "ÉÈÀÇ",
    "œ Œ æ Æ",
    "d’œuvre",
    "d'oeuvre",
    "",
    "東京",
    "e\u0301",
]


@pytest.mark.parametrize("texte", ECHANTILLON)
def test_parite_python_sql(texte):
    """La colonne est calculée par DuckDB, la saisie par Python : les deux
    doivent donner le même résultat."""
    con = duckdb.connect()
    sql = f"SELECT {normalize_text_sql('v')} FROM (SELECT ? AS v)"

    assert con.execute(sql, [texte]).fetchone()[0] == normalize_text(texte)


def test_normalize_text_sql_null():
    con = duckdb.connect()
    sql = f"SELECT {normalize_text_sql('v')} FROM (SELECT NULL::VARCHAR AS v)"

    assert con.execute(sql).fetchone()[0] is None


def test_normalized_target_et_term():
    assert normalized_target("objet", '"objet"') == '"objet_normalise"'
    assert normalized_target("montant", '"montant"') == '"montant"'
    assert normalized_term("objet", "d’œuvre") == "d'oeuvre"
    assert normalized_term("acheteur_nom", "Nîmes") == "Nîmes"
