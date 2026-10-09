import pytest

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.utils.filter_pills import (
    BANNIERE_OPERATEURS,
    col_cliquee,
    colonnes_masquees_sans,
    describe_filter,
    filter_model_sans,
    filter_pills,
)

NB = "\u00a0"


def _txt(type_, value=None):
    return {"filterType": "text", "type": type_, "filter": value}


def _num(type_, value=None, value_to=None):
    return {
        "filterType": "number",
        "type": type_,
        "filter": value,
        "filterTo": value_to,
    }


def _date(type_, date_from, date_to=None):
    return {
        "filterType": "date",
        "type": type_,
        "dateFrom": date_from,
        "dateTo": date_to,
    }


@pytest.mark.parametrize(
    ("col", "spec", "attendu"),
    [
        ("acheteur_id", _txt("equals", "123"), ("SIRET acheteur", "= 123")),
        ("acheteur_id", _txt("notEqual", "123"), ("SIRET acheteur", "≠ 123")),
        ("acheteur_id", _txt("contains", "12"), ("SIRET acheteur", "contient 12")),
        (
            "acheteur_id",
            _txt("notContains", "12"),
            ("SIRET acheteur", "ne contient pas 12"),
        ),
        (
            "acheteur_id",
            _txt("startsWith", "12"),
            ("SIRET acheteur", "commence par 12"),
        ),
        (
            "acheteur_id",
            _txt("endsWith", "12"),
            ("SIRET acheteur", "se termine par 12"),
        ),
        ("montant", _num("greaterThan", 1000), ("Montant attribué", f"> 1{NB}000")),
        ("montant", _num("greaterThanOrEqual", 5), ("Montant attribué", "≥ 5")),
        ("montant", _num("lessThan", 5), ("Montant attribué", "< 5")),
        ("montant", _num("lessThanOrEqual", 5), ("Montant attribué", "≤ 5")),
        ("montant", _num("equals", 0), ("Montant attribué", "= 0")),
        (
            "montant",
            _num("inRange", 1000, 5000),
            ("Montant attribué", f"entre 1{NB}000 et 5{NB}000"),
        ),
        ("montant", _num("blank"), ("Montant attribué", "est vide")),
        ("montant", _num("notBlank"), ("Montant attribué", "n'est pas vide")),
        (
            "dateNotification",
            _date("equals", "2025-01-15 00:00:00"),
            ("Date notification", "= 15/01/2025"),
        ),
        (
            "dateNotification",
            _date("inRange", "2025-01-01 00:00:00", "2025-12-31 00:00:00"),
            ("Date notification", "entre 01/01/2025 et 31/12/2025"),
        ),
        (
            "montant",
            {
                "filterType": "number",
                "operator": "AND",
                "conditions": [_num("greaterThan", 1000), _num("lessThan", 5000)],
            },
            ("Montant attribué", f"> 1{NB}000 et < 5{NB}000"),
        ),
        (
            "acheteur_id",
            {
                "filterType": "text",
                "operator": "OR",
                "conditions": [_txt("equals", "1"), _txt("equals", "2")],
            },
            ("SIRET acheteur", "= 1 ou = 2"),
        ),
        (
            "colonne_disparue",
            _txt("contains", "x"),
            ("colonne_disparue", "contient x"),
        ),
    ],
)
def test_describe_filter(col, spec, attendu):
    assert describe_filter(col, spec, True)[:2] == attendu


def test_pastille_corrigee():
    desc = describe_filter("objet", _txt("contains", "(béton OU"), True)
    assert desc.expression == "contient béton (parenthèse manquante, OU orphelin)"
    assert desc.corrigee is True
    pills = filter_pills({"objet": _txt("contains", "(béton OU")}, "tableau", True)
    assert pills[0].className == "filter-pill filter-pill-warning"


def test_pastille_propre_sans_classe():
    desc = describe_filter("objet", _txt("contains", "béton OU ciment"), True)
    assert desc.expression == "contient béton OU ciment"
    assert desc.corrigee is False
    pills = filter_pills(
        {"objet": _txt("contains", "béton OU ciment")}, "tableau", True
    )
    assert pills[0].className == "filter-pill"


def test_expression_vide():
    assert (
        describe_filter("objet", _txt("contains", "ET"), True).expression
        == "n'est pas vide (ET orphelin)"
    )
    assert (
        describe_filter("objet", _txt("notContains", "ET"), True).expression
        == "est vide (ET orphelin)"
    )


def test_deux_conditions():
    spec = {
        "filterType": "text",
        "operator": "OR",
        "conditions": [_txt("contains", "béton OU"), _txt("contains", "brique")],
    }
    desc = describe_filter("objet", spec, True)
    assert desc.expression == "contient béton (OU orphelin) ou contient brique"
    assert desc.corrigee is True


def test_non_abonne_saisie_telle_quelle():
    desc = describe_filter("objet", _txt("contains", "(béton OU"), False)
    assert desc.expression == "contient (béton OU"
    assert desc.corrigee is False
    assert desc.operateurs_ignores is True


def test_bandeau_non_abonne():
    fm = {"objet": _txt("contains", "béton OU ciment")}
    pills = filter_pills(fm, "tableau", False)
    assert len(pills) == 2
    assert pills[-1].className == "filter-pills-banniere"
    assert BANNIERE_OPERATEURS in pills[-1].children
    assert len(filter_pills(fm, "tableau", True)) == 1
    phrase = {"objet": _txt("contains", '"béton OU ciment"')}
    assert len(filter_pills(phrase, "tableau", False)) == 1


def test_filter_pills_sans_filtre():
    assert filter_pills(None, "tableau", True) == []
    assert filter_pills({}, "tableau", True) == []


def test_filter_pills_ids_par_colonne():
    fm = {
        "montant": _num("greaterThan", 5),
        "acheteur_id": _txt("equals", "123"),
    }
    pills = filter_pills(fm, "acheteur", True)
    body, remove = pills[0].children
    assert body.id == {"type": "acheteur-filter-pill", "col": "montant"}
    assert remove.id == {"type": "acheteur-filter-pill-remove", "col": "montant"}
    assert pills[1].children[0].id["col"] == "acheteur_id"


def test_filter_model_sans_retire_la_colonne():
    fm = {"montant": _num("greaterThan", 5), "acheteur_id": _txt("equals", "123")}
    assert filter_model_sans(fm, "montant") == {"acheteur_id": _txt("equals", "123")}
    assert "montant" in fm  # pas de mutation du State


def test_filter_model_sans_dernier_filtre_donne_un_modele_vide():
    assert filter_model_sans({"montant": _num("greaterThan", 5)}, "montant") == {}


def test_col_cliquee_ignore_le_rerendu():
    assert (
        col_cliquee({"type": "tableau-filter-pill-remove", "col": "montant"}, None)
        is None
    )
    assert col_cliquee(None, 1) is None


def test_col_cliquee_renvoie_la_colonne():
    trig = {"type": "tableau-filter-pill-remove", "col": "montant"}
    assert col_cliquee(trig, 1) == "montant"


def test_colonnes_masquees_sans_devoile_la_colonne():
    out = colonnes_masquees_sans("acheteur_id", ["acheteur_id", "montant"], "tableau")
    assert out == ["montant"]


def test_colonnes_masquees_sans_colonne_deja_visible():
    assert colonnes_masquees_sans("acheteur_id", ["montant"], "tableau") is None


def test_colonnes_masquees_sans_preference_part_des_defauts():
    from src.utils.table import get_default_hidden_columns

    defauts = get_default_hidden_columns("tableau")
    assert "acheteur_id" in defauts  # précondition
    out = colonnes_masquees_sans("acheteur_id", None, "tableau")
    assert "acheteur_id" not in out
    assert set(out) == set(defauts) - {"acheteur_id"}
