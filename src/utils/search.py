import polars as pl

from src.utils.table import add_links
from src.utils.text_normalization import COLONNE_RECHERCHE, normalize_text


def search_org(dff: pl.DataFrame, query: str, org_type: str) -> pl.DataFrame:
    """
    Search in either 'acheteur' or 'titulaire' DataFrame.

    The frame must come from `build_org_frame` (src/utils/data.py): it carries
    a precomputed `recherche_normalisee` column, against which the query is
    matched case- and accent-insensitively (#150).

    :param dff: Polars DataFrame built by `build_org_frame`
    :param query: User search string
    :param org_type: 'acheteur' or 'titulaire'
    :return: Matching organisations (id, nom, Département, Marchés), empty
        when the query holds nothing to search for
    """
    # Normalize query the same way `build_org_frame` normalized the frame:
    # lowercase, no accents, hyphens as spaces.
    normalized_query = normalize_text(query.strip()).lower().replace("-", " ")
    tokens = [" " + token for token in normalized_query.split() if token]

    # Blank query, or hyphens and spaces only: no token, so no result (and
    # `pl.sum_horizontal` would fail on an empty list). Same columns as a
    # normal result, so callers can read `{org_type}_id` either way.
    if not tokens:
        return pl.DataFrame(
            schema={
                f"{org_type}_id": pl.String,
                f"{org_type}_nom": pl.String,
                "Département": pl.String,
                "Marchés": dff.schema["Marchés"],
            }
        )

    # Columns kept for display only: what is searchable is set by
    # `champs_recherches`, concatenated into COLONNE_RECHERCHE by
    # `build_org_frame`.
    colonnes_affichees = [
        f"{org_type}_id",
        f"{org_type}_nom",
        f"{org_type}_departement_nom",
        f"{org_type}_departement_code",
        f"{org_type}_commune_nom",
    ]

    # For each token, create a boolean column: True if token is found
    # (literal match: the query is never a regular expression).
    token_matches = [
        pl.col(COLONNE_RECHERCHE)
        .str.contains(token, literal=True)
        .alias(f"token_{token}")
        for token in tokens
    ]

    # Count how many tokens match per row
    match_score = pl.sum_horizontal(token_matches).alias("match_score")

    # Column selection
    if org_type == "acheteur":
        dff = dff.select(colonnes_affichees + ["Marchés", COLONNE_RECHERCHE])
    if org_type == "titulaire":
        dff = dff.select(
            colonnes_affichees
            + ["Marchés", "titulaire_typeIdentifiant", COLONNE_RECHERCHE]
        )

    # Apply and filter
    dff = (
        dff.with_columns(token_matches + [match_score])
        .filter(pl.col("match_score") == len(tokens))
        .drop(
            [f"token_{token}" for token in tokens] + [COLONNE_RECHERCHE, "match_score"]
        )
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
