import time

import pytest

from src.utils.text_query import analyser, en_sql, en_texte, libelle_corrections


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


def _filtre(
    con, saisie, operateurs=True, colonne="objet", col_is_date=False, negation=False
):
    where, params = en_sql(analyser(saisie, operateurs), colonne, col_is_date)
    if negation:
        where = f"NOT ({where})"
    rows = con.execute(f"SELECT objet FROM decp WHERE {where}", params).fetchall()
    return sorted((r[0] for r in rows), key=lambda v: (v is None, v or ""))


_NON_VIDES = sorted(
    [
        "Travaux de béton",
        "Béton et ciment",
        "Béton ou ciment au choix",
        "Fourniture de ciment",
        "Brique et béton",
        "Ciment et brique",
        "Entretien des espaces verts",
        "Travaux de construction",
        "Travaux de voirie",
        "Conseil en étude de marché",
        "Conseil juridique",
        "Maintenance sur site",
        "Site de maintenance",
        "Maîtrise d’œuvre",
        "Réseau OUEST",
        "Prix 3+4",
        "x' OR 1=1 --",
    ]
)

_BETON_OU_CIMENT = sorted(
    [
        "Béton et ciment",
        "Béton ou ciment au choix",
        "Brique et béton",
        "Ciment et brique",
        "Fourniture de ciment",
        "Travaux de béton",
    ]
)


def test_ou(con_booleens):
    assert _filtre(con_booleens, "béton OU ciment") == _BETON_OU_CIMENT


def test_groupage(con_booleens):
    assert _filtre(con_booleens, "(béton OU ciment) ET brique") == sorted(
        ["Brique et béton", "Ciment et brique"]
    )


def test_priorite_et_sur_ou(con_booleens):
    assert _filtre(con_booleens, "béton ciment OU brique") == sorted(
        [
            "Brique et béton",
            "Béton et ciment",
            "Béton ou ciment au choix",
            "Ciment et brique",
        ]
    )


def test_et_pas(con_booleens):
    assert _filtre(con_booleens, "travaux ET PAS construction") == sorted(
        ["Travaux de béton", "Travaux de voirie"]
    )
    assert _filtre(con_booleens, 'conseil ET PAS "étude de marché"') == [
        "Conseil juridique"
    ]


def test_ou_pas_logique_stricte(con_booleens):
    resultat = _filtre(con_booleens, "béton OU PAS ciment")
    assert "Béton et ciment" in resultat
    assert "Entretien des espaces verts" in resultat
    assert "Fourniture de ciment" not in resultat
    assert "Ciment et brique" not in resultat


def test_phrase_exige_l_ordre(con_booleens):
    assert _filtre(con_booleens, '"maintenance sur site"') == ["Maintenance sur site"]
    assert _filtre(con_booleens, "maintenance site") == sorted(
        ["Maintenance sur site", "Site de maintenance"]
    )


def test_phrases_colonne_multivaluee(con_booleens):
    assert _filtre(
        con_booleens,
        '"Clause sociale" ET "Critère social"',
        colonne="considerationsSociales",
    ) == ["Travaux de béton"]


def test_mots_cles_litteraux(con_booleens):
    assert _filtre(con_booleens, "OUEST") == ["Réseau OUEST"]
    assert _filtre(con_booleens, '"béton OU ciment"') == ["Béton ou ciment au choix"]
    assert _filtre(con_booleens, "béton OU ciment") == _BETON_OU_CIMENT
    assert _filtre(con_booleens, "béton ou ciment") == ["Béton ou ciment au choix"]


def test_mots_cles_colles(con_booleens):
    assert _filtre(con_booleens, "(béton)OU(ciment)") == _BETON_OU_CIMENT
    assert _filtre(con_booleens, 'béton OU"ciment"') == _BETON_OU_CIMENT


def test_jokers_et_plus(con_booleens):
    assert _filtre(con_booleens, "maint*") == ["Maintenance sur site"]
    assert _filtre(con_booleens, '"maint*"') == []
    assert _filtre(con_booleens, "3+4") == ["Prix 3+4"]


def test_normalisation_dans_une_phrase(con_booleens):
    assert _filtre(con_booleens, '"maitrise d\'oeuvre"') == ["Maîtrise d’œuvre"]


def test_colonne_date(con_booleens):
    assert _filtre(
        con_booleens, "2024 OU 2025", colonne="dateNotification", col_is_date=True
    ) == sorted(["Conseil juridique", "Travaux de béton"])


def test_contient_exclut_null_et_vide(con_booleens):
    resultat = _filtre(con_booleens, "PAS construction")
    assert None not in resultat
    assert "" not in resultat
    assert len(resultat) == 16
    assert resultat == [o for o in _NON_VIDES if o != "Travaux de construction"]


def test_ne_contient_pas_inclut_null_et_vide(con_booleens):
    resultat = _filtre(con_booleens, "construction", negation=True)
    assert None in resultat
    assert "" in resultat


def test_expression_vide_garde_seulement(con_booleens):
    assert _filtre(con_booleens, "ET") == _NON_VIDES


def test_non_abonne_mots_ordinaires(con_booleens):
    assert _filtre(con_booleens, "béton OU ciment", operateurs=False) == [
        "Béton ou ciment au choix"
    ]


def test_valeur_liee(con_booleens):
    assert _filtre(con_booleens, "x' OR 1=1 --") == ["x' OR 1=1 --"]
