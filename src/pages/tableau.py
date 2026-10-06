import json
import os
from datetime import datetime
from urllib.parse import parse_qs

import dash_bootstrap_components as dbc
from dash import (
    ALL,
    MATCH,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
from flask_login import current_user

from src.db import query_marches, schema
from src.figures import (
    ag_grid,
    build_dashboard_cards,
    cards_drag_marker,
    make_column_picker,
    montant_modal,
    observatoire_cards_columns,
    reorder_cards,
)
from src.observatoire_order import get_card_order, save_card_order
from src.pages._compte_shell import current_user_has_subscription
from src.saved_views import db as saved_views_db
from src.saved_views import resolve as saved_views_resolve
from src.saved_views import ui as saved_views_ui
from src.theme import current_theme
from src.utils import get_data_update_timestamp, logger
from src.utils.cache import cache
from src.utils.frontend import EXCEL_MAX_ROWS, get_button_properties
from src.utils.grid import apply_persisted_layout, fetch_grid_page, grid_column_defs
from src.utils.query_ast import (
    ast_from_dict,
    ast_to_dict,
    ast_to_filtermodel,
    ast_to_sql,
    filtermodel_to_ast,
)
from src.utils.seo import META_CONTENT
from src.utils.table import (
    format_number,
    get_default_hidden_columns,
    hidden_columns_from_selection,
    selection_from_hidden_columns,
    write_csv,
    write_styled_excel,
)
from src.utils.top_org_grid import GRID_TYPE, fetch_top_org_page, scope_key
from src.utils.tracking import track_download, track_search

# L'URL de l'API data.gouv.fr redirige toujours vers la dernière version
# publiée du CSV complet des DECP (mise à jour quotidienne) : pas besoin de
# générer nous-mêmes un export de 3,19 millions de lignes quand le tableau
# n'a aucun filtre (#142).
DECP_CSV_COMPLET_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/22847056-61df-452d-837d-8b8ceadbfc52"
)

update_date_timestamp = get_data_update_timestamp(
    os.getenv("DATA_FILE_PARQUET_PATH", ""),
    os.getenv("DUCKDB_PATH", "./decp.duckdb"),
)
if update_date_timestamp is not None:
    update_date = datetime.fromtimestamp(update_date_timestamp).strftime("%d/%m/%Y")
    update_date_iso = datetime.fromtimestamp(update_date_timestamp).isoformat()
else:
    update_date = "date inconnue"
    update_date_iso = ""


NAME = "Tableau"
register_page(
    __name__,
    path="/tableau",
    title="Tableau des marchés publics | colibre",
    name=NAME,
    description="Consultez, filtrez et exportez les données essentielles de la commande publique sous forme de tableau.",
    image_url=META_CONTENT["image_url"],
    order=1,
)

# Le bloc « URL directe » (share-url-box) reste affiché tant que la vue partagée
# n'a pas dérivé. On détecte la dérive par des écouteurs d'événements AG Grid
# côté client plutôt que par diff d'état : l'application programmatique d'une vue
# (source 'api'/'gridOptionsChanged') est ignorée, seules les actions utilisateur
# effacent `active-view` et masquent le bloc. Voir
# src/assets/dashAgGridFunctions.js. Cette approche évite la course
# d'ordonnancement d'un compteur d'échos et le bruit du columnState réémis.
#
# On écoute filtre et tri (signaux natifs fiables, source utilisateur distincte
# de 'api'). La visibilité des colonnes est pilotée par le sélecteur « Colonnes »
# maison (store tableau-hidden-columns → régénération des columnDefs → événement
# columnVisible de source 'gridOptionsChanged', identique pour l'utilisateur et
# l'application programmatique) : indistinguable via AG Grid, donc non écoutée.
_SHARE_DRIFT_LISTENERS = {
    event: ["hideShareOnUserAction(params)"]
    for event in ("filterChanged", "sortChanged")
}

DATATABLE = html.Div(
    id="tableau-grid-wrapper",
    className="marches_table",
    children=ag_grid(
        "tableau_grid",
        grid_column_defs(get_default_hidden_columns("tableau")),
        event_listeners=_SHARE_DRIFT_LISTENERS,
    ),
)


def _help_button_legend():
    """Légende en tête du mode d'emploi : chaque bouton de la barre d'outils,
    reproduit à l'identique (mais inerte), en face de sa fonction."""
    rows = [
        (
            dbc.Button("Colonnes", color="secondary", size="sm"),
            "Choisir les colonnes affichées.",
        ),
        (
            dbc.Button("Sauvegarder la vue", color="secondary", size="sm"),
            "Enregistrer les filtres, tris et colonnes actuels sous un nom (abonné·es).",
        ),
        (
            dbc.Button("Mes vues ▾", color="secondary", size="sm"),
            "Rouvrir une vue que vous avez enregistrée (abonné·es).",
        ),
        (
            dbc.Button("Télécharger (Excel)", color="secondary", size="sm"),
            "Télécharger les données filtrées et triées au format Excel.",
        ),
        (
            dbc.Button("Réinitialiser", color="danger", outline=True, size="sm"),
            "Supprimer tous les filtres et tris.",
        ),
        (
            html.Span(
                id="mode-observatoire-legende",
                className="mode-observatoire-toggle",
                children=[
                    html.Span("☰", className="mode-observatoire-icone active"),
                    dbc.Switch(value=False, className="mb-0", disabled=True),
                    html.Span("📊", className="mode-observatoire-icone"),
                ],
            ),
            "Remplacer les lignes de données par les visualisations de "
            "l'observatoire, calculées sur les marchés que vos filtres "
            "retiennent (abonné·es). Les en-têtes restent en place : vous pouvez "
            "affiner les filtres sans quitter ce mode.",
        ),
        (
            dbc.Button("⍰ Mode d'emploi", color="secondary", outline=True, size="sm"),
            "Ouvrir cette aide.",
        ),
    ]
    return html.Div(
        className="help-legend",
        children=[
            html.P("Les boutons de la barre d'outils", className="fw-bold mb-2"),
            html.Table(
                className="help-legend-table",
                children=html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(btn, className="help-legend-btn"),
                                html.Td(desc, className="help-legend-desc"),
                            ]
                        )
                        for btn, desc in rows
                    ]
                ),
            ),
        ],
    )


def _layout(a_un_abonnement: bool) -> list:
    return [
        dcc.Location(id="tableau_url", refresh=False),
        dcc.Store(id="tableau-hidden-columns", storage_type="local"),
        # Choix du mode d'affichage (lignes ⇄ observatoire) persisté entre visites.
        dcc.Store(id="tableau-mode-observatoire-persiste", storage_type="local"),
        # Ordre des cards du mode observatoire (#107). Même table, même clé
        # (user_id) que /observatoire : les deux pages partagent un seul ordre.
        dcc.Store(id="tableau-card-order"),
        # Ordre poussé par observatoire-dragdrop.js ; Store distinct du précédent
        # pour que le callback de persistance ne soit pas son propre Input.
        dcc.Store(id="tableau-card-order-nouveau"),
        # Puits de sortie : la persistance écrit en base, pas dans le layout.
        dcc.Store(id="tableau-card-order-persiste"),
        dcc.Store(id="tableau-table"),
        dcc.Store(id="tableau-total"),
        dcc.Store(id="tableau-total-unique"),
        dcc.Store(id="active-view"),
        dcc.Store(id="vue-resolution"),
        # Filtre d'organisme (?acheteur_id=/?titulaire_id=) résolu depuis l'URL
        dcc.Store(id="org-filter-resolution"),
        html.Script(
            type="application/ld+json",
            id="dataset_jsonld",
            children=[
                json.dumps(
                    {
                        "@context": "https://schema.org/",
                        "@type": "Dataset",
                        "name": "Données essentielles des marchés publics français (DECP)",
                        "description": "Données de marchés publics exhaustives décrivant les marchés publics attribués en France depuis 2018.",
                        "url": "https://colibre.fr",
                        "sameAs": "https://www.data.gouv.fr/datasets/608c055b35eb4e6ee20eb325",
                        "keywords": [
                            "marchés publics",
                            "commande publique",
                            "decp",
                            "public procurement",
                        ],
                        "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
                        "isAccessibleForFree": True,
                        "creator": {
                            "@type": "Organization",
                            "url": "https://colmo.tech",
                            "name": "Colmo",
                            "sameAs": "https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350",
                            "contactPoint": {
                                "@type": "ContactPoint",
                                "contactType": "Support et contact commercial",
                                "email": "colin@colmo.tech",
                            },
                        },
                        "includedInDataCatalog": {
                            "@type": "DataCatalog",
                            "name": "data.gouv.fr",
                        },
                        "distribution": [
                            {
                                "@type": "DataDownload",
                                "encodingFormat": "CSV",
                                "contentUrl": "https://www.data.gouv.fr/api/1/datasets/r/22847056-61df-452d-837d-8b8ceadbfc52",
                            },
                            {
                                "@type": "DataDownload",
                                "encodingFormat": "Parquet",
                                "contentUrl": "https://www.data.gouv.fr/api/1/datasets/r/11cea8e8-df3e-4ed1-932b-781e2635e432",
                            },
                        ],
                        **(
                            {"temporalCoverage": f"2018-01-01/{update_date_iso[:10]}"}
                            if update_date_iso
                            else {}
                        ),
                        "spatialCoverage": {
                            "@type": "Place",
                            "address": {"countryCode": "FR"},
                        },
                    },
                    indent=2,
                )
            ],
        ),
        dcc.Markdown(
            f"Ce tableau contient tous les marchés attribués en France. Il vous permet d'appliquer un filtre sur une ou plusieurs colonnes, et ainsi produire la liste de marchés dont vous avez besoin. Par défaut seules quelques colonnes sont affichées, mais vous pouvez en afficher jusqu'à {len(schema.names())} en cliquant sur le bouton **Colonnes**. Cet outil est assez puissant, lisez le mode d'emploi pour en tirer pleinement partie.",
            style={"maxWidth": "1000px"},
        ),
        html.Div(
            [],
            id="header",
        ),
        html.Div(id="vue-resolve-feedback"),
        html.Div(
            id="tableau-mode-wrapper",
            className="tableau-mode",
            children=[
                dcc.Loading(
                    overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    id="loading-home",
                    type="default",
                    children=[
                        html.Div(
                            [
                                # Modal du mode d'emploi
                                dbc.Button(
                                    "⍰ Mode d'emploi",
                                    id="tableau_help_open",
                                    color="secondary",
                                    outline=True,
                                    size="sm",
                                ),
                                dbc.Modal(
                                    [
                                        dbc.ModalHeader(
                                            dbc.ModalTitle("Mode d'emploi")
                                        ),
                                        dbc.ModalBody(
                                            [
                                                _help_button_legend(),
                                                html.Hr(),
                                                dcc.Markdown(
                                                    dangerously_allow_html=True,
                                                    children=f"""
                ##### Définition des colonnes

                Pour voir la définition d'une colonne et ses valeurs possibles, vous pouvez passer votre souris sur son en-tête ou bien consulter [la liste des champs](/projet/donnees#champs).

                ##### Vos réglages sont persistents

                Les filtres, les tris , le choix de colonnes, le placement et la largeur des colonnes sont automatiquement enregistrés dans votre navigateur et persistent même si vous changez de page ou si vous fermez votre navigateur. À votre retour, vous retrouverez cette page comme vous l'avez laissée.

                ##### Filtrer les colonnes

                Chaque colonne a son propre filtre : saisissez une valeur dans le champ situé juste sous son en-tête, ou cliquez sur l'icône entonnoir dans l'en-tête pour ouvrir le filtre complet.

                - Champs textuels : contient (par défaut), égal à, ne contient pas, commence par, se termine par...
                - Champs numériques (durée en mois, montant, nombre d'offres...) : égal à, supérieur à, inférieur à, entre (plage)...
                - Champs date : égal à, avant, après, entre (plage)...

                Dans le filtre complet (icône entonnoir), vous pouvez combiner deux conditions sur la même colonne avec **ET** ou **OU**.

                Vous pouvez filtrer plusieurs colonnes à la fois ; les filtres de colonnes différentes se cumulent toujours (ET).

                ##### Trier les données

                Cliquez sur l'en-tête d'une colonne pour la trier. Chaque clic change le tri dans cet ordre :

                1. tri croissant
                2. tri décroissant
                3. pas de tri

                Pour trier sur plusieurs colonnes à la fois, maintenez la touche `Maj` (Shift) enfoncée en cliquant sur les en-têtes suivants : la première colonne triée a la priorité, la suivante ne départage qu'au sein des groupes de valeurs identiques de la précédente, et ainsi de suite.

                ##### Défilement

                Le tableau charge les lignes au fur et à mesure que vous faites défiler la page, plutôt que par pages numérotées. Les en-têtes de colonnes (et leurs filtres) restent toujours visibles en haut du tableau pendant le défilement.

                ##### Afficher plus de colonnes

                Par défaut, un nombre réduit de colonnes est affiché pour ne pas surcharger la page. Mais vous avez le choix parmi {len(schema.names())} colonnes, ce serait dommage de vous limiter !

                Pour afficher plus de colonnes, cliquez sur le bouton **Colonnes** et cochez les colonnes à afficher.

                ##### Vues sauvegardées (abonnés)

                Une vue est un ensemble de filtres, de tris et de colonnes affichées que vous avez appliqués. Si vous êtes abonné, le bouton **Sauvegarder la vue** vous permet d'enregistrer la configuration actuelle sous un nom, et le menu **Mes vues** de la rappeler d'un clic plus tard.

                ##### Télécharger le résultat

                Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger (Excel)**.

                ##### Liens

                Les liens dans les colonnes Identifiant unique, Acheteur et Titulaire vous permettent de consulter une vue qui leur est dédiée
                (informations, marchés attribués/remportés, etc.)

                """,
                                                ),
                                            ],
                                        ),
                                        dbc.ModalFooter(
                                            dbc.Button(
                                                "Fermer",
                                                id="tableau_help_close",
                                                className="ms-auto",
                                                n_clicks=0,
                                            )
                                        ),
                                    ],
                                    id="tableau_help",
                                    is_open=False,
                                    fullscreen="md-down",
                                    scrollable=True,
                                    size="lg",
                                ),
                                # Bouton modal des colonnes affichées
                                dbc.Button(
                                    "Colonnes",
                                    id="tableau_columns_open",
                                    color="secondary",
                                    size="sm",
                                    className="column_list",
                                    title="Choisir les colonnes à afficher et masquer",
                                ),
                                html.Div(
                                    id="saved-views-bar",
                                    className="d-inline-flex align-items-center gap-2",
                                    children=[
                                        # Boutons enveloppés dans un <span> : Bootstrap met
                                        # `pointer-events: none` sur les boutons désactivés,
                                        # ce qui empêche le survol (et donc le `title`
                                        # natif) de fonctionner directement dessus. Le
                                        # `title` est donc porté par le span englobant.
                                        html.Span(
                                            id="btn-save-view-wrapper",
                                            className="d-inline-block",
                                            children=dbc.Button(
                                                "Sauvegarder la vue",
                                                id="btn-save-view",
                                                color="secondary",
                                                size="sm",
                                                # Grisé/désactivé pour les non-abonnés (le
                                                # callback toggle_saved_views_controls
                                                # affine au chargement).
                                                disabled=True,
                                            ),
                                        ),
                                        html.Span(
                                            id="saved-views-menu-wrapper",
                                            className="d-inline-block",
                                            children=dbc.DropdownMenu(
                                                id="saved-views-menu",
                                                label="Mes vues",
                                                color="secondary",
                                                size="sm",
                                                children=[],
                                                disabled=True,
                                                className="d-inline-block",
                                            ),
                                        ),
                                    ],
                                ),
                                dcc.Store(id="saved-views-refresh"),
                                dbc.Modal(
                                    id="save-view-modal",
                                    is_open=False,
                                    children=[
                                        dbc.ModalHeader(
                                            dbc.ModalTitle("Sauvegarder la vue")
                                        ),
                                        dbc.ModalBody(
                                            [
                                                dbc.Label("Nom de la vue"),
                                                dcc.Input(
                                                    id="save-view-name",
                                                    type="text",
                                                    className="form-control",
                                                ),
                                                html.Hr(className="my-3"),
                                                dbc.Label(
                                                    "Ou remplacer une vue existante"
                                                ),
                                                dbc.Select(
                                                    id="overwrite-view-select",
                                                    options=[],
                                                    placeholder="Sélectionner une vue…",
                                                ),
                                                html.Div(
                                                    id="save-view-feedback",
                                                    className="mt-2",
                                                ),
                                            ]
                                        ),
                                        dbc.ModalFooter(
                                            dbc.Button(
                                                "Enregistrer",
                                                id="btn-save-view-confirm",
                                                color="secondary",
                                            )
                                        ),
                                    ],
                                ),
                                dbc.Button(
                                    "Télécharger au format Excel",
                                    id="btn-download-data",
                                    color="secondary",
                                    size="sm",
                                    disabled=True,
                                ),
                                dcc.Download(id="download-data"),
                                dcc.Store(id="filtered_data", storage_type="memory"),
                                dbc.Button(
                                    "Réinitialiser",
                                    id="btn-tableau-reset",
                                    color="danger",
                                    outline=True,
                                    size="sm",
                                    title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                ),
                                # Interrupteur lignes ⇄ cards. Comme pour « Sauvegarder la
                                # vue », le title est porté par le <span> englobant :
                                # Bootstrap met `pointer-events: none` sur les contrôles
                                # désactivés, ce qui empêche le survol de les atteindre.
                                html.Span(
                                    id="tableau-mode-observatoire-wrapper",
                                    className="mode-observatoire-toggle",
                                    title=(
                                        ""
                                        if a_un_abonnement
                                        else "Fonctionnalité accessible en vous abonnant"
                                    ),
                                    children=[
                                        html.Span(
                                            "☰",
                                            id="tableau-mode-observatoire-icone-lignes",
                                            className="mode-observatoire-icone active",
                                            title="Afficher les lignes de données",
                                        ),
                                        dbc.Switch(
                                            id="tableau-mode-observatoire",
                                            value=False,
                                            disabled=not a_un_abonnement,
                                            className="mb-0",
                                        ),
                                        html.Span(
                                            "📊",
                                            id="tableau-mode-observatoire-icone-cards",
                                            className="mode-observatoire-icone",
                                            title="Afficher les visualisations de l'observatoire",
                                        ),
                                    ],
                                ),
                            ],
                            className="table-toolbar",
                        ),
                        html.Div(
                            id="share-url-box",
                            className="share-url-box d-none",
                            children=[
                                dbc.Label(
                                    "Lien direct vers cette vue :",
                                    className="mb-0",
                                    style={"fontSize": "0.9em"},
                                ),
                                # URL affichée comme texte sélectionnable : prend exactement
                                # sa largeur (pas de champ pleine largeur qui encombre) et
                                # passe à la ligne si le lien est long (pas de troncature).
                                html.Span(
                                    id="share-url-text",
                                    className="share-url-text",
                                    style={"wordBreak": "break-all", "minWidth": 0},
                                ),
                                dcc.Clipboard(
                                    target_id="share-url-text",
                                    title="Copier le lien vers cette vue",
                                    className="btn btn-outline-secondary btn-sm "
                                    "d-inline-flex align-items-center",
                                    children=[
                                        html.Img(
                                            src="/assets/copy.svg",
                                            alt="",
                                            style={
                                                "height": "1em",
                                                "verticalAlign": "-0.15em",
                                                "marginRight": "0.35em",
                                            },
                                        ),
                                        "Copier le lien",
                                    ],
                                    copied_children="✓ Copié",
                                ),
                            ],
                        ),
                        html.Div(
                            className="table-meta",
                            children=[
                                html.Span(id="nb_rows"),
                                html.Span(
                                    " · Données mises à jour le " + str(update_date)
                                ),
                            ],
                        ),
                        dbc.Modal(
                            [
                                dbc.ModalHeader(
                                    dbc.ModalTitle("Choix des colonnes à afficher")
                                ),
                                dbc.ModalBody(
                                    id="tableau_columns_body",
                                    children=make_column_picker("tableau"),
                                ),
                                dbc.ModalFooter(
                                    dbc.Button(
                                        "Fermer",
                                        id="tableau_columns_close",
                                        className="ms-auto",
                                        n_clicks=0,
                                    )
                                ),
                            ],
                            id="tableau_columns",
                            is_open=False,
                            fullscreen="md-down",
                            scrollable=True,
                            size="xl",
                        ),
                        DATATABLE,
                    ],
                ),
                # Le bloc des cards vit HORS de `loading-home` : ce dcc.Loading enveloppe la
                # barre d'outils et la grille, et tourne dès qu'un de ses descendants se met
                # à jour — imbriquer celui des cards dedans affichait deux spinners empilés
                # pour un seul callback. La modale « Montants » sort pour la même raison :
                # son `is_open` est piloté par un callback (dans src/pages/observatoire.py).
                dcc.Loading(
                    overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    type="default",
                    children=dbc.Row(
                        id="tableau-observatoire-cards",
                        className="mode-observatoire-cards d-none",
                        children=[],
                    ),
                ),
                montant_modal(),
            ],
        ),
    ]


def layout(**_):
    return _layout(current_user_has_subscription())


@callback(
    Output("tableau_grid", "getRowsResponse"),
    Output("tableau-total", "data"),
    Output("tableau-total-unique", "data"),
    Input("tableau_grid", "getRowsRequest"),
    prevent_initial_call=True,
)
def get_rows_tableau(request):
    if request is None:
        return no_update, no_update, no_update
    filter_model = request.get("filterModel") or None
    sort_model = request.get("sortModel") or None
    # AG Grid renvoie une nouvelle requête getRowsRequest pour chaque bloc de
    # défilement infini, avec le même filterModel tant que le filtre ne change
    # pas. Ne compter qu'une recherche par changement de filtre/tri (bloc 0),
    # pas une par bloc chargé au défilement.
    if filter_model and request.get("startRow", 0) == 0:
        track_search(json.dumps(filter_model), "tableau")
    rows, total, total_unique = fetch_grid_page(
        filter_model,
        sort_model,
        request.get("startRow", 0),
        request.get("endRow", 100),
    )
    return {"rowData": rows, "rowCount": total}, total, total_unique


@callback(
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("btn-download-data", "children"),
    Output("btn-download-data", "title"),
    Output("btn-download-data", "href"),
    Input("tableau-total", "data"),
    Input("tableau-total-unique", "data"),
    Input("tableau_grid", "filterModel"),
)
def update_meta(total, total_unique, filter_model):
    total = total or 0
    total_unique = total_unique or 0
    nb_rows = (
        f"{format_number(total_unique) or 0} marchés "
        f"({format_number(total) or 0} lignes)"
    )
    if not filter_model:
        # Aucun filtre (les colonnes masquées n'entrent pas en compte) :
        # renvoyer directement vers le CSV complet publié sur data.gouv.fr
        # plutôt que de générer un export de plusieurs millions de lignes.
        # dbc.Button rend un <a> dès qu'il a un href, ce qui fait faire le
        # téléchargement par le navigateur (avec reprise) sans quitter la
        # page.
        return (
            nb_rows,
            False,
            "Télécharger toutes les données",
            "Le jeu de données complet est téléchargé depuis data.gouv.fr au format CSV.",
            DECP_CSV_COMPLET_URL,
        )
    download_disabled, download_text, download_title, _download_format = (
        get_button_properties(total)
    )
    return nb_rows, download_disabled, download_text, download_title, None


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_model, column_state):
    if not filter_model:
        # Sans filtre, le bouton pointe déjà (via href) vers le CSV complet
        # de data.gouv.fr — un clic ne doit pas en plus déclencher la
        # génération d'un fichier de plusieurs millions de lignes ici.
        return no_update

    from src.utils.grid import export_dataframe

    sort_model = [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or [])
        if c.get("sort")
    ]
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    track_search(json.dumps(filter_model), "tab download")
    df = export_dataframe(filter_model, sort_model, hidden_columns)

    if df.height > EXCEL_MAX_ROWS:
        extension = "csv"

        def to_bytes(buffer):
            write_csv(df, buffer)
    else:
        extension = "xlsx"

        def to_bytes(buffer):
            write_styled_excel(df, buffer)

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    track_download("/tableau")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.{extension}")


@callback(
    Output("tableau_help", "is_open"),
    [Input("tableau_help_open", "n_clicks"), Input("tableau_help_close", "n_clicks")],
    [State("tableau_help", "is_open")],
)
def toggle_tableau_help(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Input("tableau_column_list", "selectedRows"),
    State("tableau-hidden-columns", "data"),
    prevent_initial_call=True,
)
def update_hidden_columns_from_checkboxes(selected_rows, current_hidden):
    # selected_rows == [] est un choix explicite (tout décoché), à ne pas
    # confondre avec « pas encore de préférence » (store à None) : cf.
    # apply_hidden_columns et update_checkboxes_from_hidden_columns, qui
    # distinguent aussi ce cas. Sans ce traitement uniforme, décocher/cocher
    # toutes les colonnes se faisait écraser au tour suivant.
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
    Output("tableau_grid", "columnDefs"),
    Input("tableau-hidden-columns", "data"),
    State("tableau_grid", "columnState"),
)
def apply_hidden_columns(hidden_columns, column_state):
    if hidden_columns is None:
        hidden_columns = get_default_hidden_columns("tableau")
    defs = grid_column_defs(hidden_columns)
    return apply_persisted_layout(defs, column_state)


@callback(
    Output("tableau_column_list", "selectedRows"),
    # La modale démonte la grille à la fermeture : la grille recréée à la
    # réouverture n'a plus de filtre rapide, le champ de recherche est vidé.
    Output({"type": "column-search", "page": "tableau"}, "value"),
    Input("tableau_columns", "is_open"),
    State("tableau-hidden-columns", "data"),
)
def update_checkboxes_from_hidden_columns(is_open, hidden_cols):
    """Alimente les cases à cocher à l'ouverture de la modale, et seulement là.

    Déclencher sur le store créerait un liage permanent dans les deux sens
    (store → cases → store). Son écho partirait au chargement avec l'état par
    défaut et pourrait arriver APRÈS l'application d'une vue partagée, écrasant
    silencieusement ses colonnes — cf. issue #139. Or les cases vivent dans une
    modale : les tenir à jour tant qu'elle est fermée ne sert à rien.

    Il reste un écho, à l'ouverture — une action utilisateur, jamais
    concurrente d'un chargement de page — et il recalcule la valeur que le
    store contient déjà : l'écriture est sans effet.
    """
    if not is_open:
        return no_update, no_update

    # None = pas encore de préférence enregistrée (première visite) ; []
    # est un choix explicite (« ne rien masquer »/tout afficher) et doit
    # être respecté tel quel, cf. update_hidden_columns_from_checkboxes.
    if hidden_cols is None:
        hidden_cols = get_default_hidden_columns("tableau")

    # Coche toutes les colonnes qui ne sont PAS masquées
    return selection_from_hidden_columns(hidden_cols), ""


@callback(
    Output("tableau_columns", "is_open"),
    Input("tableau_columns_open", "n_clicks"),
    Input("tableau_columns_close", "n_clicks"),
    State("tableau_columns", "is_open"),
)
def toggle_tableau_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Output("tableau_grid", "columnState", allow_duplicate=True),
    Input("btn-tableau-reset", "n_clicks"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def reset_view(n_clicks, column_state):
    # On ne touche qu'au tri (sort/sortIndex) : on réécrit le columnState tel
    # quel pour préserver la largeur, l'épinglage et l'ordre des colonnes
    # choisis par l'utilisateur (auparavant resetColumnState les effaçait
    # aussi, cf. #47).
    cleared_sort = [
        {**col, "sort": None, "sortIndex": None} for col in (column_state or [])
    ]
    return {}, cleared_sort


@callback(
    Output("btn-save-view", "disabled"),
    Output("saved-views-menu", "disabled"),
    Output("btn-save-view-wrapper", "title"),
    Output("saved-views-menu-wrapper", "title"),
    Input("tableau_url", "pathname"),
)
def toggle_saved_views_controls(_pathname):
    # La barre reste visible pour tous ; « Sauvegarder la vue » et « Mes vues »
    # sont grisés et désactivés pour les non-abonnés (le gating serveur de
    # save_view reste en place via prepare_view_to_save). L'infobulle est
    # portée par les <span> englobants, cf. layout.
    disabled = saved_views_ui.controls_disabled(current_user_has_subscription())
    tooltip = "Fonctionnalité accessible en vous abonnant" if disabled else ""
    return disabled, disabled, tooltip, tooltip


def resolve_vue_from_url(search: str) -> dict | None:
    """Extrait ?vue=... de la query string et le résout. Renvoie None s'il n'y a
    pas de paramètre `vue` (chargement normal du tableau)."""
    params = parse_qs((search or "").lstrip("?"))
    values = params.get("vue")
    if not values:
        return None
    return saved_views_resolve.resolve_vue_param(values[0], schema)


_ORG_FILTER_PARAMS = ("acheteur_id", "titulaire_id")


def filtre_org_depuis_url(search: str) -> dict | None:
    """Extrait ?acheteur_id= / ?titulaire_id= de la query string et les traduit
    en filterModel AG Grid (filtre texte « égal à »). Renvoie None s'il n'y a
    pas de paramètre d'organisme exploitable (valeur vide ou blanche ignorée).

    La colonne correspondante n'a pas besoin d'être affichée : le filtrage de
    la grille est fait côté serveur (filtermodel_to_ast → SQL), indépendamment
    des columnDefs.
    """
    params = parse_qs((search or "").lstrip("?"))
    filter_model = {}
    for col in _ORG_FILTER_PARAMS:
        values = params.get(col)
        if values and values[0].strip():
            filter_model[col] = {
                "filterType": "text",
                "type": "equals",
                "filter": values[0].strip(),
            }
    return filter_model or None


@callback(
    Output("vue-resolution", "data"),
    Input("tableau_url", "search"),
)
def store_vue_resolution(search):
    # Un filtre d'organisme dans l'URL (?acheteur_id=/?titulaire_id=) prime
    # sur une éventuelle vue partagée (?vue=) : il réinitialise les filtres
    # pour appliquer le sien, on n'applique donc pas aussi la vue.
    if filtre_org_depuis_url(search) is not None:
        return no_update
    resolution = resolve_vue_from_url(search)
    return resolution if resolution is not None else no_update


@callback(
    Output("org-filter-resolution", "data"),
    Input("tableau_url", "search"),
)
def store_org_filter(search):
    filtre = filtre_org_depuis_url(search)
    return filtre if filtre is not None else no_update


@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Input("org-filter-resolution", "data"),
    prevent_initial_call=True,
)
def apply_org_filter(filtre):
    # Réinitialise les filtres (remplace le filterModel persisté en
    # localStorage) puis applique le filtre d'identifiant. Les tris et les
    # colonnes ne sont pas touchés.
    return filtre if filtre else no_update


def apply_vue_resolution(resolution):
    """Mappe le dict de résolution vers les sorties de la grille + le store
    `active-view`. Séparé du callback pour être testable sans contexte Dash.

    Sorties : (filterModel, columnState, hidden-columns, active-view, feedback).
    Le masquage du bloc de partage n'est PAS géré par comparaison d'état ici :
    c'est un écouteur d'événements AG Grid côté client (eventListeners →
    `dashAgGridFunctions.hideShareOnUserAction`) qui efface `active-view` sur
    action utilisateur (filtre/tri/colonne), en ignorant l'application
    programmatique (source == 'api'). Voir src/assets/dashAgGridFunctions.js.
    """
    if resolution is None:
        return (no_update,) * 5
    if not resolution["found"]:
        return (
            no_update,
            no_update,
            no_update,
            None,  # active-view : masque le bloc de partage
            html.Div(resolution["error"], className="alert alert-warning py-2"),
        )
    return (
        resolution["filter_model"],
        resolution["column_state"],
        resolution["hidden_columns"],
        {"token": resolution["token"], "url": resolution["url"]},
        "",
    )


@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Output("tableau_grid", "columnState", allow_duplicate=True),
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Output("active-view", "data", allow_duplicate=True),
    Output("vue-resolve-feedback", "children"),
    Input("vue-resolution", "data"),
    prevent_initial_call=True,
)
def apply_vue_resolution_cb(resolution):
    return apply_vue_resolution(resolution)


# Classe Bootstrap de visibilité du bloc de partage. On bascule la CLASSE
# (d-flex ↔ d-none, toutes deux `!important`) et non le style inline : `.d-flex`
# est `display: flex !important` et l'emporterait sur un `style={"display":
# "none"}` inline, rendant le bloc impossible à masquer par le style.
_SHARE_BOX_SHOWN = "share-url-box d-flex align-items-center gap-2 my-2"
_SHARE_BOX_HIDDEN = "share-url-box d-none"


@callback(
    Output("share-url-box", "className"),
    Output("share-url-text", "children"),
    Input("active-view", "data"),
)
def render_share_box(active_view):
    if active_view and active_view.get("url"):
        return _SHARE_BOX_SHOWN, active_view["url"]
    return _SHARE_BOX_HIDDEN, ""


@callback(
    Output("save-view-modal", "is_open"),
    Input("btn-save-view", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_save_view_modal(_open):
    return True


@callback(
    Output("save-view-modal", "is_open", allow_duplicate=True),
    Output("save-view-feedback", "children"),
    Output("saved-views-refresh", "data"),
    Output("active-view", "data", allow_duplicate=True),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-name", "value"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_model, column_state):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return (
            True,
            html.Span(error, style={"color": "red"}),
            no_update,
            no_update,
        )
    # On stocke l'AST canonique (indépendant de l'UI), pas le filterModel brut
    # d'AG Grid : cf. spec de conception, "l'AST (JSON) + columnState,
    # indépendant de l'UI".
    ast = filtermodel_to_ast(filter_model, schema)
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state or []})
    token = saved_views_db.upsert(current_user.id, "tableau", clean_name, query)
    active = {"token": token, "url": saved_views_ui.build_view_url(clean_name, token)}
    return (
        False,
        html.Span(f"Vue « {clean_name} » enregistrée.", style={"color": "green"}),
        clean_name,
        active,
    )


@callback(
    Output("saved-views-menu", "children"),
    Input("tableau_url", "pathname"),
    Input("saved-views-refresh", "data"),
)
def populate_saved_views_menu(_pathname, _refresh):
    if not current_user_has_subscription():
        return []
    views = saved_views_db.list_views(current_user.id, "tableau")
    items = saved_views_ui.saved_views_items(views)
    header = dbc.DropdownMenuItem(
        "Gérer mes vues", href="/compte/vues", className="text-primary"
    )
    # Lien de gestion en tête, séparé de la liste des vues (séparateur seulement
    # s'il y a des vues en dessous, pour éviter un séparateur orphelin).
    return [header, *([dbc.DropdownMenuItem(divider=True)] if items else []), *items]


@callback(
    Output("tableau_grid", "filterModel"),
    Output("tableau_grid", "columnState"),
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Output("active-view", "data", allow_duplicate=True),
    Input({"type": "saved-view-item", "index": ALL}, "n_clicks"),
    State({"type": "saved-view-item", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def apply_saved_view(n_clicks, ids):
    triggered = ctx.triggered_id
    if not triggered or not any(n_clicks):
        return no_update, no_update, no_update, no_update
    row = saved_views_db.get(triggered["index"], current_user.id)
    if not row:
        return no_update, no_update, no_update, no_update
    try:
        view = json.loads(row["query"])
        # L'AST canonique est stocké (pas le filterModel brut d'AG Grid) :
        # cf. save_view. `ast_from_dict(None)` -> None et
        # `ast_to_filtermodel(None, schema)` -> {} si la vue est d'un ancien
        # format (sans clé "ast") : dégradation propre, la vue se rappelle
        # sans filtre plutôt que de planter.
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Vue enregistrée avant la migration vers AG Grid (Task 10) : row["query"]
        # est encore une query string (ex. "filtres=a&tris=b"), pas du JSON. On
        # échoue proprement plutôt que de planter le callback ; pas de
        # migration automatique de l'ancien format.
        logger.warning(
            "Vue sauvegardée au format pré-migration, impossible de l'appliquer : "
            f"id={row['id']!r} name={row['name']!r}"
        )
        return no_update, no_update, no_update, no_update
    # tableau-hidden-columns pilote les cases à cocher du sélecteur de colonnes
    # (update_checkboxes_from_hidden_columns) et la régénération des
    # columnDefs (apply_hidden_columns) ; sans cette sortie, ce store restait
    # désynchronisé du columnState rappelé (revue finale #41). Même extraction
    # que download_data.
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    active = {
        "token": row["token"],
        "url": saved_views_ui.build_view_url(row["name"], row["token"]),
    }
    return filter_model, column_state, hidden_columns, active


@callback(
    Output("overwrite-view-select", "options"),
    Input("save-view-modal", "is_open"),
)
def populate_overwrite_select(is_open):
    if not is_open or not current_user_has_subscription():
        return []
    views = saved_views_db.list_views(current_user.id, "tableau")
    return [{"label": v["name"], "value": v["name"]} for v in views]


clientside_callback(
    "function(val) { return val != null ? val : window.dash_clientside.no_update; }",
    Output("save-view-name", "value"),
    Input("overwrite-view-select", "value"),
    prevent_initial_call=True,
)


MODE_OBSERVATOIRE_CLASSES = "mode-observatoire-cards"
SANS_FILTRE = (
    "Appliquez au moins un filtre à une colonne pour visualiser les données. "
    "Sans filtre, les visualisations porteraient sur l'intégralité des marchés "
    "et seraient longues à calculer."
)


def _normalize_filter_model(filter_model: dict | None) -> str:
    """Clé de cache déterministe pour un filterModel AG Grid."""
    return json.dumps(filter_model or {}, sort_keys=True)


@cache.memoize()
def _cards_pour_filtre(filter_model_json: str, theme: str):
    """Cards de l'observatoire pour le filtre courant de la grille.

    Mémoïsé sur le filterModel normalisé : basculer d'avant en arrière sur le
    même filtre ne relance pas la requête. Les colonnes masquées dans la
    grille sont ignorées — les cards ont besoin de colonnes que l'utilisateur
    n'affiche pas forcément (cf. issue #137) — et les tris aussi, ils
    n'influent sur aucune agrégation.

    `theme` fait partie de la clé de cache : les figures sont colorées côté
    serveur (#118).
    """
    ast = filtermodel_to_ast(json.loads(filter_model_json), schema)
    where_sql, params = ast_to_sql(ast, schema)
    dff = query_marches(
        where_sql=where_sql, params=params, columns=observatoire_cards_columns()
    )
    return build_dashboard_cards(
        dff,
        theme=theme,
        context="tableau",
        scope=scope_key(filter_model_json),
    )


@callback(
    Output("tableau-observatoire-cards", "children"),
    Output("tableau-observatoire-cards", "className"),
    Input("tableau-mode-observatoire", "value"),
    Input("tableau_grid", "filterModel"),
    Input("tableau-card-order", "data"),
    prevent_initial_call=True,
)
def update_mode_observatoire_cards(mode_actif, filter_model, card_order):
    if not mode_actif:
        # On masque sans vider : les cards déjà calculées restent montées, donc
        # le retour au mode observatoire est instantané tant que le filtre n'a
        # pas bougé.
        return no_update, f"{MODE_OBSERVATOIRE_CLASSES} d-none"

    if not current_user_has_subscription():
        return (
            dbc.Alert(
                "Fonctionnalité accessible en vous abonnant.",
                color="secondary",
                className="w-100",
            ),
            MODE_OBSERVATOIRE_CLASSES,
        )

    if not filter_model:
        return (
            dbc.Alert(SANS_FILTRE, color="secondary", className="w-100"),
            MODE_OBSERVATOIRE_CLASSES,
        )

    track_search(json.dumps(filter_model), "tab observatoire")
    cards = _cards_pour_filtre(_normalize_filter_model(filter_model), current_theme())

    # Après le cache mémoïsé de _cards_pour_filtre, jamais dedans : l'ordre
    # ferait exploser la cardinalité des entrées (#107).
    if card_order:
        cards = reorder_cards(cards, card_order)

    return [cards_drag_marker("tableau-card-order-nouveau"), *cards], (
        MODE_OBSERVATOIRE_CLASSES
    )


@callback(
    Output(
        {"type": GRID_TYPE, "context": "tableau", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "tableau", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State("tableau_grid", "filterModel"),
    prevent_initial_call=True,
)
def get_top_org_rows_tableau(request, filter_model):
    """Lignes d'une grille top, sur le filtre courant de la grille de marchés."""
    if request is None or ctx.triggered_id is None:
        return no_update
    where_sql, params = ast_to_sql(
        filtermodel_to_ast(filter_model or {}, schema), schema
    )
    return fetch_top_org_page(ctx.triggered_id["org_type"], where_sql, params, request)


@callback(
    Output("tableau-card-order", "data"),
    Input("tableau_url", "pathname"),
)
def load_tableau_card_order(_pathname):
    """Ordre enregistré par l'utilisateur, relu à chaque rendu de la page."""
    if not current_user.is_authenticated or not current_user_has_subscription():
        return None
    return get_card_order(current_user.id)


@callback(
    Output("tableau-card-order-persiste", "data"),
    Input("tableau-card-order-nouveau", "data"),
    prevent_initial_call=True,
)
def persist_tableau_card_order(card_order):
    """Enregistre l'ordre poussé par le drag & drop du mode observatoire."""
    if not card_order:
        return no_update
    if not current_user.is_authenticated or not current_user_has_subscription():
        return no_update
    save_card_order(current_user.id, card_order)
    return card_order


@callback(
    Output("tableau-mode-observatoire", "disabled"),
    Output("tableau-mode-observatoire-wrapper", "title"),
    Input("tableau_url", "pathname"),
)
def toggle_mode_observatoire_control(_pathname):
    """L'interrupteur reste visible pour tout le monde, mais n'est actionnable
    que par les abonnés (le gating serveur reste dans
    update_mode_observatoire_cards). Le title est porté par le <span>
    englobant, cf. layout."""
    a_un_abonnement = current_user_has_subscription()
    return (
        not a_un_abonnement,
        "" if a_un_abonnement else "Fonctionnalité accessible en vous abonnant",
    )


# Persistance du mode d'affichage, côté client pour éviter tout flash :
# le dcc.Store(storage_type="local") est hydraté depuis localStorage avant
# les callbacks initiaux, la restauration se fait donc dans le même cycle JS.
# Un non-abonné (interrupteur désactivé dès le layout) ne restaure jamais le
# mode observatoire, même s'il l'avait mémorisé avant.
clientside_callback(
    """
    function(pathname, stored, desactive) {
        if (desactive) {
            return false;
        }
        return stored === true;
    }
    """,
    Output("tableau-mode-observatoire", "value"),
    Input("tableau_url", "pathname"),
    State("tableau-mode-observatoire-persiste", "data"),
    State("tableau-mode-observatoire", "disabled"),
)


clientside_callback(
    """
    function(value) {
        return value;
    }
    """,
    Output("tableau-mode-observatoire-persiste", "data"),
    Input("tableau-mode-observatoire", "value"),
    prevent_initial_call=True,
)


# Bascule de l'affichage côté client : la classe pose le masquage du corps de
# la grille (l'en-tête et ses filtres restent visibles et actifs) et allume
# l'icône correspondante. Clientside pour que le basculement soit immédiat,
# sans attendre l'aller-retour serveur qui calcule les cards.
clientside_callback(
    """
    function(mode_actif) {
        return [
            mode_actif ? "tableau-mode mode-observatoire" : "tableau-mode",
            mode_actif ? "mode-observatoire-icone" : "mode-observatoire-icone active",
            mode_actif ? "mode-observatoire-icone active" : "mode-observatoire-icone",
        ];
    }
    """,
    Output("tableau-mode-wrapper", "className"),
    Output("tableau-mode-observatoire-icone-lignes", "className"),
    Output("tableau-mode-observatoire-icone-cards", "className"),
    Input("tableau-mode-observatoire", "value"),
)
