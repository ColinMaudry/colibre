import polars as pl
import pytest


def _make_lff(rows):
    return pl.LazyFrame(rows)


def test_compute_considerations_stats_basic():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # u1 : social oui (Clause), env non (Sans objet)
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            # u2 : social non (Sans objet), env oui (Critère)
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
            # u3 : social oui (Marché réservé), env null
            {
                "uid": "u3",
                "considerationsSociales": "Marché réservé",
                "considerationsEnvironnementales": None,
            },
            # u4 : social autre valeur (pas "Sans objet"), env null
            {
                "uid": "u4",
                "considerationsSociales": "Pas de considération sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    stats = compute_considerations_stats(lff)

    # champs_renseignes : basé sur sociales. 4 non-null / 4 total -> (4, 100%).
    assert stats["champs_renseignes"] == (4, 100)
    # Sociales renseignées : dén=4 non-null, num=3 != "Sans objet" (u1/u3/u4) -> (4, 3, 75%).
    assert stats["sociales_renseignees"] == (4, 3, 75)
    # Env renseignées : dén=3 non-null (u1/u2/u4), num=1 != "Sans objet" (u2) -> (3, 1, 33%).
    assert stats["environnementales_renseignees"] == (3, 1, 33)


def test_compute_considerations_stats_dedup_per_uid():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # u1 présent 2 fois (2 titulaires) -> compté une seule fois
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    stats = compute_considerations_stats(lff)

    # 2 uid distincts. Social 2 non-null, 1 != "Sans objet" (u1) -> (2, 1, 50%).
    assert stats["champs_renseignes"] == (2, 100)
    assert stats["sociales_renseignees"] == (2, 1, 50)
    # Env 2 non-null, 0 != "Sans objet" -> (2, 0, 0%).
    assert stats["environnementales_renseignees"] == (2, 0, 0)


def test_compute_considerations_stats_missing_column():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            {"uid": "u1", "considerationsSociales": "Clause sociale"},
            {"uid": "u2", "considerationsSociales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # Colonne env absente -> (0, 0, 0). Social : 2 non-null, 1 != "Sans objet" -> (2, 1, 50%).
    assert stats["champs_renseignes"] == (2, 100)
    assert stats["sociales_renseignees"] == (2, 1, 50)
    assert stats["environnementales_renseignees"] == (0, 0, 0)


def test_compute_considerations_stats_empty():
    from src.figures import compute_considerations_stats

    lff = pl.LazyFrame(
        {
            "uid": pl.Series([], dtype=pl.String),
            "considerationsSociales": pl.Series([], dtype=pl.String),
            "considerationsEnvironnementales": pl.Series([], dtype=pl.String),
        }
    )

    stats = compute_considerations_stats(lff)

    assert stats["champs_renseignes"] == (0, 0)
    assert stats["sociales_renseignees"] == (0, 0, 0)
    assert stats["environnementales_renseignees"] == (0, 0, 0)


def test_get_considerations_card_content_returns_three_progress_bars():
    import dash_bootstrap_components as dbc
    from dash import html

    from src.figures import get_considerations_card_content

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
        ]
    )

    div = get_considerations_card_content(lff)

    assert isinstance(div, html.Div)

    def find_progress(component, found):
        if isinstance(component, dbc.Progress):
            found.append(component)
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                find_progress(c, found)
        elif children is not None and not isinstance(children, str):
            find_progress(children, found)
        return found

    inner_bars = [b for b in find_progress(div, []) if getattr(b, "bar", False)]
    assert len(inner_bars) == 3

    bar_ren, bar_social, bar_env = inner_bars
    # Bar 1 : champs renseignés (2/2 = 100%, gris)
    assert bar_ren.value == 100
    assert bar_ren.color == "#6c757d"
    # Bar 2 : sociales parmi renseignés (u1 != "Sans objet" -> 1/2 = 50%, rose)
    assert bar_social.value == 50
    assert bar_social.color == "#CC6677"
    # Bar 3 : env parmi renseignés (u2 != "Sans objet" -> 1/2 = 50%, vert)
    assert bar_env.value == 50
    assert bar_env.color == "#117733"


def test_build_org_markers_groups_and_counts():
    from src.figures import build_org_markers

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u2",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u3",
                "acheteur_longitude": -1.68,
                "acheteur_latitude": 48.11,
                "acheteur_nom": "ACHETEUR B",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur")

    assert len(markers) == 2
    marker_a = next(m for m in markers if m["tooltip"].startswith("ACHETEUR A"))
    assert marker_a["tooltip"] == "ACHETEUR A (2 marchés)"
    assert marker_a["lat"] == 48.85
    assert marker_a["lon"] == 2.35
    assert marker_a["marker_color"] == "#E69F00"


def test_build_org_markers_filters_null_coordinates():
    from src.figures import build_org_markers

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": None,
                "acheteur_latitude": None,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u2",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR B",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur")

    assert len(markers) == 1
    assert markers[0]["tooltip"] == "ACHETEUR B (1 marchés)"


def test_build_org_markers_missing_columns_returns_empty():
    from src.figures import build_org_markers

    lff = pl.LazyFrame([{"uid": "u1", "acheteur_nom": "ACHETEUR A"}])

    assert build_org_markers(lff, "acheteur") == []
    assert build_org_markers(lff, "titulaire") == []


def _org_map_dff():
    return pl.DataFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
                "titulaire_longitude": -1.68,
                "titulaire_latitude": 48.11,
                "titulaire_nom": "TITULAIRE A",
            }
        ]
    )


def test_get_org_location_map_centers_on_home_and_counterpart():
    import dash_leaflet as dl

    from src.figures import get_org_location_map

    leaflet_map = get_org_location_map(_org_map_dff(), "acheteur", "test-map")

    assert isinstance(leaflet_map, dl.Map)
    # Centre = milieu du point acheteur (2.35, 48.85) et titulaire (-1.68, 48.11).
    assert leaflet_map.center == pytest.approx([48.48, 0.335])
    assert leaflet_map.zoom == 6

    geojson_layers = [c for c in leaflet_map.children if isinstance(c, dl.GeoJSON)]
    assert {layer.id for layer in geojson_layers} == {
        "test-map-acheteur",
        "test-map-titulaire",
    }


def test_get_org_location_map_marks_home_org_marker_acheteur():
    import dash_leaflet as dl

    from src.figures import get_org_location_map

    leaflet_map = get_org_location_map(_org_map_dff(), "acheteur", "test-map")

    geojson_layers = {
        layer.id: layer
        for layer in leaflet_map.children
        if isinstance(layer, dl.GeoJSON)
    }
    acheteur_features = geojson_layers["test-map-acheteur"].data["features"]
    titulaire_features = geojson_layers["test-map-titulaire"].data["features"]

    assert all(f["properties"]["is_home"] for f in acheteur_features)
    assert all(not f["properties"].get("is_home") for f in titulaire_features)


def test_get_org_location_map_marks_home_org_marker_titulaire():
    import dash_leaflet as dl

    from src.figures import get_org_location_map

    leaflet_map = get_org_location_map(_org_map_dff(), "titulaire", "test-map")

    geojson_layers = {
        layer.id: layer
        for layer in leaflet_map.children
        if isinstance(layer, dl.GeoJSON)
    }
    acheteur_features = geojson_layers["test-map-acheteur"].data["features"]
    titulaire_features = geojson_layers["test-map-titulaire"].data["features"]

    assert all(f["properties"]["is_home"] for f in titulaire_features)
    assert all(not f["properties"].get("is_home") for f in acheteur_features)


def test_get_org_location_map_defaults_to_france_view_without_coordinates():
    from src.figures import get_org_location_map

    dff = pl.DataFrame(
        [{"uid": "u1", "acheteur_nom": "ACHETEUR A", "titulaire_nom": "TITULAIRE A"}]
    )

    leaflet_map = get_org_location_map(dff, "acheteur", "test-map")

    assert leaflet_map.center == [46.6, 2.2]
    assert leaflet_map.zoom == 5


def test_get_org_location_map_tile_layer_has_tuiles_classname():
    """La couche de tuiles OSM porte className="tuiles" : c'est ce sélecteur
    que le bloc CSS mode sombre (#118) cible pour l'assombrir (filter)."""
    import dash_leaflet as dl

    from src.figures import get_org_location_map

    leaflet_map = get_org_location_map(_org_map_dff(), "acheteur", "test-map")

    tile_layers = [c for c in leaflet_map.children if isinstance(c, dl.TileLayer)]
    assert len(tile_layers) == 1
    assert tile_layers[0].className == "tuiles"


def test_make_clusters_map_tile_layer_has_tuiles_classname():
    import dash_leaflet as dl

    from src.figures import make_clusters_map

    region = {
        "name": "Hexagone",
        "data": ([], []),
        "coordinates": [46.6, 2.2],
        "zoom_leaflet": 5,
    }

    div = make_clusters_map(region)

    leaflet_map = next(c for c in div.children if isinstance(c, dl.Map))
    tile_layers = [c for c in leaflet_map.children if isinstance(c, dl.TileLayer)]
    assert len(tile_layers) == 1
    assert tile_layers[0].className == "tuiles"


def test_bounds_to_center_zoom_single_point_uses_max_zoom():
    from src.figures import bounds_to_center_zoom

    center, zoom = bounds_to_center_zoom(48.85, 2.35, 48.85, 2.35, max_zoom=12)

    assert center == [48.85, 2.35]
    assert zoom == 12


def test_bounds_to_center_zoom_wider_bounds_give_smaller_zoom():
    from src.figures import bounds_to_center_zoom

    _, zoom_narrow = bounds_to_center_zoom(48.11, -1.68, 48.85, 2.35)
    _, zoom_wide = bounds_to_center_zoom(16.23, -61.55, 51.0, 8.0)

    assert zoom_wide < zoom_narrow


def test_bounds_to_center_zoom_center_is_bbox_midpoint():
    from src.figures import bounds_to_center_zoom

    center, _ = bounds_to_center_zoom(40.0, 0.0, 50.0, 4.0)

    assert center == [45.0, 2.0]


def test_ag_grid_locale_text_translates_common_filter_labels():
    from src.figures import ag_grid

    grid = ag_grid("tableau_grid", [])
    locale_text = grid.dashGridOptions["localeText"]

    assert locale_text["equals"] == "Égal à"
    assert locale_text["contains"] == "Contient"
    assert locale_text["blank"] == "Vide"
    assert locale_text["notBlank"] == "Non vide"


def test_ag_grid_keeps_base_appearance():
    """Pas de thème/className custom au Lot 1 (spec de design)."""
    from src.figures import ag_grid

    grid = ag_grid("tableau_grid", [])

    assert getattr(grid, "className", None) in (None, "")


def test_ag_grid_always_shows_horizontal_scroll():
    """Réserve l'espace de la barre de défilement horizontale en permanence
    (comportement natif Chrome). Sans effet sur le curseur en overlay de
    Firefox, géré par l'OS/le navigateur, non contrôlable par l'appli."""
    from src.figures import ag_grid

    grid = ag_grid("tableau_grid", [])

    assert grid.dashGridOptions["alwaysShowHorizontalScroll"] is True


def test_ag_grid_accepts_dict_id_and_custom_persisted_props():
    """Grille entité : id pattern-matching + persistance limitée au filterModel
    (columnState géré via un store partagé, pas la persistance native)."""
    from src.figures import ag_grid

    gid = {"type": "acheteur-grid", "entity_id": "123", "year": "Toutes les années"}
    grid = ag_grid(gid, [], persisted_props=["filterModel"])

    assert grid.id == gid
    assert list(grid.persisted_props) == ["filterModel"]
    assert grid.persistence is True


def test_ag_grid_defaults_unchanged_for_tableau():
    """Sans args de persistance, comportement identique au Lot 1 (tableau.py)."""
    from src.figures import ag_grid

    grid = ag_grid("tableau_grid", [])

    assert grid.id == "tableau_grid"
    assert list(grid.persisted_props) == ["filterModel", "columnState"]
    assert grid.persistence is True


def test_get_top_org_ag_grid_returns_grid_with_rowdata():
    """Le top 10 devient une AG Grid client-side (rowData directe, pas de
    getRowsRequest server-side)."""
    import dash_ag_grid as dag

    from src.db import query_marches
    from src.figures import get_top_org_ag_grid

    lff = query_marches("TRUE", (), columns=None).lazy()
    grid = get_top_org_ag_grid(lff, "titulaire", ["titulaire_distance"])

    assert isinstance(grid, dag.AgGrid)
    assert grid.rowData is not None and len(grid.rowData) > 0
    # Colonne d'agrégat présente ; colonnes définies.
    assert any(c.get("field") == "Attributions" for c in grid.columnDefs)
    # Pas de persistance (petit tableau statique, régénéré à chaque fiche).
    assert grid.persistence in (False, None)


def test_get_top_org_ag_grid_empty_returns_div():
    """Données vides → html.Div() (parité get_top_org_table)."""
    import polars as pl
    from dash import html

    from src.figures import get_top_org_ag_grid

    empty = pl.DataFrame(
        {"uid": [], "titulaire_id": [], "titulaire_nom": [], "titulaire_distance": []}
    ).lazy()
    out = get_top_org_ag_grid(empty, "titulaire", ["titulaire_distance"])
    assert isinstance(out, html.Div)


def test_get_top_org_table_still_returns_datatable_after_refactor():
    """Non-régression : get_top_org_table (utilisé par observatoire.py) garde
    son comportement après extraction du helper d'agrégation partagé."""
    import dash_ag_grid  # noqa: F401
    from dash import html

    from src.db import query_marches
    from src.figures import DataTable, get_top_org_table

    lff = query_marches("TRUE", (), columns=None).lazy()
    out = get_top_org_table(lff, "titulaire", ["titulaire_distance"])
    assert isinstance(out, (DataTable, html.Div))


def test_top_org_aggregate_does_not_mutate_extra_columns():
    """Le helper ne mute pas la liste extra_columns passée (bug latent de
    l'ancien get_top_org_table, qui faisait extra_columns.append(...))."""
    from src.db import query_marches
    from src.figures import _top_org_aggregate

    extra = ["titulaire_distance"]
    _top_org_aggregate(
        query_marches("TRUE", (), columns=None).lazy(), "titulaire", extra
    )
    assert extra == ["titulaire_distance"]


def _fake_marches(n_orgs: int, org_type: str = "titulaire"):
    """Jeu synthétique avec n_orgs organisations distinctes.

    La base de test n'agrège qu'une seule organisation : la troncature du
    palmarès n'y est pas observable. L'organisation i reçoit n_orgs - i
    attributions, donc le classement est strictement décroissant et la
    troncature déterministe (avec des ex æquo, l'ordre du tri ne l'est pas).
    """
    import polars as pl

    uid, ids, noms = [], [], []
    for i in range(n_orgs):
        for j in range(n_orgs - i):
            uid.append(f"m{i}-{j}")
            ids.append(f"{i:014d}")
            noms.append(f"Org {i}")
    rows = {"uid": uid, f"{org_type}_id": ids, f"{org_type}_nom": noms}
    if org_type == "titulaire":
        rows["titulaire_typeIdentifiant"] = ["SIRET"] * len(uid)
    return pl.DataFrame(rows).lazy()


def test_get_top_org_table_truncates_to_limit():
    """La pagination de DataTable est côté client : sans troncature, toutes
    les lignes transitent par le navigateur pour n'en afficher que 10."""
    from src.figures import get_top_org_table

    lff = _fake_marches(120)
    complet = get_top_org_table(lff, "titulaire", [], filters=False, limit=None)
    tronque = get_top_org_table(lff, "titulaire", [], filters=False, limit=100)

    assert len(complet.data) == 120
    assert len(tronque.data) == 100
    # l'agrégat est trié par Attributions décroissant : on garde bien la tête
    # du classement, pas 100 lignes au hasard
    gardes = {row["titulaire_nom_tooltip"] for row in tronque.data}
    assert gardes == {f"Org {i}" for i in range(100)}


def test_get_top_org_table_defaults_to_100_rows():
    from src.figures import get_top_org_table

    table = get_top_org_table(_fake_marches(120), "titulaire", [], filters=False)
    assert len(table.data) == 100


def test_get_top_org_table_limit_above_row_count_is_harmless():
    from src.figures import get_top_org_table

    table = get_top_org_table(
        _fake_marches(7, "acheteur"), "acheteur", [], filters=False
    )
    assert len(table.data) == 7


# --- Ordre des cards de l'observatoire (issue #107) ---------------------------

#: card_ids fixes attendus. `distance` est absent : la card n'est produite que
#: si les colonnes de distance portent des valeurs, ce que le frame synthétique
#: ne garantit pas.
_CARD_IDS_FIXES = (
    "resume",
    "cat-acheteur",
    "cat-entreprise",
    "type-achat",
    "considerations",
    "top-acheteurs",
    "top-titulaires",
    "sources-donnees",
)


def _cards_de_test():
    from src.figures import build_dashboard_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    return build_dashboard_cards, _frame(observatoire_cards_columns())


def _card_ids(cards) -> list[str]:
    ids = []
    for card in cards:
        cid = getattr(card, "id", None)
        if isinstance(cid, dict) and cid.get("type") == "observatoire-card":
            ids.append(cid["index"])
    return ids


def test_build_dashboard_cards_assigns_card_ids():
    """Chaque card fixe reçoit un card_id via le pattern-matching index."""
    build_dashboard_cards, dff = _cards_de_test()

    ids = _card_ids(build_dashboard_cards(dff))

    for expected_id in _CARD_IDS_FIXES:
        assert expected_id in ids, f"card_id manquant : {expected_id}"


def test_build_dashboard_cards_with_order_reorders_cards():
    """L'ordre passé en paramètre contrôle l'ordre des cards retournées."""
    build_dashboard_cards, dff = _cards_de_test()

    order = ["top-acheteurs", "resume", "cat-acheteur"]
    ids = _card_ids(build_dashboard_cards(dff, order=order))

    assert ids[:3] == order


def test_build_dashboard_cards_order_none_keeps_default_order():
    """Sans order, l'ordre par défaut est conservé."""
    build_dashboard_cards, dff = _cards_de_test()

    assert _card_ids(build_dashboard_cards(dff)) == _card_ids(
        build_dashboard_cards(dff, order=None)
    )


def test_build_dashboard_cards_unknown_card_ids_in_order_ignored():
    """Un card_id inconnu dans order est ignoré sans erreur."""
    build_dashboard_cards, dff = _cards_de_test()

    ids = _card_ids(build_dashboard_cards(dff, order=["inexistant", "resume"]))

    assert ids[0] == "resume"
    assert "inexistant" not in ids


def test_build_dashboard_cards_order_partiel_garde_le_reste():
    """Les cards absentes de order restent à la fin, dans l'ordre par défaut."""
    build_dashboard_cards, dff = _cards_de_test()

    defaut = _card_ids(build_dashboard_cards(dff))
    ids = _card_ids(build_dashboard_cards(dff, order=["sources-donnees"]))

    assert ids[0] == "sources-donnees"
    assert ids[1:] == [cid for cid in defaut if cid != "sources-donnees"]


def test_reorder_cards_reorders_built_cards():
    """reorder_cards réordonne des cards déjà construites (après le cache)."""
    from src.figures import reorder_cards

    build_dashboard_cards, dff = _cards_de_test()
    cards = build_dashboard_cards(dff)

    ordre_inverse = list(reversed(_card_ids(cards)))

    assert _card_ids(reorder_cards(cards, ordre_inverse)) == ordre_inverse


def test_reorder_cards_ordre_vide_ne_change_rien():
    """Un ordre vide laisse les cards dans leur ordre d'origine."""
    from src.figures import reorder_cards

    build_dashboard_cards, dff = _cards_de_test()
    cards = build_dashboard_cards(dff)

    assert _card_ids(reorder_cards(cards, [])) == _card_ids(cards)


# --- Mode sombre (#118) : palettes Earthsong et paramètre theme -------------


def _find_components(component, cls, found=None):
    """Cherche récursivement les composants d'une classe donnée (children
    Dash pouvant être une liste, un composant unique, ou une chaîne)."""
    if found is None:
        found = []
    if isinstance(component, cls):
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            _find_components(c, cls, found)
    elif children is not None:
        _find_components(children, cls, found)
    return found


def test_appliquer_theme_sombre_pose_fond_police_et_grille():
    import plotly.graph_objects as go

    from src.figures import FOND_SOMBRE, TEXTE_SOMBRE, appliquer_theme
    from src.theme import SOMBRE

    fig = go.Figure()
    fig = appliquer_theme(fig, SOMBRE)

    assert fig.layout.paper_bgcolor == FOND_SOMBRE
    assert fig.layout.plot_bgcolor == FOND_SOMBRE
    assert fig.layout.font.color == TEXTE_SOMBRE


def test_appliquer_theme_clair_laisse_le_rendu_inchange():
    """Comparaison avec la figure avant l'appel (pas avec None) : le thème
    clair ne doit poser aucune de ces propriétés."""
    import plotly.graph_objects as go

    from src.figures import appliquer_theme
    from src.theme import CLAIR

    fig = go.Figure()
    avant = (
        fig.layout.paper_bgcolor,
        fig.layout.plot_bgcolor,
        fig.layout.font.color,
    )

    fig = appliquer_theme(fig, CLAIR)

    apres = (
        fig.layout.paper_bgcolor,
        fig.layout.plot_bgcolor,
        fig.layout.font.color,
    )
    assert apres == avant


def test_make_donut_theme_sombre_utilise_la_palette_sombre():
    from src.figures import PALETTE_SOMBRE, make_donut
    from src.theme import SOMBRE

    lff = _make_lff(
        [
            {"uid": "u1", "acheteur_categorie": "A"},
            {"uid": "u2", "acheteur_categorie": "B"},
        ]
    )

    graph = make_donut(lff, "acheteur_categorie", per_uid=True, theme=SOMBRE)
    piecolorway = list(graph.figure.layout.piecolorway)

    assert piecolorway
    assert set(piecolorway) <= set(PALETTE_SOMBRE)


def test_make_donut_theme_clair_utilise_px_safe():
    import plotly.express as px

    from src.figures import make_donut
    from src.theme import CLAIR

    lff = _make_lff(
        [
            {"uid": "u1", "acheteur_categorie": "A"},
            {"uid": "u2", "acheteur_categorie": "B"},
        ]
    )

    graph = make_donut(lff, "acheteur_categorie", per_uid=True, theme=CLAIR)
    piecolorway = list(graph.figure.layout.piecolorway)

    assert piecolorway == list(px.colors.qualitative.Safe)


def test_make_donut_sans_theme_hors_requete_reste_clair():
    """Non-régression : sans argument theme, et hors contexte de requête
    (comme en test), le rendu clair actuel est inchangé."""
    import plotly.express as px

    from src.figures import make_donut

    lff = _make_lff([{"uid": "u1", "acheteur_categorie": "A"}])

    graph = make_donut(lff, "acheteur_categorie", per_uid=True)

    assert list(graph.figure.layout.piecolorway) == list(px.colors.qualitative.Safe)


def test_get_barchart_sources_theme_sombre_utilise_palette_sombre_24():
    from datetime import datetime

    from src.figures import PALETTE_SOMBRE_24, get_barchart_sources
    from src.theme import SOMBRE

    lff = _make_lff(
        [
            {
                "uid": "u1",
                "dateNotification": datetime(2021, 1, 1),
                "sourceDataset": "a",
            },
            {
                "uid": "u2",
                "dateNotification": datetime(2021, 1, 2),
                "sourceDataset": "b",
            },
        ]
    )

    graph = get_barchart_sources(lff, "dateNotification", theme=SOMBRE)

    couleurs = {trace.marker.color for trace in graph.figure.data}
    assert couleurs
    assert couleurs <= set(PALETTE_SOMBRE_24)


def test_get_barchart_sources_sans_theme_hors_requete_reste_clair():
    """Non-régression : rendu clair (Dark24) inchangé sans argument theme."""
    from datetime import datetime

    import plotly.express as px

    from src.figures import get_barchart_sources

    lff = _make_lff(
        [
            {
                "uid": "u1",
                "dateNotification": datetime(2021, 1, 1),
                "sourceDataset": "a",
            },
        ]
    )

    graph = get_barchart_sources(lff, "dateNotification")

    couleurs = {trace.marker.color for trace in graph.figure.data}
    assert couleurs <= set(px.colors.qualitative.Dark24)


def test_build_org_markers_theme_sombre_utilise_org_colors_sombre():
    from src.figures import ORG_COLORS_SOMBRE, build_org_markers
    from src.theme import SOMBRE

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur", theme=SOMBRE)

    assert markers[0]["marker_color"] == ORG_COLORS_SOMBRE["acheteur"]


def test_build_org_markers_theme_clair_utilise_org_colors():
    """Non-régression : en clair, la couleur reste celle d'ORG_COLORS."""
    from src.figures import ORG_COLORS, build_org_markers
    from src.theme import CLAIR

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur", theme=CLAIR)

    assert markers[0]["marker_color"] == ORG_COLORS["acheteur"]


def test_palette_sombre_24_a_24_couleurs_distinctes():
    from src.figures import PALETTE_SOMBRE_24

    assert len(PALETTE_SOMBRE_24) == 24
    assert len(set(PALETTE_SOMBRE_24)) == 24


def test_get_considerations_card_content_theme_sombre_utilise_couleurs_sombres():
    import dash_bootstrap_components as dbc

    from src.figures import GRILLE_SOMBRE, get_considerations_card_content
    from src.theme import SOMBRE

    lff = _make_lff(
        [
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
        ]
    )

    div = get_considerations_card_content(lff, theme=SOMBRE)

    bars = [b for b in _find_components(div, dbc.Progress) if getattr(b, "bar", False)]
    bar_ren, bar_social, bar_env = bars

    assert bar_ren.color == GRILLE_SOMBRE
    assert bar_social.color == "#d0633d"
    assert bar_env.color == "#85c54c"


def test_get_considerations_card_content_sans_theme_hors_requete_reste_clair():
    """Non-régression : couleurs claires (#6c757d, #CC6677, #117733) inchangées."""
    import dash_bootstrap_components as dbc

    from src.figures import get_considerations_card_content

    lff = _make_lff(
        [
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    div = get_considerations_card_content(lff)

    bars = [b for b in _find_components(div, dbc.Progress) if getattr(b, "bar", False)]
    bar_ren, bar_social, bar_env = bars

    assert bar_ren.color == "#6c757d"
    assert bar_social.color == "#CC6677"
    assert bar_env.color == "#117733"


def test_build_dashboard_cards_propage_le_theme_sombre_aux_figures():
    """build_dashboard_cards résout le thème une fois et le transmet à toutes
    les figures qu'il construit (donut de la card cat-acheteur ici)."""
    from dash import dcc

    from src.figures import FOND_SOMBRE, card_id_of
    from src.theme import SOMBRE

    build_dashboard_cards, dff = _cards_de_test()
    cards = build_dashboard_cards(dff, theme=SOMBRE)

    cat_acheteur = next(c for c in cards if card_id_of(c) == "cat-acheteur")
    graphs = _find_components(cat_acheteur, dcc.Graph)

    assert graphs
    assert graphs[0].figure.layout.paper_bgcolor == FOND_SOMBRE
