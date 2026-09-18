from datetime import datetime, timedelta, timezone

import pytest

from src.auth.db import (
    create_email_verification_token,
    create_password_reset_token,
    create_user,
    delete_email_verification_tokens_for_user,
    delete_password_reset_tokens_for_user,
    delete_user,
    find_email_verification_token,
    find_password_reset_token,
    get_conn,
    get_user_by_email,
    get_user_by_id,
    init_schema,
    purge_expired_tokens,
    set_email_verified,
    update_password_hash,
)


def test_init_schema_creates_tables(users_db_path):
    init_schema()
    conn = get_conn()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "email_verification_tokens", "password_reset_tokens"} <= tables


def test_init_schema_is_idempotent(users_db_path):
    init_schema()
    init_schema()
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [r[0] for r in tables]
    assert names.count("users") == 1


def test_pragmas_active(users_db_path):
    init_schema()
    conn = get_conn()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_create_user_and_get_by_email(users_db_path):
    init_schema()
    user_id = create_user("alice@example.com", "hash-bidon")
    assert user_id > 0
    row = get_user_by_email("alice@example.com")
    assert row is not None
    assert row["email"] == "alice@example.com"
    assert row["email_verified"] == 0


def test_email_is_lowercased(users_db_path):
    init_schema()
    create_user("Alice@Example.COM", "hash")
    row = get_user_by_email("alice@example.com")
    assert row is not None
    row_upper = get_user_by_email("ALICE@example.com")
    assert row_upper is not None
    assert row["id"] == row_upper["id"]


def test_duplicate_email_raises(users_db_path):
    init_schema()
    create_user("alice@example.com", "hash")
    with pytest.raises(Exception):
        create_user("alice@example.com", "autre")


def test_get_user_by_id(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    row = get_user_by_id(uid)
    assert row["email"] == "a@b.c"
    assert get_user_by_id(999999) is None


def test_set_email_verified(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    assert get_user_by_id(uid)["email_verified"] == 0
    set_email_verified(uid)
    assert get_user_by_id(uid)["email_verified"] == 1


def test_update_password_hash(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "old")
    update_password_hash(uid, "new")
    assert get_user_by_id(uid)["password_hash"] == "new"


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_email_verification_token_roundtrip(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("hashed-token", uid, _future(24))
    row = find_email_verification_token("hashed-token")
    assert row is not None
    assert row["user_id"] == uid


def test_password_reset_token_roundtrip(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_password_reset_token("reset-hash", uid, _future(1))
    row = find_password_reset_token("reset-hash")
    assert row is not None
    assert row["user_id"] == uid


def test_delete_tokens_for_user(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("t1", uid, _future(1))
    create_email_verification_token("t2", uid, _future(1))
    delete_email_verification_tokens_for_user(uid)
    assert find_email_verification_token("t1") is None
    assert find_email_verification_token("t2") is None


def test_delete_password_reset_tokens_for_user(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_password_reset_token("r1", uid, _future(1))
    delete_password_reset_tokens_for_user(uid)
    assert find_password_reset_token("r1") is None


def test_purge_expired_tokens(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("live", uid, _future(1))
    create_email_verification_token("expired", uid, _past(1))
    create_password_reset_token("live-r", uid, _future(1))
    create_password_reset_token("expired-r", uid, _past(1))
    purge_expired_tokens()
    assert find_email_verification_token("live") is not None
    assert find_email_verification_token("expired") is None
    assert find_password_reset_token("live-r") is not None
    assert find_password_reset_token("expired-r") is None


def test_cascade_delete_on_user_delete(users_db_path):
    from src.migrations import apply_pending

    init_schema()
    # En production, apply_pending() tourne toujours au démarrage avant tout
    # appel à delete_user (celui-ci nettoie aussi user_preferences et
    # observatoire_card_order, créées par les migrations 0015/0016).
    apply_pending()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("t", uid, _future(1))
    delete_user(uid)
    assert find_email_verification_token("t") is None


def test_delete_user_supprime_les_preferences_orphelines(users_db_path):
    """`user_preferences` (thème #118) n'a pas de FK ON DELETE CASCADE vers
    `users` : `delete_user` doit nettoyer la ligne explicitement."""
    from src.migrations import apply_pending
    from src.theme import SOMBRE, get_theme, save_theme

    init_schema()
    apply_pending()
    uid = create_user("a@b.c", "h")

    save_theme(uid, SOMBRE)
    assert get_theme(uid) == SOMBRE  # ancre positive : la ligne existe bien

    delete_user(uid)

    row = (
        get_conn()
        .execute("SELECT 1 FROM user_preferences WHERE user_id = ?", (uid,))
        .fetchone()
    )
    assert row is None


def test_delete_user_supprime_l_ordre_des_cards_observatoire_orphelin(
    users_db_path,
):
    """`observatoire_card_order` (#107) n'a pas non plus de FK cascade :
    même nettoyage explicite que `user_preferences`."""
    from src.migrations import apply_pending
    from src.observatoire_order import get_card_order, save_card_order

    init_schema()
    apply_pending()
    uid = create_user("a@b.c", "h")

    save_card_order(uid, ["resume", "distance"])
    assert get_card_order(uid) == ["resume", "distance"]  # ancre positive

    delete_user(uid)

    row = (
        get_conn()
        .execute("SELECT 1 FROM observatoire_card_order WHERE user_id = ?", (uid,))
        .fetchone()
    )
    assert row is None


def test_pending_email_column_exists(users_db_path):
    from src.auth import db

    db.init_schema()
    cols = {r["name"] for r in db.get_conn().execute("PRAGMA table_info(users)")}
    assert "pending_email" in cols


def test_set_and_promote_pending_email(users_db_path):
    from werkzeug.security import generate_password_hash

    from src.auth import db

    db.init_schema()
    uid = db.create_user("old@example.fr", generate_password_hash("password12"))
    db.set_pending_email(uid, "new@example.fr")
    assert db.get_user_by_id(uid)["pending_email"] == "new@example.fr"

    promoted = db.promote_pending_email(uid)
    assert promoted == "new@example.fr"
    row = db.get_user_by_id(uid)
    assert row["email"] == "new@example.fr"
    assert row["pending_email"] is None
    assert row["email_verified"] == 1


def test_promote_pending_email_noop_when_empty(users_db_path):
    from werkzeug.security import generate_password_hash

    from src.auth import db

    db.init_schema()
    uid = db.create_user("a@b.c", generate_password_hash("password12"))
    assert db.promote_pending_email(uid) is None
    assert db.get_user_by_id(uid)["email"] == "a@b.c"


def test_list_users_orders_by_created_at_desc(users_db_path):
    from src.auth import db

    db.init_schema()
    db.create_user("first@ex.fr", "hash")
    db.create_user("second@ex.fr", "hash")

    rows = db.list_users()

    assert [r["email"] for r in rows] == ["second@ex.fr", "first@ex.fr"]


def test_list_users_respects_limit(users_db_path):
    from src.auth import db

    db.init_schema()
    for i in range(3):
        db.create_user(f"user{i}@ex.fr", "hash")

    rows = db.list_users(limit=2)

    assert len(rows) == 2
