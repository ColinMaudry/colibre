import urllib.parse
from datetime import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
from flask_login import current_user

from src.db import schema
from src.figures import (
    DataTable,
    build_dashboard_cards,
    cards_drag_marker,
    make_column_picker,
    montant_modal,
    observatoire_cards_columns,
    reorder_cards,
)
from src.observatoire_order import get_card_order, save_card_order
from src.pages._compte_shell import current_user_has_subscription
from src.theme import current_theme
from src.utils import logger
from src.utils.cache import cache
from src.utils.data import (
    DEPARTEMENTS,
    DF_ACHETEURS,
    DF_TITULAIRES,
    prepare_dashboard_data,
)
from src.utils.frontend import DROPDOWN_LABELS_FR, get_enum_values_as_dict
from src.utils.seo import META_CONTENT
from src.utils.table import (
    get_default_hidden_columns,
    hidden_columns_from_selection,
    prepare_table_data,
    selection_from_hidden_columns,
    write_styled_excel,
)
from src.utils.tracking import track_download

NAME = "Observatoire"

register_page(
    __name__,
    path="/observatoire",
    title="Observatoire | colibre",
    name=NAME,
    description="Visualisez l'état de la publication des données essentielles des marchés publics en France.",
    image_url=META_CONTENT["image_url"],
    order=3,
)
OPTIONS_YEARS = []
for year in reversed(range(2017, datetime.now().year + 1)):
    option_year = {
        "label": str(year),
        "value": year,
    }
    OPTIONS_YEARS.append(option_year)

OPTIONS_DEPARTEMENTS = []
for code in DEPARTEMENTS.keys():
    departement = {
        "label": f"{DEPARTEMENTS[code]['departement']} ({code})",
        "value": code,
    }
    OPTIONS_DEPARTEMENTS.append(departement)

OBSERVATOIRE_COLUMNS = [
    col
    for col in schema.names()
    if col.startswith("acheteur")
    or col.startswith("titulaire")
    or col
    in [
        "uid",
        "dateNotification",
        "montant",
        "considerationsSociales",
        "considerationsEnvironnementales",
        "marcheInnovant",
        "sousTraitanceDeclaree",
        "techniques",
        "sourceDataset",
        "type",
        "codeCPV",
    ]
]

layout = [
    dcc.Location(id="dashboard_url", refresh="callback-nav"),
    dcc.Store(id="observatoire-filters", storage_type="local"),
    # Ordre des cards chargé depuis la base au rendu de la page (#107).
    dcc.Store(id="observatoire-card-order"),
    # Ordre poussé par observatoire-dragdrop.js après un glisser-déposer. Store
    # distinct du précédent : s'ils n'en faisaient qu'un, le callback qui le lit
    # pour persister serait aussi celui qui l'écrit — Dash refuse ce cycle.
    dcc.Store(id="observatoire-card-order-nouveau"),
    # Puits de sortie : persist_card_order écrit en base, pas dans le layout.
    dcc.Store(id="observatoire-card-order-persiste"),
    dcc.Store(id="observatoire-hidden-columns", storage_type="local"),
    dcc.Store(
        id="filter-cleanup-trigger-observatoire-preview"
    ),  # utilisé juste pour ne pas avoir à adapter les données retournées de prepare_table data
    montant_modal(),
    html.Div(
        className="container-fluid",
        children=[
            html.H2(children=[NAME], id="page_title"),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-statistques",
                type="default",
                children=[
                    dbc.Row(
                        [
                            dbc.Col(
                                xl=3,
                                lg=4,
                                id="filters",
                                children=[
                                    html.H5("Période d'attribution"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_year",
                                                options=OPTIONS_YEARS,
                                                placeholder="12 derniers mois",
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    html.H5("Acheteur"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_acheteur_id",
                                                placeholder="SIRET",
                                                debounce=True,
                                                style={"width": "100%"},
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_acheteur_categorie",
                                                options=get_enum_values_as_dict(
                                                    "acheteur_categorie"
                                                ),
                                                placeholder="Catégorie",
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            )
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_acheteur_departement_code",
                                                searchable=True,
                                                multi=True,
                                                placeholder="Département",
                                                options=OPTIONS_DEPARTEMENTS,
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    html.H5("Titulaire"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_titulaire_id",
                                                placeholder="SIRET",
                                                debounce=True,
                                                style={"width": "100%"},
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_titulaire_categorie",
                                                placeholder="Catégorie",
                                                options=get_enum_values_as_dict(
                                                    "titulaire_categorie"
                                                ),
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_titulaire_departement_code",
                                                searchable=True,
                                                multi=True,
                                                placeholder="Département",
                                                options=OPTIONS_DEPARTEMENTS,
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    html.H5("Marché"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_type",
                                                placeholder="Type",
                                                options=get_enum_values_as_dict("type"),
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_marche_objet",
                                                placeholder="Objet",
                                                debounce=True,
                                                style={"width": "100%"},
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_marche_code_cpv",
                                                    placeholder="Code CPV (début)",
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=8,
                                            ),
                                            dbc.Col(
                                                html.A(
                                                    "liste des codes CPV",
                                                    href="https://cpvcodes.eu/fr",
                                                    target="_blank",
                                                ),
                                                lg=4,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_montant_min",
                                                    placeholder="Montant min.",
                                                    type="number",
                                                    min=0,
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                width=6,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_montant_max",
                                                    placeholder="Montant max.",
                                                    type="number",
                                                    min=0,
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                width=6,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_techniques",
                                                placeholder="Techniques d'achat",
                                                options=get_enum_values_as_dict(
                                                    "techniques"
                                                ),
                                                multi=True,
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col("Sous-traitance :", lg=5),
                                            dbc.Col(
                                                dbc.RadioItems(
                                                    id="dashboard_marche_sous_traitance_declaree",
                                                    options=[
                                                        {
                                                            "label": "Tous",
                                                            "value": "all",
                                                        },
                                                        {
                                                            "label": "Oui",
                                                            "value": "oui",
                                                        },
                                                        {
                                                            "label": "Non",
                                                            "value": "non",
                                                        },
                                                    ],
                                                    value="all",
                                                    inline=True,
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=7,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col("Marché innovant :", lg=5),
                                            dbc.Col(
                                                dbc.RadioItems(
                                                    id="dashboard_marche_innovant",
                                                    options=[
                                                        {
                                                            "label": "Tous",
                                                            "value": "all",
                                                        },
                                                        {
                                                            "label": "Oui",
                                                            "value": "oui",
                                                        },
                                                        {
                                                            "label": "Non",
                                                            "value": "non",
                                                        },
                                                    ],
                                                    value="all",
                                                    inline=True,
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=7,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerations_sociales",
                                                placeholder="Considérations sociales",
                                                options=get_enum_values_as_dict(
                                                    "considerationsSociales"
                                                ),
                                                multi=True,
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerations_environnementales",
                                                placeholder="Considérations environnementales",
                                                multi=True,
                                                options=get_enum_values_as_dict(
                                                    "considerationsEnvironnementales"
                                                ),
                                                persistence=True,
                                                persistence_type="local",
                                                labels=DROPDOWN_LABELS_FR,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    dcc.Download(
                                                        id="download-observatoire"
                                                    ),
                                                    dbc.Button(
                                                        "Voir les données",
                                                        id="btn-observatoire-preview",
                                                        color="secondary",
                                                        className="mt-2",
                                                    ),
                                                    dcc.Input(
                                                        id="observatoire-share-url",
                                                        readOnly=True,
                                                        style={"display": "none"},
                                                    ),
                                                ],
                                                lg=12,
                                                xl=6,
                                            ),
                                            dbc.Col(
                                                id="observatoire-copy-container",
                                                lg=12,
                                                xl=6,
                                            ),
                                        ]
                                    ),
                                ],
                            ),
                            dbc.Col(
                                width=12,
                                lg=8,
                                xl=9,
                                id="cards",
                                children=[],
                            ),
                        ]
                    )
                ],
            ),
        ],
    ),
    dbc.Offcanvas(
        id="observatoire-preview",
        title="Prévisualisation des données",
        placement="bottom",
        is_open=False,
        scrollable=True,
        style={"height": "75vh"},
        children=[
            # Header row: toolbar + meta
            html.Div(
                [
                    dbc.Button(
                        "Colonnes",
                        id="observatoire-preview-columns-open",
                        color="secondary",
                        size="sm",
                    ),
                    dbc.Button(
                        "Télécharger au format Excel",
                        id="btn-download-observatoire",
                        color="secondary",
                        size="sm",
                        disabled=True,
                    ),
                ],
                className="table-toolbar mb-2",
            ),
            html.Div(
                html.Span(id="nb_rows_observatoire"),
                className="table-meta",
            ),
            # Column picker modal
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle("Colonnes affichées dans la prévisualisation")
                    ),
                    dbc.ModalBody(
                        id="observatoire-preview-columns-body",
                        children=make_column_picker("observatoire_preview"),
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Fermer",
                            id="observatoire-preview-columns-close",
                            className="ms-auto",
                            n_clicks=0,
                        )
                    ),
                ],
                id="observatoire-preview-columns-modal",
                is_open=False,
                fullscreen="md-down",
                scrollable=True,
                size="xl",
            ),
            # DataTable
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-statistques",
                type="default",
                children=[
                    html.Div(
                        className="marches_table",
                        children=DataTable(
                            dtid="observatoire-preview-table",
                            page_size=5,
                            page_action="custom",
                            sort_action="custom",
                            filter_action="custom",
                            hidden_columns=[],
                            columns=[
                                {"id": col, "name": col} for col in OBSERVATOIRE_COLUMNS
                            ],
                        ),
                    )
                ],
            ),
        ],
    ),
]


FILTER_PARAMS = [
    # (component_id, url_key, is_multi, default_value)
    ("dashboard_year", "annee", False, None),
    ("dashboard_acheteur_id", "acheteur_id", False, None),
    ("dashboard_acheteur_categorie", "acheteur_cat", False, None),
    ("dashboard_acheteur_departement_code", "acheteur_dept", True, None),
    ("dashboard_titulaire_id", "titulaire_id", False, None),
    ("dashboard_titulaire_categorie", "titulaire_cat", False, None),
    ("dashboard_titulaire_departement_code", "titulaire_dept", True, None),
    ("dashboard_marche_type", "type", False, None),
    ("dashboard_marche_objet", "objet", False, None),
    ("dashboard_marche_code_cpv", "cpv", False, None),
    ("dashboard_montant_min", "montant_min", False, None),
    ("dashboard_montant_max", "montant_max", False, None),
    ("dashboard_marche_techniques", "techniques", True, None),
    ("dashboard_marche_innovant", "innovant", False, "all"),
    ("dashboard_marche_sous_traitance_declaree", "sous_traitance", False, "all"),
    ("dashboard_marche_considerations_sociales", "social", True, None),
    ("dashboard_marche_considerations_environnementales", "env", True, None),
]


@callback(
    *[Output(fp[0], "value") for fp in FILTER_PARAMS],
    Input("dashboard_url", "search"),
    Input("dashboard_url", "pathname"),
    State("observatoire-filters", "data"),
)
def restore_filters(search, _pathname, stored_filters):
    if search:
        params = urllib.parse.parse_qs(search.lstrip("?"))
        known_keys = {fp[1] for fp in FILTER_PARAMS}
        if any(k in params for k in known_keys):
            values = []
            for _comp_id, url_key, is_multi, default in FILTER_PARAMS:
                if url_key in params:
                    if is_multi:
                        values.append(params[url_key])
                    else:
                        raw = params[url_key][0]
                        if url_key in ("montant_min", "montant_max"):
                            try:
                                raw = float(raw)
                            except (ValueError, TypeError):
                                raw = None
                        values.append(raw)
                else:
                    values.append(default)
            return tuple(values)
    return (no_update,) * 17


@callback(
    Output("observatoire-share-url", "value"),
    Output("observatoire-copy-container", "children"),
    *[Input(fp[0], "value") for fp in FILTER_PARAMS],
    Input("dashboard_url", "href"),
)
def sync_observatoire_share_url(*args):
    # Last arg is href (State), rest are filter values
    filter_values = args[:-1]
    href = args[-1]

    if not href:
        return no_update, no_update

    base_url = href.split("?")[0]

    params = []
    for (_, url_key, is_multi, default), value in zip(FILTER_PARAMS, filter_values):
        if value is None or value == default or value == [] or value == "":
            continue
        if is_multi and isinstance(value, list):
            for v in value:
                params.append((url_key, v))
        else:
            params.append((url_key, value))

    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}" if query_string else base_url

    if params:
        copy_button = dcc.Clipboard(
            id="btn-copy-observatoire-url",
            target_id="observatoire-share-url",
            title="Copier l'URL de cette vue",
            style={
                "display": "inline-block",
                "fontSize": 20,
                "verticalAlign": "top",
                "cursor": "pointer",
            },
            className="fa fa-link",
            children=[
                dbc.Button(
                    "Partager cette vue",
                    id="btn-copy-observatoire",
                    color="secondary",
                    className="mt-2",
                    title="Copier l'adresse de cette vue filtrée pour la partager.",
                )
            ],
        )
    else:
        copy_button = html.Div()

    return full_url, copy_button


@callback(
    Output("observatoire-copy-container", "children", allow_duplicate=True),
    Input("btn-copy-observatoire", "n_clicks", allow_optional=True),
    prevent_initial_call=True,
)
def show_confirmation(n_clicks):
    if n_clicks:
        return html.Span(
            "Adresse de la vue copiée",
            style={"color": "green", "fontWeight": "bold", "marginLeft": "10px"},
        )
    return no_update


def _normalize_filter_params(filter_params: dict) -> tuple:
    """Produce a deterministic, hashable key for caching."""
    return tuple(
        sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in filter_params.items()
        )
    )


@cache.memoize()
def _compute_dashboard_children(filter_params_normalized: tuple, theme: str):
    # `theme` fait partie de la clé de cache : les figures sont colorées
    # côté serveur (#118).
    logger.debug("Cache miss — computing dashboard")
    filter_params = {
        k: (list(v) if isinstance(v, tuple) else v) for k, v in filter_params_normalized
    }

    dff = prepare_dashboard_data(columns=observatoire_cards_columns(), **filter_params)
    return build_dashboard_cards(dff, theme=theme)


@callback(
    Output("cards", "children"),
    Output("observatoire-filters", "data"),
    Input("observatoire-card-order", "data"),
    *[Input(fp[0], "value") for fp in FILTER_PARAMS],
)
def update_dashboard_cards(card_order, *filter_values):
    filter_params = {}
    for (input_id, _url_key, _is_multi, _default), value in zip(
        FILTER_PARAMS, filter_values
    ):
        filter_params[input_id] = value

    filter_params_normalized = _normalize_filter_params(filter_params)
    children = _compute_dashboard_children(filter_params_normalized, current_theme())

    # L'ordre est appliqué APRÈS le cache mémoïsé : le mettre dans
    # _compute_dashboard_children multiplierait les entrées de cache par le
    # nombre d'ordres possibles (#107).
    if card_order:
        children = reorder_cards(children, card_order)

    if current_user_has_subscription():
        children = [cards_drag_marker("observatoire-card-order-nouveau"), *children]

    return dbc.Row(children=children), filter_params


@callback(
    Output("observatoire-card-order", "data"),
    Input("dashboard_url", "pathname"),
)
def load_card_order(_pathname):
    """Ordre enregistré par l'utilisateur, relu à chaque rendu de la page."""
    if not current_user.is_authenticated or not current_user_has_subscription():
        return None
    return get_card_order(current_user.id)


@callback(
    Output("observatoire-card-order-persiste", "data"),
    Input("observatoire-card-order-nouveau", "data"),
    prevent_initial_call=True,
)
def persist_card_order(card_order):
    """Enregistre l'ordre poussé par le drag & drop.

    La sortie est un Store puits : le rendu des cards n'a pas à être refait,
    le DOM est déjà dans le bon ordre côté client.
    """
    if not card_order:
        return no_update
    if not current_user.is_authenticated or not current_user_has_subscription():
        return no_update
    save_card_order(current_user.id, card_order)
    return card_order


@callback(
    Output("download-observatoire", "data"),
    Input("btn-download-observatoire", "n_clicks"),
    State("observatoire-filters", "data"),
    State("observatoire-hidden-columns", "data"),
    prevent_initial_call=True,
)
def download_observatoire(_n_clicks, filter_params, hidden_columns):
    dff = prepare_dashboard_data(**(filter_params or {}))

    if hidden_columns:
        dff = dff.drop(hidden_columns)

    def to_bytes(buffer):
        write_styled_excel(dff, buffer)

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    track_download("/observatoire")
    return dcc.send_bytes(to_bytes, filename=f"decp_observatoire_{date}.xlsx")


@callback(
    Output("montant-modal", "is_open"),
    Input({"type": "modal-trigger", "index": ALL}, "n_clicks"),
    Input("montant-modal-close", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_montant_modal(n_triggers, _close):
    return isinstance(ctx.triggered_id, dict) and any(n_triggers)


@callback(
    Output("page_title", "children"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_titulaire_id", "value"),
    prevent_initial_call=False,
)
def add_organization_name_in_title(acheteur_id, titulaire_id):
    acheteur_id = acheteur_id.replace(" ", "") if acheteur_id else None
    titulaire_id = titulaire_id.replace(" ", "") if titulaire_id else None

    def lookup_nom(df_org, id_col, nom_col, org_id):
        match = df_org.filter(pl.col(id_col) == org_id)
        return match[nom_col].item(0) if match.height >= 1 else None

    if acheteur_id and len(acheteur_id) == 14:
        if nom := lookup_nom(DF_ACHETEURS, "acheteur_id", "acheteur_nom", acheteur_id):
            return [
                NAME,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    elif titulaire_id and len(titulaire_id) == 14:
        if nom := lookup_nom(
            DF_TITULAIRES, "titulaire_id", "titulaire_nom", titulaire_id
        ):
            return [
                NAME,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    return NAME


@callback(
    Output("observatoire-preview", "is_open"),
    Input("btn-observatoire-preview", "n_clicks"),
    State("observatoire-preview", "is_open"),
    prevent_initial_call=True,
)
def toggle_observatoire_preview(n_clicks, is_open):
    return not is_open


@callback(
    Output("observatoire-preview-table", "data"),
    Output("observatoire-preview-table", "columns"),
    Output("observatoire-preview-table", "tooltip_header"),
    Output("observatoire-preview-table", "data_timestamp"),
    Output("nb_rows_observatoire", "children"),
    Output("btn-download-observatoire", "disabled"),
    Output("btn-download-observatoire", "children"),
    Output("btn-download-observatoire", "title"),
    Output("filter-cleanup-trigger-observatoire-preview", "data", allow_duplicate=True),
    Input("observatoire-preview", "is_open"),
    Input("observatoire-preview-table", "filter_query"),
    Input("observatoire-preview-table", "page_current"),
    Input("observatoire-preview-table", "page_size"),
    Input("observatoire-preview-table", "sort_by"),
    State("observatoire-preview-table", "data_timestamp"),
    State("observatoire-filters", "data"),
    prevent_initial_call=True,
)
def populate_preview_table(
    is_open,
    filter_query,
    page_current,
    page_size,
    sort_by,
    data_timestamp,
    filter_params,
):
    if not is_open:
        return (no_update,) * 9

    dff = prepare_dashboard_data(**(filter_params or {}))

    return prepare_table_data(
        dff.lazy(),
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "observatoire-preview",
    )


@callback(
    Output("observatoire-hidden-columns", "data", allow_duplicate=True),
    Input("observatoire_preview_column_list", "selectedRows"),
    State("observatoire-hidden-columns", "data"),
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
        else get_default_hidden_columns("tableau")
    )
    if set(hidden) == set(reference):
        return no_update
    return hidden


@callback(
    Output("observatoire-preview-table", "hidden_columns"),
    Input(
        "observatoire-hidden-columns",
        "data",
    ),
)
def store_hidden_columns(hidden_columns):
    # None = pas encore de préférence : on masque le défaut, celui que la
    # modale décoche (update_checkboxes_from_hidden_columns). [] = tout afficher.
    if hidden_columns is None:
        return get_default_hidden_columns("tableau")
    return hidden_columns


@callback(
    Output("observatoire_preview_column_list", "selectedRows"),
    Input("observatoire-preview-columns-modal", "is_open"),
    State("observatoire-hidden-columns", "data"),
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
        return no_update

    # None = pas encore de préférence ; [] = choix explicite de tout
    # afficher, à respecter tel quel (même distinction que la garde de
    # update_hidden_columns_from_checkboxes).
    if hidden_cols is None:
        hidden_cols = get_default_hidden_columns("tableau")

    # Coche toutes les colonnes qui ne sont PAS masquées
    return selection_from_hidden_columns(hidden_cols)


@callback(
    Output("observatoire-preview-columns-modal", "is_open"),
    Input("observatoire-preview-columns-open", "n_clicks"),
    Input("observatoire-preview-columns-close", "n_clicks"),
    State("observatoire-preview-columns-modal", "is_open"),
)
def toggle_tableau_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open
