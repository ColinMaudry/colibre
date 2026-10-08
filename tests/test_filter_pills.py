import pytest

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.utils.filter_pills import describe_filter, filter_pills

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
    assert describe_filter(col, spec) == attendu


def test_filter_pills_sans_filtre():
    assert filter_pills(None, "tableau") == []
    assert filter_pills({}, "tableau") == []


def test_filter_pills_ids_par_colonne():
    fm = {
        "montant": _num("greaterThan", 5),
        "acheteur_id": _txt("equals", "123"),
    }
    pills = filter_pills(fm, "acheteur")
    body, remove = pills[0].children
    assert body.id == {"type": "acheteur-filter-pill", "col": "montant"}
    assert remove.id == {"type": "acheteur-filter-pill-remove", "col": "montant"}
    assert pills[1].children[0].id["col"] == "acheteur_id"
