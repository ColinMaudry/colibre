"""Tests des migrations de schéma SQLite (src/migrations.py)."""

import os
import sqlite3

import pytest


@pytest.fixture
def users_db_path() -> str:
    """Chemin de la base users jetable posée par conftest via USERS_DB_PATH.

    conftest recopie `tests/users.test.sqlite` vers `tests/users.runtime.sqlite`
    et pointe USERS_DB_PATH dessus ; c'est cette base que `src.auth.db.get_conn`
    ouvre. On la relit ici en lecture seule pour inspecter le schéma.
    """
    return os.environ["USERS_DB_PATH"]


def test_migration_0015_creates_observatoire_card_order(users_db_path):
    from src.migrations import apply_pending

    apply_pending()

    conn = sqlite3.connect(users_db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "observatoire_card_order" in tables

        cols = [
            row[1] for row in conn.execute("PRAGMA table_info(observatoire_card_order)")
        ]
        assert cols == ["user_id", "card_order", "updated_at"]
    finally:
        conn.close()


def test_migration_0015_is_idempotent(users_db_path):
    from src.migrations import apply_pending

    apply_pending()
    apply_pending()  # ne doit pas lever


def test_migration_0016_creates_user_preferences(users_db_path):
    from src.migrations import apply_pending

    apply_pending()

    conn = sqlite3.connect(users_db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "user_preferences" in tables

        cols = [row[1] for row in conn.execute("PRAGMA table_info(user_preferences)")]
        assert cols == ["user_id", "theme", "updated_at"]
    finally:
        conn.close()


def test_migration_0016_is_idempotent(users_db_path):
    from src.migrations import apply_pending

    apply_pending()
    apply_pending()  # ne doit pas lever
