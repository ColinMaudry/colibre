import polars as pl

from src.db import aggregate_marches


def test_aggregate_groupby_count_returns_named_columns():
    df = aggregate_marches(
        select_sql='"acheteur_departement_code", COUNT("uid") AS "uid__count"',
        group_by='"acheteur_departement_code"',
    )
    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["acheteur_departement_code", "uid__count"]
    assert df["uid__count"].sum() > 0


def test_aggregate_global_without_groupby_returns_one_row():
    df = aggregate_marches(select_sql='COUNT("uid") AS "uid__count"')
    assert df.height == 1
    assert df["uid__count"][0] > 0


def test_aggregate_having_filters_groups():
    """HAVING s'applique après le GROUP BY, avec ses paramètres liés."""
    df = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
        having="COUNT(*) >= ?",
        params=[1],
    )
    assert df.height > 0

    vide = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
        having="COUNT(*) > ?",
        params=[10**9],
    )
    assert vide.height == 0


def test_count_aggregate_counts_groups_not_rows():
    """count_aggregate renvoie le nombre de groupes, pas le nombre de lignes."""
    from src.db import count_aggregate

    groupes = count_aggregate(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
    )
    df = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
    )
    assert groupes == df.height


def test_count_aggregate_applies_having():
    from src.db import count_aggregate

    assert (
        count_aggregate(
            select_sql='"acheteur_id", COUNT(*) AS "n"',
            group_by='"acheteur_id"',
            having="COUNT(*) > ?",
            params=[10**9],
        )
        == 0
    )
