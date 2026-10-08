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
    make_column_picker,
)
from src.utils.data import DF_TITULAIRES, get_annuaire_data, get_departement_region
from src.utils.entity_grid import entity_scope, register_entity_grid_callbacks
from src.utils.frontend import DROPDOWN_LABELS_FR, EXCEL_MAX_ROWS, get_button_properties
from src.utils.seo import META_CONTENT, make_org_jsonld
from src.utils.table import (
    format_number,
    get_default_hidden_columns,
    hidden_columns_from_selection,
    selection_from_hidden_columns,
    write_csv,
    write_styled_excel,
)
from src.utils.top_org_grid import (
    GRID_TYPE,
    HOST_MIN_HEIGHT,
    fetch_top_org_page,
    scope_key,
    top_org_grid,
)
from src.utils.tracking import track_download


def get_title(titulaire_id: str = None) -> str:
    titulaire_nom = DF_TITULAIRES.filter(pl.col("titulaire_id") == titulaire_id).select(
        "titulaire_nom"
    )
    if titulaire_nom.height > 0:
        return f"Marchés publics remportés par {titulaire_nom.item(0, 0)} | colibre"
    return "Marchés publics remportés | colibre"


def get_description(titulaire_id: str | None = None) -> str:
    row = DF_TITULAIRES.filter(pl.col("titulaire_id") == titulaire_id)
    if row.height == 0:
        return "Consultez les marchés publics remportés par ce titulaire."
    nom = row.select("titulaire_nom").item(0, 0)
    return (
        f"Les marchés publics remportés par {nom} : objets, montants, "
        "acheteurs, dates de notification."
    )


def _titulaire_scope(pathname: str, titulaire_year: str | None) -> tuple[str, list]:
    """WHERE SQL scopant les requêtes à ce titulaire (et éventuellement une année)."""
    return entity_scope("titulaire", pathname.split("/")[-1], titulaire_year)


register_page(
    __name__,
    path_template="/titulaires/<titulaire_id>",
    title=get_title,
    name="Titulaire",
    description=get_description,
    image_url=META_CONTENT["image_url"],
    order=5,
)


def layout(titulaire_id=None, **kwargs):
    return [
        dcc.Store(id="titulaire-hidden-columns", storage_type="local"),
        dcc.Store(id="titulaire-total"),
        dcc.Store(id="titulaire-total-unique"),
        dcc.Store(id="entity-grid-columns-state", storage_type="local"),
        dcc.Location(id="titulaire_url", refresh="callback-nav"),
        html.Script(type="application/ld+json", id="titulaire_jsonld"),
        html.Div(
            children=[
                html.Div(
                    style={"marginBottom": "50px"},
                    children=[
                        dbc.Row(
                            className="mb-2",
                            children=[
                                dbc.Col(
                                    [
                                        html.H2(
                                            children=[
                                                html.Span(id="titulaire_siret"),
                                                " - ",
                                                html.Span(id="titulaire_nom"),
                                            ],
                                        ),
                                        html.P(
                                            id="titulaire_activite_libelle",
                                            style={
                                                "color": "gray",
                                                "marginTop": "-10px",
                                            },
                                        ),
                                    ],
                                    width=8,
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        id="titulaire_year",
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
                                                html.Strong(id="titulaire_commune"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Département : ",
                                                html.Strong(id="titulaire_departement"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Région : ",
                                                html.Strong(id="titulaire_region"),
                                            ]
                                        ),
                                        html.A(
                                            id="titulaire_lien_annuaire",
                                            children="Plus de détails sur l'Annuaire des entreprises",
                                        ),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    children=[
                                        html.P(id="titulaire_titre_stats"),
                                        html.P(id="titulaire_marches_remportes"),
                                        html.P(id="titulaire_acheteurs_differents"),
                                        html.Div(
                                            className="d-flex flex-wrap gap-2",
                                            children=[
                                                html.Button(
                                                    "Téléchargement au format Excel",
                                                    id="btn-download-data-titulaire",
                                                    className="btn btn-secondary",
                                                ),
                                                dbc.Button(
                                                    "📊 Visualiser dans l'observatoire",
                                                    id="btn-observatoire-titulaire",
                                                    href=f"/observatoire?titulaire_id={titulaire_id}"
                                                    if titulaire_id
                                                    else "/observatoire",
                                                    color="secondary",
                                                ),
                                            ],
                                        ),
                                        dcc.Download(id="download-data-titulaire"),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    id="titulaire_map",
                                    width=4,
                                    style={"minHeight": "300px"},
                                ),
                            ],
                        ),
                        dbc.Row(
                            children=[
                                dbc.Col(
                                    html.Div(
                                        children=[
                                            html.H3("Top acheteurs"),
                                            html.Div(
                                                className="marches_table",
                                                id="top10_acheteurs",
                                                # Grille posée nue (sans card) :
                                                # on réserve exactement sa
                                                # hauteur, pour que son arrivée
                                                # par callback ne décale pas la
                                                # suite de la page (#142).
                                                style={"minHeight": HOST_MIN_HEIGHT},
                                            ),
                                        ],
                                    ),
                                    width=8,
                                ),
                                dbc.Col(
                                    id="titulaire-distance-histogram",
                                    width=4,
                                    style={"minHeight": "450px"},
                                ),
                            ],
                        ),
                    ],
                ),
                # récupérer les données de l'acheteur sur l'api annuaire
                html.H3("Derniers marchés publics remportés"),
                dcc.Loading(
                    overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    id="loading-home",
                    type="default",
                    children=[
                        html.Div(
                            [
                                dbc.Button(
                                    "Colonnes",
                                    id="titulaire_columns_open",
                                    color="secondary",
                                    size="sm",
                                    className="column_list",
                                ),
                                dbc.Button(
                                    "Téléchargement désactivé au-delà de 65 000 lignes",
                                    id="btn-download-filtered-data-titulaire",
                                    color="secondary",
                                    size="sm",
                                    disabled=True,
                                ),
                                dcc.Download(id="titulaire-download-filtered-data"),
                                dbc.Button(
                                    "Réinitialiser",
                                    title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                    id="btn-titulaire-reset",
                                    color="danger",
                                    outline=True,
                                    size="sm",
                                ),
                            ],
                            className="table-toolbar",
                        ),
                        html.Div(
                            [
                                html.Span(id="titulaire_nb_rows"),
                                html.Span(
                                    id="titulaire-filter-pills",
                                    className="filter-pills",
                                ),
                            ],
                            className="table-meta",
                        ),
                        dbc.Modal(
                            [
                                dbc.ModalHeader(
                                    dbc.ModalTitle("Choix des colonnes à afficher")
                                ),
                                dbc.ModalBody(
                                    id="titulaire_columns_body",
                                    children=make_column_picker("titulaire"),
                                ),
                                dbc.ModalFooter(
                                    dbc.Button(
                                        "Fermer",
                                        id="titulaire_columns_close",
                                        className="ms-auto",
                                        n_clicks=0,
                                    )
                                ),
                            ],
                            id="titulaire_columns",
                            is_open=False,
                            fullscreen="md-down",
                            scrollable=True,
                            size="xl",
                        ),
                        html.Div(
                            id="titulaire-grid-container", className="marches_table"
                        ),
                    ],
                ),
            ],
        ),
    ]


@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Output(component_id="titulaire_activite_libelle", component_property="children"),
    Output(component_id="titulaire_jsonld", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    if "titulaire_activite_libelle" in DF_TITULAIRES.columns:
        activite_libelle_row = DF_TITULAIRES.filter(
            pl.col("titulaire_id") == titulaire_siret
        ).select("titulaire_activite_libelle")
        activite_libelle = (
            activite_libelle_row.item(0, 0) if activite_libelle_row.height > 0 else ""
        )
    else:
        activite_libelle = ""
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["commune"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{titulaire_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = html.Span(
            f"N° SIREN inconnu de l'INSEE ({titulaire_siret[:9]})"
        )
        libelle_commune = ""

    # raison_sociale peut être un composant html.Span (SIRET inconnu de l'INSEE),
    # non sérialisable en JSON : on n'émet du JSON-LD que si c'est une chaîne.
    jsonld = (
        make_org_jsonld(
            titulaire_siret, "titulaire", org_name=raison_sociale, annuaire_data=data
        )
        if isinstance(raison_sociale, str)
        else {}
    )
    jsonld_script = (
        json.dumps({"@context": "https://schema.org", **jsonld}) if jsonld else ""
    )

    return (
        titulaire_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
        activite_libelle,
        jsonld_script,
    )


@callback(
    Output(component_id="titulaire_map", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_titulaire_map(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
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
    return get_org_location_map(dff, "titulaire", "titulaire_map_leaflet")


@callback(
    Output(component_id="titulaire_marches_remportes", component_property="children"),
    Output(
        component_id="titulaire_acheteurs_differents", component_property="children"
    ),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_titulaire_stats(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    agg = aggregate_marches(
        "COUNT(DISTINCT uid) AS n, COUNT(DISTINCT acheteur_id) AS nb_acheteurs",
        where_sql,
        params,
    )
    nb_marches = format_number(int(agg["n"][0])) if agg.height else "0"
    nb_acheteurs = format_number(int(agg["nb_acheteurs"][0])) if agg.height else "0"

    texte_marches_remportes = [
        html.Strong(nb_marches),
        " marchés et accord-cadres remportés",
    ]
    texte_nb_acheteurs = [
        html.Strong(nb_acheteurs),
        " acheteurs (SIRET) différents",
    ]

    return texte_marches_remportes, texte_nb_acheteurs


@callback(
    Output("btn-download-data-titulaire", "disabled"),
    Output("btn-download-data-titulaire", "children"),
    Output("btn-download-data-titulaire", "title"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_download_button_titulaire(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    download_disabled, download_text, download_title, _download_format = (
        get_button_properties(count_marches(where_sql, params))
    )
    return download_disabled, download_text, download_title


@callback(
    Output(component_id="top10_acheteurs", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_top_acheteurs(pathname, titulaire_year):
    # Cf. src/pages/acheteur.py : la grille est alimentée page par page (#142).
    return top_org_grid(
        "titulaire",
        "acheteur",
        scope_key(pathname, titulaire_year),
        ["titulaire_distance"],
    )


@callback(
    Output(
        {"type": GRID_TYPE, "context": "titulaire", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "titulaire", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State(component_id="titulaire_url", component_property="pathname"),
    State(component_id="titulaire_year", component_property="value"),
    prevent_initial_call=True,
)
def get_top_acheteurs_rows(request, pathname, titulaire_year):
    if request is None or not pathname:
        return no_update
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return fetch_top_org_page(
        "acheteur", where_sql, params, request, ["titulaire_distance"]
    )


@callback(
    Output("download-data-titulaire", "data"),
    Input("btn-download-data-titulaire", "n_clicks"),
    State(component_id="titulaire_url", component_property="pathname"),
    State(component_id="titulaire_year", component_property="value"),
    State(component_id="titulaire_nom", component_property="children"),
    prevent_initial_call=True,
)
def download_titulaire_data(
    n_clicks,
    pathname: str,
    annee: str,
    titulaire_nom: str,
):
    where_sql, params = _titulaire_scope(pathname, annee)
    df_to_download = query_marches(
        where_sql, params, order_by='"dateNotification" DESC, uid DESC'
    ).fill_null("")
    worksheet = "DECP" if annee in ["Toutes les années", None] else annee

    if df_to_download.height > EXCEL_MAX_ROWS:
        extension = "csv"

        def to_bytes(buffer):
            write_csv(df_to_download, buffer)
    else:
        extension = "xlsx"

        def to_bytes(buffer):
            write_styled_excel(df_to_download, buffer, worksheet=worksheet)

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    track_download("/titulaires/")
    return dcc.send_bytes(to_bytes, filename=f"decp_{titulaire_nom}_{date}.{extension}")


@callback(
    Output("titulaire-hidden-columns", "data", allow_duplicate=True),
    Input("titulaire_column_list", "selectedRows"),
    State("titulaire-hidden-columns", "data"),
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
        else get_default_hidden_columns("titulaire")
    )
    if set(hidden) == set(reference):
        return no_update
    return hidden


@callback(
    Output("titulaire_column_list", "selectedRows"),
    # La modale démonte la grille à la fermeture : la grille recréée à la
    # réouverture n'a plus de filtre rapide, le champ de recherche est vidé.
    Output({"type": "column-search", "page": "titulaire"}, "value"),
    Input("titulaire_columns", "is_open"),
    State("titulaire-hidden-columns", "data"),
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
        hidden_cols = get_default_hidden_columns("titulaire")

    # Coche toutes les colonnes qui ne sont PAS masquées
    return selection_from_hidden_columns(hidden_cols), ""


@callback(
    Output("titulaire_columns", "is_open"),
    Input("titulaire_columns_open", "n_clicks"),
    Input("titulaire_columns_close", "n_clicks"),
    State("titulaire_columns", "is_open"),
)
def toggle_titulaire_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("titulaire-distance-histogram", "children"),
    Input("titulaire_url", "pathname"),
    Input("titulaire_year", "value"),
)
def update_titulaire_distance_histogram(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    lff = query_marches(where_sql, params).lazy()
    if "titulaire_distance" in lff.collect_schema().names():
        lff = lff.with_columns(
            pl.col("titulaire_distance").cast(pl.Float64, strict=False)
        )
    fig = get_distance_histogram(lff)
    return [
        html.H3("Distance acheteur-titulaire"),
        html.H6("par nombre de marchés", className="card-subtitle mb-2 text-muted"),
        fig,
    ]


register_entity_grid_callbacks("titulaire")
