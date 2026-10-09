"""Pastilles des filtres appliqués au-dessus des grilles AG Grid (#148).

Une pastille par colonne filtrée, dans la ligne `.table-meta` de la page
Tableau et des fiches acheteur/titulaire : « **Libellé** opérateur valeur × ».
"""

from typing import NamedTuple

from dash import (
    ALL,
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate

from src.figures import DATA_SCHEMA
from src.utils.table import format_number, get_default_hidden_columns
from src.utils.text_query import analyser, en_texte, libelle_corrections

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
_TEXTE_BOOLEEN = {"contains", "notContains"}
_EXPRESSION_VIDE = {"contains": "n'est pas vide", "notContains": "est vide"}

BANNIERE_OPERATEURS = (
    "Les opérateurs OU, ET, PAS et les parenthèses sont réservés aux abonné·es."
)


class Description(NamedTuple):
    label: str
    expression: str
    corrigee: bool
    operateurs_ignores: bool


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


def _condition(spec: dict, operateurs: bool) -> tuple[str, bool, bool]:
    """(texte, corrigée, opérateurs ignorés) d'une condition du filterModel."""
    filter_type = spec.get("filterType")
    type_ = spec.get("type")
    operateur = _OPERATEURS.get(type_, type_)
    if type_ in _SANS_VALEUR:
        return operateur, False, False
    if filter_type == "text" and type_ in _TEXTE_BOOLEEN:
        # Décrit le filtre réellement appliqué par le SQL (#97)
        expression = analyser(str(spec.get("filter") or ""), operateurs)
        texte = en_texte(expression)
        if not texte:
            operateur = _EXPRESSION_VIDE[type_]
        resultat = f"{operateur} {texte}" if texte else operateur
        if expression.corrections:
            resultat += f" ({libelle_corrections(expression)})"
        return (
            resultat,
            bool(expression.corrections),
            expression.operateurs_ignores,
        )
    if filter_type == "date":
        debut, fin = spec.get("dateFrom"), spec.get("dateTo")
    else:
        debut, fin = spec.get("filter"), spec.get("filterTo")
    if type_ == "inRange":
        texte = f"entre {_valeur(filter_type, debut)} et {_valeur(filter_type, fin)}"
        return texte, False, False
    return f"{operateur} {_valeur(filter_type, debut)}", False, False


def describe_filter(col: str, spec: dict, operateurs: bool) -> Description:
    """Description d'une entrée de filterModel : libellé de la colonne,
    expression appliquée, corrections éventuelles et opérateurs ignorés
    (`operateurs` : l'utilisateur·ice est abonné·e)."""
    label = DATA_SCHEMA.get(col, {}).get("title", col)
    conditions = spec.get("conditions") or [spec]
    jointure = _JOINTURES.get(spec.get("operator"), " et ")
    resultats = [_condition(c, operateurs) for c in conditions]
    return Description(
        label,
        jointure.join(texte for texte, _, _ in resultats),
        any(corrigee for _, corrigee, _ in resultats),
        any(ignores for _, _, ignores in resultats),
    )


def banniere_operateurs() -> html.Span:
    """Bandeau signalant aux non-abonné·es que les opérateurs sont ignorés."""
    return html.Span(
        [
            BANNIERE_OPERATEURS,
            " ",
            html.A("S'abonner", href="/projet/abonnement"),
        ],
        className="filter-pills-banniere",
    )


def filter_pills(filter_model: dict | None, context: str, operateurs: bool) -> list:
    """Une pastille par colonne filtrée, dans l'ordre du filterModel.

    Corps et croix sont deux boutons frères : un clic sur la croix ne compte
    pas comme un clic sur la pastille (pas de propagation vers un parent à id).
    Pastille signalée si la saisie a été corrigée ; bandeau en fin de liste si
    des opérateurs ont été ignorés (non abonné·e).
    """
    pills = []
    ignores = False
    for col, spec in (filter_model or {}).items():
        desc = describe_filter(col, spec, operateurs)
        ignores = ignores or desc.operateurs_ignores
        pills.append(
            html.Span(
                [
                    html.Button(
                        [html.Strong(desc.label), " " + desc.expression],
                        id={"type": f"{context}-filter-pill", "col": col},
                        className="filter-pill-body",
                        title="Modifier ce filtre",
                    ),
                    html.Button(
                        "×",
                        id={"type": f"{context}-filter-pill-remove", "col": col},
                        className="filter-pill-remove",
                        title=f"Supprimer le filtre {desc.label}",
                    ),
                ],
                className="filter-pill filter-pill-warning"
                if desc.corrigee
                else "filter-pill",
            )
        )
    if not operateurs and ignores:
        pills.append(banniere_operateurs())
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


def colonnes_masquees_sans(
    col: str, colonnes_masquees: list | None, context: str
) -> list | None:
    """Colonnes masquées sans `col` (store à None = colonnes masquées par
    défaut de la page). None si `col` est déjà affichée : pas de réécriture."""
    reference = (
        colonnes_masquees
        if colonnes_masquees is not None
        else get_default_hidden_columns(context)
    )
    if col not in reference:
        return None
    return [c for c in reference if c != col]


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
        from src.pages._compte_shell import current_user_has_subscription

        return filter_pills(
            _premier(filter_model), context, current_user_has_subscription()
        )

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
            # Re-rendu des pastilles. PreventUpdate et non [no_update] : sur
            # les fiches, la sortie filterModel est un motif ALL, qui exige
            # une liste (Dash refuse un NoUpdate à sa place).
            raise PreventUpdate
        if isinstance(filter_model, list):  # grilles des fiches (ALL)
            nouveau = [filter_model_sans(fm, col) for fm in filter_model]
        else:
            nouveau = filter_model_sans(filter_model, col)
        # Le filterModel posé par callback a la source 'api' : ignoré par
        # hideShareOnUserAction, on efface donc active-view ici (Tableau).
        return [nouveau, None][: len(sorties)]

    # Clic sur une pastille : 1) affiche la colonne si elle est masquée, via le
    # store du sélecteur « Colonnes » (régénère les columnDefs et garde les
    # cases à cocher cohérentes) ; 2) côté client, attend que la colonne soit
    # affichée puis place le curseur dans son filtre (src/assets/filter_pills.js).
    pastille = Input({"type": f"{context}-filter-pill", "col": ALL}, "n_clicks")

    @callback(
        Output(f"{context}-hidden-columns", "data", allow_duplicate=True),
        pastille,
        State(f"{context}-hidden-columns", "data"),
        prevent_initial_call=True,
    )
    def _devoiler(_n_clicks, colonnes_masquees):
        col = col_cliquee(ctx.triggered_id, ctx.triggered[0]["value"])
        if col is None:
            return no_update
        nouvelles = colonnes_masquees_sans(col, colonnes_masquees, context)
        return nouvelles if nouvelles is not None else no_update

    clientside_callback(
        ClientsideFunction("filterPills", "focusFilter"),
        pastille,
        State(grid_id, "id"),
        prevent_initial_call=True,
    )
