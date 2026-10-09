import json
import logging
import os
from collections import OrderedDict

import httpx
import polars as pl
from httpx import HTTPError, get

from src.db import get_cursor, query_marches, schema
from src.utils import logger
from src.utils.cache import cache

logging.getLogger("httpx").setLevel("WARNING")


# Infos d'établissement quasi figées, dont la fraîcheur n'a aucun enjeu pour un
# JSON-LD : 30 jours. Un échec technique, lui, ne dit rien de durable sur le
# SIRET — d'où la seconde durée, bien plus courte.
ANNUAIRE_TTL_SUCCES = 3600 * 24 * 30
ANNUAIRE_TTL_ECHEC = 900


def get_annuaire_data(siret: str) -> dict | None:
    """Fiche établissement de l'Annuaire des entreprises, mise en cache.

    Deux durées de vie plutôt qu'un `@cache.memoize`, qui applique le même TTL
    à tout retour : une réponse valide — fiche trouvée comme SIRET inconnu —
    est une information stable, alors qu'un échec technique (429, 5xx, timeout)
    condamnerait la fiche à rester vide un mois. Le cache court protège aussi
    recherche-entreprises.api.gouv.fr (quota par IP) du crawl des 242 005
    fiches organisme : sans lui, un rate-limit serait retenté à chaque page vue.

    Les valeurs sont enveloppées dans un dict parce que `cache.get` ne
    distingue pas une clé absente d'un None mémorisé.
    """
    key = f"annuaire:{siret}"
    entree = cache.get(key)
    if entree is not None:
        return entree["data"]

    url = f"https://recherche-entreprises.api.gouv.fr/search?q={siret}"
    try:
        results = get(url).raise_for_status().json().get("results") or []
    except (HTTPError, json.JSONDecodeError) as e:
        logger.warning(f"Could not fetch data from recherche-entreprises.api: {e!r}")
        cache.set(key, {"data": None}, timeout=ANNUAIRE_TTL_ECHEC)
        return None

    data = results[0] if results else None
    cache.set(key, {"data": data}, timeout=ANNUAIRE_TTL_SUCCES)
    return data


def get_statistics() -> dict:
    return (
        get(
            "https://www.data.gouv.fr/api/1/datasets/r/0ccf4a75-f3aa-4b46-8b6a-18aeb63e36df",
            follow_redirects=True,
        )
        .raise_for_status()
        .json()
    )


def get_departements() -> dict:
    with open("data/departements.json", "rb") as f:
        data = json.load(f)
        return data


def get_departements_geojson() -> dict:
    with open("./data/departements-1000m.geojson") as f:
        geojson = json.load(f)

    # Ajout de feature.id
    for f in geojson["features"]:
        f["id"] = f["properties"]["code"]

    return geojson


def get_departement_region(code_commune: str | None):
    """Département et région à partir du code commune INSEE.

    Le code commune (et non le code postal) est utilisé car il distingue
    nativement les deux départements corses (2A/2B) : le code postal, lui,
    donne "20" pour toute la Corse et ne permet pas de choisir.
    """
    if code_commune:
        if code_commune[:2] in ("2A", "2B"):
            code_departement = code_commune[:2]
        elif code_commune > "97000":
            code_departement = code_commune[:3]
        else:
            code_departement = code_commune[:2]
        nom_departement = DEPARTEMENTS[code_departement]["departement"]
        nom_region = DEPARTEMENTS[code_departement]["region"]
        return code_departement, nom_departement, nom_region
    return "", "", ""


def _validate_schema(raw) -> dict | None:
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("fields"), list)
        and raw["fields"]
        and all(isinstance(c, dict) and "name" in c for c in raw["fields"])
    ):
        return raw
    return None


def _fetch_remote_schema(url: str | None) -> dict | None:
    if not url:
        return None
    try:
        raw = get(url, follow_redirects=True).raise_for_status().json()
    except (
        httpx.HTTPError,
        httpx.TransportError,
        httpx.TimeoutException,
        json.JSONDecodeError,
    ) as e:
        logger.error(f"Schéma distant indisponible ({url}) : {e!r}")
        return None
    return _validate_schema(raw)


def _load_schema_file(path: str) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Schéma local illisible ({path}) : {e!r}")
        return None
    return _validate_schema(raw)


def _persist_schema_cache(raw: dict, path: str) -> None:
    if not path:
        return
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(raw, f)
        os.replace(tmp, path)
    except (OSError, ValueError) as e:
        logger.warning(f"Écriture du cache schéma échouée ({path}) : {e!r}")


def get_data_schema() -> dict:
    cache_path = os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json")
    raw = _fetch_remote_schema(os.getenv("DATA_SCHEMA_PATH"))
    if raw is not None:
        _persist_schema_cache(raw, cache_path)
    else:
        raw = _load_schema_file(cache_path)
    if raw is None:
        raise RuntimeError("Aucun schéma disponible (ni distant ni cache).")
    schema = OrderedDict((c["name"], c) for c in raw["fields"])
    for col in schema.keys():
        new_obj = schema[col]
        if "enum" in new_obj:
            enums = ", ".join(new_obj["enum"])
            new_obj["description"] = (
                f"{new_obj['description']} Valeurs possibles : {enums}"
            )
    return schema


def prepare_dashboard_data(
    columns: list[str] | None = None, *, operateurs: bool, **filter_params
) -> pl.DataFrame:
    """Exécute la requête DuckDB filtrée pour le tableau de bord.

    Retourne une pl.DataFrame matérialisée uniquement pour le sous-ensemble
    correspondant aux filtres. Les appelants qui ont besoin d'une LazyFrame
    appellent `.lazy()` sur le résultat.

    `columns` restreint la projection : les cards n'exploitent que 21 des 63
    colonnes du schéma, et la table est colonnaire (cf.
    `src.figures.observatoire_cards_columns`). L'export Excel, lui, laisse
    `columns` à None puisqu'il a besoin de tout.
    """
    from src.utils.table_sql import dashboard_filters_to_sql

    where_sql, params = dashboard_filters_to_sql(**filter_params, operateurs=operateurs)
    return query_marches(where_sql=where_sql, params=params, columns=columns)


def build_org_frame(org_type: str) -> pl.DataFrame:
    org_cols = [
        c
        for c in schema.names()
        if c.startswith(f"{org_type}_")
        and c
        not in (
            f"{org_type}_latitude",
            f"{org_type}_longitude",
            f"{org_type}_distance",
        )
    ]
    select_list = ", ".join(org_cols)
    group_list = ", ".join(org_cols)
    sql = f'SELECT {select_list}, COUNT(*) AS "Marchés" FROM decp GROUP BY {group_list}'
    return get_cursor().execute(sql).pl()


DF_ACHETEURS = build_org_frame("acheteur")
DF_TITULAIRES = build_org_frame("titulaire")
DEPARTEMENTS = get_departements()
DEPARTEMENTS_GEOJSON = get_departements_geojson()
DATA_SCHEMA = get_data_schema()
# Colonne virtuelle (dérivée de uid) : lien loupe vers la fiche du marché.
# Absente du schéma DuckDB, créée à l'affichage dans postprocess_page().
DATA_SCHEMA["marche"] = {
    "name": "marche",
    "type": "string",
    "title": "Marché",
    "description": "Lien vers la fiche détaillée du marché.",
}


# Libellés français des types Table Schema, alignés sur la documentation
# francophone du standard (Validata / schema.data.gouv.fr). Le schéma DECP
# n'utilise aujourd'hui que string, number, integer, boolean et date ; les
# autres entrées évitent d'afficher un type anglais si le schéma distant
# évolue.
TYPE_LABELS_FR = {
    "string": "Chaîne de caractères",
    "number": "Nombre décimal",
    "integer": "Nombre entier",
    "boolean": "Booléen (oui/non)",
    "date": "Date",
    "datetime": "Date et heure",
    "time": "Heure",
    "year": "Année",
}


def field_type_label(field: dict) -> str:
    """Libellé français du type d'un champ Table Schema.

    Repli sur le type brut pour un type non traduit : mieux vaut afficher
    « geopoint » qu'une case vide.
    """
    type_name = field.get("type", "")
    if type_name == "string" and field.get("format") == "uri":
        return "URL"
    return TYPE_LABELS_FR.get(type_name, type_name)


def schema_field_rows() -> list[dict]:
    """Lignes du tableau des champs publiés (/projet/donnees).

    `marche` est exclue : c'est la colonne loupe fabriquée à l'affichage,
    pas une donnée publiée. Le `<span id=...>` posé dans la colonne « nom »
    sert d'ancre aux URL de type /projet/donnees#nom_du_champ (cf.
    src/assets/anchors.js).
    """
    return [
        {
            "champ": name,
            "nom": f'<span id="{name}"></span>**{field.get("title", name)}** ({name})',
            "type": field_type_label(field),
            "description": field.get("description", ""),
        }
        for name, field in DATA_SCHEMA.items()
        if name != "marche"
    ]
