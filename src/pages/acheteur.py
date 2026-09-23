import datetime
import json

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    MATCH,
    Input,
    Output,
    State,
    callback,
    dcc,
    html,
    no_update,
    register_page,
)

from src.db import aggregate_marches, count_marches, query_marches, schema
from src.figures import (
    get_distance_histogram,
    get_org_location_map,
    make_card,
    make_column_picker,
)
from src.utils.data import DF_ACHETEURS, get_annuaire_data, get_departement_region
from src.utils.entity_grid import entity_scope, register_entity_grid_callbacks
from src.utils.frontend import DROPDOWN_LABELS_FR, get_button_properties
from src.utils.seo import META_CONTENT, make_org_jsonld
from src.utils.table import (
    format_number,
    get_default_hidden_columns,
    hidden_columns_from_selection,
    selection_from_hidden_columns,
    write_styled_excel,
)
from src.utils.top_org_grid import (
    CARD_MIN_HEIGHT,
    GRID_TYPE,
    fetch_top_org_page,
    scope_key,
    top_org_grid,
)
from src.utils.tracking import track_download


def get_title(acheteur_id: str | None = None) -> str:
    acheteur_nom = DF_ACHETEURS.filter(pl.col("acheteur_id") == acheteur_id).select(
        "acheteur_nom"
    )
    if acheteur_nom.height > 0:
        return f"Marchés publics attribués par {acheteur_nom.item(0, 0)} | colibre"
    return "Marchés publics attribués | colibre"


def get_description(acheteur_id: str | None = None) -> str:
    row = DF_ACHETEURS.filter(pl.col("acheteur_id") == acheteur_id)
    if row.height == 0:
        return "Consultez les marchés publics attribués par cet acheteur."
    nom = row.select("acheteur_nom").item(0, 0)
    return (
        f"Les marchés publics attribués par {nom} : objets, montants, "
        "titulaires, dates de notification."
    )


def _acheteur_scope(pathname: str, ach_year: str | None) -> tuple[str, list]:
    """WHERE SQL scopant les requêtes à cet acheteur (et éventuellement une année)."""
    return entity_scope("acheteur", pathname.split("/")[-1], ach_year)


register_page(
    __name__,
    path_template="/acheteurs/<acheteur_id>",
    title=get_title,
    name="Acheteur",
    description=get_description,
    image_url=META_CONTENT["image_url"],
    order=5,
)


def layout(acheteur_id=None, **kwargs):
    return [
        dcc.Store(id="acheteur-hidden-columns", storage_type="local"),
        dcc.Store(id="acheteur-total"),
        dcc.Store(id="acheteur-total-unique"),
        dcc.Store(id="entity-grid-columns-state", storage_type="local"),
        dcc.Location(id="acheteur_url", refresh="callback-nav"),
        html.Script(type="application/ld+json", id="acheteur_jsonld"),
        html.Div(
            children=[
                html.Div(
                    style={"marginBottom": "50px"},
                    children=[
                        dbc.Row(
                            className="mb-2",
                            children=[
                                dbc.Col(
                                    html.H2(
                                        children=[
                                            html.Span(id="acheteur_siret"),
                                            " - ",
                                            html.Span(id="acheteur_nom"),
                                        ],
                                    ),
                                    width=8,
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        id="acheteur_year",
                                        options=["Toutes les années"]
                                        + [
                                            str(year)
                                            for year in range(
                                                2018,
                                                int(datetime.date.today().year) + 1,
                                            )
                                        ],
                                        placeholder="Année",
                                        labels=DROPDOWN_LABELS_FR,
                                    ),
                                    width=4,
                                ),
                            ],
                        ),
                        dbc.Row(
                            className="mb-2",
                            children=[
                                dbc.Col(
                                    className="org_infos",
                                    children=[
                                        # TODO: ajouter le type d'acheteur : commune, CD, CR, etc.
                                        html.P(
                                            [
                                                "Commune : ",
                                                html.Strong(id="acheteur_commune"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Département : ",
                                                html.Strong(id="acheteur_departement"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Région : ",
                                                html.Strong(id="acheteur_region"),
                                            ]
                                        ),
                                        html.A(
                                            id="acheteur_lien_annuaire",
                                            children="Plus de détails sur l'Annuaire des entreprises",
                                        ),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    children=[
                                        html.P(id="acheteur_titre_stats"),
                                        html.P(id="acheteur_marches_attribues"),
                                        html.P(id="acheteur_titulaires_differents"),
                                        html.Div(
                                            className="d-flex flex-wrap gap-2",
                                            children=[
                                                html.Button(
                                                    "Téléchargement au format Excel",
                                                    id="btn-download-data-acheteur",
                                                    className="btn btn-secondary",
                                                ),
                                                dbc.Button(
                                                    "📊 Visualiser dans l'observatoire",
                                                    id="btn-observatoire-acheteur",
                                                    href=f"/observatoire?acheteur_id={acheteur_id}"
                                                    if acheteur_id
                                                    else "/observatoire",
                                                    color="secondary",
                                                ),
                                            ],
                                        ),
                                        dcc.Download(id="download-data-acheteur"),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    id="acheteur_map",
                                    width=4,
                                    style={"minHeight": "300px"},
                                ),
                            ],
                        ),
                        dbc.Row(
                            children=[
                                dbc.Col(
                                    className="marches_table",
                                    id="top10_titulaires",
                                    width=8,
                                    # La grille top est en modèle infinite : sa
                                    # hauteur est fixe et connue d'avance. On la
                                    # réserve pour que son arrivée par callback
                                    # ne décale pas la suite de la page (#142).
                                    style={"minHeight": CARD_MIN_HEIGHT},
                                ),
                                dbc.Col(
                                    id="acheteur-distance-histogram",
                                    width=4,
                                    style={"minHeight": "450px"},
                                ),
                            ],
                        ),
                    ],
                ),
                # récupérer les données de l'acheteur sur l'api annuaire
                html.H3("Derniers marchés publics attribués"),
                dcc.Loading(
                    overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    id="loading-home",
                    type="default",
                    children=[
                        html.Div(
                            [
                                dbc.Button(
                                    "Colonnes",
                                    id="acheteur_columns_open",
                                    color="secondary",
                                    size="sm",
                                    className="column_list",
                                ),
                                dbc.Button(
                                    "Téléchargement désactivé au-delà de 65 000 lignes",
                                    id="btn-download-filtered-data-acheteur",
                                    color="secondary",
                                    size="sm",
                                    disabled=True,
                                ),
                                dcc.Download(id="acheteur-download-filtered-data"),
                                dbc.Button(
                                    "Réinitialiser",
                                    title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                    id="btn-acheteur-reset",
                                    color="danger",
                                    outline=True,
                                    size="sm",
                                ),
                            ],
                            className="table-toolbar",
                        ),
                        html.Div(
                            html.Span(id="acheteur_nb_rows"),
                            className="table-meta",
                        ),
                        dbc.Modal(
                            [
                                dbc.ModalHeader(
                                    dbc.ModalTitle("Choix des colonnes à afficher")
                                ),
                                dbc.ModalBody(
                                    id="acheteur_columns_body",
                                    children=make_column_picker("acheteur"),
                                ),
                                dbc.ModalFooter(
                                    dbc.Button(
                                        "Fermer",
                                        id="acheteur_columns_close",
                                        className="ms-auto",
                                        n_clicks=0,
                                    )
                                ),
                            ],
                            id="acheteur_columns",
                            is_open=False,
                            fullscreen="md-down",
                            scrollable=True,
                            size="xl",
                        ),
                        html.Div(
                            id="acheteur-grid-container", className="marches_table"
                        ),
                    ],
                ),
            ],
        ),
    ]


@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="acheteur_commune", component_property="children"),
    Output(component_id="acheteur_departement", component_property="children"),
    Output(component_id="acheteur_region", component_property="children"),
    Output(component_id="acheteur_lien_annuaire", component_property="href"),
    Output(component_id="acheteur_jsonld", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["commune"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{acheteur_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = ""
        libelle_commune = ""

    jsonld = make_org_jsonld(
        acheteur_siret, "acheteur", org_name=raison_sociale, annuaire_data=data
    )
    jsonld_script = (
        json.dumps({"@context": "https://schema.org", **jsonld}) if jsonld else ""
    )

    return (
        acheteur_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
        jsonld_script,
    )


@callback(
    Output(component_id="acheteur_map", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_acheteur_map(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    geo_columns = [
        col
        for col in [
            "uid",
            "acheteur_longitude",
            "acheteur_latitude",
            "acheteur_nom",
            "titulaire_longitude",
            "titulaire_latitude",
            "titulaire_nom",
        ]
        if col in schema.names()
    ]
    dff = query_marches(where_sql, params, columns=geo_columns)
    return get_org_location_map(dff, "acheteur", "acheteur_map_leaflet")


@callback(
    Output(component_id="acheteur_marches_attribues", component_property="children"),
    Output(
        component_id="acheteur_titulaires_differents", component_property="children"
    ),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_acheteur_stats(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    agg = aggregate_marches(
        "COUNT(*) AS n, COUNT(DISTINCT titulaire_id) AS nb_titulaires",
        where_sql,
        params,
    )
    nb_marches = format_number(int(agg["n"][0])) if agg.height else "0"
    nb_titulaires = format_number(int(agg["nb_titulaires"][0])) if agg.height else "0"

    marches_attribues = [html.Strong(nb_marches), " marchés et accord-cadres attribués"]
    nb_titulaires = [
        html.Strong(nb_titulaires),
        " titulaires (SIRET) différents",
    ]

    return marches_attribues, nb_titulaires


@callback(
    Output("btn-download-data-acheteur", "disabled"),
    Output("btn-download-data-acheteur", "children"),
    Output("btn-download-data-acheteur", "title"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_download_button_acheteur(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    download_disabled, download_text, download_title = get_button_properties(
        count_marches(where_sql, params)
    )
    download_title = "Télécharger les marchés publics de cet acheteur au format Excel"
    return download_disabled, download_text, download_title


@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_top_titulaires(pathname, ach_year):
    # La grille ne porte plus le classement : ses lignes arrivent par le
    # datasource ci-dessous, une page à la fois (#142).
    grille = top_org_grid(
        "acheteur",
        "titulaire",
        scope_key(pathname, ach_year),
        ["titulaire_distance"],
    )
    return make_card(fig=grille, title="Top titulaires", lg=12, xl=12)


@callback(
    Output(
        {"type": GRID_TYPE, "context": "acheteur", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "acheteur", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State(component_id="acheteur_url", component_property="pathname"),
    State(component_id="acheteur_year", component_property="value"),
    prevent_initial_call=True,
)
def get_top_titulaires_rows(request, pathname, ach_year):
    if request is None or not pathname:
        return no_update
    where_sql, params = _acheteur_scope(pathname, ach_year)
    return fetch_top_org_page(
        "titulaire", where_sql, params, request, ["titulaire_distance"]
    )


@callback(
    Output("download-data-acheteur", "data"),
    Input("btn-download-data-acheteur", "n_clicks"),
    State(component_id="acheteur_url", component_property="pathname"),
    State(component_id="acheteur_year", component_property="value"),
    State(component_id="acheteur_nom", component_property="children"),
    prevent_initial_call=True,
)
def download_acheteur_data(
    n_clicks,
    pathname: str,
    annee: str,
    acheteur_nom: str,
):
    where_sql, params = _acheteur_scope(pathname, annee)
    df_to_download = query_marches(
        where_sql, params, order_by='"dateNotification" DESC, uid DESC'
    )

    def to_bytes(buffer):
        write_styled_excel(
            df_to_download,
            buffer,
            worksheet="DECP" if annee in ["Toutes les années", None] else annee,
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    track_download("/acheteurs/")
    return dcc.send_bytes(to_bytes, filename=f"decp_{acheteur_nom}_{date}.xlsx")


@callback(
    Output("acheteur-hidden-columns", "data", allow_duplicate=True),
    Input("acheteur_column_list", "selectedRows"),
    State("acheteur-hidden-columns", "data"),
    prevent_initial_call=True,
)
def update_hidden_columns_from_checkboxes(selected_rows, current_hidden):
    hidden = hidden_columns_from_selection(selected_rows)
    # Garde anti-écho (#139, #141) : poser selectedRows depuis le serveur à
    # l'ouverture de la modale fait réémettre selectedRows par AG Grid. Si
    # l'état calculé est déjà celui du store, ne rien réécrire.
    reference = (
        current_hidden
        if current_hidden is not None
        else get_default_hidden_columns("acheteur")
    )
    if set(hidden) == set(reference):
        return no_update
    return hidden


@callback(
    Output("acheteur_column_list", "selectedRows"),
    # La modale démonte la grille à la fermeture : la grille recréée à la
    # réouverture n'a plus de filtre rapide, le champ de recherche est vidé.
    Output({"type": "column-search", "page": "acheteur"}, "value"),
    Input("acheteur_columns", "is_open"),
    State("acheteur-hidden-columns", "data"),
)
def update_checkboxes_from_hidden_columns(is_open, hidden_cols):
    """Alimente les cases à cocher à l'ouverture de la modale, et seulement là.

    Déclencher en permanence créerait un liage à double sens (store → cases →
    store), dont l'écho part à chaque chargement de page. Il n'écrase rien ici,
    faute de second écrivain du store — mais c'est un aller-retour serveur pour
    rien, et la course réapparaîtrait le jour où un second écrivain serait
    ajouté. Cf. issue #139 et le même traitement dans src/pages/tableau.py, où
    ce second écrivain existe (application d'une vue partagée).
    """
    if not is_open:
        return no_update, no_update

    # None = pas encore de préférence ; [] = choix explicite de tout
    # afficher, à respecter tel quel (même distinction que la garde de
    # update_hidden_columns_from_checkboxes).
    if hidden_cols is None:
        hidden_cols = get_default_hidden_columns("acheteur")

    # Coche toutes les colonnes qui ne sont PAS masquées
    return selection_from_hidden_columns(hidden_cols), ""


@callback(
    Output("acheteur_columns", "is_open"),
    Input("acheteur_columns_open", "n_clicks"),
    Input("acheteur_columns_close", "n_clicks"),
    State("acheteur_columns", "is_open"),
)
def toggle_acheteur_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("acheteur-distance-histogram", "children"),
    Input("acheteur_url", "pathname"),
    Input("acheteur_year", "value"),
)
def update_acheteur_distance_histogram(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    lff = query_marches(where_sql, params).lazy()
    fig = get_distance_histogram(lff)
    return make_card(
        title="Distance acheteur–titulaire",
        subtitle="en nombre de marchés, échelle logarithmique",
        fig=fig,
        lg=12,
        xl=12,
    )


register_entity_grid_callbacks("acheteur")
