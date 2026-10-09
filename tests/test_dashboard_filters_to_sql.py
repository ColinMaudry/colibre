from datetime import datetime, timedelta

import pytest

from src.utils.table_sql import dashboard_filters_to_sql


def test_no_filters_uses_default_365_day_window():
    where_sql, params = dashboard_filters_to_sql(operateurs=False)
    assert where_sql == '"dateNotification" > ?'
    assert len(params) == 1
    assert isinstance(params[0], datetime)
    expected = datetime.now() - timedelta(days=365)
    assert abs((params[0] - expected).total_seconds()) < 2


def test_year_filter_overrides_default_window():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]


def test_marche_type_equality():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_marche_type="Marché", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "type" = ?'
    assert params == [2025, "Marché"]


def test_innovant_value_all_is_skipped():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_marche_innovant="all", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]


def test_innovant_value_oui_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_marche_innovant="oui", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "marcheInnovant" = ?'
    assert params == [2025, "oui"]


def test_sous_traitance_value_non_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_sous_traitance_declaree="non",
        operateurs=False,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "sousTraitanceDeclaree" = ?'
    assert params == [2025, "non"]


def test_acheteur_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_acheteur_id="12345678900010", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%12345678900010%"]


def test_titulaire_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_titulaire_id="999", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]


def test_code_cpv_uses_prefix_like():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_marche_code_cpv="4521", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "codeCPV" LIKE ?'
    assert params == [2025, "4521%"]


def test_acheteur_departement_multiple_uses_in_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_departement_code=["75", "92", "93"],
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? AND "acheteur_departement_code" IN (?, ?, ?)'
    )
    assert params == [2025, "75", "92", "93"]


def test_acheteur_categorie_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_acheteur_categorie="Commune", operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_categorie" = ?'
    assert params == [2025, "Commune"]


def test_titulaire_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        'AND "titulaire_categorie" = ? '
        'AND "titulaire_departement_code" IN (?)'
    )
    assert params == [2025, "PME", "35"]


def test_acheteur_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_id="123",
        dashboard_acheteur_categorie="Commune",
        dashboard_acheteur_departement_code=["75"],
        operateurs=False,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%123%"]


def test_titulaire_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_id="999",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
        operateurs=False,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]


def test_marche_techniques_reste_un_ou():
    """Contrairement aux considérations, cocher plusieurs techniques élargit."""
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_techniques=["Enchère", "Accord-cadre"],
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"techniques\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Enchère", "Accord-cadre"]]


def test_considerations_sociales_uses_list_has_all():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_sociales=["Clause sociale"],
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_all(string_split(\"considerationsSociales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause sociale"]]


def test_considerations_environnementales_uses_list_has_all():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_environnementales=["Clause env."],
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_all(string_split(\"considerationsEnvironnementales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause env."]]


@pytest.mark.parametrize(
    "coche, attendus",
    [
        (["Clause sociale"], {"sociale", "sociale+critere", "critere+sociale"}),
        (["Clause sociale", "Critère social"], {"sociale+critere", "critere+sociale"}),
        (["Critère social", "Clause sociale"], {"sociale+critere", "critere+sociale"}),
        (["Clause sociale", "Marché réservé"], set()),
    ],
)
def test_considerations_multi_valeurs_est_un_et(coche, attendus):
    """Deux valeurs cochées = marchés portant les deux, pas l'une ou l'autre.

    Vérifié en exécutant le SQL produit : la sémantique de `list_has_all`
    compte plus que la chaîne générée. L'ordre des valeurs dans la colonne
    comme dans la sélection est indifférent.
    """
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE decp AS SELECT * FROM (VALUES
            ('sociale',         DATE '2025-01-01', 'Clause sociale'),
            ('critere',         DATE '2025-01-01', 'Critère social'),
            ('sociale+critere', DATE '2025-01-01', 'Clause sociale, Critère social'),
            ('critere+sociale', DATE '2025-01-01', 'Critère social, Clause sociale'),
            ('sans_objet',      DATE '2025-01-01', 'Sans objet')
        ) t(uid, "dateNotification", "considerationsSociales")
    """)

    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_sociales=coche,
        operateurs=False,
    )
    rows = con.execute(f"SELECT uid FROM decp WHERE {where_sql}", params).fetchall()
    assert {r[0] for r in rows} == attendus


def test_montant_min_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_montant_min=1000, operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant_rationalise" >= ?'
    assert params == [2025, 1000]


def test_montant_max_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_montant_max=500, operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant_rationalise" <= ?'
    assert params == [2025, 500]


def test_montant_zero_is_a_valid_lower_bound():
    # 0 est falsy mais reste un filtre valide (distinct de None)
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025", dashboard_montant_min=0, operateurs=False
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant_rationalise" >= ?'
    assert params == [2025, 0]


def test_montant_min_and_max_combined():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=100,
        dashboard_montant_max=1000,
        operateurs=False,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? AND "montant_rationalise" >= ? AND "montant_rationalise" <= ?'
    )
    assert params == [2025, 100, 1000]
