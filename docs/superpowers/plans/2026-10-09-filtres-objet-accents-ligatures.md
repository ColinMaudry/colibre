# Filtres Objet insensibles aux accents, ligatures et apostrophes (#147) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un filtre sur `objet` (grilles, observatoire, API REST, MCP) ignore casse, accents, ligatures œ/æ et apostrophe typographique `’`, sans ralentir les requêtes.

**Architecture:** Une colonne technique `objet_normalise` est précalculée dans `decp` au build DuckDB. Un module `src/utils/text_normalization.py` fournit la normalisation Python (saisie) et son équivalent SQL (colonne). `tokenize_text_filter`, `query_ast` et `build_where` comparent `objet_normalise` à la saisie normalisée. `schema` et `query_marches()` excluent la colonne pour qu'elle reste invisible.

**Tech Stack:** Python, DuckDB, Polars, Dash, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-09-filtres-objet-accents-ligatures-design.md`

## Global Constraints

- Imports toujours en `src.…` (jamais `utils.…`).
- Tests : vraies requêtes DuckDB, jamais de texte SQL figé ; un test qui décrit l'implémentation plutôt que le résultat est supprimé, pas réécrit.
- Avant chaque `git add` : `uv run pre-commit run --files <fichiers>` (CLAUDE.md).
- Normalisation : NFD sans marques combinantes ; `œ→oe`, `Œ→OE`, `æ→ae`, `Æ→AE` ; `’` (U+2019) → `'` ; casse inchangée (l'`ILIKE` s'en charge). Seules `contains`, `notcontains`, `startswith`/`startsWith`, `endsWith` sont normalisées ; `exact`/`equals`, `differs`, `in`, `notin`, `sort` restent sur `objet`.
- `SCHEMA_VERSION` passe de 2 à 3. La colonne n'apparaît ni dans `schema`, ni dans `COLUMNS`, ni dans `query_marches()` par défaut, ni dans l'API, ni dans le MCP, ni dans les exports.
- API et MCP gardent leur sémantique de sous-chaîne entière (`%valeur%`), sans mots ni jokers.
- `acheteur_nom`/`titulaire_nom` restent traités par `_ACCENT_INSENSITIVE_COLUMNS` (`unidecode`) : voir #150, hors périmètre.
- Tests : base DuckDB isolée `tests/colibre.duckdb` (reconstruite à chaque session) ; ne jamais toucher `./decp.duckdb`.

## Review Focus

- Saisie décomposée (« e » + U+0301) ou non latine / emoji : `normalize_text` ne doit pas échouer et reste d'accord avec la version SQL (test de parité, Task 2).
- Objet `NULL` ou vide : jamais retourné par `contains`, `startswith` ni `notcontains` (comportement existant à conserver), grille comme API (Tasks 4 et 5).
- Saisie vide, espaces seuls ou `*` seul sur la grille : même résultat qu'avant (toutes les lignes non vides) (Task 4).
- Fuite de la colonne technique : absente de `schema`, `COLUMNS`, `query_marches()`, `export_dataframe` et d'une réponse `/data` sans `columns` (Tasks 3 et 5).
- Latence : un appel de grille filtré sur `objet` reste comparable à un filtre sans normalisation (≈ 1 s sur 3,3 M de lignes), pas ×4 (Task 7).

---

### Task 1: Commiter l'état actuel (nettoyage du code mort)

L'arbre contient déjà le nettoyage du code mort, ses tests, et une première version du fix qui normalise à la volée (remplacée par les Tasks 2 à 5). On le fige pour repartir d'une base propre.

**Files:**

- Modify: `src/figures.py`, `src/utils/grid.py`, `src/utils/query_ast.py`, `src/utils/table.py`, `src/utils/table_sql.py`
- Modify/Delete: `tests/test_dashboard_filters_to_sql.py`, `tests/test_table.py`, `tests/test_table_sql.py`, `tests/saved_views/test_build_view_query.py`
- Create: `tests/test_filtre_objet_accents_oe.py`

- [ ] **Step 1: Vérifier l'état**

Run: `uv run pytest -q` — Expected: `1377 passed` (52 désélectionnés). `git status --short` liste les fichiers ci-dessus (plus des fichiers non suivis étrangers à ce chantier : ne pas les ajouter).

- [ ] **Step 2: Commit**

```bash
uv run pre-commit run --files src/figures.py src/utils/grid.py src/utils/query_ast.py src/utils/table.py src/utils/table_sql.py tests/test_dashboard_filters_to_sql.py tests/test_table.py tests/test_table_sql.py tests/test_filtre_objet_accents_oe.py
git add src/figures.py src/utils/grid.py src/utils/query_ast.py src/utils/table.py src/utils/table_sql.py tests/test_dashboard_filters_to_sql.py tests/test_table.py tests/test_table_sql.py tests/test_filtre_objet_accents_oe.py
git add -A -- tests/saved_views/test_build_view_query.py
git commit -m "Nettoyage du code mort de l'ancien chemin dash_table ; filtre Objet normalisé à la volée (#147)"
```

---

### Task 2: Module `text_normalization`

**Files:**

- Create: `src/utils/text_normalization.py`
- Test: `tests/test_text_normalization.py`

**Interfaces:**

- Produces (dans `src/utils/text_normalization.py`, sans import interne) :

  - `NORMALIZED_COLUMNS: dict[str, str] = {"objet": "objet_normalise"}`
  - `normalize_text(text: str) -> str`
  - `normalize_text_sql(expr: str) -> str` : expression DuckDB, `expr` est une expression SQL de colonne (ex. `'objet'` ou `'"objet"'`)
  - `normalized_target(column: str, quoted_col: str) -> str` : `'"objet_normalise"'` si `column` est dans `NORMALIZED_COLUMNS`, sinon `quoted_col`
  - `normalized_term(column: str, term: str) -> str` : `normalize_text(term)` si `column` est dans `NORMALIZED_COLUMNS`, sinon `term`

- [ ] **Step 1: Écrire les tests en échec** dans `tests/test_text_normalization.py`

  - `test_normalize_text_exemples` : `normalize_text("Maîtrise d’œuvre") == "Maitrise d'oeuvre"` ; `normalize_text("ÉCOLE ŒUVRE ÆON") == "ECOLE OEUVRE AEON"` ; `normalize_text("français garçon") == "francais garcon"` ; casse conservée.
  - `test_normalize_text_forme_decomposee` : `normalize_text("e\u0301cole") == "ecole"`.
  - `test_normalize_text_chaine_vide_et_non_latin` : `""` → `""` ; `"東京 😀"` renvoyé inchangé.
  - `test_parite_python_sql` (paramétré sur un échantillon : `é è ê ë à ç î ï ô ù û ü ñ`, `ÉÈÀÇ`, `œ Œ æ Æ`, `d’œuvre`, `d'oeuvre`, `""`, `"東京"`, `"e\u0301"`) : pour chaque `s`, `duckdb.connect()` exécute `SELECT {normalize_text_sql('v')} FROM (SELECT ? AS v)` avec `[s]` et le résultat est égal à `normalize_text(s)`.
  - `test_normalize_text_sql_null` : la valeur SQL `NULL` reste `NULL`.
  - `test_normalized_target_et_term` : `normalized_target("objet", '"objet"') == '"objet_normalise"'` ; `normalized_target("montant", '"montant"') == '"montant"'` ; `normalized_term("objet", "d’œuvre") == "d'oeuvre"` ; `normalized_term("acheteur_nom", "Nîmes") == "Nîmes"`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_text_normalization.py -v` — Expected: FAIL `ModuleNotFoundError: src.utils.text_normalization`.

- [ ] **Step 3: Implémenter `src/utils/text_normalization.py`**

`unicodedata.normalize("NFD", …)` puis filtrer `unicodedata.combining`, puis ligatures et apostrophe via une table de remplacement partagée par les versions Python et SQL (le SQL enchaîne `strip_accents(expr)` et des `replace(...)` imbriqués ; l'apostrophe SQL s'écrit `''''`). Reprendre les noms `_LIGATURES`/`_strip_accents` de l'actuel `src/utils/table_sql.py` comme point de départ, puis les y supprimer à la Task 4.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_text_normalization.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/utils/text_normalization.py tests/test_text_normalization.py
git add src/utils/text_normalization.py tests/test_text_normalization.py
git commit -m "Module de normalisation de texte partagé Python/SQL (#147)"
```

---

### Task 3: Colonne `objet_normalise` dans `decp`, masquée du schéma

**Files:**

- Modify: `src/db.py` (`SCHEMA_VERSION` ≈ l.171, `build_database` ≈ l.216-218, `schema` ≈ l.273, `query_marches` ≈ l.295)
- Test: `tests/test_db.py`, `tests/test_grid.py`

**Interfaces:**

- Consumes: `NORMALIZED_COLUMNS`, `normalize_text_sql` (Task 2).
- Produces : table `decp` avec une colonne `objet_normalise` par entrée de `NORMALIZED_COLUMNS` ; `src.db.schema` et `query_marches(columns=None)` sans ces colonnes.

- [ ] **Step 1: Écrire les tests en échec**

Dans `tests/test_db.py` (fixture existante `built_db`, objets « Travaux », « Études », « Ancien ») :

- `test_build_ajoute_la_colonne_objet_normalise` : sur la base construite, `SELECT objet, objet_normalise FROM decp` vérifie `objet_normalise == normalize_text(objet)` pour chaque ligne (« Études » → « Etudes »), `NULL` si `objet` est `NULL`.
- `test_colonnes_normalisees_masquees_du_schema` : `"objet_normalise" not in src.db.schema.names()` ; `"objet_normalise" not in query_marches(limit=1).columns` ; `"objet_normalise" not in src.utils.table.COLUMNS` ; mais `"objet_normalise"` est bien lisible via `query_marches(columns=["objet_normalise"], limit=1)`.

Dans `tests/test_grid.py` : `test_export_dataframe_sans_colonne_technique` : `export_dataframe(None, None, hidden_columns=[])` ne contient pas `objet_normalise`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_db.py tests/test_grid.py -v` — Expected: les 3 nouveaux tests FAIL (colonne absente).

- [ ] **Step 3: Implémenter dans `src/db.py`**

  - `build_database` : `CREATE TABLE decp AS SELECT *, <normalize_text_sql(col) AS name pour chaque entrée de NORMALIZED_COLUMNS> FROM read_parquet(...)`.
  - `SCHEMA_VERSION = 3`, avec la ligne `# 3 : #147 ajoute objet_normalise à decp` dans le commentaire existant.
  - Une constante de module pour la clause d'exclusion, construite depuis `NORMALIZED_COLUMNS.values()` : `* EXCLUDE (objet_normalise)`.
  - `schema` : `SELECT {cette clause} FROM decp LIMIT 0` ; `query_marches` : `cols = ", ".join(columns) if columns else {cette clause}`.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_db.py tests/test_grid.py tests/test_schema_version.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/db.py tests/test_db.py tests/test_grid.py
git add src/db.py tests/test_db.py tests/test_grid.py
git commit -m "decp : colonne technique objet_normalise précalculée, masquée du schéma (#147)"
```

---

### Task 4: Grilles et observatoire comparent `objet_normalise`

**Files:**

- Modify: `src/utils/table_sql.py` (`_ACCENT_NORMALIZED_COLUMNS`, `_LIGATURES`, `_strip_accents_sql`, `_strip_accents`, `text_filter_target`, `normalize_text_term`, `import unicodedata`)
- Modify: `tests/conftest.py` (nouvelles fixtures, voir ci-dessous), `tests/test_filtre_objet_accents_oe.py`
- Test: `tests/test_filtre_objet_accents_oe.py`, `tests/test_query_ast.py`

**Interfaces:**

- Consumes: `NORMALIZED_COLUMNS`, `normalized_target`, `normalized_term`, `normalize_text_sql` (Task 2) ; colonne `objet_normalise` (Task 3).
- Produces (dans `tests/conftest.py`) : fixture `con_objets` (DuckDB en mémoire, table `decp(objet, objet_normalise, acheteur_nom, titulaire_nom, "dateNotification")`, `objet_normalise` remplie par `UPDATE … SET objet_normalise = {normalize_text_sql('objet')}`) et fixture `objets_maitrise` (liste triée des 5 graphies : `Maîtrise d'œuvre`, `maitrise d'œuvre`, `maîtrise d'oeuvre`, `MAÎTRISE D'ŒUVRE`, `Maîtrise d’œuvre` avec apostrophe typographique). La table contient aussi `Travaux de voirie`, `Éclairage public`, un objet `NULL` et un objet vide. Task 5 réutilise ces fixtures.

- [ ] **Step 1: Écrire les tests en échec**

Déplacer la fixture `con` et les constantes de `tests/test_filtre_objet_accents_oe.py` vers `tests/conftest.py` sous les noms ci-dessus, en ajoutant la 5ᵉ graphie (apostrophe typographique) et la colonne `objet_normalise`. Dans `tests/test_filtre_objet_accents_oe.py`, ajouter :

- `test_contains_apostrophes_droite_et_typographique_equivalentes` paramétré sur `"d'oeuvre"`, `"d’oeuvre"`, `"d’œuvre"` : `tokenize_text_filter("objet", saisie)` retrouve les 5 graphies.
- `test_starts_with_et_ends_with_apostrophe_typographique` : `startsWith "maitrise d'oe"` et `endsWith "d'oeuvre"` retrouvent les 5 graphies.
- `test_saisie_vide_ou_espaces_retourne_tout_sauf_null_et_vide` : `tokenize_text_filter("objet", " ")` retourne les 6 objets non `NULL` et non vides.
  Les tests existants (3 graphies, `notContains`, `equals` exact, observatoire, noms) doivent rester inchangés et verts.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_filtre_objet_accents_oe.py -v` — Expected: FAIL sur les cas apostrophe typographique (la version actuelle, à la volée, ne normalise pas `’`). Que la comparaison porte sur la colonne précalculée n'a pas d'effet visible sur les résultats : seul le smoke de latence (Task 7) le prouve.

- [ ] **Step 3: Implémenter dans `src/utils/table_sql.py`**

`text_filter_target(column, quoted_col)` renvoie `normalized_target(column, quoted_col)` ; `normalize_text_term(column, term)` renvoie `normalized_term(...)` pour les colonnes de `NORMALIZED_COLUMNS`, `unidecode(term)` pour `_ACCENT_INSENSITIVE_COLUMNS`, `term` sinon. Supprimer `_ACCENT_NORMALIZED_COLUMNS`, `_LIGATURES`, `_strip_accents_sql`, `_strip_accents` et `import unicodedata`. `tokenize_text_filter` et `query_ast.py` n'ont pas d'autre changement.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_filtre_objet_accents_oe.py tests/test_query_ast.py tests/test_dashboard_filters_to_sql.py tests/test_grid.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/utils/table_sql.py tests/conftest.py tests/test_filtre_objet_accents_oe.py
git add src/utils/table_sql.py tests/conftest.py tests/test_filtre_objet_accents_oe.py
git commit -m "Grilles et observatoire : filtre Objet sur la colonne normalisée (#147)"
```

---

### Task 5: API REST et MCP

**Files:**

- Modify: `src/api/filters.py` (`build_where`, branches `contains`, `notcontains`, `startswith` ≈ l.184-192)
- Modify: `tests/api/test_filters.py` (supprimer les 3 tests qui figent `'"objet" ILIKE ?'` / `'"objet" NOT ILIKE ?'` : `grep -n "ILIKE" tests/api/test_filters.py`)
- Create: `tests/api/test_filters_objet_normalise.py`
- Test: `tests/api/test_endpoints_data.py`, `tests/mcp/test_queries.py`

**Interfaces:**

- Consumes: `normalized_target`, `normalized_term` (Task 2) ; fixtures `con_objets`, `objets_maitrise` (Task 4) ; `build_where(args: list[tuple[str, str]], schema: pl.Schema) -> tuple[str, list, str | None]` (inchangée) ; `build_where_args(named, filtres_avances)` de `src/mcp/queries.py`.

- [ ] **Step 1: Écrire les tests en échec**

Dans `tests/api/test_filters_objet_normalise.py` (schéma Polars avec `objet` et `acheteur_nom` en `pl.String`, requêtes exécutées sur `con_objets`) :

- `test_objet_contains_retrouve_toutes_les_graphies` paramétré sur `"maitrise d'oeuvre"`, `"MAÎTRISE D’ŒUVRE"`, `"maîtrise d’oeuvre"` : `build_where([("objet__contains", saisie)], SCHEMA)` retrouve les 5 graphies (sous-chaîne entière, `objets_maitrise`).
- `test_objet_notcontains_exclut_les_graphies_et_les_null` : `objet__notcontains = "maitrise"` retourne `Travaux de voirie`, `Éclairage public` et la chaîne vide, jamais `NULL` ni une graphie.
- `test_objet_startswith` : `objet__startswith = "maitrise d'oe"` retrouve les 5 graphies.
- `test_objet_exact_reste_exact` : `objet__exact = "Maîtrise d'œuvre"` ne retourne que cette ligne.
- `test_autre_colonne_non_normalisee` : `acheteur_nom__contains = "Nîmes"` garde son comportement (aucun résultat sur des valeurs sans accents).
- `test_mcp_objet_contient_equivaut_a_objet_contains` : `build_where(build_where_args({"objet_contient": "maitrise d'oeuvre"}, None), SCHEMA)` retrouve les 5 graphies.

Dans `tests/api/test_endpoints_data.py` : `test_data_sans_columns_n_expose_pas_objet_normalise` (clés d'une ligne de `/api/v1/data` sans `columns`) et `test_data_objet_normalise_inconnu_retourne_400` (`objet_normalise__contains=x` et `columns=objet_normalise` → 400). Dans `tests/mcp/test_queries.py` : `test_search_marches_objet_contient_ignore_accents` (`search_marches(objet_contient=…)` sur la base de test retourne le même total pour une saisie accentuée et la même sans accent).

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/api/test_filters_objet_normalise.py -v` — Expected: FAIL sur `contains`, `notcontains`, `startswith` et MCP.

- [ ] **Step 3: Implémenter dans `src/api/filters.py`**

Dans les trois branches, remplacer `f'"{col}"'` par `normalized_target(col, f'"{col}"')` et `v` par `normalized_term(col, v)` avant la construction du motif `%…%` / `…%`. `exact`, `differs`, `in`, `notin`, `sort` et les comparaisons restent inchangés. Supprimer les 3 tests de `tests/api/test_filters.py` repérés ci-dessus.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/api tests/mcp -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/api/filters.py tests/api/test_filters.py tests/api/test_filters_objet_normalise.py tests/api/test_endpoints_data.py tests/mcp/test_queries.py
git add src/api/filters.py tests/api/test_filters.py tests/api/test_filters_objet_normalise.py tests/api/test_endpoints_data.py tests/mcp/test_queries.py
git commit -m "API REST et MCP : filtres Objet insensibles aux accents, ligatures et apostrophes (#147)"
```

---

### Task 6: Documentation et CHANGELOG

**Files:**

- Modify: `src/api/routes.py` (≈ l.181-184, description des opérateurs `contains`/`notcontains`/`startswith` ; docstring de `data()` si elle liste ces opérateurs)
- Modify: `src/mcp/tools.py` (docstring de `rechercher_marches`, ligne `objet_contient`)
- Modify: `CHANGELOG.md` (section `#### 3.3.0`)
- Test: `tests/api/test_openapi_doc.py`, `tests/mcp/test_tools.py`

- [ ] **Step 1: Mettre à jour les textes**

  - `routes.py` : les opérateurs `contains`/`notcontains` et `startswith` précisent « insensible à la casse, aux accents, aux ligatures et aux apostrophes typographiques pour `objet` ».
  - `tools.py` : `objet_contient (texte de l'objet, insensible à la casse, aux accents, aux ligatures œ/æ et à l'apostrophe typographique)`.
  - `CHANGELOG.md`, nouvelle puce sous 3.3.0 : `- Les filtres sur l'objet (tableaux, observatoire, API REST, connecteur MCP) ne sont plus sensibles aux accents, à œ/oe ni à l'apostrophe typographique ([#147](https://github.com/colinmaudry/colibre/issues/147))`.

- [ ] **Step 2: Vérifier**

Run: `uv run pytest tests/api/test_openapi_doc.py tests/mcp/test_tools.py -v` — Expected: PASS.

- [ ] **Step 3: Commit**

```bash
uv run pre-commit run --files src/api/routes.py src/mcp/tools.py CHANGELOG.md
git add src/api/routes.py src/mcp/tools.py CHANGELOG.md
git commit -m "Doc API/MCP et CHANGELOG : filtres Objet normalisés (#147)"
```

---

### Task 7: Vérification finale sur les vraies données

**Files:** aucun (scripts jetables dans `/tmp`, supprimés à la fin).

- [ ] **Step 1: Suite complète et lint**

Run: `uv run ruff check src tests && uv run pytest -q` — Expected: `All checks passed!`, tous les tests passent (1377 + nouveaux, 0 échec). Run: `uv run pytest -m selenium -q` — Expected: 50 passés ; le seul échec admis est `test_le_mode_observatoire_persiste_apres_rechargement`, déjà rouge sur `HEAD`.

- [ ] **Step 2: Smoke sur 3,3 M de lignes** (base isolée, sans toucher `./decp.duckdb`)

Écrire un script `/tmp/smoke147.py` qui, avec `DUCKDB_PATH=/tmp/smoke147.duckdb DATA_FILE_PARQUET_PATH=../decp-processing/decp_prod.parquet DEVELOPMENT=true PYTHONPATH=.`, appelle sous un contexte Flask (`cache.init_app(..., {"CACHE_TYPE": "SimpleCache"})`) :

- `fetch_grid_page` avec `contains` sur `"maitrise d'oeuvre"`, `"MAÎTRISE D’ŒUVRE"`, `"maîtrise d’œuvre"` ;
- `GET /api/v1/data?objet__contains=maitrise d'oeuvre` (client Flask, jeton de test) et `search_marches(objet_contient=…)` pour les mêmes saisies.

Expected : même total pour les trois saisies sur chaque surface (≈ 114 901 lignes pour `%d'oeuvre%` en sous-chaîne) ; chaque appel de grille ≤ 2 s sur machine au repos (référence sans normalisation : 1,0 à 1,6 s). Le premier import reconstruit la base de smoke (≈ 20 s).

- [ ] **Step 3: Nettoyer et clore**

Run: `rm -f /tmp/smoke147.py /tmp/smoke147.duckdb*` ; `git status --short` ne montre aucun fichier de ce chantier non commité. Rapporter les totaux et les temps mesurés.
