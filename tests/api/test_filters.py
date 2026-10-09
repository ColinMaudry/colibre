import polars as pl
import pytest

from src.api.filters import AggregationSpec, FilterError, build_where, parse_aggregators

SCHEMA = pl.Schema(
    {
        "uid": pl.String,
        "objet": pl.String,
        "montant": pl.Float64,
        "annee": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def test_no_filters_returns_true():
    where, params, order = build_where([], SCHEMA)
    assert where == "TRUE"
    assert params == []
    assert order is None


def test_exact_filter():
    where, params, _ = build_where([("uid__exact", "abc")], SCHEMA)
    assert where == '"uid" = ?'
    assert params == ["abc"]


def test_comparison_operators_on_int():
    where, params, _ = build_where([("annee__strictly_greater", "2023")], SCHEMA)
    assert where == '"annee" > ?'
    assert params == [2024 - 1]  # int coercion: 2023


def test_in_filter_splits_on_commas():
    where, params, _ = build_where([("annee__in", "2022,2023,2024")], SCHEMA)
    assert where == '"annee" IN (?,?,?)'
    assert params == [2022, 2023, 2024]


def test_notin_filter():
    where, params, _ = build_where([("annee__notin", "2020,2021")], SCHEMA)
    assert where == '"annee" NOT IN (?,?)'
    assert params == [2020, 2021]


def test_isnull_filter_ignores_value():
    where, params, _ = build_where([("dateNotification__isnull", "anything")], SCHEMA)
    assert where == '"dateNotification" IS NULL'
    assert params == []


def test_isnotnull_filter():
    where, params, _ = build_where([("dateNotification__isnotnull", "")], SCHEMA)
    assert where == '"dateNotification" IS NOT NULL'


def test_multiple_filters_joined_by_and():
    where, params, _ = build_where(
        [("uid__exact", "a"), ("annee__greater", "2020")], SCHEMA
    )
    assert where == '"uid" = ? AND "annee" >= ?'
    assert params == ["a", 2020]


def test_unknown_column_raises():
    with pytest.raises(FilterError) as exc:
        build_where([("foo__exact", "bar")], SCHEMA)
    assert "foo" in str(exc.value)
    assert exc.value.field == "foo__exact"


def test_unknown_operator_raises():
    with pytest.raises(FilterError) as exc:
        build_where([("uid__weird", "x")], SCHEMA)
    assert "weird" in str(exc.value)


def test_bad_int_value_raises():
    with pytest.raises(FilterError):
        build_where([("annee__exact", "notanint")], SCHEMA)


def test_bad_date_value_raises():
    with pytest.raises(FilterError):
        build_where([("dateNotification__exact", "notadate")], SCHEMA)


def test_date_iso_coercion():
    where, params, _ = build_where(
        [("dateNotification__greater", "2024-01-01")], SCHEMA
    )
    from datetime import date

    assert params == [date(2024, 1, 1)]


def test_reserved_params_are_ignored():
    where, params, order = build_where(
        [
            ("page", "2"),
            ("page_size", "100"),
            ("columns", "uid"),
            ("count_results", "false"),
            ("uid__exact", "z"),
        ],
        SCHEMA,
    )
    assert where == '"uid" = ?'
    assert params == ["z"]


def test_sort_returns_order_by():
    where, params, order = build_where(
        [("annee__sort", "desc"), ("uid__sort", "asc")], SCHEMA
    )
    assert where == "TRUE"
    assert order == '"annee" DESC, "uid" ASC'


def test_sort_invalid_direction_raises():
    with pytest.raises(FilterError):
        build_where([("uid__sort", "sideways")], SCHEMA)


def test_param_without_operator_raises():
    with pytest.raises(FilterError):
        build_where([("uidexact", "x")], SCHEMA)


def test_differs_filter():
    where, params, _ = build_where([("uid__differs", "abc")], SCHEMA)
    assert where == '"uid" IS DISTINCT FROM ?'
    assert params == ["abc"]


def test_differs_filter_on_int():
    where, params, _ = build_where([("annee__differs", "2020")], SCHEMA)
    assert where == '"annee" IS DISTINCT FROM ?'
    assert params == [2020]


def test_parse_aggregators_none_when_absent():
    assert parse_aggregators([("uid__exact", "a")], SCHEMA) is None


def test_parse_aggregators_groupby_and_count():
    spec = parse_aggregators([("annee__groupby", ""), ("uid__count", "")], SCHEMA)
    assert isinstance(spec, AggregationSpec)
    assert spec.select_sql == '"annee", COUNT("uid") AS "uid__count"'
    assert spec.group_by_sql == '"annee"'


def test_parse_aggregators_multiple_aggregates():
    spec = parse_aggregators(
        [
            ("annee__groupby", ""),
            ("montant__sum", ""),
            ("montant__avg", ""),
            ("montant__min", ""),
            ("montant__max", ""),
        ],
        SCHEMA,
    )
    assert spec.select_sql == (
        '"annee", SUM("montant") AS "montant__sum", '
        'AVG("montant") AS "montant__avg", '
        'MIN("montant") AS "montant__min", '
        'MAX("montant") AS "montant__max"'
    )
    assert spec.group_by_sql == '"annee"'


def test_parse_aggregators_global_without_groupby():
    spec = parse_aggregators([("uid__count", "")], SCHEMA)
    assert spec.select_sql == 'COUNT("uid") AS "uid__count"'
    assert spec.group_by_sql is None


def test_parse_aggregators_unknown_column_raises():
    with pytest.raises(FilterError):
        parse_aggregators([("nope__count", "")], SCHEMA)


def test_build_where_ignores_aggregator_flags():
    where, params, _ = build_where(
        [("annee__groupby", ""), ("uid__count", ""), ("montant__greater", "100")],
        SCHEMA,
    )
    assert where == '"montant" >= ?'
    assert params == [100.0]
