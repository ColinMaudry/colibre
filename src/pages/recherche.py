import math

import dash_bootstrap_components as dbc
import polars as pl
from dash import Input, Output, State, callback, dcc, html, register_page

from src.db import count_unique_marches, schema
from src.figures import client_grid
from src.pages.projet.abonnement import abonnement_features
from src.utils.cache import cache
from src.utils.data import DATA_SCHEMA, DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org
from src.utils.seo import META_CONTENT
from src.utils.table import format_number

NAME = "Recherche"

_STAT_STYLE = {"fontWeight": "bold", "color": "var(--primary-color-text)"}


#: Largeurs fixes des colonnes de résultats, en pixels. Les clés d'identifiant
#: et de nom sont données sans préfixe : les grilles acheteurs et titulaires
#: ont la même structure, seul le préfixe des deux premières colonnes change.
_RESULT_COLUMN_WIDTHS = {
    "_id": 173,
    "_nom": 247,
    "Département": 135,
    "Marchés": 95,
}


def _result_column_width(col: str) -> int | None:
    """Largeur fixe d'une colonne de résultats, ou None si elle n'en a pas."""
    for suffixe, largeur in _RESULT_COLUMN_WIDTHS.items():
        if col == suffixe or (suffixe.startswith("_") and col.endswith(suffixe)):
            return largeur
    return None


def _result_column_defs(dff: pl.DataFrame) -> list[dict]:
    """columnDefs des résultats de recherche (liens markdown, infobulle d'en-tête).

    Les largeurs sont fixes (cf. `_RESULT_COLUMN_WIDTHS`) : `flex` est donc
    absent du `defaultColDef` de la grille, sinon AG Grid étirerait les
    colonnes pour occuper toute la largeur et ignorerait ces valeurs.
    """
    defs = []
    for col in dff.columns:
        meta = DATA_SCHEMA.get(col, {})
        col_def = {
            "field": col,
            "headerName": meta.get("title", col),
            "cellRenderer": "markdown",
            "wrapText": True,
            "autoHeight": True,
        }
        largeur = _result_column_width(col)
        if largeur is not None:
            col_def["width"] = largeur
        if meta.get("description"):
            col_def["headerTooltip"] = meta["description"]
        defs.append(col_def)
    return defs


@cache.memoize(timeout=12 * 60 * 60)
def _vignette(nom: str, cible: str) -> html.Span:
    """Vignette de l'accueil, en deux versions : thème clair et thème sombre.

    Les deux images sont dans la page ; le CSS (`.vignette-claire` /
    `.vignette-sombre` dans style.css) n'en affiche qu'une selon
    `data-bs-theme`. Un simple `html.Img` piloté par callback clignoterait au
    chargement, le temps que le callback réponde, et le thème est déjà posé
    côté serveur sur `<html>` (cf. #118).
    """
    return html.Span(
        [
            html.Img(
                src=f"/assets/{nom}-thumbnail.png",
                alt=f"Aperçu de {cible}",
                className="vignette-claire",
            ),
            html.Img(
                src=f"/assets/{nom}-thumbnail-dark.png",
                alt=f"Aperçu de {cible}",
                className="vignette-sombre",
            ),
        ]
    )


def _tagline_stats() -> tuple[str, str, str]:
    nb_acheteurs = format_number(round(DF_ACHETEURS.height, -3))
    nb_titulaires = format_number(round(DF_TITULAIRES.height, -3))
    nb_marches_millions = math.floor(count_unique_marches() / 100_000) / 10
    unite_marches = "million" if nb_marches_millions < 2 else "millions"
    nb_marches = f"{nb_marches_millions:.1f}".replace(".", ",") + " " + unite_marches
    return nb_acheteurs, nb_titulaires, nb_marches


def _tagline() -> html.P:
    nb_acheteurs, nb_titulaires, nb_marches = _tagline_stats()
    return html.P(
        [
            "Recherchez parmi ",
            html.Span(nb_acheteurs, style=_STAT_STYLE),
            " acheteurs et ",
            html.Span(nb_titulaires, style=_STAT_STYLE),
            " titulaires dans une base de données de plus de ",
            html.Span(nb_marches, style=_STAT_STYLE),
            " de marchés publics",
        ]
    )


_features_gratuites = dcc.Markdown("""
- Recherche d'acheteurs et de titulaires
- [Tableau](/tableau) filtrable et personnalisable sur des dizaines de colonnes et exports Excel
- Cartes, statistiques et [Observatoire](/observatoire) national personnalisable
- Fiches détaillées : acheteur, titulaire, marché
- 100 % [open source](/projet/explorer) et [Open Data](/projet/donnees)
""")

home_intro = html.Div(
    id="home_intro",
    className="container px-4",
    style={"maxWidth": "900px", "marginTop": "1rem"},
    children=[
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.P(
                            [
                                "Trouvez exactement les marchés que vous cherchez grâce aux ",
                                html.Span(len(schema.names()), style=_STAT_STYLE),
                                " colonnes filtrables du ",
                                dcc.Link("Tableau", href="/tableau"),
                            ]
                        ),
                    ],
                    md=5,
                    className="text-center",
                ),
                dbc.Col(
                    [
                        html.P(
                            [
                                "Visualisez les données sous tous les angles dans l'",
                                dcc.Link("Observatoire", href="/observatoire"),
                            ]
                        ),
                    ],
                    # L'offset doit rester sur le breakpoint md : passé via
                    # `width` il s'appliquerait aussi en xs (col-5 offset-2),
                    # écrasant la colonne sur petit écran au lieu de la laisser
                    # s'empiler en pleine largeur.
                    md={"size": 5, "offset": 2},
                    # mt-5 : respiration quand les colonnes s'empilent (xs/sm) ;
                    # mt-md-0 : annulé dès qu'elles sont côte à côte. On n'utilise
                    # pas gy-* sur la Row : son margin-top négatif serait écrasé
                    # par le style inline marginTop de celle-ci.
                    className="text-center mt-5 mt-md-0",
                ),
            ],
            style={"marginTop": "6rem"},
            className="gx-5",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dcc.Link(
                            _vignette("table", "le tableau de données"), href="/tableau"
                        ),
                    ],
                    md=5,
                    className="text-center",
                ),
                dbc.Col(
                    [
                        dcc.Link(
                            _vignette("dashboard", "l'observatoire"),
                            href="/observatoire",
                        ),
                    ],
                    # L'offset doit rester sur le breakpoint md : passé via
                    # `width` il s'appliquerait aussi en xs (col-5 offset-2),
                    # écrasant la colonne sur petit écran au lieu de la laisser
                    # s'empiler en pleine largeur.
                    md={"size": 5, "offset": 2},
                    # mt-5 : respiration quand les colonnes s'empilent (xs/sm) ;
                    # mt-md-0 : annulé dès qu'elles sont côte à côte. On n'utilise
                    # pas gy-* sur la Row : son margin-top négatif serait écrasé
                    # par le style inline marginTop de celle-ci.
                    className="text-center mt-5 mt-md-0",
                ),
            ],
            className="gx-5",
        ),
        html.P(
            [
                html.Span(
                    "colibre",
                    style={
                        "fontWeight": 600,
                        "fontSize": "1.5rem",
                        "color": "var(--primary-color-text)",
                    },
                ),
                " ouvre les données des marchés publics français à toutes et "
                "tous : recherchez, filtrez, cartographiez, téléchargez.",
            ],
            className="text-center",
            style={
                "maxWidth": "750px",
                "fontSize": "1.5rem",
                "margin": "6rem auto 1.5rem",
            },
        ),
        dbc.Row(
            [
                dbc.Col(
                    [html.H4("✅ Gratuit, sans compte"), _features_gratuites],
                    md=6,
                    style={
                        "borderRight": "1px solid var(--bs-border-color)",
                        "paddingRight": "2rem",
                    },
                ),
                dbc.Col(
                    [
                        html.H4("⭐ Avec un abonnement"),
                        abonnement_features,
                        dcc.Link(
                            "En savoir plus et s'abonner",
                            href="/projet/abonnement",
                            style={"marginLeft": "20px"},
                        ),
                    ],
                    md=6,
                    style={"paddingLeft": "2rem"},
                ),
            ],
            className="align-items-start",
        ),
    ],
)

register_page(
    __name__,
    path="/",
    title="Outils pour l'exploration des marchés publics | colibre",
    name=NAME,
    description="Explorez et analysez les données des marchés publics français. Pour une commande publique accessible à toutes et tous.",
    image_url=META_CONTENT["image_url"],
    order=0,
)


def layout(**_):
    return html.Div(
        className="container",
        children=[
            html.Div(
                className="tagline",
                children=_tagline(),
            ),
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "marginTop": "30px",
                    "marginBottom": "30px",
                },
                children=[
                    dcc.Input(
                        id="search",
                        type="text",
                        placeholder="Nom d'acheteur/entreprise, SIREN/SIRET, code département",
                        autoFocus=True,
                        style={
                            "margin": "0",
                            "width": "500px",
                            "border": "1px solid #ccc",
                            "borderRight": "none",
                            "borderRadius": "3px 0 0 3px",
                            "padding": "5px 10px",
                            "outline": "none",
                            "height": "34px",
                        },
                    ),
                    html.Button(
                        "=>",
                        id="search-button",
                        className="btn btn-secondary",
                        style={
                            "border": "1px solid #ccc",
                            "borderRadius": "0 3px 3px 0",
                            "marginLeft": "0",
                            "height": "34px",
                            # Le padding vertical (.375rem) et le line-height
                            # (1.5) de .btn dépassent la hauteur fixe de 34px :
                            # le glyphe débordait vers le bas. On centre en flex
                            # et on neutralise le padding vertical.
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "paddingTop": "0",
                            "paddingBottom": "0",
                            "lineHeight": "1",
                        },
                    ),
                ],
            ),
            home_intro,
            # html.Div(
            #     className="search_options",
            #     children=[dcc.RadioItems(options=["Acheteur(s)"])],
            # ),
            dbc.Row(id="search_results"),
        ],
    )


@callback(
    Output("search_results", "children"),
    Output("home_intro", "style"),
    Input("search", "n_submit"),
    Input("search-button", "n_clicks"),
    State("search", "value"),
    prevent_initial_call=True,
)
def update_search_results(n_submit, n_clicks, query):
    if query and len(query) >= 1:
        cols = []

        for org_type in ["acheteur", "titulaire"]:
            if org_type == "acheteur":
                dff = DF_ACHETEURS
            elif org_type == "titulaire":
                dff = DF_TITULAIRES
            else:
                raise ValueError(f"{org_type} is not supported")

            # Search acheteurs and titulaires using the same function
            results = search_org(dff, query, org_type=org_type)
            count = results.height

            col = (
                dbc.Col(
                    children=[
                        html.H3(f"{org_type.title()}s : {count}"),
                        client_grid(
                            f"results_{org_type}_datatable",
                            _result_column_defs(results),
                            results.to_dicts(),
                            page_size=10,
                            defaultColDef={
                                "sortable": False,
                                "filter": False,
                            },
                        ),
                    ],
                    md=6,
                )
                if count > 0
                else html.P(f"Aucun {org_type} trouvé.")
            )
            cols.append(col)

        return cols, {"display": "none"}
    return html.P(""), home_intro.style
