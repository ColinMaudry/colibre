"""Résolution publique d'une vue depuis le paramètre d'URL ?vue=<token>_<slug>.

Fonction pure (aucune dépendance à Dash), testable directement : elle prend le
paramètre brut et le schéma, renvoie un dict décrivant la vue à appliquer ou une
erreur. Le slug est ignoré ; seul le jeton fait foi.
"""

import json

from src.saved_views import db, ui
from src.utils import logger
from src.utils.query_ast import (
    ast_from_dict,
    ast_to_dict,
    ast_to_filtermodel,
    filtermodel_to_ast,
)

NOT_FOUND_MESSAGE = "Cette vue est introuvable ou a été supprimée."


def _error() -> dict:
    return {
        "found": False,
        "filter_model": None,
        "column_state": None,
        "hidden_columns": None,
        "token": None,
        "url": None,
        "error": NOT_FOUND_MESSAGE,
    }


def resolve_vue_param(vue_param: str | None, schema) -> dict:
    token = ui.token_from_vue_param(vue_param)
    if not token:
        return _error()
    row = db.get_by_token(token)
    if row is None:
        return _error()
    try:
        view = json.loads(row["query"])
        # AST canonique stocké par save_view (cf. spec vues sauvegardées).
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Vue pré-migration (query string, pas du JSON) : repli propre, même
        # message que pour un jeton inconnu (anti-énumération).
        logger.warning(
            "Vue partagée au format pré-migration, non applicable : "
            f"token={token!r} name={row['name']!r}"
        )
        return _error()
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    return {
        "found": True,
        "filter_model": filter_model,
        "column_state": column_state,
        "hidden_columns": hidden_columns,
        "token": row["token"],
        "url": ui.build_view_url(row["name"], row["token"]),
        "error": None,
    }


def _forme_canonique(filter_model: dict | None, schema) -> dict:
    """Filtre colonne par colonne sous forme d'AST sérialisé : insensible à
    l'ordre des colonnes et aux écarts d'écriture du filterModel. Les entrées
    sans effet en SQL (colonne hors schéma, type inconnu) sont omises."""
    forme = {}
    for col, entree in (filter_model or {}).items():
        ast = filtermodel_to_ast({col: entree}, schema)
        if ast is not None:
            forme[col] = ast_to_dict(ast)
    return forme


def vue_autorise_operateurs(
    vue_resolution: dict | None, filter_model: dict | None, schema
) -> bool:
    """Vrai si `filter_model` est exactement le filtre de la vue ouverte par
    ?vue= (#97) : ses opérateurs booléens s'appliquent alors sans abonnement.

    Seul le jeton de `vue_resolution` est lu ; la vue est relue en base, son
    `filter_model` (venu du navigateur) n'est jamais utilisé."""
    if not filter_model or not vue_resolution or not vue_resolution.get("found"):
        return False
    token = vue_resolution.get("token")
    if not token:
        return False
    row = db.get_by_token(token)
    if row is None:
        return False
    try:
        ast = ast_from_dict(json.loads(row["query"]).get("ast"))
        vue = ast_to_filtermodel(ast, schema)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False
    return _forme_canonique(vue, schema) == _forme_canonique(filter_model, schema)
