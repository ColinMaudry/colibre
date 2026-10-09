import unicodedata
from datetime import datetime, timedelta

import polars as pl
from unidecode import unidecode

from src.utils import logger


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


# Colonnes dont les valeurs sont déjà stockées sans accents (cf. #138) : seule
# la saisie utilisateur est désaccentuée pour matcher, comme sur /recherche.
_ACCENT_INSENSITIVE_COLUMNS = {"acheteur_nom", "titulaire_nom"}

# Colonnes qui contiennent de vrais accents et ligatures (#147) : la colonne ET
# la saisie sont normalisées (accents retirés, œ → oe, æ → ae) avant la
# comparaison, pour que « maitrise d'oeuvre » retrouve « Maîtrise d'œuvre ».
_ACCENT_NORMALIZED_COLUMNS = {"objet"}

_LIGATURES = {"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE"}


def _strip_accents_sql(expr: str) -> str:
    """Expression DuckDB équivalente à `_strip_accents` appliquée à `expr`."""
    sql = f"strip_accents({expr})"
    for ligature, replacement in _LIGATURES.items():
        sql = f"replace({sql}, '{ligature}', '{replacement}')"
    return sql


def _strip_accents(text: str) -> str:
    """Équivalent Python de `_strip_accents_sql`, pour que saisie et colonne
    soient normalisées de la même façon (ex. « ’ » reste « ’ » des deux côtés)."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    for ligature, replacement in _LIGATURES.items():
        stripped = stripped.replace(ligature, replacement)
    return stripped


def text_filter_target(column: str, quoted_col: str) -> str:
    """Expression SQL de la colonne, à comparer avec `normalize_text_term`."""
    if column in _ACCENT_NORMALIZED_COLUMNS:
        return _strip_accents_sql(quoted_col)
    return quoted_col


def normalize_text_term(column: str, term: str) -> str:
    """Saisie normalisée selon la colonne filtrée (cf. `text_filter_target`)."""
    if column in _ACCENT_NORMALIZED_COLUMNS:
        return _strip_accents(term)
    if column in _ACCENT_INSENSITIVE_COLUMNS:
        return unidecode(term)
    return term


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
    target = text_filter_target(column, quoted_col)

    params = []

    for term in terms:
        term = normalize_text_term(column, term)
        conditions.append(f"{target} ILIKE ?")

        if term.startswith("*") or term.endswith("*"):
            params.append(term.replace("*", "%"))
        elif "+" in term:
            params.append(f"%{term.replace('+', ' ')}%")
        else:
            params.append(f"%{term}%")

    where_clause = " AND ".join(conditions)
    return where_clause, params
