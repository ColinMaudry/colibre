"""Grilles « Top acheteurs / Top titulaires » paginées côté serveur (#142)."""

import duckdb
import pytest
from dash import no_update

import src.db as db_module
import src.utils.top_org_grid as top_module
from src.utils.top_org_grid import (
    AGG_COLUMN,
    fetch_top_org_page,
    group_columns,
    top_org_filter_sql,
    top_org_sort_sql,
)


@pytest.fixture(scope="module")
def flask_app():
    """App Flask minimale pour que @cache.memoize() fonctionne (même pattern
    que tests/test_grid.py)."""
    from flask import Flask

    from src.utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    from src.utils.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            pass
        yield


@pytest.fixture
def decp_synthetique(monkeypatch):
    """Table `decp` en mémoire : 30 titulaires, l'organisation i ayant
    30 - i attributions (classement strictement décroissant, donc
    déterministe). La base de test partagée ne contient qu'une seule ligne :
    ni le classement, ni la pagination n'y seraient observables.
    """
    conn = duckdb.connect(":memory:")
    lignes = []
    for i in range(30):
        for j in range(30 - i):
            lignes.append(
                f"('m{i}-{j}', 'T{i:03d}', 'Organisation {i:03d}', 'SIRET', {i})"
            )
    conn.execute(
        "CREATE TABLE decp AS SELECT * FROM (VALUES " + ",".join(lignes) + ") AS t("
        "uid, titulaire_id, titulaire_nom, titulaire_typeIdentifiant, titulaire_distance)"
    )
    monkeypatch.setattr(db_module, "get_cursor", lambda: conn)
    yield conn
    conn.close()


def _request(start=0, end=10, filter_model=None, sort_model=None):
    return {
        "startRow": start,
        "endRow": end,
        "filterModel": filter_model,
        "sortModel": sort_model,
    }


def test_fetch_page_renvoie_lignes_et_total(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(), operateurs=False
        )

    assert response["rowCount"] == 30  # nombre de groupes, pas de lignes
    assert len(response["rowData"]) == 10
    # Tri par défaut : l'organisation 000 a le plus d'attributions.
    assert response["rowData"][0]["Attributions"] == 30
    # add_links a posé un lien vers la fiche.
    assert '<a href = "/titulaires/T000">' in response["rowData"][0]["titulaire_nom"]


def test_fetch_page_offset_sans_doublon(flask_app, decp_synthetique):
    with flask_app.app_context():
        page1 = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(0, 10), operateurs=False
        )
        page2 = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(10, 20), operateurs=False
        )

    ids1 = [r["titulaire_id"] for r in page1["rowData"]]
    ids2 = [r["titulaire_id"] for r in page2["rowData"]]
    assert len(set(ids1) & set(ids2)) == 0
    assert ids1 == [f"T{i:03d}" for i in range(10)]


def test_fetch_page_filtre_trouve_au_dela_du_10e_rang(flask_app, decp_synthetique):
    """Le cœur de #142 : le filtre porte sur tout le classement, pas sur la
    page affichée ni sur un top tronqué."""
    filtre = {
        "titulaire_nom": {"filterType": "text", "type": "contains", "filter": "025"}
    }
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(0, 10, filtre), operateurs=False
        )

    assert response["rowCount"] == 1
    assert response["rowData"][0]["titulaire_id"] == "T025"


def test_fetch_page_having_sur_attributions(flask_app, decp_synthetique):
    filtre = {
        "Attributions": {"filterType": "number", "type": "greaterThan", "filter": 25}
    }
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(0, 10, filtre), operateurs=False
        )

    assert response["rowCount"] == 5  # 30, 29, 28, 27, 26
    assert all(row["Attributions"] > 25 for row in response["rowData"])


def test_fetch_page_tri_numerique_pas_lexicographique(flask_app, decp_synthetique):
    """9 doit rester inférieur à 10 : l'ancienne grille comparait des chaînes."""
    tri = [{"colId": "Attributions", "sort": "asc"}]
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "TRUE", [], _request(0, 5, sort_model=tri), operateurs=False
        )

    valeurs = [row["Attributions"] for row in response["rowData"]]
    assert valeurs == [1, 2, 3, 4, 5]


def test_fetch_page_respecte_le_perimetre(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "titulaire_id = ?", ["T003"], _request(), operateurs=False
        )

    assert response["rowCount"] == 1
    assert response["rowData"][0]["titulaire_id"] == "T003"


def test_fetch_page_compte_mis_en_cache_entre_les_pages(
    flask_app, decp_synthetique, monkeypatch
):
    """Régression : un COUNT par page rendrait la pagination deux fois plus
    coûteuse (même raison que _cached_count dans src/utils/grid.py)."""
    appels = {"n": 0}
    vrai_count = top_module.count_aggregate

    def compter(*args, **kwargs):
        appels["n"] += 1
        return vrai_count(*args, **kwargs)

    monkeypatch.setattr(top_module, "count_aggregate", compter)

    with flask_app.app_context():
        fetch_top_org_page("titulaire", "TRUE", [], _request(0, 10), operateurs=False)
        fetch_top_org_page("titulaire", "TRUE", [], _request(10, 20), operateurs=False)
        fetch_top_org_page("titulaire", "TRUE", [], _request(20, 30), operateurs=False)

    assert appels["n"] == 1


def test_fetch_page_sans_request():
    assert (
        fetch_top_org_page("titulaire", "TRUE", [], None, operateurs=False) is no_update
    )


def test_fetch_page_perimetre_vide(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "titulaire_id = ?", ["INCONNU"], _request(), operateurs=False
        )

    assert response == {"rowData": [], "rowCount": 0}


def test_fetch_page_perimetre_et_having_ordonnes(flask_app, decp_synthetique):
    """Comble un trou de couverture de la tâche 1 : un périmètre à paramètre
    lié (WHERE) combiné à un filtre sur la colonne agrégée (HAVING) doit lier
    ses paramètres dans l'ordre WHERE puis HAVING. Si l'ordre était inversé,
    la valeur numérique du HAVING (15) se retrouverait liée au `?` du LIKE
    (une chaîne attendue), ce qui ferait échouer la requête ou la fausserait
    silencieusement.
    """
    filtre = {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": 15}}
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire",
            "titulaire_nom LIKE ?",
            ["Organisation 01%"],
            _request(0, 10, filtre),
            operateurs=False,
        )

    # Périmètre : organisations 010 à 019 (10 orgs, Attributions 20..11).
    # HAVING : Attributions > 15 -> restreint à 010..014 (20,19,18,17,16).
    assert response["rowCount"] == 5
    assert {row["titulaire_id"] for row in response["rowData"]} == {
        f"T{i:03d}" for i in range(10, 15)
    }
    assert all(row["Attributions"] > 15 for row in response["rowData"])


def test_group_columns_titulaire_inclut_type_identifiant():
    """add_links n'ajoute le lien SIRET que si titulaire_typeIdentifiant est là."""
    cols = group_columns("titulaire", ["titulaire_distance"])
    assert cols[:2] == ["titulaire_id", "titulaire_nom"]
    assert "titulaire_typeIdentifiant" in cols
    assert "titulaire_distance" in cols


def test_group_columns_acheteur_sans_type_identifiant():
    assert group_columns("acheteur") == ["acheteur_id", "acheteur_nom"]


def test_filtre_sur_le_nom_produit_un_where():
    where_sql, where_params, having_sql, having_params = top_org_filter_sql(
        {
            "titulaire_nom": {
                "filterType": "text",
                "type": "contains",
                "filter": "mairie",
            }
        },
        "titulaire",
        operateurs=False,
    )
    assert where_sql != "TRUE"
    assert where_params  # valeur liée, jamais concaténée
    assert "mairie" in " ".join(str(p) for p in where_params).lower()
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_attributions_produit_un_having():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": 5}},
        "titulaire",
        operateurs=False,
    )
    assert having_sql == "(COUNT(*) > ?)"
    assert having_params == [5]


def test_filtre_attributions_in_range():
    _, _, having_sql, having_params = top_org_filter_sql(
        {
            AGG_COLUMN: {
                "filterType": "number",
                "type": "inRange",
                "filter": 2,
                "filterTo": 7,
            }
        },
        "titulaire",
        operateurs=False,
    )
    assert having_sql == "(COUNT(*) BETWEEN ? AND ?)"
    assert having_params == [2, 7]


def test_filtre_attributions_deux_conditions():
    _, _, having_sql, having_params = top_org_filter_sql(
        {
            AGG_COLUMN: {
                "filterType": "number",
                "operator": "AND",
                "conditions": [
                    {"filterType": "number", "type": "greaterThan", "filter": 2},
                    {"filterType": "number", "type": "lessThan", "filter": 9},
                ],
            }
        },
        "titulaire",
        operateurs=False,
    )
    assert having_sql == "(COUNT(*) > ?) AND (COUNT(*) < ?)"
    assert having_params == [2, 9]


def test_filtre_attributions_valeur_decimale_non_tronquee():
    """AG Grid autorise une décimale ; elle ne doit pas être tronquée (5.5 -> 5)."""
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "lessThan", "filter": 5.5}},
        "titulaire",
        operateurs=False,
    )
    assert having_sql == "(COUNT(*) < ?)"
    assert having_params == [5.5]


def test_filtre_attributions_valeur_non_numerique_ignoree():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": "abc"}},
        "titulaire",
        operateurs=False,
    )
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_colonne_hors_perimetre_ignore():
    """Une colonne du schéma mais absente du GROUP BY ne doit pas filtrer."""
    where_sql, where_params, _, _ = top_org_filter_sql(
        {"objet": {"filterType": "text", "type": "contains", "filter": "route"}},
        "titulaire",
        operateurs=False,
    )
    assert where_sql == "TRUE"
    assert where_params == []


def test_tri_par_defaut_attributions_puis_id():
    assert (
        top_org_sort_sql(None, "titulaire") == '"Attributions" DESC, "titulaire_id" ASC'
    )


def test_tri_explicite_puis_id():
    sql = top_org_sort_sql([{"colId": "titulaire_nom", "sort": "asc"}], "titulaire")
    assert sql == '"titulaire_nom" ASC, "titulaire_id" ASC'


def test_tri_sur_colonne_inconnue_ignore():
    sql = top_org_sort_sql(
        [{"colId": "objet; DROP TABLE decp", "sort": "asc"}], "titulaire"
    )
    assert sql == '"Attributions" DESC, "titulaire_id" ASC'


def test_grid_id_pattern_matching():
    import dash_ag_grid as dag

    from src.utils.top_org_grid import top_org_grid

    grille = top_org_grid("observatoire", "titulaire", "abc123")

    assert isinstance(grille, dag.AgGrid)
    assert grille.id == {
        "type": "top-org-grid",
        "context": "observatoire",
        "org_type": "titulaire",
        "scope": "abc123",
    }


def test_grid_est_en_modele_infinite_pagine():
    from src.utils.top_org_grid import PAGE_SIZE, top_org_grid

    grille = top_org_grid("observatoire", "acheteur", "abc123")
    options = grille.dashGridOptions

    assert grille.rowModelType == "infinite"
    assert options["pagination"] is True
    assert options["paginationPageSize"] == PAGE_SIZE
    assert options["cacheBlockSize"] == PAGE_SIZE
    # domLayout: "autoHeight" est incompatible avec le modèle infinite : ne
    # doit pas être posé du tout, la hauteur doit être fixe.
    assert "domLayout" not in options
    assert grille.style["height"].endswith("px")
    assert grille.rowData is None  # aucune donnée embarquée
    assert grille.persistence in (False, None)


def test_grid_scopes_distincts_donnent_des_ids_distincts():
    from src.utils.top_org_grid import scope_key, top_org_grid_id

    id1 = top_org_grid_id("acheteur", "titulaire", scope_key("/acheteurs/1", "2025"))
    id2 = top_org_grid_id("acheteur", "titulaire", scope_key("/acheteurs/2", "2025"))
    id3 = top_org_grid_id("tableau", "titulaire", scope_key("/acheteurs/1", "2025"))

    assert id1 != id2  # sinon React ne remonte pas la grille au changement de fiche
    assert id1 != id3  # un callback par contexte


def test_column_defs_types_de_filtre():
    from src.utils.top_org_grid import top_org_column_defs

    defs = {
        d["field"]: d for d in top_org_column_defs("titulaire", ["titulaire_distance"])
    }

    assert "titulaire_id" not in defs  # lien porté par le nom
    assert "titulaire_typeIdentifiant" not in defs  # technique, requis par add_links
    assert defs["titulaire_nom"]["filter"] == "agTextColumnFilter"
    assert defs["titulaire_nom"]["cellRenderer"] == "markdown"
    assert defs["Attributions"]["filter"] == "agNumberColumnFilter"
    assert defs["titulaire_distance"]["filter"] == "agNumberColumnFilter"
    assert all(d["sortable"] for d in defs.values())


def test_callbacks_datasource_enregistres_pour_chaque_contexte():
    """Un callback getRowsResponse par contexte, sinon deux pages écriraient
    la même sortie (Dash refuse une sortie dupliquée).

    Les clés de GLOBAL_CALLBACK_MAP sont les ids sérialisés en JSON à clés
    triées, par exemple :
    {"context":"acheteur","org_type":["MATCH"],"scope":["MATCH"],"type":"top-org-grid"}
    """
    import dash

    from src.app import app  # instancie Dash → register_page()

    # Tant que l'app n'a pas été servie, les callbacks enregistrés via le
    # décorateur global `dash.callback` vivent dans
    # dash._callback.GLOBAL_CALLBACK_MAP ; ils ne migrent vers
    # app.callback_map qu'à la première requête (_setup_server). On inspecte
    # donc les deux registres pour ne pas dépendre de l'ordre des tests (voir
    # tests/test_entity_grid.py et tests/test_csrf_architecture.py pour le
    # même motif).
    callback_keys = set(dash._callback.GLOBAL_CALLBACK_MAP) | set(app.callback_map)

    cles = [
        k.replace(" ", "")
        for k in callback_keys
        if "top-org-grid" in k and "getRowsResponse" in k
    ]
    contextes = {
        contexte
        for contexte in ("observatoire", "tableau", "acheteur", "titulaire")
        if any(f'"context":"{contexte}"' in k for k in cles)
    }

    assert contextes == {"observatoire", "tableau", "acheteur", "titulaire"}
