import math
from datetime import datetime
from typing import Literal

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from dash import MATCH, Input, State, clientside_callback, dash_table, dcc, html
from dash_extensions.javascript import Namespace

from src.db import schema
from src.theme import SOMBRE, current_theme
from src.utils import logger
from src.utils.cache import cache
from src.utils.data import DATA_SCHEMA, DEPARTEMENTS_GEOJSON, schema_field_rows
from src.utils.table import format_number

ORG_COLORS = {
    "acheteur": "#E69F00",  # orange
    "titulaire": "#56B4E9",  # bleu ciel
}


# Mode sombre (#118) : palette Earthsong, plus sombre que les palettes du
# thème clair mais contrastée entre ses teintes.
FOND_SOMBRE = "#292520"
TEXTE_SOMBRE = "#e5c7a9"
GRILLE_SOMBRE = "#675f54"
ATTENUE_SOMBRE = "#968c83"  # --earth-muted

PALETTE_SOMBRE = [
    "#c94234",
    "#1398b9",
    "#85c54c",
    "#f5ae2e",
    "#d0633d",
    "#509552",
    "#e0d561",
    "#5fdaff",
    "#ff9269",
    "#84f088",
    "#ff645a",
    "#98e036",
]


def _assombrir(hex_color: str, facteur: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*(round(c * (1 - facteur)) for c in (r, g, b)))


# ~24 sources dans le graphique des sources : la palette Earthsong puis ses
# variantes assombries, pour 24 teintes distinctes (équivalent sombre de Dark24).
PALETTE_SOMBRE_24 = PALETTE_SOMBRE + [_assombrir(c, 0.4) for c in PALETTE_SOMBRE]

ECHELLE_SOMBRE = [FOND_SOMBRE, "#e06c57"]

# Jaune et bleu Earthsong assombris : moins éclatants sur les tuiles sombres,
# et le compte en blanc des clusters (dash_clientside.js) y gagne en contraste.
ORG_COLORS_SOMBRE = {
    "acheteur": _assombrir("#f5ae2e", 0.15),  # -> #d09427
    "titulaire": _assombrir("#1398b9", 0.15),  # -> #10819d
}


def _theme(theme: str | None) -> str:
    return theme or current_theme()


def org_colors(theme: str) -> dict[str, str]:
    return ORG_COLORS_SOMBRE if theme == SOMBRE else ORG_COLORS


def appliquer_theme(fig: go.Figure, theme: str) -> go.Figure:
    """Fond, police et grille Earthsong en sombre ; sans effet en clair."""
    if theme != SOMBRE:
        return fig
    fig.update_layout(
        paper_bgcolor=FOND_SOMBRE,
        plot_bgcolor=FOND_SOMBRE,
        font_color=TEXTE_SOMBRE,
        # Barre d'outils : fond blanc translucide et icônes grises par défaut
        modebar={
            "bgcolor": "rgba(0,0,0,0)",
            "color": ATTENUE_SOMBRE,
            "activecolor": TEXTE_SOMBRE,
        },
    )
    fig.update_xaxes(
        gridcolor=GRILLE_SOMBRE, linecolor=GRILLE_SOMBRE, zerolinecolor=GRILLE_SOMBRE
    )
    fig.update_yaxes(
        gridcolor=GRILLE_SOMBRE, linecolor=GRILLE_SOMBRE, zerolinecolor=GRILLE_SOMBRE
    )
    fig.update_geos(bgcolor=FOND_SOMBRE)
    return fig


def get_barchart_sources(lff: pl.LazyFrame, type_date: str, theme: str | None = None):
    theme = _theme(theme)
    labels = {
        "dateNotification": "notification",
        "datePublicationDonnees": "publication des données",
    }

    now_year = datetime.now().year

    lff = lff.select("uid", type_date, "sourceDataset")

    lff = lff.unique("uid")

    # Rassemblement des datasets Atexo pour ne pas surcharger le graphique
    lff = lff.with_columns(
        pl.when(pl.col("sourceDataset").str.starts_with("atexo"))
        .then(pl.lit("plateformes atexo"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    # Rassemblement des datasets AWS pour ne pas surcharger le graphique
    lff = lff.with_columns(
        pl.when(pl.col("sourceDataset").str.contains(r"aws|marches\-publics.info"))
        .then(pl.lit("aws"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    lff = lff.with_columns(pl.col(type_date).dt.year().alias("annee"))
    lff = lff.filter(
        pl.col(type_date).is_not_null() & pl.col("annee").is_between(2019, now_year)
    )
    lff = lff.with_columns(pl.col(type_date).cast(pl.String).str.head(7))
    lff = (
        lff.group_by([type_date, "sourceDataset"])
        .len()
        .sort(by=[type_date, "len"], descending=True)
    )

    lff = lff.sort(by=["sourceDataset"], descending=False)

    dff: pl.DataFrame = lff.collect(engine="streaming")

    # ~24 sources distinctes : la palette Plotly par défaut (10 couleurs) se
    # répète. Dark24 fournit 24 couleurs uniques, ce qui suffit à toutes les
    # distinguer sans recourir à des motifs.
    fig = px.bar(
        dff,
        x=type_date,
        y="len",
        color="sourceDataset",
        color_discrete_sequence=(
            PALETTE_SOMBRE_24 if theme == SOMBRE else px.colors.qualitative.Dark24
        ),
        labels={
            "len": "Nombre de marchés",
            type_date: f"Mois de {labels[type_date]}",
            "sourceDataset": "Source de données",
        },
    )
    fig = appliquer_theme(fig, theme)

    graph = dcc.Graph(figure=fig)

    return graph


# Fichiers distants (data.gouv.fr) régénérés au plus une fois par jour : sans
# cache, chaque visite de /projet/donnees les retéléchargeait (~0,9 s cumulées).
# Une exception n'est pas mise en cache, un échec réseau est donc retenté.
DUREE_CACHE_SOURCES = 6 * 60 * 60


@cache.memoize(timeout=DUREE_CACHE_SOURCES)
def _lire_stats_sources(source_path: str) -> pl.DataFrame:
    return pl.read_csv(source_path)


@cache.memoize(timeout=DUREE_CACHE_SOURCES)
def _lire_matrice_doublons() -> pl.DataFrame:
    lff = pl.scan_parquet(
        "https://www.data.gouv.fr/api/1/datasets/r/a545bf6c-8b24-46ed-b49f-a32bf02eaffa"
    ).sort("sourceDataset")
    lff = lff.select(
        ["sourceDataset", "unique"] + sorted(lff.collect_schema().names()[2:])
    )
    return lff.collect()


def get_sources_tables(source_path) -> html.Div:
    try:
        if not source_path:
            raise ValueError("SOURCE_STATS_CSV_PATH non défini")
        dff = _lire_stats_sources(source_path)
    except Exception as e:
        logger.warning(f"Sources de données indisponibles ({e})")
        return html.Div("Sources de données momentanément indisponibles.")
    dff = dff.with_columns(
        (
            pl.lit('<a href = "')
            + pl.col("url")
            + pl.lit('">')
            + pl.col("nom")
            + pl.lit("</a>")
        ).alias("nom"),
    )
    dff = dff.drop("url", "unique")
    dff = dff.sort(by=["nb_marchés"], descending=True)
    # nb_marchés et nb_acheteurs restent numériques dans rowData (tri AG Grid
    # numérique) ; le formatage français est fait côté grille via
    # valueFormatter, pas ici avec format_number.

    columns = {
        "nom": "Nom de la source",
        "organisation": "Responsable de publication",
        "nb_marchés": "Nb de marchés",
        "nb_acheteurs": "Nb d'acheteurs",
        "code": "Code",
    }

    column_defs = []
    for col in dff.columns:
        col_def = {"field": col, "headerName": columns[col], "sortable": True}
        if col in ("nom", "organisation"):
            col_def |= {
                "cellRenderer": "markdown",
                "wrapText": True,
                "autoHeight": True,
                "flex": 2,
                "minWidth": 220,
            }
        elif col in ("nb_marchés", "nb_acheteurs"):
            col_def |= {
                "type": "rightAligned",
                "flex": 1,
                "valueFormatter": {
                    "function": (
                        "params.value == null ? 'N/A' : "
                        "Intl.NumberFormat('fr-FR').format(params.value)"
                    )
                },
            }
        else:
            col_def["flex"] = 1
        column_defs.append(col_def)

    return html.Div(
        client_grid(
            "source_table",
            column_defs,
            dff.to_dicts(),
            defaultColDef={"valueFormatter": {"function": "params.value ?? 'N/A'"}},
        )
    )


class DataTable(dash_table.DataTable):
    def __init__(
        self,
        dtid: str,
        hidden_columns: list[str] | None = None,
        data: list[dict[str, str | int | float | bool]] | None = None,
        columns: list[dict[str, str]] | None = None,
        page_size: int = 20,
        page_action: Literal["native", "custom", "none"] = "native",
        sort_action: Literal["native", "custom", "none"] = "native",
        filter_action: Literal["native", "custom", "none"] = "native",
        style_cell_conditional: list | None = None,
        style_cell: dict | None = None,
        **kwargs,
    ):
        # Styles de base
        style_cell_conditional_common = [
            {
                "if": {"column_id": "objet"},
                "minWidth": "350px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "acheteur_id"},
                "minWidth": "160px",
                "overflow": "hidden",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "acheteur_nom"},
                "minWidth": "250px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "titulaire_nom"},
                "minWidth": "250px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
        ]

        style_cell_common = {"fontFamily": "Inter", "fontSize": "16px"}

        for key in DATA_SCHEMA.keys():
            field = DATA_SCHEMA[key]
            if field["type"] in ["number", "integer"]:
                rule = {
                    "if": {"column_id": field["name"]},
                    "textAlign": "right",
                    # "fontFamily": "Fira Code",
                }
                style_cell_conditional_common.append(rule)

        style_cell_conditional = (
            style_cell_conditional or []
        ) + style_cell_conditional_common
        if style_cell:
            style_cell.update(style_cell_common)
        else:
            style_cell = style_cell_common
        style_header = style_cell

        # Initialisation de la classe parente avec les arguments
        super().__init__(
            id=dtid,
            data=data,
            columns=columns,
            cell_selectable=False,
            page_size=page_size,
            filter_action=filter_action,
            page_action=page_action,
            filter_options={
                "case": "insensitive",
                "placeholder_text": "Filtre de colonne...",
            },
            sort_action=sort_action,
            sort_mode="multi",
            row_deletable=False,
            page_current=0,
            style_cell_conditional=style_cell_conditional,
            data_timestamp=0,
            markdown_options={"html": True},
            style_header=style_header,
            style_cell=style_cell,
            tooltip_duration=8000,
            tooltip_delay=350,
            hidden_columns=hidden_columns,
            **kwargs,  # Possibilité de remplacer des arguments
        )


def get_duplicate_matrix(theme: str | None = None) -> dcc.Graph:
    """
    Fonction développée avec l'aide de la LLM Euria d'Infomaniak.
    :return:
    """
    theme = _theme(theme)
    dff = _lire_matrice_doublons()

    # Extract data
    z_data = dff.select(pl.all().exclude("sourceDataset")).fill_null(0).to_numpy()
    x_labels = dff.columns[1:]  # columns after "sourceDataset"
    y_labels = dff["sourceDataset"].to_list()

    # Create heatmap
    colorscale = (
        [[0.0, FOND_SOMBRE], [0.10, "#d0633d"], [1.0, "#ff9269"]]
        if theme == SOMBRE
        else [
            [0.0, "white"],  # 0% → white
            [0.10, "lightsalmon"],  # 10% → light warm tone
            [1.0, "darkred"],  # 100% → deep red
        ]
    )
    fig = go.Figure(
        data=go.Heatmap(
            z=z_data,
            x=x_labels,
            y=y_labels,
            colorscale=colorscale,
            zmin=0,
            zmax=1,
            hoverongaps=False,
            showscale=True,
            hovertemplate=(
                "<b>%{z:.0%}</b> des marchés présents dans <b>%{y}</b> sont également présents dans <b>%{x}</b>"
            ),
        )
    )

    # Hauteur adaptée au nombre de sources pour que chaque libellé ait sa
    # propre ligne (sinon Plotly n'affiche qu'un libellé sur deux faute de
    # place).
    height = max(1000, 22 * len(y_labels) + 150)

    # Update layout: make it wider and taller
    fig.update_layout(
        title="",
        xaxis_title="Sources de données",
        yaxis_title="Sources de données",
        yaxis=dict(autorange="reversed", tickmode="linear", dtick=1),
        xaxis=dict(tickangle=45, tickfont=dict(size=10)),  # Smaller x-tick labels
        coloraxis_colorbar=dict(title="Percentage", tickfont=dict(size=10)),
        width=1000,  # Wider
        height=height,
        font=dict(size=11),  # Overall font size
        margin=dict(l=100, r=50, t=80, b=100),  # Add margin for labels
    )
    fig = appliquer_theme(fig, theme)

    return dcc.Graph(figure=fig)


def build_org_markers(
    lff: pl.LazyFrame,
    org_type: Literal["acheteur", "titulaire"],
    theme: str | None = None,
) -> list[dict]:
    """Regroupe les marchés par point géographique pour un type d'organisme.

    Renvoie [] (sans exception) si les colonnes longitude/latitude de ce
    type sont absentes du LazyFrame (ex: tests/test.parquet).
    """
    theme = _theme(theme)
    lon_col = f"{org_type}_longitude"
    lat_col = f"{org_type}_latitude"
    nom_col = f"{org_type}_nom"

    available = set(lff.collect_schema().names())
    if lon_col not in available or lat_col not in available:
        return []

    lff_org = (
        lff.select("uid", lon_col, lat_col, nom_col)
        .group_by(lon_col, lat_col, nom_col)
        .len("nb_marches")
        .filter(pl.col(lat_col).is_not_null() & pl.col(lon_col).is_not_null())
    )

    return [
        {
            "lat": row[lat_col],
            "lon": row[lon_col],
            "tooltip": f"{row[nom_col]} ({row['nb_marches']} marchés)",
            "marker_color": org_colors(theme)[org_type],
        }
        for row in lff_org.collect().to_dicts()
    ]


def get_geographic_maps(
    dff: pl.DataFrame, theme: str | None = None
) -> list[dbc.Col] | list:
    """
    Génère les cartes géographiques pour l'hexagone et les DOM-TOM.
    """
    theme = _theme(theme)

    regions: dict = {
        "Hexagone": {
            "coordinates": [46.6, 2.2],
            "zoom_leaflet": 5,
            "zoom_chloropleth": 1,
            "name": "Hexagone",
        },
        "971": {
            "coordinates": [16.23, -61.55],
            "zoom_leaflet": 9,
            "zoom_chloropleth": 1,
            "name": "Guadeloupe",
        },
        "972": {
            "coordinates": [14.64, -61.02],
            "zoom_leaflet": 10,
            "zoom_chloropleth": 1,
            "name": "Martinique",
        },
        "973": {
            "coordinates": [3.93, -53.12],
            "zoom_leaflet": 7,
            "zoom_chloropleth": 1,
            "name": "Guyane",
        },
        "974": {
            "coordinates": [-21.11, 55.53],
            "zoom_leaflet": 9,
            "zoom_chloropleth": 1,
            "name": "La Réunion",
        },
        "976": {
            "coordinates": [-12.82, 45.16],
            "zoom_leaflet": 10,
            "zoom_chloropleth": 1,
            "name": "Mayotte",
        },
    }

    def make_map_data(region_code: str) -> tuple[list, str | None]:
        lff: pl.LazyFrame = dff.lazy()
        if region_code == "Hexagone":
            lff = lff.filter(
                (pl.col("acheteur_departement_code").str.len_chars() == 2)
                & (pl.col("titulaire_departement_code").str.len_chars() == 2)
            )
        else:
            lff = lff.filter(
                (pl.col("acheteur_departement_code") == code)
                | (pl.col("titulaire_departement_code") == code)
            )

        nb_marches = lff.select("uid").collect()["uid"].n_unique()

        if nb_marches == 0:
            return [], None

        dfs = []

        if (code == "Hexagone" and nb_marches > 30000) or (
            code != "Hexagone" and nb_marches > 10000
        ):
            _map_type: str = "chloropleth"

            lff = lff.rename({"acheteur_departement_code": "Département"})
            lff = (
                lff.select(["uid", "Département"])
                .drop_nulls()
                .group_by("uid")
                .agg(pl.col("Département").first())
                .group_by("Département")
                .len("uid")
            )
            dfs.append(lff.collect())
        else:
            _map_type: str = "clusters"
            for org_type in ["acheteur", "titulaire"]:
                dfs.append(build_org_markers(lff, org_type, theme=theme))

        return dfs, _map_type

    cols = []

    for code in regions.keys():
        regions[code]["data"], map_type = make_map_data(code)

        if map_type == "chloropleth":
            map_graph = make_chloropleth_map(regions[code], theme=theme)
        elif map_type == "clusters":
            map_graph = make_clusters_map(regions[code], theme=theme)
        elif map_type is None:
            continue
        else:
            raise ValueError(f"Map type '{map_type}' not recognised")

        lg, xl = (12, 8) if code == "Hexagone" else (6, 4)

        col = make_card(
            regions[code]["name"], fig=map_graph, lg=lg, xl=xl, card_id=f"carte-{code}"
        )
        cols.append(col)

    return cols


def make_chloropleth_map(region: dict, theme: str | None = None) -> dcc.Graph:
    theme = _theme(theme)
    df_map = region["data"][0]

    fig = px.choropleth(
        df_map,
        geojson=DEPARTEMENTS_GEOJSON,
        locations="Département",
        color="uid",
        color_continuous_scale=ECHELLE_SOMBRE if theme == SOMBRE else "Reds",
        range_color=(df_map["uid"].min(), df_map["uid"].max()),
        labels={"uid": "Marchés attribués"},
        scope="europe",
    )

    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        mapbox={
            "style": "carto-positron",
            "center": {"lon": 10, "lat": 10},
            "zoom": 8,
            "domain": {"x": [0, 1], "y": [0, 1]},
        }
    )
    fig = appliquer_theme(fig, theme)

    graph = dcc.Graph(figure=fig, config={"displayModeBar": False})
    return graph


def make_clusters_map(region: dict, theme: str | None = None) -> html.Div:
    theme = _theme(theme)
    # JavaScript functions for styling
    ns = Namespace("dash_clientside", "leaflet")
    point_to_layer = ns("pointToLayer")
    cluster_to_layer = ns("clusterToLayer")

    name = region["name"]

    # Données de la région
    region_acheteurs = region["data"][0]
    region_titulaires = region["data"][1]

    # Couleurs
    colors = org_colors(theme)
    color_acheteur = colors["acheteur"]
    color_titulaire = colors["titulaire"]

    acheteurs_geojson_data = dlx.dicts_to_geojson(region_acheteurs)
    titulaires_geojson_data = dlx.dicts_to_geojson(region_titulaires)

    center, zoom = region["coordinates"], region["zoom_leaflet"]
    region_id = name.lower().replace(" ", "-")
    leaflet_map = dl.Map(
        [
            dl.TileLayer(className="tuiles"),
            dl.GeoJSON(
                data=titulaires_geojson_data,
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"geojson-{region_id}-titulaires",
                options={"fillColor": color_titulaire},
            ),
            dl.GeoJSON(
                data=acheteurs_geojson_data,
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"geojson-{region_id}-acheteurs",
                options={"fillColor": color_acheteur},
            ),
        ],
        center=center,
        zoom=zoom,
        style={
            "width": "100%",
            "height": "400px" if name == "Hexagone" else "300px",
        },
        id=f"map-{region_id}",
    )

    # Légende superposée en bas à gauche : rappelle la couleur des points
    # acheteur et titulaire. Les couleurs viennent de org_colors(theme) pour
    # rester synchrones avec les marqueurs (#118 : palette sombre en mode
    # sombre).
    legend = html.Div(
        [
            html.Div(
                [
                    html.Span(
                        className="map-legend-dot",
                        style={"backgroundColor": color_acheteur},
                    ),
                    "Acheteur",
                ],
                className="map-legend-item",
            ),
            html.Div(
                [
                    html.Span(
                        className="map-legend-dot",
                        style={"backgroundColor": color_titulaire},
                    ),
                    "Titulaire",
                ],
                className="map-legend-item",
            ),
        ],
        className="map-legend",
    )

    return html.Div([leaflet_map, legend], className="map-with-legend")


_MERCATOR_TILE_SIZE = 256


def _mercator_y(lat: float) -> float:
    lat_rad = math.radians(lat)
    return math.log(math.tan(math.pi / 4 + lat_rad / 2)) / (2 * math.pi)


def bounds_to_center_zoom(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    container_width_px: float = 350,
    container_height_px: float = 300,
    padding_px: float = 30,
    max_zoom: int = 12,
) -> tuple[list[float], int]:
    """Calcule un centre et un niveau de zoom (projection Web Mercator) pour
    cadrer une bounding box dans un conteneur de taille donnée.

    Approximation côté serveur d'un fitBounds Leaflet : la taille réelle du
    conteneur navigateur n'est pas connue côté Python, `container_width_px`
    est une estimation raisonnable (la carte occupe une colonne étroite de
    la page). Le résultat n'est donc pas pixel-perfect, contrairement à un
    fitBounds() exécuté côté client, mais évite d'utiliser la prop `bounds`
    de dash-leaflet (bug connu : exception au premier montage du composant).
    """
    avail_w = max(container_width_px - 2 * padding_px, 1)
    avail_h = max(container_height_px - 2 * padding_px, 1)

    dx_norm = (max_lon - min_lon) / 360
    dy_norm = abs(_mercator_y(max_lat) - _mercator_y(min_lat))

    zoom_candidates = []
    if dx_norm > 0:
        zoom_candidates.append(math.log2(avail_w / (_MERCATOR_TILE_SIZE * dx_norm)))
    if dy_norm > 0:
        zoom_candidates.append(math.log2(avail_h / (_MERCATOR_TILE_SIZE * dy_norm)))

    zoom = math.floor(min(zoom_candidates)) if zoom_candidates else max_zoom
    zoom = max(0, min(zoom, max_zoom))

    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
    return center, zoom


def get_org_location_map(
    dff: pl.DataFrame,
    home_type: Literal["acheteur", "titulaire"],
    map_id: str,
    theme: str | None = None,
) -> dl.Map:
    """Carte cluster (dash-leaflet) d'un organisme et de sa contrepartie.

    Affiche les marchés de `home_type` (fiche /acheteur ou /titulaire
    consultée) ainsi que ceux de son type complémentaire, clusterisés et
    colorés comme sur /observatoire. Cadrage calculé côté serveur
    (`bounds_to_center_zoom`) sur l'ensemble des points ; repli sur une vue
    France fixe si aucun point n'est disponible. Un center/zoom statiques
    sont utilisés plutôt que la prop `bounds` de dash-leaflet, qui lève une
    exception au premier montage du composant (bug connu de la librairie).
    """
    theme = _theme(theme)
    lff = dff.lazy()
    markers_by_type = {
        "acheteur": build_org_markers(lff, "acheteur", theme=theme),
        "titulaire": build_org_markers(lff, "titulaire", theme=theme),
    }
    for marker in markers_by_type[home_type]:
        marker["is_home"] = True

    ns = Namespace("dash_clientside", "leaflet")
    point_to_layer = ns("pointToLayer")
    cluster_to_layer = ns("clusterToLayer")

    layers: list = [dl.TileLayer(className="tuiles")]
    all_points: list[tuple[float, float]] = []
    # Ordre fixe (titulaire puis acheteur), comme sur /observatoire. Le point
    # de l'organisme consulté (is_home) est de toute façon toujours ramené au
    # premier plan côté client (pointToLayer, dash_clientside.js).
    for org_type in ("titulaire", "acheteur"):
        markers = markers_by_type[org_type]
        if not markers:
            continue
        all_points.extend((m["lat"], m["lon"]) for m in markers)
        layers.append(
            dl.GeoJSON(
                data=dlx.dicts_to_geojson(markers),
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"{map_id}-{org_type}",
                options={"fillColor": org_colors(theme)[org_type]},
            )
        )

    if all_points:
        lats = [lat for lat, _ in all_points]
        lons = [lon for _, lon in all_points]
        center, zoom = bounds_to_center_zoom(min(lats), min(lons), max(lats), max(lons))
    else:
        center, zoom = [46.6, 2.2], 5

    return dl.Map(
        layers,
        center=center,
        zoom=zoom,
        style={"width": "100%", "height": "300px"},
        id=map_id,
    )


def get_distance_histogram(lff: pl.LazyFrame, theme: str | None = None) -> dcc.Graph:
    theme = _theme(theme)
    if "titulaire_distance" not in lff.collect_schema().names():
        dff = pl.DataFrame({"titulaire_distance": pl.Series([], dtype=pl.Float64)})
    else:
        dff = (
            lff.select("titulaire_distance")
            .drop_nulls()
            .filter(pl.col("titulaire_distance") > 0)
            .collect(engine="streaming")
        )
    log_distances = dff["titulaire_distance"].log(10).to_numpy()

    fig = go.Figure()
    if len(log_distances) > 0:
        counts, bin_edges = np.histogram(log_distances, bins=25)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_widths = bin_edges[1:] - bin_edges[:-1]
        bin_edges_km = 10.0**bin_edges

        def fmt_km(km):
            if km < 10:
                return f"{km:.1f}"
            elif km < 1000:
                return f"{round(km)}"
            else:
                return f"{round(km):,}".replace(",", " ")

        hover_texts = []
        for i in range(len(counts)):
            nb = f"{counts[i]:,}".replace(",", " ")
            hover_texts.append(
                f"Distance : {fmt_km(bin_edges_km[i])} – {fmt_km(bin_edges_km[i + 1])} km"
                f"<br>Nombre de marchés : {nb}"
            )

        fig.add_trace(
            go.Bar(
                x=bin_centers,
                y=counts,
                width=bin_widths,
                hovertext=hover_texts,
                hoverinfo="text",
                marker_color="#e06c57" if theme == SOMBRE else None,
            )
        )
        fig.update_layout(bargap=0)

    fig.update_layout(margin=dict(r=10, t=10), height=450)
    fig.update_xaxes(
        tickvals=[0, 1, 2, 3, 4],
        ticktext=["1", "10", "100", "1 000", "10 000"],
        title_text="Distance (km)",
    )
    fig.update_yaxes(title_text="Nombre de marchés")
    fig = appliquer_theme(fig, theme)
    return dcc.Graph(figure=fig)


def get_dashboard_summary_table(dff, dff_per_uid, nb_marches):
    nb_acheteurs = dff.select("acheteur_id").n_unique()
    nb_titulaires = dff.select("titulaire_id", "titulaire_typeIdentifiant").n_unique()
    total_montant = int(dff_per_uid.select(pl.col("montant").sum()).item())
    median_distance = dff.select(pl.median("titulaire_distance")).item()

    summary_table = [
        html.P(["Nombre de marchés : ", html.Strong(str(format_number(nb_marches)))]),
        html.P(
            [
                "Nombre d'acheteurs uniques : ",
                html.Strong(str(format_number(nb_acheteurs))),
            ]
        ),
        html.P(
            [
                "Nombre de titulaires uniques : ",
                html.Strong(str(format_number(nb_titulaires))),
            ]
        ),
        html.P(
            [
                "Montant total (",
                html.Span(
                    "?",
                    id={"type": "modal-trigger", "index": "montant"},
                    style={"cursor": "pointer", "textDecoration": "underline dotted"},
                ),
                ") : ",
                html.Strong(format_number(total_montant) + " €"),
            ]
        ),
        html.P(
            [
                "Distance acheteur-titulaire médiane : ",
                html.Strong(format_number(median_distance) + " km"),
            ]
        ),
    ]

    return summary_table


CONSIDERATIONS_REGEX = r"(?i)Clause|Critère|Marché réservé"
CONSIDERATIONS_COLUMNS = {
    "sociales": "considerationsSociales",
    "environnementales": "considerationsEnvironnementales",
}


def compute_considerations_stats(lff: pl.LazyFrame) -> dict[str, tuple[int, int, int]]:
    """Statistiques considérations pour l'observatoire.

    Clés renvoyées :
      - "champs_renseignes"        : (count_ren_sociales, pct / total)
      - "{key}_renseignees"        : (count_ren, count_pos_ren, pct positifs parmi renseignés)
    Colonne absente/vide -> "champs_renseignes" (0, 0), "{key}_renseignees" (0, 0, 0).
    """
    names = lff.collect_schema().names()
    present = {key: col for key, col in CONSIDERATIONS_COLUMNS.items() if col in names}

    stats: dict[str, tuple[int, ...]] = {"champs_renseignes": (0, 0)}
    for key in CONSIDERATIONS_COLUMNS:
        stats[f"{key}_renseignees"] = (0, 0, 0)

    if not present:
        return stats

    agg = (
        lff.select(["uid"] + list(present.values()))
        .group_by("uid")
        .agg([pl.col(col).first() for col in present.values()])
        .collect(engine="streaming")
    )

    total = agg.height
    if total == 0:
        return stats

    for key, col in present.items():
        count_ren = agg.filter(pl.col(col).is_not_null()).height
        count_pos_ren = agg.filter(
            pl.col(col).is_not_null() & (pl.col(col) != "Sans objet")
        ).height
        pct_pos_ren = round(100 * count_pos_ren / count_ren) if count_ren > 0 else 0
        stats[f"{key}_renseignees"] = (count_ren, count_pos_ren, pct_pos_ren)
        if key == "sociales":
            stats["champs_renseignes"] = (count_ren, round(100 * count_ren / total))

    return stats


# (clé stats, libellé, couleur claire, couleur sombre)
CONSIDERATIONS_RENSEIGNEES = [
    ("sociales_renseignees", "Considérations sociales", "#CC6677", "#d0633d"),
    (
        "environnementales_renseignees",
        "Considérations environnementales",
        "#117733",
        "#85c54c",
    ),
]


def _progress_bar(pct: int, color: str, theme: str | None = None) -> dbc.Progress:
    # Le blanc du label ne tient pas sur les barres claires de la palette
    # Earthsong (ex. #85c54c, environnement, ≈2.1:1) ; en sombre on bascule
    # sur le même texte foncé que le bouton primaire (--btn-terracotta-text).
    label_color = "#121418" if _theme(theme) == SOMBRE else "white"
    return dbc.Progress(
        dbc.Progress(
            value=pct,
            label=f"{pct} %",
            bar=True,
            color=color,
            style={"color": label_color},
        ),
    )


def get_considerations_card_content(
    lff: pl.LazyFrame, theme: str | None = None
) -> html.Div:
    """Trois barres : champs renseignés + part positive pour sociales et environnementales."""
    theme = _theme(theme)
    stats = compute_considerations_stats(lff)

    count_ren, pct_ren = stats["champs_renseignes"]
    couleur_neutre = GRILLE_SOMBRE if theme == SOMBRE else "#6c757d"
    blocks = [
        html.Div(
            className="mb-3",
            children=[
                html.Div(
                    className="d-flex justify-content-between",
                    children=[
                        html.Span("Champs considérations renseignés"),
                        html.Span(
                            f"{format_number(count_ren)} marchés",
                            className="text-muted",
                        ),
                    ],
                ),
                _progress_bar(pct_ren, couleur_neutre, theme),
            ],
        )
    ]

    for key, label, color_clair, color_sombre in CONSIDERATIONS_RENSEIGNEES:
        color = color_sombre if theme == SOMBRE else color_clair
        total_count, count, pct = stats[key]
        blocks.append(
            html.Div(
                className="mb-3",
                children=[
                    html.Div(
                        className="d-flex justify-content-between",
                        children=[
                            html.Span(label),
                            html.Span(
                                f"dans {format_number(count)} marchés",
                                className="text-muted",
                            ),
                        ],
                    ),
                    _progress_bar(pct, color, theme),
                ],
            )
        )

    return html.Div(children=blocks)


#: Classe posée sur chaque card ordonnable ; `CARD_CLASS--<card_id>` porte
#: l'identifiant. Partagée avec observatoire-dragdrop.js et style.css (#107).
CARD_CLASS = "observatoire-card"


def cards_drag_marker(store_id: str) -> html.Div:
    """Balise invisible qui active le drag & drop sur son conteneur parent.

    Le marqueur est glissé parmi les cards plutôt que posé sur le conteneur
    lui-même : celui-ci est un `dbc.Row`, qui n'accepte aucune prop wildcard
    `data-*`, et l'envelopper dans un `html.Div` casserait la grille Bootstrap
    (`.row > div > .row`). `observatoire-dragdrop.js` remonte donc au
    `parentElement` du marqueur pour trouver la liste à ordonner.

    Les pages ne rendent ce marqueur que pour les abonné·es : son absence
    désactive le drag & drop sans aucun contrôle de droits côté client.
    """
    return html.Div(
        hidden=True,
        **{"data-observatoire-cards": "", "data-card-order-store": store_id},
    )


def make_card(
    title: str, subtitle=None, fig=None, paragraphs=None, lg=6, xl=4, card_id=None
) -> dbc.Col:
    """Une card de l'observatoire.

    `card_id` pose sur la colonne un id pattern-matching (pour les callbacks
    Dash) et les classes `observatoire-card observatoire-card--<card_id>`
    (pour le drag & drop côté client, issue #107).

    Le card_id passe par une classe et non par un `data-card-id` parce que
    `dbc.Col` n'accepte aucune prop wildcard : `_valid_wildcard_attributes`
    y est vide, contrairement aux composants `dash.html`. Tous les card_ids
    (`resume`, `cat-acheteur`, `carte-971`…) sont des noms de classe valides.
    """
    children = []
    if title:
        children.append(html.H5(title, className="card-title"))
    if subtitle:
        children.append(html.H6(subtitle, className="card-subtitle mb-2 text-muted"))
    if fig is not None:
        children.append(fig)
    if paragraphs:
        for p in paragraphs:
            p.className = "card-text"
            children.append(p)

    col_kwargs = {}
    if card_id is not None:
        col_kwargs["id"] = {"type": "observatoire-card", "index": card_id}
        col_kwargs["className"] = f"{CARD_CLASS} {CARD_CLASS}--{card_id}"

    card = dbc.Col(
        html.Div(html.Div(className="card-body", children=children), className="card"),
        lg=lg,
        xl=xl,
        # width=width,
        # className="mb-4",
        **col_kwargs,
    )
    return card


def make_donut(
    lff: pl.LazyFrame,
    names_col,
    per_uid: bool,
    nulls="?",
    potentially_many_names: bool = False,
    theme: str | None = None,
):
    theme = _theme(theme)
    title = DATA_SCHEMA[names_col]["title"]
    lff = lff.rename({names_col: title})
    lff = lff.select("uid", title)

    if per_uid:
        lff = lff.group_by("uid").first()

    lff = lff.group_by(title).len("Nombre")
    lff = lff.with_columns(pl.col(title).replace(None, pl.lit(nulls)))
    dff = lff.collect(engine="streaming")
    nb_names = dff[title].n_unique()

    sum_values = dff["Nombre"].sum()
    dff = dff.with_columns(
        pl.when((pl.col("Nombre") / sum_values) < 0.01)
        .then(pl.lit("Autres"))
        .otherwise(pl.col(title))
        .alias(title)
    )

    dff = dff.with_columns(
        pl.col("Nombre")
        .map_elements(format_number, return_dtype=pl.String)
        .alias("Nombre_fmt")
    )
    fig = px.pie(
        dff,
        values="Nombre",
        names=title,
        hole=0.4,
        color_discrete_sequence=(
            PALETTE_SOMBRE if theme == SOMBRE else px.colors.qualitative.Safe
        ),
        custom_data=["Nombre_fmt"],
    )
    fig = fig.update_traces(
        texttemplate="<b>%{label}</b><br><b>%{percent}</b>",
        hovertemplate="<b>%{label}</b><br>%{customdata[0]}<extra></extra>",
    )
    fig = fig.update_layout(showlegend=False, font=dict(size=14))
    fig = appliquer_theme(fig, theme)
    graph = dcc.Graph(figure=fig)
    if potentially_many_names:
        return graph, nb_names
    return graph


def make_column_picker(page: str):
    """Sélecteur de colonnes (modale « Colonnes ») : une grille AG Grid dont
    chaque ligne est une colonne du jeu de données, cochée si elle est affichée.

    Les lignes ont pour id le nom de la colonne (`getRowId`), ce qui permet de
    poser `selectedRows = {"ids": [...]}` depuis le serveur à l'ouverture de la
    modale (cf. selection_from_hidden_columns).
    """
    rows = [
        {
            "id": col,
            "name": DATA_SCHEMA[col]["title"],
            "description": DATA_SCHEMA[col]["description"],
        }
        for col in schema.names()
    ]
    return html.Div(
        [
            dbc.Input(
                id={"type": "column-search", "page": page},
                type="search",
                placeholder="Rechercher une colonne…",
                className="mb-2",
                debounce=False,
            ),
            client_grid(
                f"{page}_column_list",
                [
                    {"field": "name", "headerName": "Nom", "flex": 1, "minWidth": 200},
                    {
                        "field": "description",
                        "headerName": "Description",
                        "flex": 2,
                        "minWidth": 300,
                        "wrapText": True,
                        "autoHeight": True,
                    },
                ],
                rows,
                dash_grid_options={
                    "rowSelection": {
                        "mode": "multiRow",
                        "checkboxes": True,
                        "headerCheckbox": True,
                        "selectAll": "filtered",
                        "enableClickSelection": True,
                    },
                },
                getRowId="params.data.id",
                defaultColDef={"sortable": False, "filter": False},
            ),
        ]
    )


# Filtre rapide du sélecteur de colonnes : un seul callback pour toutes les
# pages (MATCH sur la page), qui passe le texte saisi au quickFilterText de la
# grille correspondante.
clientside_callback(
    """
    function (value, id) {
        // getApi lève une erreur si la grille n'est pas (encore) montée.
        let api;
        try {
            api = dash_ag_grid.getApi(id.page + "_column_list");
        } catch (e) {
            return;
        }
        if (api) { api.setGridOption("quickFilterText", value || ""); }
    }
    """,
    Input({"type": "column-search", "page": MATCH}, "value"),
    State({"type": "column-search", "page": MATCH}, "id"),
    prevent_initial_call=True,
)


def make_schema_grid():
    """Tableau des champs publiés affiché en bas de /projet/donnees (#136).

    Grille client-side (64 lignes) en `domLayout: "autoHeight"` : toutes les
    lignes sont rendues dans la page, donc les ancres `#nom_du_champ` posées
    dans la colonne « Nom » existent réellement dans le DOM (lien direct,
    Ctrl+F) et le défilement reste celui de la page, sans scroll interne.
    """
    return client_grid(
        "schema_champs_grid",
        [
            {
                "field": "nom",
                "headerName": "Nom",
                "cellRenderer": "markdown",
                "filter": "agTextColumnFilter",
                "wrapText": True,
                "autoHeight": True,
                "flex": 3,
                "minWidth": 260,
            },
            {
                "field": "type",
                "headerName": "Type de données",
                "filter": "agTextColumnFilter",
                "flex": 2,
                # « Chaîne de caractères », le libellé le plus long, doit tenir
                # sur une ligne sans être tronqué.
                "minWidth": 210,
            },
            {
                "field": "description",
                "headerName": "Description",
                "filter": "agTextColumnFilter",
                "wrapText": True,
                "autoHeight": True,
                "flex": 6,
                "minWidth": 320,
            },
        ],
        schema_field_rows(),
        dash_grid_options={"enableCellTextSelection": True, "ensureDomOrder": True},
        defaultColDef={
            "resizable": True,
            "sortable": False,
            "floatingFilter": True,
        },
    )


# Thème AG Grid commun à toutes les grilles du site (en-tête rouge brique,
# lignes alternées, police Inter), aligné sur les dash_table.DataTable.
AG_GRID_THEME = {
    "function": (
        "themeQuartz.withParams({"
        "accentColor: 'rgb(179, 56, 33)',"
        "headerTextColor: 'white',"
        "headerBackgroundColor: 'rgb(179, 56, 33)',"
        "oddRowBackgroundColor: 'rgba(255, 240, 240, 0.4)',"
        "borderColor: '#ccc',"
        "fontFamily: 'Inter, sans-serif',"
        "fontSize: 16"
        "})"
    )
}


# Libellés du menu de filtre AG Grid, traduits en français (option native
# AG Grid localeText, exposée via dashGridOptions — n'affecte pas l'apparence
# de base conservée au Lot 1, seulement le texte).
AG_GRID_LOCALE_FR = {
    # Filtres texte / nombre / date
    "contains": "Contient",
    "notContains": "Ne contient pas",
    "equals": "Égal à",
    "notEqual": "Différent de",
    "startsWith": "Commence par",
    "endsWith": "Se termine par",
    "blank": "Vide",
    "notBlank": "Non vide",
    "empty": "Choisir une option",
    "lessThan": "Inférieur à",
    "lessThanOrEqual": "Inférieur ou égal à",
    "greaterThan": "Supérieur à",
    "greaterThanOrEqual": "Supérieur ou égal à",
    "inRange": "Entre",
    "inRangeStart": "de",
    "inRangeEnd": "à",
    "before": "Avant",
    "after": "Après",
    "to": "à",
    "of": "de",
    "pageSizeSelectorLabel": "Lignes par page",
    # Chrome du menu de filtre
    "filterOoo": "Filtrer...",
    "applyFilter": "Appliquer",
    "resetFilter": "Réinitialiser",
    "clearFilter": "Effacer",
    "cancelFilter": "Annuler",
    "andCondition": "ET",
    "orCondition": "OU",
    "noRowsToShow": "Aucune ligne à afficher",
    "noMatchingRows": "Aucune ligne ne correspond aux filtres appliqués",
    "loadingOoo": "Chargement...",
}


def client_grid(
    grid_id,
    column_defs,
    row_data,
    *,
    page_size=None,
    dash_grid_options=None,
    **ag_grid_kwargs,
):
    """Grille AG Grid client-side (rowData directe) au thème du site.

    Pendant de ag_grid(), réservée au modèle `infinite` de /tableau et des
    fiches. Le mode sombre suit via les variables --ag-* redéfinies sous
    [data-bs-theme="dark"] (style.css).
    """
    options = {
        "domLayout": "autoHeight",  # row model client-side : OK
        "suppressCellFocus": True,
        "localeText": AG_GRID_LOCALE_FR,
        "theme": AG_GRID_THEME,
    }
    if page_size:
        options |= {"pagination": True, "paginationPageSize": page_size}
    options |= dash_grid_options or {}
    return dag.AgGrid(
        id=grid_id,
        columnDefs=column_defs,
        rowData=row_data,
        dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
        dashGridOptions=options,
        style={"width": "100%"},
        persistence=False,
        **ag_grid_kwargs,
    )


def ag_grid(
    grid_id: "str | dict",
    column_defs: list[dict],
    persisted_props=("filterModel", "columnState"),
    persistence: bool = True,
    event_listeners: "dict | None" = None,
) -> "dag.AgGrid":
    """Grille AG Grid server-side (infinite) pour la page Tableau.

    Thème aligné sur les dash_table.DataTable du reste du site (en-tête
    rouge brique, lignes alternées, police Inter) ; libellés de filtre
    traduits en français via localeText.
    """
    return dag.AgGrid(
        id=grid_id,
        columnDefs=column_defs,
        defaultColDef={"resizable": True, "minWidth": 120, "floatingFilter": True},
        eventListeners=event_listeners,
        rowModelType="infinite",
        dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
        dashGridOptions={
            "cacheBlockSize": 100,
            "maxBlocksInCache": 10,
            "rowBuffer": 0,
            "infiniteInitialRowCount": 100,
            # rowHeight fixe (pas autoHeight, non supporté par rowModelType
            # "infinite") pour laisser la place au texte replié à la ligne
            # de la colonne "objet" (cf. grid_column_defs).
            "rowHeight": 60,
            "suppressCellFocus": True,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            # Permet de sélectionner/copier le texte des infobulles (ex.
            # colonne "objet" tronquée, cf. tooltipField dans grid_column_defs).
            "tooltipInteraction": True,
            # Délai avant apparition des infobulles natives (200ms au lieu
            # des 2000ms par défaut d'AG Grid).
            "tooltipShowDelay": 200,
            "localeText": AG_GRID_LOCALE_FR,
            "theme": AG_GRID_THEME,
            # Réserve l'espace de la barre de défilement horizontale en permanence
            # (comportement natif de Chrome). Sans effet sur Firefox : le curseur
            # de la barre y reste en overlay au survol, géré par l'OS/le navigateur
            # (ex. réglage GTK overlay-scrollbars), non contrôlable par l'appli.
            "alwaysShowHorizontalScroll": True,
        },
        # Pas de columnSize="responsiveSizeToFit" : les colonnes gardent leur
        # largeur définie dans columnDefs (cf. _column_width dans
        # src.utils.grid) même à 50 colonnes affichées, quitte à faire
        # apparaître le défilement horizontal natif d'AG Grid plutôt que de
        # les compresser/étirer toutes à la même largeur.
        style={"height": "70vh", "width": "100%"},
        persistence=persistence,
        persistence_type="local",
        persisted_props=list(persisted_props),
    )


# Colonnes lues par build_dashboard_cards. La projeter dans la requête au lieu
# d'un SELECT * divise par ~4 le temps de la requête DuckDB et d'autant
# l'empreinte mémoire du DataFrame : le stockage est colonnaire, et les cards
# n'exploitent que 21 des 63 colonnes du schéma. Toute card qui lirait une
# colonne absente d'ici échouerait sur un ColumnNotFoundError — c'est ce que
# vérifie tests/test_observatoire_cards_columns.py.
OBSERVATOIRE_CARDS_COLUMNS = [
    "uid",
    "montant",
    "dateNotification",
    "type",
    "sourceDataset",
    "titulaire_distance",
    "considerationsSociales",
    "considerationsEnvironnementales",
    "acheteur_id",
    "acheteur_nom",
    "acheteur_categorie",
    "acheteur_departement_code",
    "acheteur_latitude",
    "acheteur_longitude",
    "titulaire_id",
    "titulaire_nom",
    "titulaire_categorie",
    "titulaire_typeIdentifiant",
    "titulaire_departement_code",
    "titulaire_latitude",
    "titulaire_longitude",
]


def observatoire_cards_columns() -> list[str]:
    """OBSERVATOIRE_CARDS_COLUMNS restreintes aux colonnes réellement présentes
    dans la table DuckDB.

    En production les 21 y sont toutes ; mais tests/test.parquet ne porte qu'un
    sous-ensemble du schéma, et projeter une colonne absente de la table ferait
    échouer le SELECT. Même précaution que `export_dataframe` dans
    src/utils/grid.py.
    """
    from src.db import schema

    return [c for c in OBSERVATOIRE_CARDS_COLUMNS if c in schema.names()]


def build_dashboard_cards(
    dff: pl.DataFrame,
    order: list[str] | None = None,
    theme: str | None = None,
    context: str = "observatoire",
    scope: str = "",
) -> list:
    """Cards de l'observatoire pour un jeu de marchés déjà filtré.

    Partagé par la page /observatoire (filtres du panneau latéral) et par le
    mode observatoire du Tableau (filtres AG Grid), cf. issue #137 : les deux
    affichent exactement les mêmes cards, seules les sources du filtrage
    diffèrent. `dff` doit contenir toutes les colonnes du schéma (les cards en
    utilisent bien plus que celles affichées dans la grille).

    `order` est la liste des card_ids dans l'ordre choisi par l'utilisateur
    (issue #107) ; None conserve l'ordre par défaut. Les appelants qui passent
    par un cache mémoïsé doivent laisser `order` à None et appliquer
    `reorder_cards` sur le résultat, pour ne pas multiplier les entrées de
    cache par le nombre d'ordres possibles.

    `theme` (#118) est résolu une seule fois ici et transmis à toutes les
    figures construites, pour éviter un appel current_theme() par figure.

    `context` distingue les deux appelants (`observatoire` / `tableau`) :
    chacun déclare son propre callback de datasource pour les grilles top, et
    deux pages ne peuvent pas alimenter la même sortie. `scope` identifie le
    périmètre courant et force le remontage des grilles quand il change (cf.
    `src.utils.top_org_grid.scope_key`).
    """
    theme = _theme(theme)
    lff = dff.lazy()

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )
    nb_marches = df_per_uid.height

    cards = []
    card_summary_table = get_dashboard_summary_table(dff, df_per_uid, nb_marches)
    cards.append(
        make_card(title="Résumé", paragraphs=card_summary_table, card_id="resume")
    )

    donut_acheteur_categorie, nb_acheteur_categories = make_donut(
        lff,
        "acheteur_categorie",
        nulls="Autres",
        per_uid=True,
        potentially_many_names=True,
        theme=theme,
    )
    cards.append(
        make_card(
            title="Catégorie d'acheteur",
            subtitle="en nombre de marchés attribués",
            fig=donut_acheteur_categorie,
            lg=12 if nb_acheteur_categories > 4 else 6,
            xl=8 if nb_acheteur_categories > 4 else 4,
            card_id="cat-acheteur",
        )
    )

    donut_titulaire_categorie = make_donut(
        lff, "titulaire_categorie", per_uid=False, nulls="?", theme=theme
    )
    cards.append(
        make_card(
            title="Catégorie d'entreprise",
            subtitle="en nombre de titulaires",
            fig=donut_titulaire_categorie,
            card_id="cat-entreprise",
        )
    )

    donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?", theme=theme)
    cards.append(
        make_card(
            title="Type d'achat",
            subtitle="en nombre de marchés attribués",
            fig=donut_marche_type,
            card_id="type-achat",
        )
    )

    considerations_content = get_considerations_card_content(lff, theme=theme)
    cards.append(
        make_card(
            title="Considérations sociales et environnementales",
            subtitle="part des marchés concernés",
            fig=considerations_content,
            card_id="considerations",
        )
    )

    distance_histogram = get_distance_histogram(lff, theme=theme)
    cards.append(
        make_card(
            title="Distance acheteur–titulaire",
            subtitle="en nombre de marchés, échelle logarithmique",
            fig=distance_histogram,
            card_id="distance",
        )
    )

    # Import local : src.utils.top_org_grid importe le thème AG Grid depuis ce
    # module, un import en tête créerait un cycle.
    from src.utils.top_org_grid import top_org_grid

    top_acheteurs = top_org_grid(context, "acheteur", scope)
    cards.append(
        make_card(
            title="Top acheteurs",
            fig=top_acheteurs,
            lg=12,
            xl=8,
            card_id="top-acheteurs",
        )
    )

    top_titulaires = top_org_grid(context, "titulaire", scope)
    cards.append(
        make_card(
            title="Top titulaires",
            fig=top_titulaires,
            lg=12,
            xl=8,
            card_id="top-titulaires",
        )
    )

    geographic_maps: list[dbc.Col] | None = get_geographic_maps(dff, theme=theme)

    other_cards = []
    sources_barchart = get_barchart_sources(
        lff, type_date="dateNotification", theme=theme
    )
    other_cards.append(
        make_card(
            title="Sources de données",
            subtitle="Nombre de marchés attribués par mois de notification et source de données",
            fig=sources_barchart,
            lg=12,
            xl=8,
            card_id="sources-donnees",
        )
    )

    toutes = cards + geographic_maps + other_cards
    return toutes if order is None else reorder_cards(toutes, order)


def card_id_of(card) -> str | None:
    """card_id d'une card construite par `make_card`, ou None si elle n'en a pas."""
    cid = getattr(card, "id", None)
    if isinstance(cid, dict) and cid.get("type") == "observatoire-card":
        return cid["index"]
    return None


def reorder_cards(cards: list, order: list[str]) -> list:
    """Réordonne des cards déjà construites selon leurs card_ids (issue #107).

    Le tri est stable : les cards sans card_id, ou dont le card_id est absent
    de `order`, restent à la fin dans leur ordre d'origine. C'est ce qui rend
    l'opération sûre face aux cartes géographiques, dont le nombre varie avec
    le filtre : un `carte-<code>` absent de l'ordre enregistré ne disparaît pas,
    il se range simplement après les cards explicitement ordonnées.
    """
    rang = {card_id: i for i, card_id in enumerate(order)}
    return sorted(cards, key=lambda card: rang.get(card_id_of(card), len(order)))


def montant_modal():
    """Modale « Montants » ouverte par le « ? » de la card Résumé.

    Présente dans les deux layouts qui affichent les cards de l'observatoire
    (/observatoire et le mode observatoire du Tableau) : le déclencheur
    `{"type": "modal-trigger", "index": "montant"}` est rendu par
    `get_dashboard_summary_table`, et son callback (dans src/pages/observatoire.py)
    a besoin de trouver la modale dans le layout de la page affichée.
    """
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Montants")),
            dbc.ModalBody(
                [
                    dcc.Markdown(
                        """
Les données saisies et publiées par les acheteurs comportent de nombreux montants farfelus qui sabotent les statistiques,
au lieu de montants estimés avec rigueur. Ils atteignent parfois les millions de milliards.
Certains réutilisateurs des données mettent de côté ces marchés ou bien modifient les montants selon des règles fatalement arbitraires.
Les données ne sont quasiment pas modifiées afin de visibiliser le problème.

Alors, comment fait-on ?

\\* Les montants composés de plus de 11 chiffres, sans les décimales,
[sont ramenés](https://github.com/ColinMaudry/decp-processing/blob/main/src/tasks/clean.py#L63-L71) à
12 311 111 111, un nombre qui reste très élevé et qui est facilement reconnaissable.
"""
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button("Fermer", id="montant-modal-close", className="ms-auto")
            ),
        ],
        id="montant-modal",
        is_open=False,
    )
