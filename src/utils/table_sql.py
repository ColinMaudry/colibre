from datetime import datetime, timedelta

import polars as pl
from unidecode import unidecode

from src.utils import logger
from src.utils.table import split_filter_part


def filter_query_to_sql(filter_query: str, schema: pl.Schema) -> tuple[str, list]:
    """Traduit le DSL de filtres de dash_table.DataTable en fragment SQL DuckDB.

    Retourne (where_clause, params) où where_clause est un fragment à injecter
    après WHERE et params est la liste des valeurs à passer à
    cursor.execute(sql, params). Les identifiants de colonnes sont validés
    contre le schéma fourni ; jamais concaténés avec des valeurs utilisateur.
    """
    if not filter_query:
        return "TRUE", []

    clauses: list[str] = []
    params: list = []

    for part in filter_query.split(" && "):
        col_name, operator, raw_value = split_filter_part(part)
        if not isinstance(col_name, str) or not isinstance(raw_value, str):
            continue

        if col_name not in schema.names():
            logger.warning(f"Colonne inconnue ignorée : {col_name!r}")
            continue

        col_type = schema[col_name]
        is_numeric = col_type.is_numeric()
        col_is_date = col_type == pl.Date
        quoted_col = f'"{col_name}"'

        if is_numeric:
            try:
                value = int(raw_value) if col_type.is_integer() else float(raw_value)
            except ValueError:
                logger.warning(f"Valeur numérique invalide ignorée : {raw_value!r}")
                continue

            if operator == "contains":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} = ?")
            elif operator == ">":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} > ?")
            elif operator == "<":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} < ?")
            else:
                logger.warning(f"Opérateur invalide pour numérique : {operator!r}")
                continue
            params.append(value)
            continue

        # String / Date : toujours traité comme texte (parité avec Polars)
        value = raw_value.strip('"')

        if operator == "contains":
            if col_is_date:
                target = f"CAST({quoted_col} AS VARCHAR)"

            if col_name in ("acheteur_id", "titulaire_id"):
                value = value.replace(" ", "")
            where_clause, param_list = tokenize_text_filter(
                col_name, value, col_is_date
            )
            clauses.append(where_clause)
            params.extend(param_list)
            logger.debug(params)
            continue

        elif operator in (">", "<"):
            target = f"CAST({quoted_col} AS VARCHAR)" if col_is_date else quoted_col
            clauses.append(f"{quoted_col} IS NOT NULL AND {target} {operator} ?")
            params.append(value)
        else:
            logger.warning(f"Opérateur invalide pour chaîne : {operator!r}")
            continue

    if not clauses:
        return "TRUE", []
    return " AND ".join(clauses), params


def sort_by_to_sql(sort_by: list[dict] | None, schema: pl.Schema) -> str:
    """Traduit sort_by (format Dash) en clause ORDER BY DuckDB.

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
        where_clause, param_list = tokenize_text_filter("objet", dashboard_marche_objet)
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


# Colonnes dont les valeurs sont déjà stockées sans accents (cf. #138) : la
# saisie utilisateur est désaccentuée pour matcher, comme sur /recherche.
# Les autres colonnes texte (ex. "objet") contiennent de vrais accents et ne
# doivent pas être désaccentuées, ni côté colonne ni côté saisie.
_ACCENT_INSENSITIVE_COLUMNS = {"acheteur_nom", "titulaire_nom"}


def tokenize_text_filter(
    column: str, text: str, col_is_date: bool = False
) -> tuple[str, list]:
    terms = text.split()
    # si col_is_date alors le deuxième doit être casté en VARCHAR
    if col_is_date:
        quoted_col = f'CAST("{column}" AS VARCHAR)'
    else:
        quoted_col = f'"{column}"'

    conditions = [f'"{column}" IS NOT NULL', f"{quoted_col} <> ''"]

    params = []
    strip_query_accents = column in _ACCENT_INSENSITIVE_COLUMNS

    for term in terms:
        if strip_query_accents:
            term = unidecode(term)
        conditions.append(f"{quoted_col} ILIKE ?")

        if term.startswith("*") or term.endswith("*"):
            params.append(term.replace("*", "%"))
        elif "+" in term:
            params.append(f"%{term.replace('+', ' ')}%")
        else:
            params.append(f"%{term}%")

    where_clause = " AND ".join(conditions)
    return where_clause, params
