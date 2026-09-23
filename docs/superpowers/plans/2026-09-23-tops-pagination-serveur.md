# Tops acheteurs/titulaires côté serveur — plan d'implémentation (#142)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** remplacer les grilles « Top acheteurs / Top titulaires » client-side
par des grilles AG Grid en modèle `infinite`, dont chaque page est agrégée,
filtrée et triée par DuckDB.

**Architecture :** un module `src/utils/top_org_grid.py` porte la traduction
`filterModel`/`sortModel` → SQL, la requête agrégée paginée et la fabrique de
grille. Chaque page (observatoire, tableau, acheteur, titulaire) déclare un
petit callback de datasource qui reconstruit son périmètre SQL à partir de
l'état de la page, puis délègue à ce module. Même schéma que
`src/utils/entity_grid.py`.

**Tech Stack :** Dash 4.4, dash-ag-grid 35.2 (`rowModelType="infinite"`),
DuckDB, Polars, pytest (+ Selenium via `dash_duo`).

**Spec :** `docs/superpowers/specs/2026-09-22-tops-pagination-serveur-design.md`

## Global Constraints

- Imports du projet toujours préfixés `src.` (`from src.utils...`), jamais
  `utils...`.
- Le client n'envoie jamais de SQL : seuls des noms de colonnes validés
  contre une liste blanche entrent dans le SQL ; toutes les valeurs passent
  par le binding `?`.
- UI et messages en français.
- Avant tout `git add` / `git commit`, lancer `pre-commit run --files <fichiers>`.
- Tests lancés avec `uv run pytest` (jamais deux runs pytest en parallèle).
- Chaque tâche ne lance que **ses** fichiers de tests. La suite complète
  n'est lancée qu'à la tâche 7.
- Pagination : `PAGE_SIZE = 10` (inchangé par rapport à l'existant).
- Colonne agrégée nommée `"Attributions"`, calculée par `COUNT(*)`.
- Tri par défaut : `"Attributions" DESC`, puis `"<org>_id" ASC`.

---

### Task 1 : `having` et `count_aggregate` dans `src/db.py`

**Files:**

- Modify: `src/db.py:325-352` (`aggregate_marches`)
- Test: `tests/api/test_db_aggregate.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `aggregate_marches(select_sql, where_sql="TRUE", params=(), group_by=None, having=None, order_by=None, limit=None, offset=None) -> pl.DataFrame`
  - `count_aggregate(select_sql, where_sql="TRUE", params=(), group_by=None, having=None) -> int`

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/api/test_db_aggregate.py` :

```python
def test_aggregate_having_filters_groups():
    """HAVING s'applique après le GROUP BY, avec ses paramètres liés."""
    df = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
        having="COUNT(*) >= ?",
        params=[1],
    )
    assert df.height > 0

    vide = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
        having="COUNT(*) > ?",
        params=[10**9],
    )
    assert vide.height == 0


def test_count_aggregate_counts_groups_not_rows():
    """count_aggregate renvoie le nombre de groupes, pas le nombre de lignes."""
    from src.db import count_aggregate

    groupes = count_aggregate(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
    )
    df = aggregate_marches(
        select_sql='"acheteur_id", COUNT(*) AS "n"',
        group_by='"acheteur_id"',
    )
    assert groupes == df.height


def test_count_aggregate_applies_having():
    from src.db import count_aggregate

    assert (
        count_aggregate(
            select_sql='"acheteur_id", COUNT(*) AS "n"',
            group_by='"acheteur_id"',
            having="COUNT(*) > ?",
            params=[10**9],
        )
        == 0
    )
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/api/test_db_aggregate.py -v`
Attendu : ÉCHEC — `TypeError: aggregate_marches() got an unexpected keyword argument 'having'` et `ImportError: cannot import name 'count_aggregate'`.

- [ ] **Step 3 : implémenter**

Dans `src/db.py`, ajouter le paramètre `having` à `aggregate_marches` (entre
`group_by` et `order_by` dans la signature comme dans le SQL) :

```python
def aggregate_marches(
    select_sql: str,
    where_sql: str = "TRUE",
    params: tuple | list = (),
    group_by: str | None = None,
    having: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pl.DataFrame:
```

et, juste après la ligne `sql += f" GROUP BY {group_by}"` :

```python
    if having:
        sql += f" HAVING {having}"
```

Compléter la docstring : « `having` est un fragment SQL construit depuis des
noms de colonnes validés ; ses valeurs sont liées via `params`, à la suite de
celles du `WHERE`. »

Puis ajouter, sous `aggregate_marches` :

```python
def count_aggregate(
    select_sql: str,
    where_sql: str = "TRUE",
    params: tuple | list = (),
    group_by: str | None = None,
    having: str | None = None,
) -> int:
    """Nombre de lignes renvoyées par un SELECT agrégé (COUNT des groupes).

    Pendant de `count_marches` pour les grilles paginées sur un agrégat : la
    grille a besoin du nombre total de groupes pour dimensionner sa
    pagination, sans rapatrier les groupes eux-mêmes.
    """
    inner = f"SELECT {select_sql} FROM decp WHERE {where_sql}"
    if group_by:
        inner += f" GROUP BY {group_by}"
    if having:
        inner += f" HAVING {having}"

    result = get_cursor().execute(f"SELECT COUNT(*) FROM ({inner})", list(params)).fetchone()
    return int(result[0]) if result else 0
```

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/api/test_db_aggregate.py -v`
Attendu : tous PASS.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/db.py tests/api/test_db_aggregate.py
git add src/db.py tests/api/test_db_aggregate.py
git commit -m "aggregate_marches: HAVING et count_aggregate #142"
```

---

### Task 2 : traduction filtre/tri → SQL (`src/utils/top_org_grid.py`)

**Files:**

- Create: `src/utils/top_org_grid.py`
- Test: `tests/test_top_org_grid.py` (créé ici)

**Interfaces:**

- Consumes: `filtermodel_to_ast`, `ast_to_sql` (`src.utils.query_ast`),
  `schema` (`src.db`).
- Produces:

  - `AGG_COLUMN = "Attributions"`
  - `group_columns(org_type: str, extra_columns=()) -> list[str]`
  - `top_org_filter_sql(filter_model, org_type, extra_columns=()) -> tuple[str, list, str, list]`
    (where_sql, where_params, having_sql, having_params)
  - `top_org_sort_sql(sort_model, org_type, extra_columns=()) -> str`

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `tests/test_top_org_grid.py` :

```python
"""Grilles « Top acheteurs / Top titulaires » paginées côté serveur (#142)."""

from src.utils.top_org_grid import (
    AGG_COLUMN,
    group_columns,
    top_org_filter_sql,
    top_org_sort_sql,
)


def test_group_columns_titulaire_inclut_type_identifiant():
    """add_links n'ajoute le lien SIRET que si titulaire_typeIdentifiant est là."""
    cols = group_columns("titulaire", ["titulaire_distance"])
    assert cols[:2] == ["titulaire_id", "titulaire_nom"]
    assert "titulaire_typeIdentifiant" in cols
    assert "titulaire_distance" in cols


def test_group_columns_acheteur_sans_type_identifiant():
    assert group_columns("acheteur") == ["acheteur_id", "acheteur_nom"]


def test_filtre_sur_le_nom_produit_un_where():
    where_sql, where_params, having_sql, having_params = top_org_filter_sql(
        {"titulaire_nom": {"filterType": "text", "type": "contains", "filter": "mairie"}},
        "titulaire",
    )
    assert where_sql != "TRUE"
    assert where_params  # valeur liée, jamais concaténée
    assert "mairie" in " ".join(str(p) for p in where_params).lower()
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_attributions_produit_un_having():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": 5}},
        "titulaire",
    )
    assert having_sql == "(COUNT(*) > ?)"
    assert having_params == [5]


def test_filtre_attributions_in_range():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "inRange", "filter": 2, "filterTo": 7}},
        "titulaire",
    )
    assert having_sql == "(COUNT(*) BETWEEN ? AND ?)"
    assert having_params == [2, 7]


def test_filtre_attributions_deux_conditions():
    _, _, having_sql, having_params = top_org_filter_sql(
        {
            AGG_COLUMN: {
                "filterType": "number",
                "operator": "AND",
                "conditions": [
                    {"filterType": "number", "type": "greaterThan", "filter": 2},
                    {"filterType": "number", "type": "lessThan", "filter": 9},
                ],
            }
        },
        "titulaire",
    )
    assert having_sql == "(COUNT(*) > ?) AND (COUNT(*) < ?)"
    assert having_params == [2, 9]


def test_filtre_attributions_valeur_non_numerique_ignoree():
    _, _, having_sql, having_params = top_org_filter_sql(
        {AGG_COLUMN: {"filterType": "number", "type": "greaterThan", "filter": "abc"}},
        "titulaire",
    )
    assert having_sql == ""
    assert having_params == []


def test_filtre_sur_colonne_hors_perimetre_ignore():
    """Une colonne du schéma mais absente du GROUP BY ne doit pas filtrer."""
    where_sql, where_params, _, _ = top_org_filter_sql(
        {"objet": {"filterType": "text", "type": "contains", "filter": "route"}},
        "titulaire",
    )
    assert where_sql == "TRUE"
    assert where_params == []


def test_tri_par_defaut_attributions_puis_id():
    assert top_org_sort_sql(None, "titulaire") == '"Attributions" DESC, "titulaire_id" ASC'


def test_tri_explicite_puis_id():
    sql = top_org_sort_sql([{"colId": "titulaire_nom", "sort": "asc"}], "titulaire")
    assert sql == '"titulaire_nom" ASC, "titulaire_id" ASC'


def test_tri_sur_colonne_inconnue_ignore():
    sql = top_org_sort_sql([{"colId": "objet; DROP TABLE decp", "sort": "asc"}], "titulaire")
    assert sql == '"Attributions" DESC, "titulaire_id" ASC'
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : ÉCHEC — `ModuleNotFoundError: No module named 'src.utils.top_org_grid'`.

- [ ] **Step 3 : implémenter**

Créer `src/utils/top_org_grid.py` :

```python
"""Grilles « Top acheteurs / Top titulaires » paginées côté serveur (#142).

Les tops étaient des AG Grid client-side : tout le classement agrégé partait
au navigateur (jusqu'à 33 Mo dans l'observatoire, d'où une troncature à 100
lignes qui rendait le filtre trompeur). Ici, chaque page est agrégée, filtrée
et triée par DuckDB, et seules les lignes affichées transitent.

Ce module ne contient que des fonctions pures + la fabrique de grille ; les
callbacks de datasource vivent dans les pages, qui savent reconstruire leur
périmètre SQL (cf. src/utils/entity_grid.py, même découpage).
"""

from src.db import schema
from src.utils import logger
from src.utils.query_ast import ast_to_sql, filtermodel_to_ast

#: Nom de la colonne agrégée, affichée telle quelle dans la grille.
AGG_COLUMN = "Attributions"
_AGG_SQL = "COUNT(*)"

#: Opérateurs du filtre numérique AG Grid → SQL. `inRange` est traité à part
#: (deux valeurs), `blank`/`notBlank` n'ont pas de sens sur un COUNT(*).
_NUM_OPS = {
    "equals": "=",
    "notEqual": "<>",
    "lessThan": "<",
    "lessThanOrEqual": "<=",
    "greaterThan": ">",
    "greaterThanOrEqual": ">=",
}


def group_columns(org_type: str, extra_columns=()) -> list[str]:
    """Colonnes du GROUP BY (hors agrégat), dans l'ordre d'affichage.

    `titulaire_typeIdentifiant` est nécessaire à `add_links`, qui ne pose un
    lien vers la fiche que pour les SIRET. Les colonnes absentes du schéma
    sont écartées : tests/test.parquet n'en porte qu'un sous-ensemble.
    """
    cols = [f"{org_type}_id", f"{org_type}_nom"]
    if org_type == "titulaire":
        cols.append("titulaire_typeIdentifiant")
    cols += [c for c in extra_columns if c not in cols]
    return [c for c in cols if c in schema.names()]


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(f"Filtre {AGG_COLUMN} : valeur non entière ignorée ({value!r})")
        return None


def _having_leaf(cond: dict) -> tuple[str, list]:
    op = cond.get("type")
    if op == "inRange":
        low, high = _to_int(cond.get("filter")), _to_int(cond.get("filterTo"))
        if low is None or high is None:
            return "", []
        return f"{_AGG_SQL} BETWEEN ? AND ?", [low, high]
    sql_op = _NUM_OPS.get(op)
    value = _to_int(cond.get("filter"))
    if sql_op is None or value is None:
        if sql_op is None:
            logger.warning(f"Filtre {AGG_COLUMN} : opérateur ignoré ({op!r})")
        return "", []
    return f"{_AGG_SQL} {sql_op} ?", [value]


def _having_sql(spec: dict | None) -> tuple[str, list]:
    """Traduit le filtre AG Grid de la colonne agrégée en clause HAVING.

    `filtermodel_to_ast` ne peut pas s'en charger : il valide les colonnes
    contre le schéma DECP, or `Attributions` n'existe qu'après agrégation.
    """
    if not spec:
        return "", []
    conditions = spec.get("conditions")
    if conditions is None:  # forme dépréciée condition1/condition2, ou unitaire
        conditions = [c for c in (spec.get("condition1"), spec.get("condition2")) if c] or [spec]
    joiner = " OR " if spec.get("operator") == "OR" else " AND "

    fragments, params = [], []
    for cond in conditions:
        sql, cond_params = _having_leaf(cond)
        if sql:
            fragments.append(f"({sql})")
            params.extend(cond_params)
    return (joiner.join(fragments), params) if fragments else ("", [])


def top_org_filter_sql(
    filter_model, org_type: str, extra_columns=()
) -> tuple[str, list, str, list]:
    """(where_sql, where_params, having_sql, having_params) pour un filterModel.

    Les colonnes non agrégées passent par l'AST partagé (`filtermodel_to_ast`
    + `ast_to_sql`), qui gère notamment le désaccentuage des noms (#138). La
    colonne agrégée part en HAVING. Toute autre clé est ignorée : seules les
    colonnes du GROUP BY sont filtrables.
    """
    model = dict(filter_model or {})
    agg_spec = model.pop(AGG_COLUMN, None)

    allowed = set(group_columns(org_type, extra_columns))
    for column in [c for c in model if c not in allowed]:
        logger.warning(f"Filtre top ignoré (colonne hors périmètre) : {column!r}")
        model.pop(column)

    where_sql, where_params = ast_to_sql(filtermodel_to_ast(model, schema), schema)
    having_sql, having_params = _having_sql(agg_spec)
    return where_sql, where_params, having_sql, having_params


def top_org_sort_sql(sort_model, org_type: str, extra_columns=()) -> str:
    """Clause ORDER BY, avec l'id en dernier critère (pagination stable).

    Sans ce départage, deux organisations à égalité peuvent changer d'ordre
    d'une page à l'autre et apparaître deux fois ou pas du tout.
    """
    allowed = set(group_columns(org_type, extra_columns)) | {AGG_COLUMN}
    fragments = []
    for item in sort_model or []:
        column = item.get("colId")
        if column not in allowed:
            logger.warning(f"Tri top ignoré (colonne inconnue) : {column!r}")
            continue
        direction = "DESC" if item.get("sort") == "desc" else "ASC"
        fragments.append(f'"{column}" {direction}')

    if not fragments:
        fragments.append(f'"{AGG_COLUMN}" DESC')
    fragments.append(f'"{org_type}_id" ASC')
    return ", ".join(fragments)
```

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : tous PASS.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/utils/top_org_grid.py tests/test_top_org_grid.py
git add src/utils/top_org_grid.py tests/test_top_org_grid.py
git commit -m "Traduction filtre/tri des tops en SQL #142"
```

---

### Task 3 : requête paginée `fetch_top_org_page`

**Files:**

- Modify: `src/utils/top_org_grid.py`
- Test: `tests/test_top_org_grid.py`

**Interfaces:**

- Consumes: Task 1 (`aggregate_marches(having=...)`, `count_aggregate`),
  Task 2 (`group_columns`, `top_org_filter_sql`, `top_org_sort_sql`,
  `AGG_COLUMN`).
- Produces:

  - `fetch_top_org_page(org_type, where_sql, params, request, extra_columns=()) -> dict | no_update`
    renvoyant `{"rowData": list[dict], "rowCount": int}`.
  - `_cached_top_count(select_sql, where_sql, params, group_by, having) -> int`

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à `tests/test_top_org_grid.py` (en tête, à côté des imports existants) :

```python
import duckdb
import pytest
from dash import no_update

import src.db as db_module
import src.utils.top_org_grid as top_module
from src.utils.top_org_grid import fetch_top_org_page


@pytest.fixture(scope="module")
def flask_app():
    """App Flask minimale pour que @cache.memoize() fonctionne (même pattern
    que tests/test_grid.py)."""
    from flask import Flask

    from src.utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    from src.utils.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            pass
        yield


@pytest.fixture
def decp_synthetique(monkeypatch):
    """Table `decp` en mémoire : 30 titulaires, l'organisation i ayant
    30 - i attributions (classement strictement décroissant, donc
    déterministe). La base de test partagée ne contient qu'une seule ligne :
    ni le classement, ni la pagination n'y seraient observables.
    """
    conn = duckdb.connect(":memory:")
    lignes = []
    for i in range(30):
        for j in range(30 - i):
            lignes.append(
                f"('m{i}-{j}', 'T{i:03d}', 'Organisation {i:03d}', 'SIRET', {i})"
            )
    conn.execute(
        "CREATE TABLE decp AS SELECT * FROM (VALUES " + ",".join(lignes) + ") AS t("
        "uid, titulaire_id, titulaire_nom, titulaire_typeIdentifiant, titulaire_distance)"
    )
    monkeypatch.setattr(db_module, "get_cursor", lambda: conn)
    yield conn
    conn.close()


def _request(start=0, end=10, filter_model=None, sort_model=None):
    return {
        "startRow": start,
        "endRow": end,
        "filterModel": filter_model,
        "sortModel": sort_model,
    }


def test_fetch_page_renvoie_lignes_et_total(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page("titulaire", "TRUE", [], _request())

    assert response["rowCount"] == 30  # nombre de groupes, pas de lignes
    assert len(response["rowData"]) == 10
    # Tri par défaut : l'organisation 000 a le plus d'attributions.
    assert response["rowData"][0]["Attributions"] == 30
    # add_links a posé un lien vers la fiche.
    assert '<a href = "/titulaires/T000">' in response["rowData"][0]["titulaire_nom"]


def test_fetch_page_offset_sans_doublon(flask_app, decp_synthetique):
    with flask_app.app_context():
        page1 = fetch_top_org_page("titulaire", "TRUE", [], _request(0, 10))
        page2 = fetch_top_org_page("titulaire", "TRUE", [], _request(10, 20))

    ids1 = [r["titulaire_id"] for r in page1["rowData"]]
    ids2 = [r["titulaire_id"] for r in page2["rowData"]]
    assert len(set(ids1) & set(ids2)) == 0
    assert ids1 == [f"T{i:03d}" for i in range(10)]


def test_fetch_page_filtre_trouve_au_dela_du_10e_rang(flask_app, decp_synthetique):
    """Le cœur de #142 : le filtre porte sur tout le classement, pas sur la
    page affichée ni sur un top tronqué."""
    filtre = {
        "titulaire_nom": {"filterType": "text", "type": "contains", "filter": "025"}
    }
    with flask_app.app_context():
        response = fetch_top_org_page("titulaire", "TRUE", [], _request(0, 10, filtre))

    assert response["rowCount"] == 1
    assert response["rowData"][0]["titulaire_id"] == "T025"


def test_fetch_page_having_sur_attributions(flask_app, decp_synthetique):
    filtre = {
        "Attributions": {"filterType": "number", "type": "greaterThan", "filter": 25}
    }
    with flask_app.app_context():
        response = fetch_top_org_page("titulaire", "TRUE", [], _request(0, 10, filtre))

    assert response["rowCount"] == 5  # 30, 29, 28, 27, 26
    assert all(row["Attributions"] > 25 for row in response["rowData"])


def test_fetch_page_tri_numerique_pas_lexicographique(flask_app, decp_synthetique):
    """9 doit rester inférieur à 10 : l'ancienne grille comparait des chaînes."""
    tri = [{"colId": "Attributions", "sort": "asc"}]
    with flask_app.app_context():
        response = fetch_top_org_page("titulaire", "TRUE", [], _request(0, 5, sort_model=tri))

    valeurs = [row["Attributions"] for row in response["rowData"]]
    assert valeurs == [1, 2, 3, 4, 5]


def test_fetch_page_respecte_le_perimetre(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "titulaire_id = ?", ["T003"], _request()
        )

    assert response["rowCount"] == 1
    assert response["rowData"][0]["titulaire_id"] == "T003"


def test_fetch_page_compte_mis_en_cache_entre_les_pages(
    flask_app, decp_synthetique, monkeypatch
):
    """Régression : un COUNT par page rendrait la pagination deux fois plus
    coûteuse (même raison que _cached_count dans src/utils/grid.py)."""
    appels = {"n": 0}
    vrai_count = top_module.count_aggregate

    def compter(*args, **kwargs):
        appels["n"] += 1
        return vrai_count(*args, **kwargs)

    monkeypatch.setattr(top_module, "count_aggregate", compter)

    with flask_app.app_context():
        fetch_top_org_page("titulaire", "TRUE", [], _request(0, 10))
        fetch_top_org_page("titulaire", "TRUE", [], _request(10, 20))
        fetch_top_org_page("titulaire", "TRUE", [], _request(20, 30))

    assert appels["n"] == 1


def test_fetch_page_sans_request():
    assert fetch_top_org_page("titulaire", "TRUE", [], None) is no_update


def test_fetch_page_perimetre_vide(flask_app, decp_synthetique):
    with flask_app.app_context():
        response = fetch_top_org_page(
            "titulaire", "titulaire_id = ?", ["INCONNU"], _request()
        )

    assert response == {"rowData": [], "rowCount": 0}
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'fetch_top_org_page'`.

- [ ] **Step 3 : implémenter**

Compléter les imports en tête de `src/utils/top_org_grid.py` :

```python
import polars as pl
from dash import no_update

from src.db import aggregate_marches, count_aggregate, schema
from src.utils.cache import cache
from src.utils.table import add_links
```

Puis ajouter en fin de module :

```python
def _select_and_group(org_type: str, extra_columns=()) -> tuple[str, str]:
    """Fragments SELECT et GROUP BY partagés par le COUNT et la page."""
    group_by = ", ".join(f'"{c}"' for c in group_columns(org_type, extra_columns))
    return f'{group_by}, {_AGG_SQL} AS "{AGG_COLUMN}"', group_by


@cache.memoize()
def _cached_top_count(select_sql, where_sql, params, group_by, having) -> int:
    """COUNT des groupes, mémoïsé sur la requête.

    AG Grid redemande le total à chaque bloc ; pour un même filtre tous les
    blocs partagent la même requête (cf. `_cached_count` dans
    src/utils/grid.py, même raison).
    """
    return count_aggregate(
        select_sql=select_sql,
        where_sql=where_sql,
        params=params,
        group_by=group_by,
        having=having,
    )


def _rows_with_links(dff: pl.DataFrame) -> list[dict]:
    """Lignes prêtes pour la grille : textes non nuls, liens HTML posés.

    Seules les colonnes texte sont castées : `Attributions` et
    `titulaire_distance` restent numériques, pour que la grille les affiche
    et les aligne comme des nombres.
    """
    if dff.height == 0:
        return []
    texte = [c for c, dtype in dff.schema.items() if dtype == pl.String]
    dff = dff.with_columns([pl.col(c).fill_null("") for c in texte])
    return add_links(dff).to_dicts()


def fetch_top_org_page(org_type, where_sql, params, request, extra_columns=()):
    """Datasource server-side d'une grille top, scopée par (where_sql, params).

    Renvoie {"rowData": ..., "rowCount": <nombre de groupes>}, ou `no_update`
    si AG Grid n'a pas (encore) envoyé de requête.
    """
    if request is None:
        return no_update

    select_sql, group_by = _select_and_group(org_type, extra_columns)
    filter_sql, filter_params, having_sql, having_params = top_org_filter_sql(
        request.get("filterModel"), org_type, extra_columns
    )
    scoped_where = f"({where_sql}) AND ({filter_sql})"
    query_params = [*params, *filter_params, *having_params]

    total = _cached_top_count(
        select_sql, scoped_where, tuple(query_params), group_by, having_sql or None
    )

    start = int(request.get("startRow", 0))
    end = int(request.get("endRow", start))
    dff = aggregate_marches(
        select_sql=select_sql,
        where_sql=scoped_where,
        params=query_params,
        group_by=group_by,
        having=having_sql or None,
        order_by=top_org_sort_sql(request.get("sortModel"), org_type, extra_columns),
        limit=max(0, end - start),
        offset=start,
    )
    return {"rowData": _rows_with_links(dff), "rowCount": total}
```

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : tous PASS. Si `add_links` échoue sur une colonne manquante, vérifier
que `group_columns` renvoie bien `titulaire_typeIdentifiant`.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/utils/top_org_grid.py tests/test_top_org_grid.py
git add src/utils/top_org_grid.py tests/test_top_org_grid.py
git commit -m "Page agrégée paginée pour les tops #142"
```

---

### Task 4 : composant de grille `top_org_grid`

**Files:**

- Modify: `src/utils/top_org_grid.py`
- Test: `tests/test_top_org_grid.py`

**Interfaces:**

- Consumes: Task 2 (`group_columns`, `AGG_COLUMN`), `AG_GRID_THEME` et
  `AG_GRID_LOCALE_FR` de `src.figures`.
- Produces:

  - `GRID_TYPE = "top-org-grid"`, `PAGE_SIZE = 10`
  - `scope_key(*parts) -> str`
  - `top_org_grid_id(context, org_type, scope) -> dict`
  - `top_org_column_defs(org_type, extra_columns=()) -> list[dict]`
  - `top_org_grid(context, org_type, scope, extra_columns=()) -> dag.AgGrid`

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à `tests/test_top_org_grid.py` :

```python
def test_grid_id_pattern_matching():
    import dash_ag_grid as dag

    from src.utils.top_org_grid import top_org_grid

    grille = top_org_grid("observatoire", "titulaire", "abc123")

    assert isinstance(grille, dag.AgGrid)
    assert grille.id == {
        "type": "top-org-grid",
        "context": "observatoire",
        "org_type": "titulaire",
        "scope": "abc123",
    }


def test_grid_est_en_modele_infinite_pagine():
    from src.utils.top_org_grid import PAGE_SIZE, top_org_grid

    grille = top_org_grid("observatoire", "acheteur", "abc123")
    options = grille.dashGridOptions

    assert grille.rowModelType == "infinite"
    assert options["pagination"] is True
    assert options["paginationPageSize"] == PAGE_SIZE
    assert options["cacheBlockSize"] == PAGE_SIZE
    # autoHeight est incompatible avec le modèle infinite : hauteur fixe.
    assert "autoHeight" not in options.get("domLayout", "")
    assert grille.style["height"].endswith("px")
    assert grille.rowData is None  # aucune donnée embarquée
    assert grille.persistence in (False, None)


def test_grid_scopes_distincts_donnent_des_ids_distincts():
    from src.utils.top_org_grid import scope_key, top_org_grid_id

    id1 = top_org_grid_id("acheteur", "titulaire", scope_key("/acheteurs/1", "2025"))
    id2 = top_org_grid_id("acheteur", "titulaire", scope_key("/acheteurs/2", "2025"))
    id3 = top_org_grid_id("tableau", "titulaire", scope_key("/acheteurs/1", "2025"))

    assert id1 != id2  # sinon React ne remonte pas la grille au changement de fiche
    assert id1 != id3  # un callback par contexte


def test_column_defs_types_de_filtre():
    from src.utils.top_org_grid import top_org_column_defs

    defs = {d["field"]: d for d in top_org_column_defs("titulaire", ["titulaire_distance"])}

    assert "titulaire_id" not in defs  # lien porté par le nom
    assert "titulaire_typeIdentifiant" not in defs  # technique, requis par add_links
    assert defs["titulaire_nom"]["filter"] == "agTextColumnFilter"
    assert defs["titulaire_nom"]["cellRenderer"] == "markdown"
    assert defs["Attributions"]["filter"] == "agNumberColumnFilter"
    assert defs["titulaire_distance"]["filter"] == "agNumberColumnFilter"
    assert all(d["sortable"] for d in defs.values())
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'top_org_grid'`.

- [ ] **Step 3 : implémenter**

Compléter les imports de `src/utils/top_org_grid.py` :

```python
import hashlib
import json

import dash_ag_grid as dag

from src.figures import AG_GRID_LOCALE_FR, AG_GRID_THEME
from src.utils.data import DATA_SCHEMA
```

Puis ajouter en fin de module :

```python
GRID_TYPE = "top-org-grid"
PAGE_SIZE = 10
_ROW_HEIGHT = 42
#: Hauteur totale : en-tête (49) + filtre flottant (40) + 10 lignes + barre de
#: pagination (48). `domLayout: "autoHeight"` n'existe pas en modèle infinite.
GRID_HEIGHT = f"{49 + 40 + PAGE_SIZE * _ROW_HEIGHT + 48}px"

#: Colonnes du GROUP BY qui ne sont pas affichées : l'id sert au lien porté
#: par le nom, typeIdentifiant sert à add_links.
_HIDDEN_FIELDS = ("_id", "titulaire_typeIdentifiant")


def scope_key(*parts) -> str:
    """Clé courte et stable identifiant un périmètre.

    Elle n'entre JAMAIS dans une requête : elle sert uniquement à faire varier
    l'id de la grille, donc à forcer React à la remonter quand le périmètre
    change. Sans remontage, AG Grid garderait son bloc en cache et
    n'appellerait pas le datasource.
    """
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.blake2s(raw.encode(), digest_size=8).hexdigest()


def top_org_grid_id(context: str, org_type: str, scope: str) -> dict:
    return {"type": GRID_TYPE, "context": context, "org_type": org_type, "scope": scope}


def top_org_column_defs(org_type: str, extra_columns=()) -> list[dict]:
    """columnDefs statiques : elles ne dépendent plus des données."""
    numeric = {AGG_COLUMN, *extra_columns}
    defs = []
    for column in [*group_columns(org_type, extra_columns), AGG_COLUMN]:
        if column.endswith("_id") or column == "titulaire_typeIdentifiant":
            continue
        col_def = {
            "field": column,
            "headerName": DATA_SCHEMA.get(column, {}).get("title", column),
            "sortable": True,
            "filter": "agNumberColumnFilter"
            if column in numeric
            else "agTextColumnFilter",
        }
        if column == f"{org_type}_nom":
            col_def |= {"cellRenderer": "markdown", "flex": 1}
        defs.append(col_def)
    return defs


def top_org_grid(context: str, org_type: str, scope: str, extra_columns=()):
    """Grille top paginée côté serveur, alimentée par le callback du contexte."""
    return dag.AgGrid(
        id=top_org_grid_id(context, org_type, scope),
        columnDefs=top_org_column_defs(org_type, extra_columns),
        rowModelType="infinite",
        dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": PAGE_SIZE,
            "cacheBlockSize": PAGE_SIZE,
            "maxBlocksInCache": 10,
            "rowBuffer": 0,
            "infiniteInitialRowCount": PAGE_SIZE,
            "rowHeight": _ROW_HEIGHT,
            "suppressCellFocus": True,
            "localeText": {
                **AG_GRID_LOCALE_FR,
                "noRowsToShow": "Aucune organisation",
            },
            "theme": AG_GRID_THEME,
        },
        defaultColDef={"resizable": True, "floatingFilter": True},
        style={"height": GRID_HEIGHT, "width": "100%"},
        persistence=False,
        columnSize="responsiveSizeToFit",
    )
```

Note : `src.figures` n'importe pas ce module au niveau module (Task 6 utilise
un import local) — le cycle est donc évité, comme dans `src/utils/entity_grid.py`.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/test_top_org_grid.py -v`
Attendu : tous PASS.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/utils/top_org_grid.py tests/test_top_org_grid.py
git add src/utils/top_org_grid.py tests/test_top_org_grid.py
git commit -m "Composant de grille top paginée #142"
```

---

### Task 5 : branchement des fiches acheteur et titulaire

**Files:**

- Modify: `src/pages/acheteur.py:394-409` (callback `get_top_titulaires`)
- Modify: `src/pages/titulaire.py:431-445` (callback `get_top_acheteurs`)
- Test: `tests/test_fiches_top_org.py` (réécrit)

**Interfaces:**

- Consumes: Task 3 (`fetch_top_org_page`), Task 4 (`top_org_grid`,
  `scope_key`, `GRID_TYPE`), `_acheteur_scope` / `_titulaire_scope` existants.
- Produces: callbacks `get_top_titulaires_rows` (page acheteur) et
  `get_top_acheteurs_rows` (page titulaire).

- [ ] **Step 1 : écrire les tests qui échouent**

Remplacer tout le contenu de `tests/test_fiches_top_org.py` par :

```python
"""Les tops des fiches sont paginés côté serveur (#142, suite de #141).

Avant : tout le classement partait au navigateur (jusqu'à ~2 Mo). Désormais
la grille est en modèle infinite et son datasource est scopé à la fiche.
"""

import dash_ag_grid as dag
import pytest


def _trouver_grille(node):
    if isinstance(node, dag.AgGrid):
        return node
    enfants = getattr(node, "children", None)
    if enfants is None:
        return None
    if not isinstance(enfants, (list, tuple)):
        enfants = [enfants]
    for enfant in enfants:
        trouve = _trouver_grille(enfant)
        if trouve is not None:
            return trouve
    return None


@pytest.mark.parametrize(
    "module,fonction,org_type",
    [
        ("acheteur", "get_top_titulaires", "titulaire"),
        ("titulaire", "get_top_acheteurs", "acheteur"),
    ],
)
def test_la_fiche_rend_une_grille_infinite_sans_donnees(module, fonction, org_type):
    import importlib

    from src.app import app  # noqa: F401  (instancie Dash avant les pages)

    page = importlib.import_module(f"src.pages.{module}")
    grille = _trouver_grille(getattr(page, fonction)("/x/123", None))

    assert grille is not None, "aucune grille rendue"
    assert grille.rowModelType == "infinite"
    assert grille.rowData is None  # plus aucun classement embarqué
    assert grille.id["type"] == "top-org-grid"
    assert grille.id["context"] == module
    assert grille.id["org_type"] == org_type


@pytest.mark.parametrize(
    "module,fonction",
    [("acheteur", "get_top_titulaires"), ("titulaire", "get_top_acheteurs")],
)
def test_changer_de_fiche_change_le_scope(module, fonction):
    """L'id doit varier avec la fiche et l'année, sinon React réutilise la
    grille et AG Grid ne redemande pas ses lignes."""
    import importlib

    from src.app import app  # noqa: F401

    page = importlib.import_module(f"src.pages.{module}")
    scopes = {
        _trouver_grille(getattr(page, fonction)(url, annee)).id["scope"]
        for url, annee in [("/x/1", None), ("/x/2", None), ("/x/1", "2025")]
    }
    assert len(scopes) == 3


@pytest.mark.parametrize(
    "module,fonction,scope_attr,org_type",
    [
        ("acheteur", "get_top_titulaires_rows", "_acheteur_scope", "titulaire"),
        ("titulaire", "get_top_acheteurs_rows", "_titulaire_scope", "acheteur"),
    ],
)
def test_le_datasource_est_scope_a_la_fiche(
    monkeypatch, module, fonction, scope_attr, org_type
):
    import importlib

    from src.app import app  # noqa: F401

    page = importlib.import_module(f"src.pages.{module}")
    monkeypatch.setattr(page, scope_attr, lambda *_: ("titulaire_id = ?", ["T1"]))

    recu = {}

    def faux_fetch(org, where_sql, params, request, extra_columns=()):
        recu.update(
            org=org, where_sql=where_sql, params=params, extra=list(extra_columns)
        )
        return {"rowData": [], "rowCount": 0}

    monkeypatch.setattr(page, "fetch_top_org_page", faux_fetch)

    request = {"startRow": 0, "endRow": 10, "filterModel": None, "sortModel": None}
    getattr(page, fonction)(request, "/x/123", None)

    assert recu["org"] == org_type
    assert recu["where_sql"] == "titulaire_id = ?"
    assert recu["params"] == ["T1"]
    assert recu["extra"] == ["titulaire_distance"]
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/test_fiches_top_org.py -v`
Attendu : ÉCHEC — la grille rendue porte encore `rowData` et l'id `top10_...`,
et `get_top_titulaires_rows` n'existe pas.

- [ ] **Step 3 : implémenter**

Dans `src/pages/acheteur.py`, remplacer le callback `get_top_titulaires`
(lignes 394-409) par :

```python
@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_top_titulaires(pathname, ach_year):
    # La grille ne porte plus le classement : ses lignes arrivent par le
    # datasource ci-dessous, une page à la fois (#142).
    grille = top_org_grid(
        "acheteur",
        "titulaire",
        scope_key(pathname, ach_year),
        ["titulaire_distance"],
    )
    return make_card(fig=grille, title="Top titulaires", lg=12, xl=12)


@callback(
    Output(
        {"type": GRID_TYPE, "context": "acheteur", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "acheteur", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State(component_id="acheteur_url", component_property="pathname"),
    State(component_id="acheteur_year", component_property="value"),
    prevent_initial_call=True,
)
def get_top_titulaires_rows(request, pathname, ach_year):
    if request is None or not pathname:
        return no_update
    where_sql, params = _acheteur_scope(pathname, ach_year)
    return fetch_top_org_page(
        "titulaire", where_sql, params, request, ["titulaire_distance"]
    )
```

Ajuster les imports en tête de `src/pages/acheteur.py` :

- retirer `get_top_org_ag_grid` de l'import `from src.figures import (...)` ;
- ajouter `from src.utils.top_org_grid import (GRID_TYPE, fetch_top_org_page, scope_key, top_org_grid)` ;
- vérifier que `MATCH`, `State` et `no_update` sont bien importés depuis `dash`
  (les ajouter à l'import existant sinon).

Dans `src/pages/titulaire.py`, remplacer le callback `get_top_acheteurs`
(lignes 431-445) par :

```python
@callback(
    Output(component_id="top10_acheteurs", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_top_acheteurs(pathname, titulaire_year):
    # Cf. src/pages/acheteur.py : la grille est alimentée page par page (#142).
    return top_org_grid(
        "titulaire",
        "acheteur",
        scope_key(pathname, titulaire_year),
        ["titulaire_distance"],
    )


@callback(
    Output(
        {"type": GRID_TYPE, "context": "titulaire", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "titulaire", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State(component_id="titulaire_url", component_property="pathname"),
    State(component_id="titulaire_year", component_property="value"),
    prevent_initial_call=True,
)
def get_top_acheteurs_rows(request, pathname, titulaire_year):
    if request is None or not pathname:
        return no_update
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return fetch_top_org_page(
        "acheteur", where_sql, params, request, ["titulaire_distance"]
    )
```

Mêmes ajustements d'imports que pour la page acheteur.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/test_fiches_top_org.py tests/test_top_org_grid.py -v`
Attendu : tous PASS.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/pages/acheteur.py src/pages/titulaire.py tests/test_fiches_top_org.py
git add src/pages/acheteur.py src/pages/titulaire.py tests/test_fiches_top_org.py
git commit -m "Tops des fiches paginés côté serveur #142"
```

---

### Task 6 : branchement de l'observatoire et du tableau

**Files:**

- Modify: `src/figures.py:1551-1700` (`build_dashboard_cards`, cards top)
- Modify: `src/pages/observatoire.py:666-678` (`_compute_dashboard_children`)
  et ajout d'un callback de datasource
- Modify: `src/pages/tableau.py:1026-1044` (`_cards_pour_filtre`) et ajout
  d'un callback de datasource
- Test: `tests/test_figures.py` (adaptation), `tests/test_top_org_grid.py`

**Interfaces:**

- Consumes: Task 3 (`fetch_top_org_page`), Task 4 (`top_org_grid`,
  `scope_key`, `GRID_TYPE`).
- Produces: `build_dashboard_cards(dff, order=None, theme=None, context="observatoire", scope="")`.

- [ ] **Step 1 : écrire les tests qui échouent**

Dans `tests/test_figures.py`, remplacer
`test_build_dashboard_cards_top_org_cards_use_ag_grid` par :

```python
def test_build_dashboard_cards_top_org_cards_sont_paginees_serveur():
    """Les cards top passent en modèle infinite (#142) : plus de classement
    embarqué dans la page, donc plus de troncature à 100 lignes."""
    import dash_ag_grid as dag
    from dash import dash_table

    build_dashboard_cards, dff = _cards_de_test()
    cards = build_dashboard_cards(dff, context="observatoire", scope="abc123")

    for card_id, org_type in (("top-acheteurs", "acheteur"), ("top-titulaires", "titulaire")):
        card = next(
            c
            for c in cards
            if isinstance(getattr(c, "id", None), dict) and c.id.get("index") == card_id
        )
        grids = _find_components(card, dag.AgGrid)
        tables = _find_components(card, dash_table.DataTable)

        assert grids, f"aucune AgGrid dans la card {card_id}"
        assert grids[0].rowModelType == "infinite"
        assert grids[0].rowData is None
        assert grids[0].id == {
            "type": "top-org-grid",
            "context": "observatoire",
            "org_type": org_type,
            "scope": "abc123",
        }
        assert not tables, f"DataTable encore présent dans la card {card_id}"
```

Ajouter dans `tests/test_top_org_grid.py` :

```python
def test_callbacks_datasource_enregistres_pour_chaque_contexte():
    """Un callback getRowsResponse par contexte, sinon deux pages écriraient
    la même sortie (Dash refuse une sortie dupliquée).

    Les clés de GLOBAL_CALLBACK_MAP sont les ids sérialisés en JSON à clés
    triées, par exemple :
    {"context":"acheteur","org_type":["MATCH"],"scope":["MATCH"],"type":"top-org-grid"}
    """
    import src.app  # noqa: F401  # instancie Dash → register_page()
    from dash._callback import GLOBAL_CALLBACK_MAP

    cles = [
        k.replace(" ", "")
        for k in GLOBAL_CALLBACK_MAP
        if "top-org-grid" in k and "getRowsResponse" in k
    ]
    contextes = {
        contexte
        for contexte in ("observatoire", "tableau", "acheteur", "titulaire")
        if any(f'"context":"{contexte}"' in k for k in cles)
    }

    assert contextes == {"observatoire", "tableau", "acheteur", "titulaire"}
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/test_figures.py -k top_org tests/test_top_org_grid.py -v`
Attendu : ÉCHEC — `build_dashboard_cards() got an unexpected keyword argument 'context'`,
et le test des callbacks ne trouve que les contextes `acheteur`/`titulaire`.

- [ ] **Step 3 : implémenter**

Dans `src/figures.py`, modifier la signature de `build_dashboard_cards` :

```python
def build_dashboard_cards(
    dff: pl.DataFrame,
    order: list[str] | None = None,
    theme: str | None = None,
    context: str = "observatoire",
    scope: str = "",
) -> list:
```

Compléter sa docstring : « `context` distingue les deux appelants
(`observatoire` / `tableau`) : chacun déclare son propre callback de
datasource pour les grilles top, et deux pages ne peuvent pas alimenter la
même sortie. `scope` identifie le périmètre courant et force le remontage des
grilles quand il change (cf. `src.utils.top_org_grid.scope_key`). »

Remplacer les deux blocs `get_top_org_ag_grid` (lignes ~1662 et ~1675) par :

```python
    # Import local : src.utils.top_org_grid importe le thème AG Grid depuis ce
    # module, un import en tête créerait un cycle.
    from src.utils.top_org_grid import top_org_grid

    top_acheteurs = top_org_grid(context, "acheteur", scope)
    cards.append(
        make_card(
            title="Top acheteurs",
            fig=top_acheteurs,
            lg=12,
            xl=8,
            card_id="top-acheteurs",
        )
    )

    top_titulaires = top_org_grid(context, "titulaire", scope)
    cards.append(
        make_card(
            title="Top titulaires",
            fig=top_titulaires,
            lg=12,
            xl=8,
            card_id="top-titulaires",
        )
    )
```

Dans `src/pages/observatoire.py`, `_compute_dashboard_children` :

```python
    dff = prepare_dashboard_data(columns=observatoire_cards_columns(), **filter_params)
    return build_dashboard_cards(
        dff,
        theme=theme,
        context="observatoire",
        scope=scope_key(filter_params_normalized),
    )
```

et ajouter, après `update_dashboard_cards` :

```python
@callback(
    Output(
        {
            "type": GRID_TYPE,
            "context": "observatoire",
            "org_type": MATCH,
            "scope": MATCH,
        },
        "getRowsResponse",
    ),
    Input(
        {
            "type": GRID_TYPE,
            "context": "observatoire",
            "org_type": MATCH,
            "scope": MATCH,
        },
        "getRowsRequest",
    ),
    *[State(fp[0], "value") for fp in FILTER_PARAMS],
    prevent_initial_call=True,
)
def get_top_org_rows(request, *filter_values):
    """Lignes d'une grille top, sur le périmètre courant de l'observatoire.

    Les filtres sont relus à la source (leurs composants) plutôt que dans le
    store `observatoire-filters`, écrit par le même callback que les cards.
    """
    if request is None or ctx.triggered_id is None:
        return no_update
    filter_params = {
        input_id: value
        for (input_id, _url_key, _is_multi, _default), value in zip(
            FILTER_PARAMS, filter_values
        )
    }
    where_sql, params = dashboard_filters_to_sql(**filter_params)
    return fetch_top_org_page(ctx.triggered_id["org_type"], where_sql, params, request)
```

Imports à ajouter dans `src/pages/observatoire.py` : `MATCH`, `State`, `ctx`,
`no_update` depuis `dash` (compléter l'import existant),
`from src.utils.table_sql import dashboard_filters_to_sql`, et
`from src.utils.top_org_grid import (GRID_TYPE, fetch_top_org_page, scope_key)`.

Dans `src/pages/tableau.py`, `_cards_pour_filtre` :

```python
    return build_dashboard_cards(
        dff,
        theme=theme,
        context="tableau",
        scope=scope_key(filter_model_json),
    )
```

et ajouter, après `update_mode_observatoire_cards` :

```python
@callback(
    Output(
        {"type": GRID_TYPE, "context": "tableau", "org_type": MATCH, "scope": MATCH},
        "getRowsResponse",
    ),
    Input(
        {"type": GRID_TYPE, "context": "tableau", "org_type": MATCH, "scope": MATCH},
        "getRowsRequest",
    ),
    State("tableau_grid", "filterModel"),
    prevent_initial_call=True,
)
def get_top_org_rows_tableau(request, filter_model):
    """Lignes d'une grille top, sur le filtre courant de la grille de marchés."""
    if request is None or ctx.triggered_id is None:
        return no_update
    where_sql, params = ast_to_sql(filtermodel_to_ast(filter_model or {}, schema), schema)
    return fetch_top_org_page(ctx.triggered_id["org_type"], where_sql, params, request)
```

Imports à ajouter dans `src/pages/tableau.py` : `MATCH` et `ctx` depuis `dash`
si absents, et
`from src.utils.top_org_grid import (GRID_TYPE, fetch_top_org_page, scope_key)`.
`filtermodel_to_ast`, `ast_to_sql` et `schema` y sont déjà importés (utilisés
par `_cards_pour_filtre`) ; le vérifier avant d'ajouter.

- [ ] **Step 4 : lancer les tests et vérifier qu'ils passent**

Run : `uv run pytest tests/test_figures.py tests/test_top_org_grid.py tests/test_fiches_top_org.py -v`
Attendu : PASS, sauf les tests de `get_top_org_ag_grid` encore présents dans
`tests/test_figures.py` s'ils échouent déjà — ils sont supprimés en Task 7.

- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/figures.py src/pages/observatoire.py src/pages/tableau.py tests/test_figures.py tests/test_top_org_grid.py
git add src/figures.py src/pages/observatoire.py src/pages/tableau.py tests/test_figures.py tests/test_top_org_grid.py
git commit -m "Tops de l'observatoire et du tableau paginés côté serveur #142"
```

---

### Task 7 : suppression de l'ancien code, test Selenium, vérification finale

**Files:**

- Modify: `src/figures.py` (suppression de `_top_org_aggregate` et
  `get_top_org_ag_grid`)
- Modify: `tests/test_figures.py` (suppression des tests devenus caducs)
- Create: `tests/test_top_org_grid_selenium.py`

**Interfaces:**

- Consumes: tout ce qui précède.
- Produces: rien de nouveau.

- [ ] **Step 1 : écrire le test Selenium**

Créer `tests/test_top_org_grid_selenium.py` :

```python
"""Les grilles top reçoivent réellement leurs lignes du datasource (#142).

Les tests unitaires vérifient la requête et la grille séparément ; seul un
test de bout en bout montre que le callback pattern-matching est bien
dispatché. Il tourne en debug=True (dev-renderer), qui valide la cohérence
des wildcards MATCH — la même erreur avait fait échouer la grille entité (#41).
"""

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.db import query_marches


def _an_acheteur_id():
    return query_marches("TRUE", (), columns=["acheteur_id"])["acheteur_id"][0]


def test_top_titulaires_de_la_fiche_affiche_des_lignes(dash_duo):
    from src.app import app

    ach = _an_acheteur_id()

    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + f"/acheteurs/{ach}")

    dash_duo.wait_for_element(
        "#top10_titulaires .ag-center-cols-container .ag-row", timeout=15
    )

    match_errors = [
        entry
        for entry in (dash_duo.get_logs() or [])
        if "MATCH" in str(entry.get("message", ""))
    ]
    assert not match_errors, f"Erreur dev-renderer MATCH : {match_errors}"


def test_top_acheteurs_de_l_observatoire_affiche_des_lignes(dash_duo):
    from src.app import app

    dash_duo.start_server(
        app, debug=True, use_reloader=False, dev_tools_hot_reload=False
    )
    dash_duo.wait_for_text_to_equal(".logo > h1", "colibre", timeout=6)
    dash_duo.wait_for_page(dash_duo.server_url + "/observatoire")

    dash_duo.wait_for_element(
        "#cards .ag-center-cols-container .ag-row", timeout=20
    )
```

- [ ] **Step 2 : lancer le test Selenium**

Run : `uv run pytest tests/test_top_org_grid_selenium.py -v`
Attendu : PASS. En cas d'échec, lire le message : soit le callback n'est pas
dispatché (erreur MATCH dans les logs), soit le sélecteur doit être ajusté à
la structure réelle de la card (l'inspecter avec le navigateur avant de
modifier le test).

- [ ] **Step 3 : supprimer l'ancien code**

Dans `src/figures.py`, supprimer les fonctions `_top_org_aggregate`
(lignes ~1281-1313) et `get_top_org_ag_grid` (lignes ~1316-1369). Vérifier
qu'il ne reste aucune référence :

```bash
grep -rn "get_top_org_ag_grid\|_top_org_aggregate" src/ tests/ --include=*.py
```

Attendu : aucun résultat. Si `client_grid` n'a plus d'appelant, le vérifier de
la même façon et le supprimer aussi.

Dans `tests/test_figures.py`, supprimer les tests devenus caducs :
`test_get_top_org_ag_grid_returns_grid_with_rowdata`,
`test_get_top_org_ag_grid_empty_returns_div`,
`test_top_org_aggregate_does_not_mutate_extra_columns`,
`test_get_top_org_ag_grid_truncates_to_limit`,
`test_get_top_org_ag_grid_defaults_to_100_rows`,
`test_get_top_org_ag_grid_limit_above_row_count_is_harmless`, ainsi que le
helper `_fake_marches` s'il n'a plus d'appelant dans le fichier.

- [ ] **Step 4 : lancer la suite complète**

Run : `uv run pytest`
Attendu : aucune régression. Comparer tout échec avec l'état de la branche
avant le chantier (`git stash` ou une seconde copie de travail) : ne corriger
que ce que ce chantier a cassé.

Puis les tests Selenium et d'intégration :

Run : `uv run pytest -m "selenium or integration"`

- [ ] **Step 5 : vérification manuelle dans le navigateur**

Lancer l'app avec les données de production
(`DATA_FILE_PARQUET_PATH` pointant sur `../decp-processing/decp_prod.parquet`) :

```bash
uv run run.py
```

Contrôler, en clair **et** en sombre :

1. `/observatoire` : les deux cards top affichent 10 lignes, la pagination
   fonctionne, le filtre par nom trouve une organisation absente de la
   première page, le tri par Attributions est numérique.
2. La hauteur fixe de la grille (`GRID_HEIGHT`) ne laisse ni bande vide ni
   barre de défilement verticale ; ajuster la constante si besoin et
   relancer `uv run pytest tests/test_top_org_grid.py`.
3. `/tableau` en mode observatoire (avec un filtre de colonne) : mêmes
   contrôles.
4. Une fiche acheteur à fort volume (par exemple un CHU ou une grande ville) :
   le top titulaires se pagine, changer d'année recharge bien la grille.
5. Une fiche titulaire : idem, et les liens des noms ouvrent la bonne fiche.

- [ ] **Step 6 : commit**

```bash
pre-commit run --files src/figures.py tests/test_figures.py tests/test_top_org_grid_selenium.py
git add src/figures.py tests/test_figures.py tests/test_top_org_grid_selenium.py
git commit -m "Suppression des tops client-side #142"
```

---

## Notes pour l'exécutant

- **Ne pas re-vérifier codegraph après une édition dans le même tour** : le
  watcher a environ 500 ms de retard.
- **Jamais deux `pytest` en parallèle** : `tests/conftest.py` recopie les bases
  à l'import, des runs concurrents produisent des erreurs de fixture
  trompeuses.
- **Ne pas pousser ni ouvrir de PR** sans demande explicite.
