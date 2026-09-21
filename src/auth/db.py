import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import local

_local = local()

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    pending_email TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oauth_identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, subject),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _db_path() -> Path:
    return Path(os.getenv("USERS_DB_PATH", "users.sqlite"))


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_db_path()), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


def reset_conn_for_tests() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(USERS_SCHEMA)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
    if "pending_email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pending_email TEXT")
        cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
    if cols.get("password_hash") and cols["password_hash"]["notnull"] == 1:
        _rebuild_users_password_nullable(conn)


def _rebuild_users_password_nullable(conn: sqlite3.Connection) -> None:
    # SQLite ne peut pas retirer un NOT NULL via ALTER : on reconstruit la table.
    # foreign_keys OFF pour éviter le cascade-delete pendant le DROP.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                pending_email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO users_new (id, email, password_hash, email_verified, "
            "pending_email, created_at, updated_at) "
            "SELECT id, email, password_hash, email_verified, pending_email, "
            "created_at, updated_at FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password_hash: str) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, email_verified, created_at, updated_at) "
        "VALUES (?, ?, 0, ?, ?)",
        (email.lower(), password_hash, now, now),
    )
    return cur.lastrowid


def get_user_by_email(email: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        .fetchone()
    )


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users(limit: int = 1000) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
        .fetchall()
    )


def set_email_verified(user_id: int) -> None:
    get_conn().execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (_now(), user_id),
    )


def update_password_hash(user_id: int, password_hash: str) -> None:
    get_conn().execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (password_hash, _now(), user_id),
    )


def get_siret(user_id: int) -> str | None:
    row = (
        get_conn()
        .execute("SELECT siret FROM users WHERE id = ?", (user_id,))
        .fetchone()
    )
    return row["siret"] if row else None


def set_siret(user_id: int, siret: str) -> None:
    get_conn().execute(
        "UPDATE users SET siret = ?, updated_at = ? WHERE id = ?",
        (siret, _now(), user_id),
    )


def set_pending_email(user_id: int, email: str) -> None:
    get_conn().execute(
        "UPDATE users SET pending_email = ?, updated_at = ? WHERE id = ?",
        (email.lower(), _now(), user_id),
    )


def promote_pending_email(user_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT pending_email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None or not row["pending_email"]:
        return None
    new_email = row["pending_email"]
    conn.execute(
        "UPDATE users SET email = ?, pending_email = NULL, "
        "email_verified = 1, updated_at = ? WHERE id = ?",
        (new_email, _now(), user_id),
    )
    return new_email


def delete_user(user_id: int) -> None:
    conn = get_conn()
    # `user_preferences` (thème, migration 0016) et `observatoire_card_order`
    # (migration 0015) n'ont pas de FOREIGN KEY ... ON DELETE CASCADE vers
    # `users` (contrairement aux tables de tokens) : sans ce nettoyage
    # explicite, ces lignes restent orphelines après suppression du compte.
    conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM observatoire_card_order WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_email_verification_token(
    token_hash: str, user_id: int, expires_at: str
) -> None:
    get_conn().execute(
        "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (token_hash, user_id, expires_at, _now()),
    )


def find_email_verification_token(token_hash: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM email_verification_tokens "
            "WHERE token_hash = ? AND expires_at > ?",
            (token_hash, _now()),
        )
        .fetchone()
    )


def delete_email_verification_tokens_for_user(user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,)
    )


def create_password_reset_token(token_hash: str, user_id: int, expires_at: str) -> None:
    get_conn().execute(
        "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (token_hash, user_id, expires_at, _now()),
    )


def find_password_reset_token(token_hash: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM password_reset_tokens "
            "WHERE token_hash = ? AND expires_at > ?",
            (token_hash, _now()),
        )
        .fetchone()
    )


def delete_password_reset_tokens_for_user(user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,)
    )


def purge_expired_tokens() -> None:
    now = _now()
    conn = get_conn()
    conn.execute("DELETE FROM email_verification_tokens WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM password_reset_tokens WHERE expires_at <= ?", (now,))


def create_oauth_user(email: str) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, email_verified, created_at, updated_at) "
        "VALUES (?, NULL, 1, ?, ?)",
        (email.lower(), now, now),
    )
    return cur.lastrowid


def get_oauth_identity(provider: str, subject: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM oauth_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        )
        .fetchone()
    )


def link_oauth_identity(provider: str, subject: str, user_id: int) -> None:
    get_conn().execute(
        "INSERT INTO oauth_identities (provider, subject, user_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (provider, subject, user_id, _now()),
    )
