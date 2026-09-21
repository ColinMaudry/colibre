from dash import Input, Output, State, callback, ctx, dcc, html, register_page

from src.utils.seo import META_CONTENT

NAME = "Quelles données pour quelles étapes et quels seuils dans les marchés publics ?"

register_page(
    __name__,
    path="/etapes",
    title=f"{NAME} | colibre",
    name="Étapes et données",
    description=(
        "À chaque étape d'un marché public (programmation, publicité, "
        "attribution), quelles données sont publiées et à partir de quel "
        "seuil : DECP, BOAMP, JOUE, journaux d'annonces légales, Approch."
    ),
    image_url=META_CONTENT["image_url"],
)

# Contenu des fiches — à rédiger en Markdown.
# Clés barres : "bar-approch", "bar-jal", "bar-boamp", "bar-joue-marche",
#               "bar-decp", "bar-joue-attribution"
# Clés étapes (mobile) : "stage-programmation", "stage-publicite",
#                         "stage-attribution", "stage-contrat", "stage-paiement"
ALL_CONTENT: dict[str, str | None] = {
    "bar-approch": None,
    "bar-jal": None,
    "bar-boamp": None,
    "bar-joue-marche": None,
    "bar-decp": None,
    "bar-joue-attribution": None,
    "stage-programmation": None,
    "stage-publicite": None,
    "stage-attribution": None,
    "stage-contrat": None,
    "stage-paiement": None,
}

_BAR_IDS = [
    "bar-approch",
    "bar-jal",
    "bar-boamp",
    "bar-joue-marche",
    "bar-decp",
    "bar-joue-attribution",
]
_STAGE_IDS = [
    "stage-programmation",
    "stage-publicite",
    "stage-attribution",
    "stage-contrat",
    "stage-paiement",
]


def _lane(*bars):
    """Une ligne d'étape : fond segmenté en 5 + barres positionnées."""
    return html.Div(
        className="etapes-lane",
        children=[
            html.Div(
                className="etapes-segs",
                children=[html.Div() for _ in range(5)],
            ),
            *bars,
        ],
    )


def _bar(label, color, style, bar_id=None):
    base = {"backgroundColor": color}
    base.update(style)
    props = {"className": "etapes-bar", "style": base}
    if bar_id is not None:
        props["id"] = bar_id
        props["n_clicks"] = 0
    return html.Div(label, **props)


def build_chart():
    return html.Div(
        className="etapes-chart-scroll",
        children=html.Div(
            className="etapes-chart",
            children=[
                # En-tête : coin vide + 5 marqueurs de seuils
                html.Div(className="etapes-corner"),
                html.Div(
                    className="etapes-xhead",
                    children=[
                        html.Div("0 €", className="etapes-xcell"),
                        html.Div(
                            [html.Strong("40 000 €"), "seuil DECP"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("90 000 €"), "publicité"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("140 k€ / 216 k€"), "seuils formalisés (UE)"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("5,404 M€"), "travaux (UE)"],
                            className="etapes-xcell",
                        ),
                    ],
                ),
                # Programmation
                html.Div("Programmation", className="etapes-stage"),
                _lane(
                    _bar(
                        "Approch — sourcing / préinformation (non réglementaire)",
                        "var(--etape-approch)",
                        {"left": "2%", "right": "2%"},
                        bar_id="bar-approch",
                    ),
                ),
                # Publicité (appel d'offres)
                html.Div(["Publicité"], className="etapes-stage"),
                _lane(
                    _bar(
                        "JAL",
                        "var(--etape-jal)",
                        {"left": "40%", "right": "40%", "top": "6px", "height": "20px"},
                        bar_id="bar-jal",
                    ),
                    _bar(
                        "BOAMP",
                        "var(--etape-boamp)",
                        {"left": "40%", "right": "2%", "top": "28px", "height": "20px"},
                        bar_id="bar-boamp",
                    ),
                    _bar(
                        "JOUE — avis de marché",
                        "var(--etape-joue)",
                        {"left": "60%", "right": "2%", "top": "6px", "height": "20px"},
                        bar_id="bar-joue-marche",
                    ),
                ),
                # Attribution
                html.Div("Attribution", className="etapes-stage"),
                _lane(
                    _bar(
                        "DECP — données essentielles",
                        "var(--etape-decp)",
                        {"left": "20%", "right": "2%", "top": "6px", "height": "20px"},
                        bar_id="bar-decp",
                    ),
                    _bar(
                        "JOUE — avis d'attribution",
                        "var(--etape-joue)",
                        {"left": "60%", "right": "2%", "top": "28px", "height": "20px"},
                        bar_id="bar-joue-attribution",
                    ),
                ),
                # Contrat (vide)
                html.Div("Contrat", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
                # Paiement (vide)
                html.Div("Paiement", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
            ],
        ),
    )


# Données par étape, partagées par la vue mobile.
# Chaque tuple : (libellé étape, id CSS, [(libellé, couleur, plage seuils)]).
STAGES_MOBILE = [
    (
        "Programmation",
        "stage-programmation",
        [
            (
                "Approch",
                "var(--etape-approch)",
                "tous montants — publication non réglementaire",
            ),
        ],
    ),
    (
        "Publicité (appel d'offres)",
        "stage-publicite",
        [
            ("JAL", "var(--etape-jal)", "de 90 000 € au seuil formalisé"),
            ("BOAMP", "var(--etape-boamp)", "à partir de 90 000 €"),
            (
                "JOUE — avis de marché",
                "var(--etape-joue)",
                "à partir des seuils formalisés (140 k€ / 216 k€)",
            ),
        ],
    ),
    (
        "Attribution",
        "stage-attribution",
        [
            (
                "DECP — données essentielles",
                "var(--etape-decp)",
                "à partir de 40 000 €",
            ),
            (
                "JOUE — avis d'attribution",
                "var(--etape-joue)",
                "à partir des seuils formalisés",
            ),
        ],
    ),
    ("Contrat", "stage-contrat", []),
    ("Paiement", "stage-paiement", []),
]


def build_mobile():
    blocks = []
    for stage, stage_id, items in STAGES_MOBILE:
        if items:
            children = [
                html.Div(
                    [
                        html.I(style={"backgroundColor": color}),
                        html.Span(label, className="etapes-m-label"),
                        html.Span(seuil, className="etapes-m-seuil"),
                    ],
                    className="etapes-m-item",
                )
                for label, color, seuil in items
            ]
        else:
            children = [
                html.Div(
                    "aucune donnée publiée aujourd'hui",
                    className="etapes-m-item etapes-m-empty",
                )
            ]
        blocks.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.H4(stage, className="etapes-m-stage"),
                            html.Button(
                                "Voir fiche →",
                                id=stage_id,
                                n_clicks=0,
                                className="etapes-m-link",
                            ),
                        ],
                        className="etapes-m-header",
                    ),
                    *children,
                ],
                className="etapes-m-block",
            )
        )
    return html.Div(blocks, className="etapes-mobile")


layout = html.Div(
    className="container",
    children=[
        html.H2(NAME),
        dcc.Markdown(
            "Un marché public passe par plusieurs étapes. À chacune, des "
            "données peuvent être publiées — selon le montant du marché et "
            "des obligations réglementaires. Ce graphique situe les "
            "principales publications de données par **étape** (de haut en "
            "bas) et par **seuil** (de gauche à droite, en euros hors taxes)."
        ),
        build_chart(),
        build_mobile(),
        dcc.Store(id="etapes-selected", data=None),
        html.Div(id="etapes-detail", className="etapes-detail"),
        dcc.Markdown(
            "**À noter :** l'axe horizontal n'est pas linéaire — les seuils "
            "sont espacés régulièrement pour rester lisibles. Les étapes "
            "*Contrat* et *Paiement* n'ont aujourd'hui aucune donnée publiée "
            "en open data.",
            className="etapes-note",
        ),
    ],
)


@callback(
    Output("etapes-detail", "children"),
    Output("etapes-selected", "data"),
    [Input(id_, "n_clicks") for id_ in _BAR_IDS + _STAGE_IDS],
    State("etapes-selected", "data"),
    prevent_initial_call=True,
)
def _show_detail(*args):
    current = args[-1]
    triggered = ctx.triggered_id
    if triggered == current:
        return None, None
    content = ALL_CONTENT.get(triggered)
    if content is None:
        return dcc.Markdown(f"*Fiche en cours de rédaction.* {triggered}"), triggered
    return dcc.Markdown(content), triggered
