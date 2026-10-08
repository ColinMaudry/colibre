"""Pastilles des filtres appliqués au-dessus des grilles AG Grid (#148).

Une pastille par colonne filtrée, dans la ligne `.table-meta` de la page
Tableau et des fiches acheteur/titulaire : « **Libellé** opérateur valeur × ».
"""

from src.figures import DATA_SCHEMA
from src.utils.table import format_number

_OPERATEURS = {
    "equals": "=",
    "notEqual": "≠",
    "lessThan": "<",
    "lessThanOrEqual": "≤",
    "greaterThan": ">",
    "greaterThanOrEqual": "≥",
    "contains": "contient",
    "notContains": "ne contient pas",
    "startsWith": "commence par",
    "endsWith": "se termine par",
    "blank": "est vide",
    "notBlank": "n'est pas vide",
}
_SANS_VALEUR = {"blank", "notBlank"}
_JOINTURES = {"AND": " et ", "OR": " ou "}


def _valeur(filter_type: str, value) -> str:
    if value is None:
        return ""
    if filter_type == "date":
        # AG Grid : "AAAA-MM-JJ hh:mm:ss" → JJ/MM/AAAA
        annee, mois, jour = str(value)[:10].split("-")
        return f"{jour}/{mois}/{annee}"
    if filter_type == "number":
        return format_number(value) or str(value)  # format_number(0) == ""
    return str(value)


def _condition(spec: dict) -> str:
    filter_type = spec.get("filterType")
    type_ = spec.get("type")
    operateur = _OPERATEURS.get(type_, type_)
    if type_ in _SANS_VALEUR:
        return operateur
    if filter_type == "date":
        debut, fin = spec.get("dateFrom"), spec.get("dateTo")
    else:
        debut, fin = spec.get("filter"), spec.get("filterTo")
    if type_ == "inRange":
        return f"entre {_valeur(filter_type, debut)} et {_valeur(filter_type, fin)}"
    return f"{operateur} {_valeur(filter_type, debut)}"


def describe_filter(col: str, spec: dict) -> tuple[str, str]:
    """(libellé de la colonne, expression du filtre) pour une entrée de filterModel."""
    label = DATA_SCHEMA.get(col, {}).get("title", col)
    conditions = spec.get("conditions")
    if conditions:
        jointure = _JOINTURES.get(spec.get("operator"), " et ")
        return label, jointure.join(_condition(c) for c in conditions)
    return label, _condition(spec)
