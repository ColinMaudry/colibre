import polars as pl
from unidecode import unidecode

from src.utils.table import add_links


def search_org(dff: pl.DataFrame, query: str, org_type: str) -> pl.DataFrame:
    """
    Search in either 'acheteur' or 'titulaire' DataFrame.

    :param dff: Polars DataFrame with acheteur or titulaire columns
    :param query: User search string
    :param org_type: 'acheteur' or 'titulaire'
    :return: Filtered DataFrame with 'matches' column
    """
    if not query.strip():
        return dff.select(pl.lit(False).alias("matches"))

    # Normalize query
    normalized_query = unidecode(query.strip()).upper()
    tokens = [" " + t.strip() for t in normalized_query.split() if t.strip()]

    # Define columns based on entity type
    cols = [
        f"{org_type}_id",
        f"{org_type}_nom",
        f"{org_type}_departement_nom",
        f"{org_type}_departement_code",
        f"{org_type}_commune_nom",
    ]

    # Concatenate all fields into one string per row
    org_str = pl.concat_str(pl.lit(" "), pl.col(cols), separator=" ").str.replace(
        "-", " "
    )

    # For each token, create a boolean column: True if token is found
    token_matches = []
    for token in tokens:
        token_match = org_str.str.contains(token).alias(f"token_{token}")
        token_matches.append(token_match)

    # Count how many tokens match per row
    match_score = pl.sum_horizontal(token_matches).alias("match_score")

    # For each token, create a boolean column: True if token is found
    token_matches = []
    for token in tokens:
        token_match = org_str.str.contains(token).alias(f"token_{token}")
        token_matches.append(token_match)

    # Sélection des colonnes
    if org_type == "acheteur":
        dff = dff.select(cols + ["Marchés"])
    if org_type == "titulaire":
        dff = dff.select(cols + ["Marchés", "titulaire_typeIdentifiant"])

    # Apply and filter
    dff = (
        dff.with_columns(token_matches + [match_score])
        .filter(pl.col("match_score") == len(tokens))
        .drop([f"token_{token}" for token in tokens])
    )

    # Format result
    dff = add_links(dff)
    dff = dff.with_columns(
        pl.concat_str(
            pl.col(f"{org_type}_departement_nom"),
            pl.lit(" ("),
            pl.col(f"{org_type}_departement_code"),
            pl.lit(")"),
        ).alias("Département")
    )

    dff = dff.select(f"{org_type}_id", f"{org_type}_nom", "Département", "Marchés")
    dff = dff.group_by(f"{org_type}_id", f"{org_type}_nom", "Département").sum()
    dff = dff.sort("Marchés", descending=True)

    return dff
