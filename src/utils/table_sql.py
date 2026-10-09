from datetime import datetime, timedelta

import polars as pl

from src.utils import logger
from src.utils.text_query import analyser, en_sql


def sort_by_to_sql(sort_by: list[dict] | None, schema: pl.Schema) -> str:
    """Traduit une liste de {column_id, direction} en clause ORDER BY DuckDB.

    Retourne '' si pas de tri (aucun ORDER BY à ajouter).
    """
    if not sort_by:
        return ""

    fragments: list[str] = []
    for entry in sort_by:
        col = entry.get("column_id")
        direction = entry.get("direction")
        if col not in schema.names():
            logger.warning(f"Tri sur colonne inconnue ignoré : {col!r}")
            continue
        if direction not in ("asc", "desc"):
            logger.warning(f"Tri sur direction inconnue ignoré : {direction!r}")
            continue
        fragments.append(f'"{col}" {direction.upper()} NULLS LAST')

    return ", ".join(fragments)


def dashboard_filters_to_sql(
    dashboard_year=None,
    dashboard_acheteur_id=None,
    dashboard_acheteur_categorie=None,
    dashboard_acheteur_departement_code=None,
    dashboard_titulaire_id=None,
    dashboard_titulaire_categorie=None,
    dashboard_titulaire_departement_code=None,
    dashboard_marche_type=None,
    dashboard_marche_objet=None,
    dashboard_marche_code_cpv=None,
    dashboard_marche_considerations_sociales=None,
    dashboard_marche_considerations_environnementales=None,
    dashboard_marche_techniques=None,
    dashboard_marche_innovant=None,
    dashboard_marche_sous_traitance_declaree=None,
    dashboard_montant_min=None,
    dashboard_montant_max=None,
    *,
    operateurs: bool,
) -> tuple[str, list]:
    """Traduit les filtres du tableau de bord en (where_clause, params) DuckDB."""
    clauses: list[str] = []
    params: list = []

    if dashboard_year:
        clauses.append('YEAR("dateNotification") = ?')
        params.append(int(dashboard_year))
    else:
        clauses.append('"dateNotification" > ?')
        params.append(datetime.now() - timedelta(days=365))

    if dashboard_acheteur_id:
        dashboard_acheteur_id = dashboard_acheteur_id.replace(" ", "")
        clauses.append('"acheteur_id" LIKE ?')
        params.append(f"%{dashboard_acheteur_id}%")
    else:
        if dashboard_acheteur_categorie:
            clauses.append('"acheteur_categorie" = ?')
            params.append(dashboard_acheteur_categorie)
        if dashboard_acheteur_departement_code:
            placeholders = ", ".join(["?"] * len(dashboard_acheteur_departement_code))
            clauses.append(f'"acheteur_departement_code" IN ({placeholders})')
            params.extend(dashboard_acheteur_departement_code)

    if dashboard_titulaire_id:
        dashboard_titulaire_id = dashboard_titulaire_id.replace(" ", "")
        clauses.append('"titulaire_id" LIKE ?')
        params.append(f"%{dashboard_titulaire_id}%")
    else:
        if dashboard_titulaire_categorie:
            clauses.append('"titulaire_categorie" = ?')
            params.append(dashboard_titulaire_categorie)
        if dashboard_titulaire_departement_code:
            placeholders = ", ".join(["?"] * len(dashboard_titulaire_departement_code))
            clauses.append(f'"titulaire_departement_code" IN ({placeholders})')
            params.extend(dashboard_titulaire_departement_code)

    if dashboard_marche_type:
        clauses.append('"type" = ?')
        params.append(dashboard_marche_type)

    if dashboard_marche_objet:
        where_clause, param_list = en_sql(
            analyser(dashboard_marche_objet, operateurs), "objet"
        )
        clauses.append(where_clause)
        params.extend(param_list)

    if dashboard_marche_code_cpv:
        clauses.append('"codeCPV" LIKE ?')
        params.append(f"{dashboard_marche_code_cpv}%")

    if dashboard_marche_innovant and dashboard_marche_innovant != "all":
        clauses.append('"marcheInnovant" = ?')
        params.append(dashboard_marche_innovant)

    if (
        dashboard_marche_sous_traitance_declaree
        and dashboard_marche_sous_traitance_declaree != "all"
    ):
        clauses.append('"sousTraitanceDeclaree" = ?')
        params.append(dashboard_marche_sous_traitance_declaree)

    # Techniques d'achat : `list_has_any`, cocher plusieurs techniques élargit
    # la sélection. Les considérations juste en dessous font l'inverse.
    if dashboard_marche_techniques:
        clauses.append("list_has_any(string_split(\"techniques\", ', '), ?::VARCHAR[])")
        params.append(list(dashboard_marche_techniques))

    # `list_has_all` : cocher deux considérations veut dire « marchés portant
    # les deux », pas « l'une ou l'autre ». Ces colonnes stockent plusieurs
    # valeurs par ligne, jointes par ', ' (ex. "Critère social, Clause sociale"),
    # un ET y a donc du sens — contrairement aux dropdowns Département,
    # scalaires par ligne, qui restent en IN (...).
    if dashboard_marche_considerations_sociales:
        clauses.append(
            "list_has_all(string_split(\"considerationsSociales\", ', '), ?::VARCHAR[])"
        )
        params.append(list(dashboard_marche_considerations_sociales))

    if dashboard_marche_considerations_environnementales:
        clauses.append(
            "list_has_all(string_split(\"considerationsEnvironnementales\", ', '), ?::VARCHAR[])"
        )
        params.append(list(dashboard_marche_considerations_environnementales))

    if dashboard_montant_min is not None:
        clauses.append('"montant_rationalise" >= ?')
        params.append(dashboard_montant_min)

    if dashboard_montant_max is not None:
        clauses.append('"montant_rationalise" <= ?')
        params.append(dashboard_montant_max)

    return " AND ".join(clauses), params
