"""Migration 0017 : dans les vues sauvegardées, les phrases `a+b` deviennent
`"a b"` (le `+` n'est plus un séparateur de phrase, issue #97)."""

import json

import pytest

from src import migrations
from src.auth import db as auth_db
from src.migrations import _plus_vers_guillemets, apply_pending
from src.saved_views import db as saved_views_db

ID_MIGRATION = "0017_saved_views_plus_vers_guillemets"


def cond(column, operator, value, value2=None):
    return {
        "t": "cond",
        "column": column,
        "operator": operator,
        "value": value,
        "value2": value2,
    }


def _creer_vue(query: str) -> int:
    auth_db.init_schema()
    saved_views_db.init_schema()
    conn = auth_db.get_conn()
    user = conn.execute("SELECT id FROM users WHERE email = ?", ("u@ex.fr",))
    row = user.fetchone()
    uid = row["id"] if row else auth_db.create_user("u@ex.fr", "hash")
    saved_views_db.upsert(uid, "tableau", f"Vue {query[:20]}", query)
    return conn.execute(
        "SELECT id FROM saved_views WHERE query = ?", (query,)
    ).fetchone()["id"]


def _query(view_id: int) -> str:
    return (
        auth_db.get_conn()
        .execute("SELECT query FROM saved_views WHERE id = ?", (view_id,))
        .fetchone()["query"]
    )


def _ids_appliques() -> list[str]:
    return [
        row[0] for row in auth_db.get_conn().execute("SELECT id FROM schema_migrations")
    ]


@pytest.mark.parametrize(
    "avant, apres",
    [
        ("maitrise+d'oeuvre", '"maitrise d\'oeuvre"'),
        ("distri* metropole+rennes", 'distri* "metropole rennes"'),
        ("a+b*", "a+b*"),
        ('a+"b', 'a+"b'),
        ("sans plus", "sans plus"),
    ],
)
def test_plus_vers_guillemets(avant, apres):
    assert _plus_vers_guillemets(avant) == apres


def test_migration_reecrit_les_vues(users_db_path):
    column_state = [{"colId": "objet", "width": 300}]
    query = json.dumps(
        {
            "ast": {
                "t": "and",
                "children": [
                    cond("objet", "contains", "maitrise+d'oeuvre"),
                    cond("objet", "equals", "a+b"),
                    cond("montant", "greaterThan", 5),
                ],
            },
            "columnState": column_state,
        }
    )
    view_id = _creer_vue(query)

    apply_pending()

    apres = json.loads(_query(view_id))
    enfants = apres["ast"]["children"]
    assert enfants[0]["value"] == '"maitrise d\'oeuvre"'
    assert enfants[1]["value"] == "a+b"
    assert enfants[2]["value"] == 5
    assert apres["columnState"] == column_state


def test_migration_reecrit_les_noeuds_imbriques(users_db_path):
    query = json.dumps(
        {
            "ast": {
                "t": "or",
                "children": [
                    {"t": "not", "child": cond("objet", "notContains", "a+b")},
                    cond("objet", "contains", None),
                ],
            },
            "columnState": [],
        }
    )
    view_id = _creer_vue(query)

    apply_pending()

    apres = json.loads(_query(view_id))
    assert apres["ast"]["children"][0]["child"]["value"] == '"a b"'
    assert apres["ast"]["children"][1]["value"] is None


def test_migration_ignore_les_anciennes_vues(users_db_path):
    non_json = "objet icontains a+b"
    sans_ast = json.dumps({"filtres": "objet icontains a+b"})
    id_non_json = _creer_vue(non_json)
    id_sans_ast = _creer_vue(sans_ast)

    apply_pending()

    assert _query(id_non_json) == non_json
    assert _query(id_sans_ast) == sans_ast


def test_migration_sans_table(users_db_path):
    apply_pending()

    tables = {
        row[0]
        for row in auth_db.get_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "saved_views" not in tables
    assert ID_MIGRATION in _ids_appliques()


def test_migration_idempotente(users_db_path):
    query = json.dumps(
        {"ast": cond("objet", "contains", "a+b"), "columnState": []},
    )
    view_id = _creer_vue(query)

    apply_pending()
    premiere = _query(view_id)
    apply_pending()

    assert _query(view_id) == premiere
    assert json.loads(premiere)["ast"]["value"] == '"a b"'
    assert _ids_appliques().count(ID_MIGRATION) == 1


def test_migration_en_echec_annulee(users_db_path, monkeypatch):
    query = json.dumps(
        {"ast": cond("objet", "contains", "a+b"), "columnState": []},
    )
    view_id = _creer_vue(query)
    apply_pending()
    avant = _query(view_id)

    def migration_en_echec(conn):
        conn.execute("UPDATE saved_views SET query = 'cassé'")
        raise RuntimeError("échec volontaire")

    monkeypatch.setattr(
        migrations,
        "_MIGRATIONS",
        [*migrations._MIGRATIONS, ("9999_en_echec", migration_en_echec)],
    )

    with pytest.raises(RuntimeError, match="échec volontaire"):
        apply_pending()

    assert _query(view_id) == avant
    assert "9999_en_echec" not in _ids_appliques()


def test_migration_qui_clot_sa_transaction_garde_l_erreur(users_db_path, monkeypatch):
    apply_pending()

    def migration_qui_commite(conn):
        conn.execute("COMMIT")
        raise ValueError("erreur d'origine")

    monkeypatch.setattr(
        migrations,
        "_MIGRATIONS",
        [*migrations._MIGRATIONS, ("9998_commit_puis_echec", migration_qui_commite)],
    )

    with pytest.raises(ValueError, match="erreur d'origine"):
        apply_pending()

    assert "9998_commit_puis_echec" not in _ids_appliques()
