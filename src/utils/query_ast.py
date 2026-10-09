"""Représentation canonique d'un filtre (AST booléen) et compilation en SQL DuckDB.

Ce module est indépendant de l'UI : plusieurs producteurs (filtres de colonne
AG Grid, futur champ de requête booléenne #97) construisent le même AST, compilé
ici en SQL paramétré. Les identifiants de colonnes sont validés contre le schéma ;
les valeurs passent toujours par le binding `?` (jamais concaténées).
"""

from dataclasses import dataclass

import polars as pl

from src.utils import logger
from src.utils.table_sql import (
    normalize_text_term,
    sort_by_to_sql,
    text_filter_target,
    tokenize_text_filter,
)


@dataclass
class Condition:
    column: str
    operator: str
    value: object = None
    value2: object = None


@dataclass
class And:
    children: list


@dataclass
class Or:
    children: list


@dataclass
class Not:
    child: object


Node = object  # Condition | And | Or | Not | None


def ast_to_sql(node, schema: pl.Schema) -> tuple[str, list]:
    """Compile un AST en (where_sql, params). Nœud neutre -> ('TRUE', [])."""
    if node is None:
        return "TRUE", []
    if isinstance(node, And):
        return _join(node.children, "AND", schema)
    if isinstance(node, Or):
        return _join(node.children, "OR", schema)
    if isinstance(node, Not):
        sql, params = ast_to_sql(node.child, schema)
        if sql == "TRUE":
            return "TRUE", []
        return f"NOT ({sql})", params
    if isinstance(node, Condition):
        return _condition_to_sql(node, schema)
    logger.warning(f"Nœud AST inconnu ignoré : {node!r}")
    return "TRUE", []


def _join(children, op: str, schema: pl.Schema) -> tuple[str, list]:
    fragments: list[str] = []
    params: list = []
    for child in children:
        sql, child_params = ast_to_sql(child, schema)
        if sql == "TRUE":
            continue
        fragments.append(f"({sql})")
        params.extend(child_params)
    if not fragments:
        return "TRUE", []
    return f" {op} ".join(fragments), params


def _condition_to_sql(cond: Condition, schema: pl.Schema) -> tuple[str, list]:
    col = cond.column
    if col not in schema.names():
        logger.warning(f"Colonne inconnue ignorée : {col!r}")
        return "TRUE", []

    col_type = schema[col]
    quoted = f'"{col}"'

    is_numeric = col_type.is_numeric()
    col_is_date = col_type == pl.Date

    if cond.operator == "blank":
        if is_numeric or col_is_date:
            return f"{quoted} IS NULL", []
        return f"({quoted} IS NULL OR {quoted} = '')", []
    if cond.operator == "notBlank":
        if is_numeric or col_is_date:
            return f"{quoted} IS NOT NULL", []
        return f"({quoted} IS NOT NULL AND {quoted} <> '')", []

    if is_numeric:
        return _numeric_to_sql(cond, col_type, quoted)

    # texte / date : traité comme texte (parité avec l'existant)
    if cond.operator == "contains":
        return tokenize_text_filter(col, str(cond.value), col_is_date)
    if cond.operator == "notContains":
        where, params = tokenize_text_filter(col, str(cond.value), col_is_date)
        return f"NOT ({where})", params

    target = f"CAST({quoted} AS VARCHAR)" if col_is_date else quoted
    op_map = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if cond.operator in op_map:
        return f"{quoted} IS NOT NULL AND {target} {op_map[cond.operator]} ?", [
            str(cond.value)
        ]
    if cond.operator == "range":
        return f"{quoted} IS NOT NULL AND {target} BETWEEN ? AND ?", [
            str(cond.value),
            str(cond.value2),
        ]
    if cond.operator == "startsWith":
        value = normalize_text_term(col, str(cond.value))
        return f"{text_filter_target(col, quoted)} ILIKE ?", [f"{value}%"]
    if cond.operator == "endsWith":
        value = normalize_text_term(col, str(cond.value))
        return f"{text_filter_target(col, quoted)} ILIKE ?", [f"%{value}"]
    logger.warning(f"Opérateur texte invalide : {cond.operator!r}")
    return "TRUE", []


def _coerce_number(value, col_type):
    try:
        return int(value) if col_type.is_integer() else float(value)
    except (TypeError, ValueError):
        logger.warning(f"Valeur numérique invalide ignorée : {value!r}")
        return None


def _numeric_to_sql(cond: Condition, col_type, quoted: str) -> tuple[str, list]:
    op_map = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if cond.operator in op_map:
        v = _coerce_number(cond.value, col_type)
        if v is None:
            return "TRUE", []
        return f"{quoted} IS NOT NULL AND {quoted} {op_map[cond.operator]} ?", [v]
    if cond.operator == "range":
        v1 = _coerce_number(cond.value, col_type)
        v2 = _coerce_number(cond.value2, col_type)
        if v1 is None or v2 is None:
            return "TRUE", []
        return f"{quoted} BETWEEN ? AND ?", [v1, v2]
    logger.warning(f"Opérateur numérique invalide : {cond.operator!r}")
    return "TRUE", []


_TEXT_TYPE = {
    "contains": "contains",
    "notContains": "notContains",
    "equals": "eq",
    "notEqual": "neq",
    "startsWith": "startsWith",
    "endsWith": "endsWith",
    "blank": "blank",
    "notBlank": "notBlank",
}
_NUM_TYPE = {
    "equals": "eq",
    "notEqual": "neq",
    "lessThan": "lt",
    "lessThanOrEqual": "lte",
    "greaterThan": "gt",
    "greaterThanOrEqual": "gte",
    "inRange": "range",
    "blank": "blank",
    "notBlank": "notBlank",
}


def _leaf(column: str, spec: dict):
    """Convertit une condition AG Grid unitaire en Condition."""
    ftype = spec.get("filterType", "text")
    ag_type = spec.get("type")
    if ftype == "date":
        op = _NUM_TYPE.get(ag_type)
        if op == "range":
            return Condition(column, "range", spec.get("dateFrom"), spec.get("dateTo"))
        return Condition(column, op, spec.get("dateFrom")) if op else None
    if ftype == "number":
        op = _NUM_TYPE.get(ag_type)
        if op == "range":
            return Condition(column, "range", spec.get("filter"), spec.get("filterTo"))
        return Condition(column, op, spec.get("filter")) if op else None
    # texte
    op = _TEXT_TYPE.get(ag_type)
    return Condition(column, op, spec.get("filter")) if op else None


def filtermodel_to_ast(filter_model, schema):
    """Traduit un filterModel AG Grid en AST. Colonnes combinées en And.

    AG Grid >=29.2 (pinné à 35.2.0 ici) encode un filtre à conditions
    multiples via une liste `conditions` (N éléments, cf. `maxNumConditions`),
    et non plus via `condition1`/`condition2` (dépréciés depuis 29.2, mais
    l'API dit "still accept" ces clés en entrée — on les supporte donc aussi
    en repli, sans qu'AG Grid ne les envoie normalement).
    """
    if not filter_model:
        return None
    children = []
    for column, spec in filter_model.items():
        if column not in schema.names():
            logger.warning(f"Filtre sur colonne inconnue ignoré : {column!r}")
            continue
        if "conditions" in spec:  # forme courante AG Grid >=29.2 (N conditions)
            parts = [c for c in (_leaf(column, s) for s in spec["conditions"]) if c]
            if not parts:
                continue
            node = And(parts) if spec.get("operator") == "AND" else Or(parts)
        elif "operator" in spec:  # forme dépréciée condition1/condition2
            c1 = _leaf(column, spec.get("condition1", {}))
            c2 = _leaf(column, spec.get("condition2", {}))
            parts = [c for c in (c1, c2) if c is not None]
            if not parts:
                continue
            node = And(parts) if spec["operator"] == "AND" else Or(parts)
        else:
            node = _leaf(column, spec)
            if node is None:
                continue
        children.append(node)
    return And(children) if children else None


_TEXT_TYPE_INV = {v: k for k, v in _TEXT_TYPE.items()}
_NUM_TYPE_INV = {v: k for k, v in _NUM_TYPE.items()}


def _condition_to_filterspec(cond: Condition, schema: pl.Schema) -> dict | None:
    """Convertit une Condition en spec de filtre AG Grid unitaire (une colonne).

    Inverse de `_leaf`. Renvoie None (avec warning) si la colonne est inconnue
    ou si l'opérateur n'a pas d'équivalent AG Grid — ne devrait pas arriver
    pour un AST produit par `filtermodel_to_ast`, mais on reste défensif.
    """
    if cond.column not in schema.names():
        logger.warning(
            f"Colonne inconnue ignorée (ast_to_filtermodel) : {cond.column!r}"
        )
        return None

    col_type = schema[cond.column]
    if col_type.is_numeric():
        filter_type = "number"
    elif col_type == pl.Date:
        filter_type = "date"
    else:
        filter_type = "text"

    if filter_type in ("number", "date") and cond.operator == "range":
        if filter_type == "number":
            return {
                "filterType": "number",
                "type": "inRange",
                "filter": cond.value,
                "filterTo": cond.value2,
            }
        return {
            "filterType": "date",
            "type": "inRange",
            "dateFrom": cond.value,
            "dateTo": cond.value2,
        }

    if filter_type == "date":
        ag_type = _NUM_TYPE_INV.get(cond.operator)
        if ag_type is None:
            logger.warning(
                f"Opérateur sans équivalent AG Grid ignoré : {cond.operator!r} "
                f"(colonne {cond.column!r})"
            )
            return None
        return {"filterType": "date", "type": ag_type, "dateFrom": cond.value}

    if filter_type == "number":
        ag_type = _NUM_TYPE_INV.get(cond.operator)
        if ag_type is None:
            logger.warning(
                f"Opérateur sans équivalent AG Grid ignoré : {cond.operator!r} "
                f"(colonne {cond.column!r})"
            )
            return None
        return {"filterType": "number", "type": ag_type, "filter": cond.value}

    # texte
    ag_type = _TEXT_TYPE_INV.get(cond.operator)
    if ag_type is None:
        logger.warning(
            f"Opérateur sans équivalent AG Grid ignoré : {cond.operator!r} "
            f"(colonne {cond.column!r})"
        )
        return None
    return {"filterType": "text", "type": ag_type, "filter": cond.value}


def _child_to_filterspec(child, schema: pl.Schema):
    """Convertit un enfant du And de haut niveau en (colonne, spec filterModel).

    Ne sait inverser que les deux formes produites par `filtermodel_to_ast` :
    une Condition seule, ou un And/Or à N enfants (N = maxNumConditions)
    portant tous sur la MÊME colonne (filtre AG Grid natif multi-conditions,
    forme `conditions` — cf. AG Grid >=29.2). Toute autre forme (Not, And/Or
    imbriqué plus profondément, colonnes différentes) est ignorée avec un
    warning : un filterModel est par nature par-colonne et ne peut représenter
    une expression booléenne arbitraire (cf. #97).
    """
    if isinstance(child, Condition):
        spec = _condition_to_filterspec(child, schema)
        if spec is None:
            return None
        return child.column, spec

    if isinstance(child, (And, Or)) and len(child.children) >= 2:
        conditions = child.children
        if not all(isinstance(c, Condition) for c in conditions):
            logger.warning(
                f"Nœud AST non représentable en filterModel, ignoré : {child!r}"
            )
            return None
        columns = {c.column for c in conditions}
        if len(columns) != 1:
            logger.warning(
                f"Nœud AST non représentable en filterModel, ignoré : {child!r}"
            )
            return None
        specs = [_condition_to_filterspec(c, schema) for c in conditions]
        if any(s is None for s in specs):
            return None
        operator = "AND" if isinstance(child, And) else "OR"
        return conditions[0].column, {
            "filterType": specs[0]["filterType"],
            "operator": operator,
            "conditions": specs,
        }

    logger.warning(f"Nœud AST non représentable en filterModel, ignoré : {child!r}")
    return None


def ast_to_filtermodel(node: Node, schema: pl.Schema) -> dict:
    """Traduit un AST en filterModel AG Grid. Inverse de `filtermodel_to_ast`.

    Seules les formes que `filtermodel_to_ast` peut effectivement produire sont
    garanties d'être inversées correctement (voir `_child_to_filterspec`).
    """
    if node is None:
        return {}
    if isinstance(node, And) and not node.children:
        return {}

    # Le niveau supérieur est normalement un And multi-enfants (un enfant par
    # colonne filtrée) ; on tolère aussi un nœud "nu" (une seule colonne).
    children = node.children if isinstance(node, And) else [node]

    filter_model: dict = {}
    for child in children:
        entry = _child_to_filterspec(child, schema)
        if entry is None:
            continue
        column, spec = entry
        filter_model[column] = spec
    return filter_model


def sort_model_to_sql(sort_model: list | None, schema: pl.Schema) -> str:
    """Traduit un sortModel AG Grid en clause ORDER BY DuckDB (adapte à sort_by_to_sql)."""
    if not sort_model:
        return ""
    sort_by = [
        {"column_id": s.get("colId"), "direction": s.get("sort")} for s in sort_model
    ]
    return sort_by_to_sql(sort_by, schema)


def ast_to_dict(node: Node) -> dict | None:
    """Sérialise un AST en dict JSON-compatible (pour persistance en base)."""
    if node is None:
        return None
    if isinstance(node, Condition):
        return {
            "t": "cond",
            "column": node.column,
            "operator": node.operator,
            "value": node.value,
            "value2": node.value2,
        }
    if isinstance(node, And):
        return {"t": "and", "children": [ast_to_dict(c) for c in node.children]}
    if isinstance(node, Or):
        return {"t": "or", "children": [ast_to_dict(c) for c in node.children]}
    if isinstance(node, Not):
        return {"t": "not", "child": ast_to_dict(node.child)}
    return None


def ast_from_dict(data: dict | None) -> Node:
    """Reconstruit un AST à partir d'un dict produit par ast_to_dict."""
    if data is None:
        return None
    t = data.get("t")
    if t == "cond":
        return Condition(
            data["column"], data["operator"], data.get("value"), data.get("value2")
        )
    if t == "and":
        return And([ast_from_dict(c) for c in data["children"]])
    if t == "or":
        return Or([ast_from_dict(c) for c in data["children"]])
    if t == "not":
        return Not(ast_from_dict(data["child"]))
    return None
