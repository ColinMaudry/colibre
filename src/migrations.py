"""
Migrations de schéma SQLite.

Ajouter une migration : append un tuple (id, migration) à _MIGRATIONS, où
migration est soit une requête SQL, soit une fonction Python (conn) -> None
(réécriture de données). La fonction est exécutée entre BEGIN et COMMIT avec
l'enregistrement de son id ; elle doit tolérer une table absente (base
fraîche : les init_schema des modules tournent après).
L'id doit être unique et croissant (convention : NNNN_description).
apply_pending() est idempotent ; elle peut être appelée à chaque démarrage.
"""

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from src.auth.db import get_conn

_OPERATEURS_TEXTE = ("contains", "notContains")


def _plus_vers_guillemets(valeur: str) -> str:
    """Réécrit les mots `a+b` en phrases `"a b"` (le `+` est désormais littéral).

    Un mot qui commence ou finit par `*` (le `+` y était déjà littéral) ou qui
    contient déjà `"` est laissé tel quel.
    """
    mots = []
    for mot in valeur.split():
        if (
            "+" in mot
            and not mot.startswith("*")
            and not mot.endswith("*")
            and '"' not in mot
        ):
            mot = '"' + mot.replace("+", " ") + '"'
        mots.append(mot)
    return " ".join(mots)


def _reecrire_noeud(noeud) -> None:
    """Parcourt récursivement un AST de filtres et réécrit les valeurs texte."""
    if not isinstance(noeud, dict):
        return
    if noeud.get("t") == "cond":
        valeur = noeud.get("value")
        if noeud.get("operator") in _OPERATEURS_TEXTE and isinstance(valeur, str):
            noeud["value"] = _plus_vers_guillemets(valeur)
        return
    for enfant in noeud.get("children") or []:
        _reecrire_noeud(enfant)
    _reecrire_noeud(noeud.get("child"))


def _migrer_vues_plus(conn: sqlite3.Connection) -> None:
    """Migration 0017 : les filtres texte des vues sauvegardées passent de
    `a+b` à `"a b"`. Les vues sans AST JSON (anciennes vues) sont ignorées."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'saved_views'"
    ).fetchone()
    if table is None:
        return
    for view_id, query in conn.execute("SELECT id, query FROM saved_views").fetchall():
        try:
            donnees = json.loads(query)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(donnees, dict) or "ast" not in donnees:
            continue
        _reecrire_noeud(donnees["ast"])
        nouvelle = json.dumps(donnees)
        if nouvelle != query:
            conn.execute(
                "UPDATE saved_views SET query = ? WHERE id = ?", (nouvelle, view_id)
            )


_MIGRATIONS: list[tuple[str, str | Callable[[sqlite3.Connection], None]]] = [
    (
        "0001_add_prix_ht_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN prix_ht REAL",
    ),
    (
        "0002_add_siret_to_users",
        "ALTER TABLE users ADD COLUMN siret TEXT",
    ),
    (
        "0003_add_votes_balance_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_balance INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "0004_add_votes_last_credited_at_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_last_credited_at TEXT",
    ),
    (
        "0005_rename_votes_credited_until_to_votes_last_credited_at",
        "ALTER TABLE subscriptions RENAME COLUMN votes_credited_until TO votes_last_credited_at",
    ),
    (
        "0006_create_admin_actions",
        "CREATE TABLE IF NOT EXISTS admin_actions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "admin_email TEXT NOT NULL, "
        "action TEXT NOT NULL, "
        "target_user_id INTEGER, "
        "details TEXT, "
        "created_at TEXT NOT NULL)",
    ),
    (
        "0007_add_kind_to_api_tokens",
        "ALTER TABLE api_tokens ADD COLUMN kind TEXT NOT NULL DEFAULT 'api'",
    ),
    (
        "0008_create_oauth_clients",
        "CREATE TABLE IF NOT EXISTS oauth_clients ("
        "client_id TEXT PRIMARY KEY, client_metadata TEXT NOT NULL, "
        "created_at TEXT NOT NULL)",
    ),
    (
        "0009_create_oauth_codes",
        "CREATE TABLE IF NOT EXISTS oauth_codes ("
        "code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_id INTEGER NOT NULL, "
        "redirect_uri TEXT, code_challenge TEXT, code_challenge_method TEXT, "
        "scope TEXT, resource TEXT, expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)",
    ),
    (
        "0010_create_oauth_tokens",
        "CREATE TABLE IF NOT EXISTS oauth_tokens ("
        "id INTEGER PRIMARY KEY, access_token_hash TEXT NOT NULL UNIQUE, "
        "refresh_token_hash TEXT UNIQUE, client_id TEXT NOT NULL, user_id INTEGER NOT NULL, "
        "scope TEXT, resource TEXT NOT NULL, issued_at TEXT NOT NULL, "
        "access_expires_at TEXT NOT NULL, refresh_expires_at TEXT, revoked_at TEXT, "
        "count_total INTEGER NOT NULL DEFAULT 0, last_used_at TEXT)",
    ),
    (
        "0011_create_mcp_usage",
        "CREATE TABLE IF NOT EXISTS mcp_usage ("
        "id INTEGER PRIMARY KEY, user_id INTEGER, token_id INTEGER, "
        "kind TEXT NOT NULL, created_at TEXT NOT NULL)",
    ),
    (
        "0012_add_token_to_saved_views",
        "ALTER TABLE saved_views ADD COLUMN token TEXT",
    ),
    (
        "0013_add_token_enc_to_api_tokens",
        "ALTER TABLE api_tokens ADD COLUMN token_enc TEXT",
    ),
    (
        "0014_add_trial_ends_at_to_subscriber_state",
        "ALTER TABLE subscriber_state ADD COLUMN trial_ends_at TEXT",
    ),
    (
        "0015_create_observatoire_card_order",
        "CREATE TABLE IF NOT EXISTS observatoire_card_order ("
        "user_id INTEGER PRIMARY KEY, "
        "card_order TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)",
    ),
    (
        "0016_create_user_preferences",
        "CREATE TABLE IF NOT EXISTS user_preferences ("
        "user_id INTEGER PRIMARY KEY, "
        "theme TEXT NOT NULL DEFAULT 'clair', "
        "updated_at TEXT NOT NULL)",
    ),
    ("0017_saved_views_plus_vers_guillemets", _migrer_vues_plus),
]


def apply_pending() -> None:
    conn = get_conn()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        row[0] for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
    }
    now = datetime.now(timezone.utc).isoformat()
    for migration_id, migration in _MIGRATIONS:
        if migration_id in applied:
            continue
        if callable(migration):
            # get_conn est en autocommit : transaction explicite pour que la
            # réécriture et son enregistrement soient atomiques.
            conn.execute("BEGIN")
            try:
                migration(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                    (migration_id, now),
                )
                conn.execute("COMMIT")
            except BaseException:
                # Une migration qui a clos sa propre transaction ne doit pas
                # masquer l'erreur d'origine sous un ROLLBACK invalide.
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            continue
        try:
            conn.execute(migration)
        except sqlite3.OperationalError as exc:
            # Sur une DB fraîche (schéma déjà à jour), certaines migrations
            # sont sans effet : ADD COLUMN → "duplicate column name",
            # RENAME COLUMN → "no such column", et un ALTER sur une table pas
            # encore créée → "no such table" (elle sera créée plus tard par
            # init_schema avec la colonne déjà dans SCHEMA).
            err = str(exc)
            if (
                "duplicate column name" not in err
                and "no such column" not in err
                and "no such table" not in err
            ):
                raise
        conn.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, now),
        )
    conn.commit()
