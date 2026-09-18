import string

from src.auth import db as auth_db
from src.saved_views import db


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_table(users_db_path):
    db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "saved_views" in tables


def test_upsert_creates_and_lists(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["name"] == "Ma vue"
    assert views[0]["query"] == "filtres=foo"


def test_upsert_same_name_overwrites(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    db.upsert(uid, "tableau", "Ma vue", "filtres=bar")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["query"] == "filtres=bar"


def test_list_views_is_isolated_per_user(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    assert db.list_views(uid2, "tableau") == []


def test_rename_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.rename(view_id, uid2, "Pirate")  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1)["name"] == "Vue A"
    db.rename(view_id, uid1, "Vue B")
    assert db.get(view_id, uid1)["name"] == "Vue B"


def test_delete_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.delete(view_id, uid2)  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1) is not None
    db.delete(view_id, uid1)
    assert db.get(view_id, uid1) is None


def test_views_deleted_on_user_cascade(users_db_path):
    from src.migrations import apply_pending

    db.init_schema()
    # En production, apply_pending() tourne toujours au démarrage avant tout
    # appel à delete_user (celui-ci nettoie aussi user_preferences et
    # observatoire_card_order, créées par les migrations 0015/0016).
    apply_pending()
    uid = _make_user()
    db.upsert(uid, "tableau", "Vue A", "filtres=a")
    auth_db.delete_user(uid)
    assert db.list_views(uid, "tableau") == []


def test_generate_token_is_lowercase_base36_and_length_6():
    token = db.generate_token()
    assert len(token) == 6
    alphabet = set(string.ascii_lowercase + string.digits)
    assert set(token) <= alphabet
    # Jamais de majuscule (lien plus lisible/dictable, cohérent avec le slug).
    assert token == token.lower()


def test_upsert_returns_token_on_insert(users_db_path):
    db.init_schema()
    uid = _make_user()
    token = db.upsert(uid, "tableau", "Ma vue", "q1")
    assert token
    assert db.list_views(uid, "tableau")[0]["token"] == token


def test_upsert_preserves_token_on_overwrite(users_db_path):
    db.init_schema()
    uid = _make_user()
    token1 = db.upsert(uid, "tableau", "Ma vue", "q1")
    token2 = db.upsert(uid, "tableau", "Ma vue", "q2")
    assert token2 == token1  # écrasement → lien stable
    assert db.list_views(uid, "tableau")[0]["query"] == "q2"


def test_get_by_token_public_lookup(users_db_path):
    db.init_schema()
    uid = _make_user()
    token = db.upsert(uid, "tableau", "Ma vue", "q1")
    row = db.get_by_token(token)
    assert row is not None
    assert row["name"] == "Ma vue"
    assert db.get_by_token("zzzzzz") is None


def test_tokens_are_unique_across_views(users_db_path):
    db.init_schema()
    uid = _make_user()
    t1 = db.upsert(uid, "tableau", "Vue A", "a")
    t2 = db.upsert(uid, "tableau", "Vue B", "b")
    assert t1 != t2


def test_backfill_assigns_tokens_to_null_rows(users_db_path):
    db.init_schema()
    uid = _make_user()
    conn = auth_db.get_conn()
    # Simule une ligne pré-migration (token NULL) en contournant upsert.
    conn.execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, token, created_at, updated_at) "
        "VALUES (?, 'tableau', 'Ancienne', 'q', NULL, '', '')",
        (uid,),
    )
    db.init_schema()  # doit backfiller
    row = conn.execute(
        "SELECT token FROM saved_views WHERE name = 'Ancienne'"
    ).fetchone()
    assert row["token"] and len(row["token"]) == 6
    # Idempotent : un second appel ne change pas le jeton attribué.
    token_after_first = row["token"]
    db.init_schema()
    row2 = conn.execute(
        "SELECT token FROM saved_views WHERE name = 'Ancienne'"
    ).fetchone()
    assert row2["token"] == token_after_first
