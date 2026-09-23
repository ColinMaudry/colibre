"""Grilles « Top acheteurs / Top titulaires » paginées côté serveur (#142)."""

from src.utils.top_org_grid import (
    AGG_COLUMN,
    group_columns,
    top_org_filter_sql,
    top_org_sort_sql,
)


def test_group_columns_titulaire_inclut_type_identifiant():
    """add_links n'ajoute le lien SIRET que si titulaire_typeIdentifiant est là."""
    cols = group_columns("titulaire", ["titulaire_distance"])
    assert cols[:2] == ["titulaire_id", "titulaire_nom"]
    assert "titulaire_typeIdentifiant" in cols
    assert "titulaire_distance" in cols


def test_group_columns_acheteur_sans_type_identifiant():
    assert group_columns("acheteur") == ["acheteur_id", "acheteur_nom"]


def test_filtre_sur_le_nom_produit_un_where():
    where_sql, where_params, having_sql, having_params = top_org_filter_sql(
        {
            "titulaire_nom": {
                "filterType": "text",
                "type": "contains",
                "filter": "mairie",
            }
        },
        "titulaire",
    )
    assert where_sql != "TRUE"
    assert where_params  # valeur liée, jamais concaténée
    assert "mairie" in " ".join(str(p) for p in where_params).lower()
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_attributions_produit_un_having():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": 5}},
        "titulaire",
    )
    assert having_sql == "(COUNT(*) > ?)"
    assert having_params == [5]


def test_filtre_attributions_in_range():
    _, _, having_sql, having_params = top_org_filter_sql(
        {
            AGG_COLUMN: {
                "filterType": "number",
                "type": "inRange",
                "filter": 2,
                "filterTo": 7,
            }
        },
        "titulaire",
    )
    assert having_sql == "(COUNT(*) BETWEEN ? AND ?)"
    assert having_params == [2, 7]


def test_filtre_attributions_deux_conditions():
    _, _, having_sql, having_params = top_org_filter_sql(
        {
            AGG_COLUMN: {
                "filterType": "number",
                "operator": "AND",
                "conditions": [
                    {"filterType": "number", "type": "greaterThan", "filter": 2},
                    {"filterType": "number", "type": "lessThan", "filter": 9},
                ],
            }
        },
        "titulaire",
    )
    assert having_sql == "(COUNT(*) > ?) AND (COUNT(*) < ?)"
    assert having_params == [2, 9]


def test_filtre_attributions_valeur_decimale_non_tronquee():
    """AG Grid autorise une décimale ; elle ne doit pas être tronquée (5.5 -> 5)."""
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "lessThan", "filter": 5.5}},
        "titulaire",
    )
    assert having_sql == "(COUNT(*) < ?)"
    assert having_params == [5.5]


def test_filtre_attributions_valeur_non_numerique_ignoree():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": "abc"}},
        "titulaire",
    )
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_colonne_hors_perimetre_ignore():
    """Une colonne du schéma mais absente du GROUP BY ne doit pas filtrer."""
    where_sql, where_params, _, _ = top_org_filter_sql(
        {"objet": {"filterType": "text", "type": "contains", "filter": "route"}},
        "titulaire",
    )
    assert where_sql == "TRUE"
    assert where_params == []


def test_tri_par_defaut_attributions_puis_id():
    assert (
        top_org_sort_sql(None, "titulaire") == '"Attributions" DESC, "titulaire_id" ASC'
    )


def test_tri_explicite_puis_id():
    sql = top_org_sort_sql([{"colId": "titulaire_nom", "sort": "asc"}], "titulaire")
    assert sql == '"titulaire_nom" ASC, "titulaire_id" ASC'


def test_tri_sur_colonne_inconnue_ignore():
    sql = top_org_sort_sql(
        [{"colId": "objet; DROP TABLE decp", "sort": "asc"}], "titulaire"
    )
    assert sql == '"Attributions" DESC, "titulaire_id" ASC'
