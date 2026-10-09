from dataclasses import dataclass
from datetime import date, datetime

import polars as pl

from src.utils.text_normalization import normalized_target, normalized_term

OPERATORS = {
    "exact",
    "contains",
    "notcontains",
    "startswith",
    "differs",
    "less",
    "greater",
    "strictly_less",
    "strictly_greater",
    "in",
    "notin",
    "isnull",
    "isnotnull",
    "sort",
}

RESERVED_PARAMS = {"page", "page_size", "columns", "count_results"}

AGGREGATORS = {"groupby", "count", "sum", "avg", "min", "max"}
AGG_SQL = {"count": "COUNT", "sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}


@dataclass
class AggregationSpec:
    select_sql: str
    group_by_sql: str | None


def parse_aggregators(
    args: list[tuple[str, str]], schema: pl.Schema
) -> "AggregationSpec | None":
    """Détecte les drapeaux d'agrégation (`col__groupby`, `col__count`, ...).

    Retourne None si aucun agrégateur. Sinon, construit les fragments SQL
    `select_sql` et `group_by_sql` (noms de colonnes validés contre le schéma).
    """
    group_cols: list[str] = []
    aggregates: list[tuple[str, str]] = []  # (operator, column)
    has_agg = False

    for key, _ in args:
        parsed = _split_key(key)
        if not parsed:
            continue
        col, op = parsed
        if op not in AGGREGATORS:
            continue
        has_agg = True
        if col not in schema:
            raise FilterError(f"Colonne inconnue : {col!r}", field=key)
        if op == "groupby":
            group_cols.append(col)
        else:
            aggregates.append((op, col))

    if not has_agg:
        return None

    select_parts = [f'"{c}"' for c in group_cols]
    for op, col in aggregates:
        select_parts.append(f'{AGG_SQL[op]}("{col}") AS "{col}__{op}"')

    group_by_sql = ", ".join(f'"{c}"' for c in group_cols) if group_cols else None
    return AggregationSpec(
        select_sql=", ".join(select_parts), group_by_sql=group_by_sql
    )


class FilterError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def _coerce(value: str, dtype: pl.DataType, key: str):
    if dtype == pl.String:
        return value
    if dtype.is_integer():
        try:
            return int(value)
        except ValueError:
            raise FilterError(f"Valeur entière attendue, reçu {value!r}", field=key)
    if dtype.is_float():
        try:
            return float(value)
        except ValueError:
            raise FilterError(f"Valeur décimale attendue, reçu {value!r}", field=key)
    if dtype == pl.Date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise FilterError(
                f"Date ISO 8601 attendue (YYYY-MM-DD), reçu {value!r}", field=key
            )
    if dtype == pl.Datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise FilterError(f"Datetime ISO 8601 attendu, reçu {value!r}", field=key)
    return value


def _split_key(key: str) -> tuple[str, str] | None:
    if "__" not in key:
        return None
    col, _, op = key.rpartition("__")
    if not col or not op:
        return None
    return col, op


def build_where(
    args: list[tuple[str, str]], schema: pl.Schema
) -> tuple[str, list, str | None]:
    """Parse query params into (where_sql, params, order_by_sql).

    args: list of (key, value) tuples preserving URL order (Werkzeug MultiDict
    preserves insertion order on `request.args.items(multi=True)`).
    """
    where_parts: list[str] = []
    params: list = []
    order_parts: list[str] = []

    for key, value in args:
        if key in RESERVED_PARAMS:
            continue

        parsed = _split_key(key)
        if not parsed:
            raise FilterError(f"Paramètre non reconnu : {key}", field=key)
        col, op = parsed

        if op in AGGREGATORS:
            continue

        if op not in OPERATORS:
            raise FilterError(f"Opérateur inconnu : __{op}", field=key)

        if col not in schema:
            raise FilterError(f"Colonne inconnue : {col!r}", field=key)

        if op == "sort":
            direction = value.lower()
            if direction not in ("asc", "desc"):
                raise FilterError(
                    f"Tri attendu 'asc' ou 'desc', reçu {value!r}", field=key
                )
            order_parts.append(f'"{col}" {direction.upper()}')
            continue

        if op in ("isnull", "isnotnull"):
            sql = "IS NULL" if op == "isnull" else "IS NOT NULL"
            where_parts.append(f'"{col}" {sql}')
            continue

        dtype = schema[col]

        if op in ("in", "notin"):
            values = [_coerce(v.strip(), dtype, key) for v in value.split(",")]
            placeholders = ",".join(["?"] * len(values))
            sql_op = "IN" if op == "in" else "NOT IN"
            where_parts.append(f'"{col}" {sql_op} ({placeholders})')
            params.extend(values)
            continue

        v = _coerce(value, dtype, key)
        # Colonne comparée par contains/notcontains/startswith : la colonne
        # précalculée pour les colonnes normalisées (#147), sinon la colonne.
        text_target = normalized_target(col, f'"{col}"')

        op_sql = {
            "exact": "=",
            "less": "<=",
            "greater": ">=",
            "strictly_less": "<",
            "strictly_greater": ">",
        }
        if op in op_sql:
            where_parts.append(f'"{col}" {op_sql[op]} ?')
            params.append(v)
        elif op == "contains":
            where_parts.append(f"{text_target} ILIKE ?")
            params.append(f"%{normalized_term(col, v)}%")
        elif op == "notcontains":
            where_parts.append(f"{text_target} NOT ILIKE ?")
            params.append(f"%{normalized_term(col, v)}%")
        elif op == "startswith":
            where_parts.append(f"{text_target} ILIKE ?")
            params.append(f"{normalized_term(col, v)}%")
        elif op == "differs":
            where_parts.append(f'"{col}" IS DISTINCT FROM ?')
            params.append(v)

    where_sql = " AND ".join(where_parts) if where_parts else "TRUE"
    order_sql = ", ".join(order_parts) if order_parts else None
    return where_sql, params, order_sql
