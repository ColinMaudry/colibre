import base64
import io
import json
from unittest.mock import patch

import dash
import openpyxl
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.auth import db as auth_db
from src.db import schema
from src.pages import tableau
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    query = json.dumps(
        {"ast": ast_to_dict(ast), "columnState": [{"colId": "montant", "hide": True}]}
    )
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_vue_from_url_found(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid)
    out = tableau.resolve_vue_from_url(f"?vue={token}_ma-vue")
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_vue_from_url_no_param_returns_none(users_db_path):
    saved_views_db.init_schema()
    assert tableau.resolve_vue_from_url("") is None
    assert tableau.resolve_vue_from_url("?autre=1") is None


def test_apply_vue_resolution_found_shows_box(users_db_path):
    resolution = {
        "found": True,
        "filter_model": {
            "objet": {"filterType": "text", "type": "contains", "filter": "route"}
        },
        "column_state": [{"colId": "montant", "hide": True}],
        "hidden_columns": ["montant"],
        "token": "abc123",
        "url": "https://test.colibre.fr/tableau?vue=abc123_ma-vue",
        "error": None,
    }
    fm, cs, hidden, active, feedback = tableau.apply_vue_resolution(resolution)
    assert fm == resolution["filter_model"]
    assert cs == resolution["column_state"]
    assert hidden == ["montant"]
    assert active == {"token": "abc123", "url": resolution["url"]}
    assert feedback == ""


def test_apply_vue_resolution_not_found_shows_alert(users_db_path):
    resolution = {
        "found": False,
        "filter_model": None,
        "column_state": None,
        "hidden_columns": None,
        "token": None,
        "url": None,
        "error": resolve.NOT_FOUND_MESSAGE,
    }
    fm, cs, hidden, active, feedback = tableau.apply_vue_resolution(resolution)
    assert fm is dash.no_update
    assert cs is dash.no_update
    assert active is None
    assert resolve.NOT_FOUND_MESSAGE in str(feedback)


def test_apply_vue_resolution_none_is_noop(users_db_path):
    out = tableau.apply_vue_resolution(None)
    assert all(v is dash.no_update for v in out)


def _fake_user(user_id):
    u = type("U", (), {})()
    u.is_authenticated = True
    u.id = user_id
    return u


class _Ctx:
    triggered_id = None


def test_render_share_box_visible_when_active():
    class_name, value = tableau.render_share_box(
        {"token": "abc123", "url": "https://x/tableau?vue=abc123_a"}
    )
    assert "d-flex" in class_name
    assert "d-none" not in class_name
    assert value == "https://x/tableau?vue=abc123_a"


def test_render_share_box_hidden_when_none():
    class_name, value = tableau.render_share_box(None)
    assert "d-none" in class_name
    assert value == ""


def test_apply_saved_view_sets_active(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid, "Ma vue")
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]
    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )
    # (filter_model, column_state, hidden, active-view)
    assert out[3] == {
        "token": token,
        "url": f"https://test.colibre.fr/tableau?vue={token}_ma-vue",
    }


def test_save_view_shows_box(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: True)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.save_view(1, "Nouvelle", {}, [])
    # (is_open, feedback, refresh, active-view)
    assert out[3]["url"].endswith("_nouvelle")


def _type_in_first_filter(dash_duo):
    """Saisit du texte dans le premier filtre flottant présent dans le DOM (AG
    Grid virtualise horizontalement : 'objet' peut être hors DOM). Re-localise
    l'élément à chaque appel : la grille se re-rend juste après l'application de
    la vue (echo columnVisible) et remplace l'input."""
    selector = "#tableau_grid .ag-floating-filter-input input"
    dash_duo.wait_for_element(selector, timeout=8)
    el = dash_duo.find_elements(selector)[0]
    dash_duo.driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el
    )
    el.click()
    el.send_keys("z")


def test_open_shared_view_applies_and_shows_box(dash_duo, users_db_path):
    """?vue=<token> applique la vue et affiche le bloc de partage ; une action
    utilisateur (saisie d'un filtre) le masque via l'écouteur d'événements AG
    Grid (source utilisateur ≠ 'api'), l'écho de l'application étant ignoré."""
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid, "Ma vue")

    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + f"/tableau?vue={token}_ma-vue")

    # Le bloc de partage est visible et affiche l'URL courte (jeton). Le texte est
    # renseigné par le même callback que l'affichage : le lire non vide prouve que
    # l'écho de l'application n'a PAS masqué le bloc.
    dash_duo.wait_for_style_to_equal("#share-url-box", "display", "flex", timeout=10)
    dash_duo.wait_for_element("#share-url-text", timeout=6)
    WebDriverWait(dash_duo.driver, 10).until(
        lambda _d: token in (dash_duo.find_element("#share-url-text").text or "")
    )

    # Le bouton de copie porte un libellé explicite (UX : pas d'icône seule).
    assert "Copier le lien" in dash_duo.find_element("#share-url-box").text

    # Une action utilisateur (filtre) masque la box. On re-tente la saisie tant
    # que le bloc n'est pas masqué : la fenêtre de re-render post-application
    # peut invalider l'input entre le find et le send_keys.
    def _box_hidden(_d):
        _type_in_first_filter(dash_duo)
        display = dash_duo.find_element("#share-url-box").value_of_css_property(
            "display"
        )
        return display == "none"

    WebDriverWait(dash_duo.driver, 15).until(_box_hidden)


# --- Opérateurs booléens d'une vue ouverte, pour un non-abonné (#97) -------
# tests/test.parquet n'a qu'une ligne (objet « Objet test ») : `test OU zzz`
# la trouve avec les opérateurs, pas sans (les trois mots sont alors exigés).


def _vue_booleenne(monkeypatch, ast=None):
    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)
    saved_views_db.init_schema()
    ast = ast or And([Condition("objet", "contains", "test OU zzz")])
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": []})
    token = saved_views_db.upsert(_make_user(), "tableau", "Ma vue", query)
    return resolve.resolve_vue_param(token, schema)


def test_get_rows_vue_non_abonne(monkeypatch, users_db_path):
    res = _vue_booleenne(monkeypatch)
    req = {"filterModel": res["filter_model"], "startRow": 0, "endRow": 100}

    rows, total, _ = tableau.get_rows_tableau(req, res)
    assert rows["rowCount"] == 1 and total == 1

    modifie = {"objet": {**res["filter_model"]["objet"], "filter": "test OU zzzz"}}
    _, total, _ = tableau.get_rows_tableau({**req, "filterModel": modifie}, res)
    assert total == 0

    _, total, _ = tableau.get_rows_tableau(req, None)
    assert total == 0


def test_export_vue_non_abonne(monkeypatch, users_db_path):
    res = _vue_booleenne(monkeypatch)

    out = tableau.download_data(1, res["filter_model"], [], 1, res)

    assert out["filename"].endswith(".xlsx")
    contenu = base64.b64decode(out["content"])
    # En-tête + la ligne ; sans l'exception, l'export serait vide.
    assert openpyxl.load_workbook(io.BytesIO(contenu)).active.max_row == 2


def test_vue_partagee_operateurs_non_abonne(dash_duo, users_db_path):
    """Visiteur non connecté : la vue partagée applique ses filtres booléens
    sans bandeau ; une frappe dans le filtre Objet rend le régime non-abonné.
    La vue mêle filtres texte, nombre et date pour vérifier que le filterModel
    renvoyé par la vraie grille reste reconnu identique à celui de la vue."""
    saved_views_db.init_schema()
    ast = And(
        [
            Condition("objet", "contains", "test OU zzz"),
            Condition("montant", "gt", 5),
            Condition("dateNotification", "gt", "2024-01-01 00:00:00"),
        ]
    )
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": []})
    token = saved_views_db.upsert(_make_user(), "tableau", "Ma vue", query)

    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + f"/tableau?vue={token}_ma-vue")

    dash_duo.wait_for_contains_text("#nb_rows", "1 marchés (1 lignes)", timeout=15)
    dash_duo.wait_for_contains_text("#tableau-filter-pills", "test OU zzz", timeout=10)
    assert not dash_duo.driver.find_elements(
        By.CSS_SELECTOR, "#tableau-filter-pills .filter-pills-banniere"
    )

    # Colonnes virtualisées par AG Grid : Objet n'est dans le DOM qu'une fois
    # amenée à l'écran (même procédé que src/assets/filter_pills.js).
    dash_duo.driver.execute_script(
        'dash_ag_grid.getApi("tableau_grid").ensureColumnVisible("objet");'
    )
    champ = '#tableau_grid .ag-floating-filter[col-id="objet"] input'
    dash_duo.wait_for_element(champ, timeout=10)

    def _bandeau_visible(_d):
        # Nouvelle tentative tant que le bandeau n'est pas là : le re-rendu qui
        # suit l'application de la vue peut invalider le champ.
        dash_duo.find_element(champ).send_keys("z")
        return bool(
            dash_duo.driver.find_elements(
                By.CSS_SELECTOR, "#tableau-filter-pills .filter-pills-banniere"
            )
        )

    WebDriverWait(dash_duo.driver, 15, poll_frequency=2).until(_bandeau_visible)
    dash_duo.wait_for_contains_text("#nb_rows", "0 marchés", timeout=10)
