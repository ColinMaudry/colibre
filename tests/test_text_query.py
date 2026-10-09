import time

import pytest

from src.utils.text_query import analyser, en_texte, libelle_corrections


@pytest.mark.parametrize(
    "saisie, texte, corrections",
    [
        ("(béton OU", "béton", "parenthèse manquante, OU orphelin"),
        ("(béton OU ciment", "béton OU ciment", "parenthèse manquante"),
        ("béton) ET brique", "béton ET brique", "parenthèse en trop"),
        ("travaux ET PAS", "travaux", "PAS orphelin"),
        ('"maintenance sur', '"maintenance sur"', "guillemet manquant"),
        ("ET", "", "ET orphelin"),
        ("béton OU OU ciment", "béton OU ciment", "OU orphelin"),
        ("béton () ciment", "béton ET ciment", "parenthèses vides"),
        ('béton "" ciment', "béton ET ciment", "guillemets vides"),
        ('béton " " ciment', "béton ET ciment", "guillemets vides"),
        ("(béton PAS)", "béton", "PAS orphelin"),
        ("((béton OU", "béton", "parenthèse manquante, OU orphelin"),
        ("béton (", "béton", "parenthèse manquante"),
        (
            "(a OU b) c PAS (d OU e) )",
            "(a OU b) ET c ET PAS (d OU e)",
            "parenthèse en trop",
        ),
    ],
)
def test_reparations(saisie, texte, corrections):
    expr = analyser(saisie, operateurs=True)
    assert en_texte(expr) == texte
    assert libelle_corrections(expr) == corrections


def test_sans_correction_texte_tel_que_saisi():
    expr = analyser(" (béton OU ciment) brique", True)
    assert en_texte(expr) == "(béton OU ciment) brique"
    assert libelle_corrections(expr) == ""


def test_imbrication_limitee():
    expr = analyser("(" * 10 + "béton" + ")" * 10, True)
    assert libelle_corrections(expr) == ""

    expr = analyser("(" * 12 + "béton" + ")" * 12, True)
    assert en_texte(expr) == "béton"
    assert libelle_corrections(expr) == "trop de parenthèses imbriquées"

    expr = analyser("(" * 2000 + "x", True)
    assert en_texte(expr) == "x"
    assert (
        libelle_corrections(expr)
        == "parenthèse manquante, trop de parenthèses imbriquées"
    )


def test_mots_cles_en_majuscules_seulement():
    assert libelle_corrections(analyser("béton ou", True)) == ""
    assert libelle_corrections(analyser("OUEST", True)) == ""
    assert libelle_corrections(analyser("béton OU", True)) == "OU orphelin"


def test_saisie_vide():
    assert analyser(" ", True).arbre is None
    assert analyser("", False).arbre is None


def test_non_abonne():
    expr = analyser("(béton OU ciment", False)
    assert libelle_corrections(expr) == ""
    assert expr.operateurs_ignores is True
    assert en_texte(expr) == "(béton OU ciment"
    assert analyser('"béton OU ciment"', False).operateurs_ignores is False
    assert analyser("béton ou ciment", False).operateurs_ignores is False
    assert libelle_corrections(analyser('"maintenance sur', False)) == ""


def test_abonne_n_ignore_rien():
    assert analyser("béton OU ciment", True).operateurs_ignores is False


def test_pas_consecutifs_sans_recursion():
    expr = analyser("PAS " * 3000 + "x )", True)
    assert en_texte(expr) == "x"  # 3000 négations : nombre pair
    assert libelle_corrections(expr) == "parenthèse en trop"
    expr = analyser("PAS " * 3001 + "x )", True)
    assert en_texte(expr) == "PAS x"


def test_nettoyage_lineaire():
    debut = time.perf_counter()
    analyser("PAS " * 10000, True)
    analyser("a OU " * 10000, True)
    assert time.perf_counter() - debut < 2


def test_phrase_litterale():
    expr = analyser('"maintenance   sur" )', True)
    assert en_texte(expr) == '"maintenance   sur"'
