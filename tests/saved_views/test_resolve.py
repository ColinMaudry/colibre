import json

from src.auth import db as auth_db
from src.db import schema
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, Or, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed_view(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    column_state = [
        {"colId": "montant", "sort": "desc"},
        {"colId": "acheteur_nom", "hide": True},
    ]
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state})
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_found_applies_view(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid, "Mes Marchés")

    out = resolve.resolve_vue_param(f"{token}_mes-marches", schema)

    assert out["found"] is True
    assert out["filter_model"] == {
        "objet": {"filterType": "text", "type": "contains", "filter": "route"}
    }
    assert out["hidden_columns"] == ["acheteur_nom"]
    assert out["token"] == token
    assert out["url"] == f"https://test.colibre.fr/tableau?vue={token}_mes-marches"
    assert out["error"] is None


def test_resolve_slug_is_ignored(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid)
    # Slug bidon → même résolution.
    out = resolve.resolve_vue_param(f"{token}_nimportequoi", schema)
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_unknown_token_returns_error(users_db_path):
    saved_views_db.init_schema()
    _make_user()
    out = resolve.resolve_vue_param("zzzzzz_slug", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE
    assert out["filter_model"] is None


def test_resolve_empty_param_returns_error(users_db_path):
    saved_views_db.init_schema()
    out = resolve.resolve_vue_param("", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE


def test_resolve_corrupt_query_returns_error(users_db_path):
    saved_views_db.init_schema()
    uid = _make_user()
    # query pré-migration (pas du JSON) → même message de repli.
    token = saved_views_db.upsert(uid, "tableau", "Vieille", "filtres=a&tris=b")
    out = resolve.resolve_vue_param(f"{token}_vieille", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE


# --- Opérateurs booléens débloqués par une vue ouverte (#97) ---------------

VUE = And(
    [
        Condition("objet", "contains", "béton OU ciment"),
        Condition("montant", "gt", 5),
    ]
)


def _seed_ast(uid, ast, name="Vue booléenne"):
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": []})
    return saved_views_db.upsert(uid, "tableau", name, query)


def _ouvrir(ast=VUE):
    """Résolution telle que le store vue-resolution la contient."""
    saved_views_db.init_schema()
    token = _seed_ast(_make_user(), ast)
    return resolve.resolve_vue_param(token, schema)


def _autorise(res, filter_model):
    return resolve.vue_autorise_operateurs(res, filter_model, schema)


def test_vue_autorise_filtre_identique(users_db_path):
    res = _ouvrir()
    assert _autorise(res, res["filter_model"]) is True


def test_vue_autorise_ordre_des_colonnes(users_db_path):
    res = _ouvrir()
    inverse = dict(reversed(list(res["filter_model"].items())))
    assert _autorise(res, inverse) is True


def test_vue_autorise_filtre_booleen_modifie(users_db_path):
    res = _ouvrir()
    fm = res["filter_model"]
    modifie = {**fm, "objet": {**fm["objet"], "filter": "béton OU ciments"}}
    assert _autorise(res, modifie) is False


def test_vue_autorise_colonne_ajoutee(users_db_path):
    res = _ouvrir()
    ajout = {"filterType": "text", "type": "contains", "filter": "x"}
    assert _autorise(res, {**res["filter_model"], "acheteur_nom": ajout}) is False


def test_vue_autorise_colonne_retiree(users_db_path):
    res = _ouvrir()
    assert _autorise(res, {"objet": res["filter_model"]["objet"]}) is False


def test_vue_autorise_sans_resolution(users_db_path):
    res = _ouvrir()
    fm = res["filter_model"]
    assert _autorise(None, fm) is False
    assert _autorise({**res, "found": False}, fm) is False
    assert _autorise({**res, "token": None}, fm) is False


def test_vue_autorise_jeton_inconnu(users_db_path):
    res = _ouvrir()
    assert _autorise({**res, "token": "zzzzzz"}, res["filter_model"]) is False


def test_vue_autorise_ignore_filter_model_du_store(users_db_path):
    """Le filter_model du store vient du navigateur : falsifié pour coller au
    filtre courant, il ne débloque rien, seule la vue en base fait foi."""
    res = _ouvrir()
    courant = {"objet": {"filterType": "text", "type": "contains", "filter": "a OU b"}}
    assert _autorise({**res, "filter_model": courant}, courant) is False


def test_vue_autorise_filtre_vide(users_db_path):
    res = _ouvrir()
    assert _autorise(res, None) is False
    assert _autorise(res, {}) is False


def test_vue_autorise_deux_conditions(users_db_path):
    ast = And(
        [
            Or(
                [
                    Condition("objet", "contains", "béton OU ciment"),
                    Condition("objet", "contains", "brique"),
                ]
            )
        ]
    )
    res = _ouvrir(ast)
    assert _autorise(res, res["filter_model"]) is True


def test_vue_autorise_ignore_entree_sans_effet(users_db_path):
    """Une entrée que le SQL ignore (colonne hors schéma) est aussi ignorée par
    la comparaison."""
    res = _ouvrir()
    inconnue = {"filterType": "text", "type": "contains", "filter": "x"}
    fm = {**res["filter_model"], "colonne_inexistante": inconnue}
    assert _autorise(res, fm) is True


def test_vue_autorise_query_illisible(users_db_path):
    saved_views_db.init_schema()
    token = saved_views_db.upsert(_make_user(), "tableau", "Vieille", "objet=route")
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "route"}}
    assert _autorise({"found": True, "token": token}, fm) is False
