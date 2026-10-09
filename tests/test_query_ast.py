import polars as pl

from src.utils.query_ast import (
    And,
    Condition,
    Not,
    Or,
    ast_from_dict,
    ast_to_dict,
    ast_to_filtermodel,
    ast_to_sql,
    filtermodel_to_ast,
    sort_model_to_sql,
)

SCHEMA = pl.Schema(
    {
        "acheteur_nom": pl.String,
        "objet": pl.String,
        "montant": pl.Float64,
        "dureeMois": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def _run(node):
    """Compile et retourne (sql, params)."""
    return ast_to_sql(node, SCHEMA, operateurs=True)


def test_none_is_true():
    assert _run(None) == ("TRUE", [])


def test_empty_and_is_true():
    assert _run(And([])) == ("TRUE", [])


def test_text_contains_uses_ilike_and_params():
    sql, params = _run(Condition("objet", "contains", "voirie"))
    assert "ILIKE ?" in sql
    assert params == ["%voirie%"]


def test_text_contains_multiword_is_and():
    sql, params = _run(Condition("objet", "contains", "metropole rennes"))
    assert sql.count("ILIKE ?") == 2
    assert params == ["%metropole%", "%rennes%"]


def test_text_contains_wildcard_and_phrase():
    _, params = _run(Condition("objet", "contains", 'distri* "metropole rennes"'))
    assert params == ["distri%", "%metropole rennes%"]


def test_text_notcontains_negates():
    sql, params = _run(Condition("objet", "notContains", "construction"))
    assert "NOT (" in sql
    assert params == ["%construction%"]


def test_numeric_gt():
    sql, params = _run(Condition("montant", "gt", 40000))
    assert '"montant" > ?' in sql
    assert params == [40000.0]


def test_numeric_eq_int_column():
    sql, params = _run(Condition("dureeMois", "eq", "12"))
    assert '"dureeMois" = ?' in sql
    assert params == [12]


def test_numeric_range():
    sql, params = _run(Condition("montant", "range", 100, 200))
    assert params == [100.0, 200.0]
    assert "BETWEEN" in sql or ("> ?" in sql and "< ?" in sql)


def test_numeric_invalid_value_is_true():
    # valeur non numérique -> condition neutralisée (TRUE), pas d'exception
    assert _run(Condition("montant", "gt", "abc")) == ("TRUE", [])


def test_date_gt_casts_varchar():
    sql, params = _run(Condition("dateNotification", "gt", "2022"))
    assert "VARCHAR" in sql
    assert params == ["2022"]


def test_blank_and_notblank():
    sql_b, _ = _run(Condition("objet", "blank"))
    assert "IS NULL" in sql_b
    sql_nb, _ = _run(Condition("objet", "notBlank"))
    assert "IS NOT NULL" in sql_nb


def test_date_range_uses_between():
    sql, params = _run(
        Condition("dateNotification", "range", "2022-01-01", "2022-12-31")
    )
    assert "BETWEEN" in sql
    assert params == ["2022-01-01", "2022-12-31"]


def test_text_range_uses_between():
    sql, params = _run(Condition("acheteur_nom", "range", "a", "m"))
    assert "BETWEEN" in sql
    assert params == ["a", "m"]


def test_blank_on_numeric_column_no_empty_string():
    sql, params = _run(Condition("montant", "blank"))
    assert sql == '"montant" IS NULL'
    assert params == []


def test_notblank_on_date_column_no_empty_string():
    sql, params = _run(Condition("dateNotification", "notBlank"))
    assert sql == '"dateNotification" IS NOT NULL'
    assert params == []


def test_unknown_column_is_true():
    assert _run(Condition("colonne_inexistante", "contains", "x")) == ("TRUE", [])


def test_and_or_not_grouping():
    node = And(
        [
            Or(
                [
                    Condition("objet", "contains", "beton"),
                    Condition("objet", "contains", "ciment"),
                ]
            ),
            Not(Condition("objet", "contains", "demolition")),
        ]
    )
    sql, params = _run(node)
    assert " OR " in sql and " AND " in sql and "NOT (" in sql
    assert params == ["%beton%", "%ciment%", "%demolition%"]


def test_filtermodel_empty_is_none():
    assert filtermodel_to_ast(None, SCHEMA) is None
    assert filtermodel_to_ast({}, SCHEMA) is None


def test_filtermodel_text_contains():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "voirie"}}
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert params == ["%voirie%"]


def test_filtermodel_number_greaterthan():
    fm = {"montant": {"filterType": "number", "type": "greaterThan", "filter": 40000}}
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert '"montant"' in sql and params == [40000.0]


def test_filtermodel_number_inrange():
    fm = {
        "montant": {
            "filterType": "number",
            "type": "inRange",
            "filter": 100,
            "filterTo": 200,
        }
    }
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert params == [100.0, 200.0]


def test_filtermodel_date_uses_datefrom():
    fm = {
        "dateNotification": {
            "filterType": "date",
            "type": "greaterThan",
            "dateFrom": "2022-01-01",
        }
    }
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert params == ["2022-01-01"]


def test_filtermodel_two_conditions_or():
    fm = {
        "objet": {
            "filterType": "text",
            "operator": "OR",
            "condition1": {"filterType": "text", "type": "contains", "filter": "beton"},
            "condition2": {
                "filterType": "text",
                "type": "contains",
                "filter": "ciment",
            },
        }
    }
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert " OR " in sql and params == ["%beton%", "%ciment%"]


def test_filtermodel_two_conditions_or_real_ag_grid_shape():
    """AG Grid >=29.2 (pinné à 35.2.0 ici) envoie 'conditions' (liste), pas
    condition1/condition2 (déprécié). Voir la doc Dash AG Grid "Filter Model
    & Dash Callbacks" > "Filter Model Multiple Conditions". Bug de régression :
    filtermodel_to_ast ignorait silencieusement ces filtres (#41)."""
    fm = {
        "acheteur_nom": {
            "filterType": "text",
            "operator": "OR",
            "conditions": [
                {"filterType": "text", "type": "contains", "filter": "91"},
                {"filterType": "text", "type": "contains", "filter": "78"},
            ],
        }
    }
    ast = filtermodel_to_ast(fm, SCHEMA)
    assert ast is not None, "le filtre ne doit pas être silencieusement ignoré"
    sql, params = ast_to_sql(ast, SCHEMA, operateurs=True)
    assert " OR " in sql
    assert params == ["%91%", "%78%"]


def test_filtermodel_conditions_and_three_values():
    """La liste 'conditions' n'est pas limitée à 2 éléments (maxNumConditions)."""
    fm = {
        "objet": {
            "filterType": "text",
            "operator": "AND",
            "conditions": [
                {"filterType": "text", "type": "contains", "filter": "voirie"},
                {"filterType": "text", "type": "notContains", "filter": "reparation"},
                {"filterType": "text", "type": "contains", "filter": "route"},
            ],
        }
    }
    ast = filtermodel_to_ast(fm, SCHEMA)
    sql, params = ast_to_sql(ast, SCHEMA, operateurs=True)
    assert sql.count(" AND ") >= 2
    assert params == ["%voirie%", "%reparation%", "%route%"]


def test_filtermodel_multiple_columns_are_anded():
    fm = {
        "objet": {"filterType": "text", "type": "contains", "filter": "voirie"},
        "montant": {"filterType": "number", "type": "greaterThan", "filter": 1000},
    }
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA, operateurs=True)
    assert " AND " in sql and set(params) == {"%voirie%", 1000.0}


def test_sort_model_to_sql():
    sm = [{"colId": "montant", "sort": "desc"}, {"colId": "dureeMois", "sort": "asc"}]
    out = sort_model_to_sql(sm, SCHEMA)
    assert out == '"montant" DESC NULLS LAST, "dureeMois" ASC NULLS LAST'


def test_sort_model_empty():
    assert sort_model_to_sql(None, SCHEMA) == ""
    assert sort_model_to_sql([], SCHEMA) == ""


def test_ast_dict_roundtrip():
    node = And(
        [
            Or([Condition("objet", "contains", "beton")]),
            Not(Condition("objet", "contains", "x")),
        ]
    )
    restored = ast_from_dict(ast_to_dict(node))
    assert ast_to_sql(restored, SCHEMA, operateurs=True) == ast_to_sql(
        node, SCHEMA, operateurs=True
    )


def test_ast_dict_none():
    assert ast_to_dict(None) is None
    assert ast_from_dict(None) is None


def _roundtrip_sql(fm):
    """Compile fm -> ast -> filterModel -> ast à nouveau, renvoie (sql, params)
    de la première et de la seconde compilation, pour vérifier l'équivalence
    sémantique du round-trip (pas l'égalité dict-à-dict)."""
    ast1 = filtermodel_to_ast(fm, SCHEMA)
    rebuilt_fm = ast_to_filtermodel(ast1, SCHEMA)
    ast2 = filtermodel_to_ast(rebuilt_fm, SCHEMA)
    return ast_to_sql(ast1, SCHEMA, operateurs=True), ast_to_sql(
        ast2, SCHEMA, operateurs=True
    )


def test_ast_to_filtermodel_roundtrip_text_contains():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "voirie"}}
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_roundtrip_number_greaterthan():
    fm = {"montant": {"filterType": "number", "type": "greaterThan", "filter": 40000}}
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_roundtrip_number_inrange():
    fm = {
        "montant": {
            "filterType": "number",
            "type": "inRange",
            "filter": 100,
            "filterTo": 200,
        }
    }
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_roundtrip_date_greaterthan():
    fm = {
        "dateNotification": {
            "filterType": "date",
            "type": "greaterThan",
            "dateFrom": "2022-01-01",
        }
    }
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_roundtrip_two_conditions_or():
    fm = {
        "objet": {
            "filterType": "text",
            "operator": "OR",
            "condition1": {"filterType": "text", "type": "contains", "filter": "beton"},
            "condition2": {
                "filterType": "text",
                "type": "contains",
                "filter": "ciment",
            },
        }
    }
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_roundtrip_multiple_columns():
    fm = {
        "objet": {"filterType": "text", "type": "contains", "filter": "voirie"},
        "montant": {"filterType": "number", "type": "greaterThan", "filter": 1000},
    }
    original, rebuilt = _roundtrip_sql(fm)
    assert original == rebuilt


def test_ast_to_filtermodel_none_and_empty_and():
    assert ast_to_filtermodel(None, SCHEMA) == {}
    assert ast_to_filtermodel(And([]), SCHEMA) == {}


def test_ast_to_filtermodel_skips_not_with_warning():
    node = And([Not(Condition("objet", "contains", "x"))])
    assert ast_to_filtermodel(node, SCHEMA) == {}


def test_ast_to_filtermodel_skips_mismatched_columns_with_warning():
    node = And(
        [Or([Condition("objet", "contains", "a"), Condition("montant", "gt", 1)])]
    )
    assert ast_to_filtermodel(node, SCHEMA) == {}


def test_ast_to_filtermodel_bare_single_condition():
    """filtermodel_to_ast enveloppe toujours dans And, mais on tolère un nœud
    non enveloppé (Condition seule) en entrée, défensivement."""
    node = Condition("objet", "contains", "voirie")
    fm = ast_to_filtermodel(node, SCHEMA)
    assert fm == {
        "objet": {"filterType": "text", "type": "contains", "filter": "voirie"}
    }
