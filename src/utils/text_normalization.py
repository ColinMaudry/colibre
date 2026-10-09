"""Normalisation de texte pour des filtres insensibles aux accents (#147).

Une colonne filtrable listée dans `NORMALIZED_COLUMNS` est doublée, dans la table
`decp`, d'une colonne précalculée où accents, ligatures et apostrophes
typographiques sont ramenés à leur forme simple. La saisie est normalisée en
Python (`normalize_text`), la colonne en SQL (`normalize_text_sql`) : les deux
doivent donner le même résultat.

Ce module n'importe rien du projet : il est utilisé par `src.db` comme par
`src.utils` et `src.api`.
"""

import unicodedata

# Colonne filtrable -> colonne précalculée dans `decp`.
NORMALIZED_COLUMNS: dict[str, str] = {"objet": "objet_normalise"}

# La casse n'est pas modifiée : c'est l'ILIKE qui l'ignore.
_REPLACEMENTS = {
    "œ": "oe",
    "Œ": "OE",
    "æ": "ae",
    "Æ": "AE",
    "’": "'",
}


def normalize_text(text: str) -> str:
    """Retire accents et marques combinantes, remplace ligatures et apostrophe
    typographique (`’` → `'`). Ne change pas la casse."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    for source, target in _REPLACEMENTS.items():
        stripped = stripped.replace(source, target)
    return stripped


def normalize_text_sql(expr: str) -> str:
    """Expression DuckDB équivalente à `normalize_text`, appliquée à `expr`
    (une expression SQL de colonne, ex. `objet` ou `"objet"`)."""
    sql = f"strip_accents({expr})"
    for source, target in _REPLACEMENTS.items():
        literal = target.replace("'", "''")
        sql = f"replace({sql}, '{source}', '{literal}')"
    return sql


def normalized_target(column: str, quoted_col: str) -> str:
    """Colonne à comparer à une saisie passée par `normalized_term` : la colonne
    précalculée (entre guillemets) si `column` est normalisée, sinon `quoted_col`."""
    if column in NORMALIZED_COLUMNS:
        return f'"{NORMALIZED_COLUMNS[column]}"'
    return quoted_col


def normalized_term(column: str, term: str) -> str:
    """Saisie normalisée si `column` l'est, sinon inchangée."""
    if column in NORMALIZED_COLUMNS:
        return normalize_text(term)
    return term
