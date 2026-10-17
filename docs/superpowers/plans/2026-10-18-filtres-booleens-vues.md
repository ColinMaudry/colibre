# Filtres booléens appliqués par une vue partagée — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un non-abonné qui ouvre `/tableau?vue=<jeton>` voit les filtres booléens de la vue appliqués (grille, compteurs, export, pastilles), jusqu'à ce que son filtre diffère de celui de la vue.

**Architecture:** Une fonction pure `vue_autorise_operateurs` dans `src/saved_views/resolve.py` relit la vue par le jeton du store `vue-resolution` et compare la forme canonique de son filtre à celle du filtre courant. Les callbacks de `/tableau` calculent `operateurs = abonné or vue_autorise_operateurs(...)` ; les pastilles reçoivent le même calcul par un paramètre optionnel de `register_filter_pills_callbacks`.

**Tech Stack:** Python, Dash 4, Dash AG Grid, SQLite (`users.sqlite`), DuckDB, pytest, `dash[testing]` + Selenium.

**Spec:** `docs/superpowers/specs/2026-10-18-filtres-booleens-vues-design.md`

## Global Constraints

- Imports de l'app toujours en `src.…` (CLAUDE.md).
- `vue_autorise_operateurs` n'utilise **jamais** `vue_resolution["filter_model"]` : seul `vue_resolution["token"]` sert, la vue est relue en base.
- `current_user_has_subscription()` est évalué avant `vue_autorise_operateurs` (pas de lecture SQLite pour un abonné).
- Inchangés : `update_mode_observatoire_cards`, `get_top_org_rows_tableau`, fiches acheteur/titulaire, `/observatoire`, API, MCP, mode d'emploi.
- Avant chaque `git add` : `pre-commit run --files <fichiers>` (CLAUDE.md).

## Review Focus

- Filtre **numérique ou date** dans la vue, réappliqué puis renvoyé par la vraie grille AG Grid : doit rester reconnu identique (pas de `5` → `5.0`, pas d'écart de format de date). Couvert par le test Selenium de la tâche 3 (vue avec `montant` et `dateNotification`).
- Colonne à **deux conditions** (`operator` + `conditions`) dans la vue : reconnue identique. Test `test_vue_autorise_deux_conditions` (tâche 1).
- Entrée de `filterModel` **sans effet** (colonne inconnue du schéma, type d'opérateur inconnu) présente d'un côté seulement : ignorée par la comparaison, comme elle l'est par le SQL. Test `test_vue_autorise_ignore_entree_sans_effet` (tâche 1).
- Vue **supprimée** après ouverture (jeton toujours dans le store) : plus d'exception. Couvert par `test_vue_autorise_jeton_inconnu` (tâche 1).
- `query` de vue **illisible** (pré-migration, JSON sans `ast`) : faux, sans exception. Test `test_vue_autorise_query_illisible` (tâche 1).

---

### Task 1: Règle `vue_autorise_operateurs`

**Files:**

- Modify: `src/saved_views/resolve.py`
- Test: `tests/saved_views/test_resolve.py`

**Interfaces:**

- Produces: `resolve.vue_autorise_operateurs(vue_resolution: dict | None, filter_model: dict | None, schema) -> bool`

- [ ] **Step 1: Write the failing tests** (dans `tests/saved_views/test_resolve.py`, helpers `_make_user` existants)

Helper : `_seed_ast(uid, ast) -> token` (même forme que `_seed_view`, AST fourni). La vue de référence :

```python
VUE = And([
    Condition("objet", "contains", "béton OU ciment"),
    Condition("montant", "gt", 5),
])

def _ouvrir(token):
    """Résolution telle que le store vue-resolution la contient."""
    return resolve.resolve_vue_param(token, schema)
```

Tests (chacun : `saved_views_db.init_schema()`, `uid = _make_user()`, `token = _seed_ast(uid, VUE)`, `res = _ouvrir(token)`, `fm = res["filter_model"]`) :

- `test_vue_autorise_filtre_identique` : `vue_autorise_operateurs(res, fm, schema) is True`.
- `test_vue_autorise_ordre_des_colonnes` : `dict(reversed(list(fm.items())))` → `True`.
- `test_vue_autorise_filtre_booleen_modifie` : `fm["objet"]["filter"] = "béton OU ciments"` (copie profonde) → `False`.
- `test_vue_autorise_colonne_ajoutee` : `{**fm, "acheteur_nom": {"filterType": "text", "type": "contains", "filter": "x"}}` → `False`.
- `test_vue_autorise_colonne_retiree` : `{"objet": fm["objet"]}` → `False`.
- `test_vue_autorise_sans_resolution` : `vue_autorise_operateurs(None, fm, schema) is False` ; `{**res, "found": False}` → `False` ; `{**res, "token": None}` → `False`.
- `test_vue_autorise_jeton_inconnu` : `{**res, "token": "zzzzzz"}` → `False`.
- `test_vue_autorise_ignore_filter_model_du_store` : `courant = {"objet": {"filterType": "text", "type": "contains", "filter": "a OU b"}}` ; `vue_autorise_operateurs({**res, "filter_model": courant}, courant, schema) is False`.
- `test_vue_autorise_filtre_vide` : `None` et `{}` → `False`.
- `test_vue_autorise_deux_conditions` : vue `And([Or([Condition("objet", "contains", "béton OU ciment"), Condition("objet", "contains", "brique")])])` ; filtre issu de `_ouvrir` → `True`.
- `test_vue_autorise_ignore_entree_sans_effet` : `{**fm, "colonne_inexistante": {"filterType": "text", "type": "contains", "filter": "x"}}` → `True`.
- `test_vue_autorise_query_illisible` : `saved_views_db.upsert(uid, "tableau", "Vieille", "objet=route")` puis résolution forgée `{"found": True, "token": <ce jeton>}` → `False`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/saved_views/test_resolve.py -v`
Expected: FAIL, `AttributeError: module 'src.saved_views.resolve' has no attribute 'vue_autorise_operateurs'`.

- [ ] **Step 3: Implement in `src/saved_views/resolve.py`**

- `_forme_canonique(filter_model: dict | None, schema) -> dict` : `{col: ast_to_dict(filtermodel_to_ast({col: entree}, schema))}` pour chaque colonne, **en omettant** les colonnes dont l'AST est `None` (entrée sans effet en SQL).
- `vue_autorise_operateurs(...)` : faux si `not filter_model`, si `vue_resolution` est falsy, `found` faux ou `token` absent. Relit `db.get_by_token(token)` ; faux si `None`. Lit l'AST comme `resolve_vue_param` (`json.loads(row["query"])`, `ast_from_dict(view.get("ast"))`, `ast_to_filtermodel`), en attrapant les mêmes exceptions (`json.JSONDecodeError, TypeError, AttributeError`) → faux. Retourne `_forme_canonique(vue) == _forme_canonique(filter_model)`.
- Importer `ast_to_dict` et `filtermodel_to_ast` depuis `src.utils.query_ast`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/saved_views/test_resolve.py -v`
Expected: PASS (anciens et nouveaux tests).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/saved_views/resolve.py tests/saved_views/test_resolve.py
git add src/saved_views/resolve.py tests/saved_views/test_resolve.py
git commit -m "Vues : règle d'activation des opérateurs pour un filtre identique à la vue (#97)"
```

### Task 2: Grille, compteurs et export de `/tableau`

**Files:**

- Modify: `src/pages/tableau.py` (`get_rows_tableau` l. ~648-667, `download_data` l. ~710-754)
- Test: `tests/saved_views/test_tableau_share.py`

**Interfaces:**

- Consumes: `saved_views_resolve.vue_autorise_operateurs(vue_resolution, filter_model, schema) -> bool` (tâche 1)
- Produces: `tableau._operateurs(filter_model: dict | None, vue_resolution: dict | None) -> bool` ; signatures `get_rows_tableau(request, vue_resolution)` et `download_data(n_clicks, filter_model, column_state, total, vue_resolution)`.

Données : `tests/test.parquet` a une ligne (objet « Objet test », montant 10, dateNotification 2025-01-01). `test OU zzz` trouve 1 ligne avec opérateurs, 0 sans.

- [ ] **Step 1: Write the failing tests**

Helper `_seed_ast(uid, ast)` comme en tâche 1. Vue : `And([Condition("objet", "contains", "test OU zzz")])`. Non-abonné : `monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)`. `res = resolve.resolve_vue_param(token, schema)` (importer `schema` depuis `src.db`).

- `test_get_rows_vue_non_abonne` :
  ```python
  req = {"filterModel": res["filter_model"], "startRow": 0, "endRow": 100}
  rows, total, _ = tableau.get_rows_tableau(req, res)
  assert rows["rowCount"] == 1 and total == 1
  modifie = {"objet": {**res["filter_model"]["objet"], "filter": "test OU zzzz"}}
  _, total, _ = tableau.get_rows_tableau({**req, "filterModel": modifie}, res)
  assert total == 0
  _, total, _ = tableau.get_rows_tableau(req, None)
  assert total == 0
  ```
- `test_export_vue_non_abonne` : `out = tableau.download_data(1, res["filter_model"], [], 1, res)` ; `out["filename"]` finit par `.xlsx` ; `openpyxl.load_workbook(io.BytesIO(base64.b64decode(out["content"]))).active.max_row == 2` (en-tête + la ligne ; sans l'exception, l'export serait vide). Même procédé de lecture que `tests/test_excel.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -k "vue_non_abonne" -v`
Expected: FAIL, `TypeError` (argument `vue_resolution` en trop).

- [ ] **Step 3: Implement in `src/pages/tableau.py`**

- `_operateurs(filter_model, vue_resolution) -> bool` : `current_user_has_subscription() or saved_views_resolve.vue_autorise_operateurs(vue_resolution, filter_model, schema)`.
- `get_rows_tableau` : ajouter `State("vue-resolution", "data")` ; `operateurs=_operateurs(filter_model, vue_resolution)` avec le `filter_model` de la requête.
- `download_data` : ajouter `State("vue-resolution", "data")` en dernier ; `operateurs=_operateurs(filter_model, vue_resolution)`. Le paramètre `total=None` existant reste avant `vue_resolution=None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -k "vue_non_abonne" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py tests/saved_views/test_tableau_share.py
git add src/pages/tableau.py tests/saved_views/test_tableau_share.py
git commit -m "Tableau : opérateurs actifs pour les filtres d'une vue ouverte, grille et export (#97)"
```

### Task 3: Pastilles et parcours complet (Selenium)

**Files:**

- Modify: `src/utils/filter_pills.py` (`register_filter_pills_callbacks`, l. ~203-220)
- Modify: `src/pages/tableau.py:707` (appel `register_filter_pills_callbacks`)
- Test: `tests/saved_views/test_tableau_share.py`

**Interfaces:**

- Consumes: `vue_autorise_operateurs` (tâche 1), `tableau._operateurs` n'est pas réutilisé (import circulaire `utils` → `pages`).
- Produces: `register_filter_pills_callbacks(context, grid_id, clear_active_view=False, vue_resolution_id: str | None = None)`.

- [ ] **Step 1: Write the failing Selenium test** `test_vue_partagee_operateurs_non_abonne(dash_duo, users_db_path)`

Utilisateur non connecté. Vue enregistrée (forme d'un filtre sauvegardé depuis la grille) :

```python
ast = And([
    Condition("objet", "contains", "test OU zzz"),
    Condition("montant", "gt", 5),
    Condition("dateNotification", "gt", "2024-01-01 00:00:00"),
])
```

Déroulé (sur le modèle de `test_open_shared_view_applies_and_shows_box`) :

- ouvrir `/tableau?vue=<token>_ma-vue` ;
- attendre que `#nb_rows` contienne `"1 marchés"` ;
- attendre la pastille Objet (`#tableau-filter-pills`) et vérifier qu'aucun `.filter-pills-banniere` n'est présent ;
- avec `WebDriverWait`, saisir `"z"` dans le filtre flottant de la colonne Objet (sélecteur `.ag-header-cell[col-id="objet"] … input` ou `_type_in_first_filter` si la colonne Objet est la première) jusqu'à ce que `.filter-pills-banniere` apparaisse.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/saved_views/test_tableau_share.py::test_vue_partagee_operateurs_non_abonne -v`
Expected: FAIL : la bannière est présente dès l'ouverture (les pastilles ignorent encore la vue).

- [ ] **Step 3: Implement**

- `filter_pills.py` : si `vue_resolution_id` est fourni, `_render` reçoit `State(vue_resolution_id, "data")` et passe à `filter_pills` `current_user_has_subscription() or vue_autorise_operateurs(vue_resolution, _premier(filter_model), schema)` (`schema` depuis `src.db`, import local comme celui de `current_user_has_subscription`). Sinon, callback identique à aujourd'hui.
- `tableau.py:707` : `register_filter_pills_callbacks("tableau", "tableau_grid", clear_active_view=True, vue_resolution_id="vue-resolution")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/saved_views/test_tableau_share.py tests/test_filter_pills.py -v`
Expected: PASS. Si `#nb_rows` reste à 0 avec la vue complète alors que la vue à seul filtre Objet passe, la forme canonique d'un filtre `montant`/`dateNotification` renvoyé par la grille diffère de celle de la vue : corriger `_forme_canonique` (tâche 1), pas le test.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/filter_pills.py src/pages/tableau.py tests/saved_views/test_tableau_share.py
git add src/utils/filter_pills.py src/pages/tableau.py tests/saved_views/test_tableau_share.py
git commit -m "Pastilles : pas de bandeau pour les filtres booléens d'une vue ouverte (#97)"
```

### Task 4: Régression

- [ ] **Step 1:** `uv run pytest` → tout passe.
- [ ] **Step 2:** `uv run pytest -m selenium` → tout passe.
