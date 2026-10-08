"""Pastilles des filtres appliqués au-dessus des grilles AG Grid (#148).

Une pastille par colonne filtrée, dans la ligne `.table-meta` de la page
Tableau et des fiches acheteur/titulaire : « **Libellé** opérateur valeur × ».
"""

from dash import ALL, Input, Output, State, callback, ctx, html, no_update

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


def filter_pills(filter_model: dict | None, context: str) -> list:
    """Une pastille par colonne filtrée, dans l'ordre du filterModel.

    Corps et croix sont deux boutons frères : un clic sur la croix ne compte
    pas comme un clic sur la pastille (pas de propagation vers un parent à id).
    """
    pills = []
    for col, spec in (filter_model or {}).items():
        label, expression = describe_filter(col, spec)
        pills.append(
            html.Span(
                [
                    html.Button(
                        [html.Strong(label), " " + expression],
                        id={"type": f"{context}-filter-pill", "col": col},
                        className="filter-pill-body",
                        title="Modifier ce filtre",
                    ),
                    html.Button(
                        "×",
                        id={"type": f"{context}-filter-pill-remove", "col": col},
                        className="filter-pill-remove",
                        title=f"Supprimer le filtre {label}",
                    ),
                ],
                className="filter-pill",
            )
        )
    return pills


def filter_model_sans(filter_model: dict | None, col: str) -> dict:
    """Copie du filterModel sans le filtre de `col`."""
    return {c: spec for c, spec in (filter_model or {}).items() if c != col}


def col_cliquee(triggered_id, triggered_value) -> str | None:
    """Colonne de la pastille cliquée, ou None si le déclenchement vient d'un
    (re)rendu des pastilles (nouveaux boutons, n_clicks à None)."""
    if not isinstance(triggered_id, dict) or not triggered_value:
        return None
    return triggered_id.get("col")


def _premier(valeur):
    """Grilles des fiches (id pattern-matching ALL) : liste d'une valeur au plus."""
    if isinstance(valeur, list):
        return valeur[0] if valeur else None
    return valeur


def register_filter_pills_callbacks(
    context: str, grid_id: "str | dict", clear_active_view: bool = False
) -> None:
    """Callbacks des pastilles pour une page (`tableau`, `acheteur`, `titulaire`).

    `grid_id` : id fixe de la grille, ou motif ALL pour les grilles des fiches.
    """

    @callback(
        Output(f"{context}-filter-pills", "children"),
        Input(grid_id, "filterModel"),
    )
    def _render(filter_model):
        return filter_pills(_premier(filter_model), context)

    sorties = [Output(grid_id, "filterModel", allow_duplicate=True)]
    if clear_active_view:
        sorties.append(Output("active-view", "data", allow_duplicate=True))

    @callback(
        sorties,  # liste : le retour est toujours une liste, même à une sortie
        Input({"type": f"{context}-filter-pill-remove", "col": ALL}, "n_clicks"),
        State(grid_id, "filterModel"),
        prevent_initial_call=True,
    )
    def _remove(_n_clicks, filter_model):
        col = col_cliquee(ctx.triggered_id, ctx.triggered[0]["value"])
        if col is None:
            return [no_update] * len(sorties)
        if isinstance(filter_model, list):  # grilles des fiches (ALL)
            nouveau = [filter_model_sans(fm, col) for fm in filter_model]
        else:
            nouveau = filter_model_sans(filter_model, col)
        # Le filterModel posé par callback a la source 'api' : ignoré par
        # hideShareOnUserAction, on efface donc active-view ici (Tableau).
        return [nouveau, None][: len(sorties)]
