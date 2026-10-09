import polars as pl

SCHEMA = pl.Schema(
    {
        "uid": pl.String,
        "objet": pl.String,
        "acheteur_id": pl.String,
        "acheteur_nom": pl.String,
        "titulaire_nom": pl.String,
        "montant": pl.Float64,
        "dureeMois": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def test_sort_by_empty():
    from src.utils.table_sql import sort_by_to_sql

    assert sort_by_to_sql([], SCHEMA) == ""
    assert sort_by_to_sql(None, SCHEMA) == ""


def test_sort_by_single_column_desc():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql([{"column_id": "montant", "direction": "desc"}], SCHEMA)
    assert result == '"montant" DESC NULLS LAST'


def test_sort_by_multiple_columns_preserves_order():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql(
        [
            {"column_id": "dateNotification", "direction": "desc"},
            {"column_id": "montant", "direction": "asc"},
        ],
        SCHEMA,
    )
    assert result == '"dateNotification" DESC NULLS LAST, "montant" ASC NULLS LAST'


def test_sort_by_ignores_unknown_column():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql([{"column_id": "fake", "direction": "asc"}], SCHEMA)
    assert result == ""
