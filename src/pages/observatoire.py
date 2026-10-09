import urllib.parse
from datetime import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    ALL,
    MATCH,
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

from src.db import count_marches, count_unique_marches
from src.figures import (
    build_dashboard_cards,
    cards_drag_marker,
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
from src.utils.frontend import (
    DROPDOWN_LABELS_FR,
    EXCEL_MAX_ROWS,
    get_button_properties,
    get_enum_values_as_dict,
)
from src.utils.seo import META_CONTENT
from src.utils.suivi import emettre
from src.utils.table import format_number, write_csv, write_styled_excel
from src.utils.table_sql import dashboard_filters_to_sql
from src.utils.top_org_grid import GRID_TYPE, fetch_top_org_page, scope_key

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
                                                        "Télécharger au format Excel",
                                                        id="btn-download-observatoire",
                                                        color="secondary",
                                                        className="mt-2",
                                                        disabled=True,
                                                    ),
                                                    html.Div(
                                                        html.Span(
                                                            id="nb_rows_observatoire"
                                                        ),
                                                        className="table-meta",
                                                    ),
                                                    dcc.Input(
                                                        id="observatoire-share-url",
                                                        readOnly=True,
                                                        style={"display": "none"},
                                                    ),
                                                ],
                                            ),
                                        ]
                                    ),
                                    dbc.Row(dbc.Col(id="observatoire-copy-container")),
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
    return build_dashboard_cards(
        dff,
        theme=theme,
        context="observatoire",
        scope=scope_key(filter_params_normalized),
    )


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
    Output(
        {
            "type": GRID_TYPE,
            "context": "observatoire",
            "org_type": MATCH,
            "scope": MATCH,
        },
        "getRowsResponse",
    ),
    Input(
        {
            "type": GRID_TYPE,
            "context": "observatoire",
            "org_type": MATCH,
            "scope": MATCH,
        },
        "getRowsRequest",
    ),
    *[State(fp[0], "value") for fp in FILTER_PARAMS],
    prevent_initial_call=True,
)
def get_top_org_rows(request, *filter_values):
    """Lignes d'une grille top, sur le périmètre courant de l'observatoire.

    Les filtres sont relus à la source (leurs composants) plutôt que dans le
    store `observatoire-filters`, écrit par le même callback que les cards.
    """
    if request is None or ctx.triggered_id is None:
        return no_update
    filter_params = {
        input_id: value
        for (input_id, _url_key, _is_multi, _default), value in zip(
            FILTER_PARAMS, filter_values
        )
    }
    where_sql, params = dashboard_filters_to_sql(**filter_params)
    return fetch_top_org_page(ctx.triggered_id["org_type"], where_sql, params, request)


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
    prevent_initial_call=True,
)
def download_observatoire(_n_clicks, filter_params):
    dff = prepare_dashboard_data(**(filter_params or {}))

    if dff.height > EXCEL_MAX_ROWS:
        extension = "csv"

        def to_bytes(buffer):
            write_csv(dff, buffer)
    else:
        extension = "xlsx"

        def to_bytes(buffer):
            write_styled_excel(dff, buffer)

    emettre("Observatoire", "telechargement", extension, dff.height)
    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_observatoire_{date}.{extension}")


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
    Output("nb_rows_observatoire", "children"),
    Output("btn-download-observatoire", "disabled"),
    Output("btn-download-observatoire", "children"),
    Output("btn-download-observatoire", "title"),
    Input("observatoire-filters", "data"),
)
def update_download_button_observatoire(filter_params):
    """Compteur de lignes et état du bouton d'export, sur le périmètre filtré.

    Même motif que update_download_button_acheteur (src/pages/acheteur.py) :
    le compte est refait à chaque changement de filtre, indépendamment du
    rendu des cards (déjà mémoïsé par _compute_dashboard_children).
    """
    where_sql, params = dashboard_filters_to_sql(**(filter_params or {}))
    height = count_marches(where_sql, params)
    total_unique = count_unique_marches(where_sql, params)

    nb_rows = f"{format_number(height)} lignes ({format_number(total_unique)} marchés)"
    download_disabled, download_text, download_title, _download_format = (
        get_button_properties(height)
    )

    return nb_rows, download_disabled, download_text, download_title
