import sqlite3
from dataclasses import dataclass
from typing import Callable

from src.auth.db import get_conn
from src.subscriptions.db import SUBSCRIPTION_STATUSES
from src.subscriptions.plans import PLANS


@dataclass(frozen=True)
class TableConfig:
    columns: list[str]
    editable_columns: frozenset[str]
    pk: str
    column_types: dict[str, type]
    dropdowns: dict[str, list[str]]
    target_user_id: Callable[[dict], int | None]
    sort_by: str
    join_user_email: bool = False
    row_limit: int | None = None


# Plafond appliqué aux seules tables auto-découvertes : `mcp_usage` grossit de
# plusieurs centaines de lignes par jour et serait envoyée entière au navigateur.
AUTO_ROW_LIMIT = 2000

# Une colonne dont le nom contient l'un de ces motifs est exclue de la liste
# `columns`, donc du SELECT : le secret ne quitte jamais le serveur.
SECRET_PATTERNS = ("hash", "token", "secret", "password", "challenge", "_enc")

# Exceptions au filtre ci-dessus : clés étrangères, pas des secrets.
SAFE_COLUMNS = frozenset({"token_id"})

# Première colonne trouvée dans cet ordre → tri par défaut d'une table auto.
SORT_PREFERENCE = ("updated_at", "created_at", "applied_at", "issued_at", "expires_at")


# TABLES ne décrit plus que les tables aux réglages particuliers (colonnes
# éditables, menus déroulants, jointure sur l'email). Toutes les autres sont
# découvertes et exposées en lecture seule par all_tables().
TABLES: dict[str, TableConfig] = {
    "users": TableConfig(
        columns=[
            "id",
            "email",
            "email_verified",
            "siret",
            "pending_email",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"email", "email_verified", "siret", "pending_email"}
        ),
        pk="id",
        column_types={
            "email": str,
            "email_verified": int,
            "siret": str,
            "pending_email": str,
        },
        dropdowns={"email_verified": ["0", "1"]},
        target_user_id=lambda row: row["id"],
        sort_by="updated_at",
    ),
    "subscriptions": TableConfig(
        columns=[
            "id",
            "user_id",
            "email",
            "frisbii_customer_handle",
            "frisbii_subscription_handle",
            "plan",
            "prix_ht",
            "status",
            "current_period_end",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset({"plan", "prix_ht", "status", "current_period_end"}),
        pk="id",
        column_types={
            "plan": str,
            "prix_ht": float,
            "status": str,
            "current_period_end": str,
        },
        dropdowns={
            "status": list(SUBSCRIPTION_STATUSES),
            "plan": list(PLANS.keys()),
        },
        target_user_id=lambda row: row["user_id"],
        sort_by="updated_at",
        join_user_email=True,
    ),
    "subscriber_state": TableConfig(
        columns=[
            "user_id",
            "email",
            "trial_ends_at",
            "votes_balance",
            "votes_last_credited_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"trial_ends_at", "votes_balance", "votes_last_credited_at"}
        ),
        pk="user_id",
        column_types={
            "trial_ends_at": str,
            "votes_balance": int,
            "votes_last_credited_at": str,
        },
        dropdowns={},
        target_user_id=lambda row: row["user_id"],
        sort_by="updated_at",
        join_user_email=True,
    ),
    "admin_actions": TableConfig(
        columns=[
            "id",
            "admin_email",
            "action",
            "target_user_id",
            "details",
            "created_at",
        ],
        editable_columns=frozenset(),
        pk="id",
        column_types={},
        dropdowns={},
        target_user_id=lambda row: None,
        sort_by="created_at",
    ),
}


def _is_secret(column: str) -> bool:
    col = column.lower()
    if col in SAFE_COLUMNS:
        return False
    return any(pattern in col for pattern in SECRET_PATTERNS)


def _discover_tables() -> list[str]:
    rows = get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in rows]


def _table_columns(table: str) -> list[str]:
    return [row[1] for row in get_conn().execute(f"PRAGMA table_info({table})")]


def _auto_config(table: str) -> TableConfig | None:
    """Config lecture seule d'une table non déclarée. None si rien à afficher."""
    columns = [col for col in _table_columns(table) if not _is_secret(col)]
    if not columns:
        return None
    sort_by = next((col for col in SORT_PREFERENCE if col in columns), columns[0])
    return TableConfig(
        columns=columns,
        editable_columns=frozenset(),
        pk=columns[0],
        column_types={},
        dropdowns={},
        target_user_id=lambda row: row.get("user_id"),
        sort_by=sort_by,
        row_limit=AUTO_ROW_LIMIT,
    )


def all_tables() -> dict[str, TableConfig]:
    """Tables déclarées dans TABLES + toutes celles présentes en base."""
    configs = {}
    for table in _discover_tables():
        cfg = TABLES.get(table) or _auto_config(table)
        if cfg is not None:
            configs[table] = cfg
    return configs


def get_rows(table: str) -> list[dict]:
    cfg = all_tables()[table]
    if cfg.join_user_email:
        real_cols = [col for col in cfg.columns if col != "email"]
        cols_sql = ", ".join(f"{table}.{col}" for col in real_cols)
        query = (
            f"SELECT {cols_sql}, users.email AS email FROM {table} "
            f"LEFT JOIN users ON users.id = {table}.user_id "
            f"ORDER BY {table}.{cfg.sort_by} DESC"
        )
    else:
        cols_sql = ", ".join(cfg.columns)
        query = f"SELECT {cols_sql} FROM {table} ORDER BY {cfg.sort_by} DESC"
    if cfg.row_limit is not None:
        query += f" LIMIT {cfg.row_limit}"
    rows = get_conn().execute(query).fetchall()
    return [dict(row) for row in rows]


def _coerce_value(table: str, column: str, value):
    cfg = all_tables()[table]
    if column not in cfg.editable_columns:
        raise ValueError(f"Colonne non éditable : {column}")
    if column in cfg.dropdowns and str(value) not in cfg.dropdowns[column]:
        raise ValueError(f"Valeur non autorisée pour {column} : {value!r}")
    expected_type = cfg.column_types[column]
    try:
        if expected_type is int:
            return int(value)
        if expected_type is float:
            return float(value)
        return str(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valeur invalide pour {column} : {value!r}") from exc


def set_cell(table: str, pk_value, column: str, value) -> None:
    configs = all_tables()
    if table not in configs:
        raise ValueError(f"Table inconnue : {table}")
    cfg = configs[table]
    coerced = _coerce_value(table, column, value)
    try:
        cursor = get_conn().execute(
            f"UPDATE {table} SET {column} = ? WHERE {cfg.pk} = ?", (coerced, pk_value)
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"Écriture refusée pour {column} (contrainte violée) : {value!r}"
        ) from exc
    if cursor.rowcount == 0:
        raise ValueError(
            f"Ligne introuvable (table={table}, {cfg.pk}={pk_value!r}) — "
            "probablement supprimée entre-temps."
        )
