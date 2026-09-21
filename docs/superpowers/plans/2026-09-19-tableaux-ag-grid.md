# Migration des derniers tableaux vers AG Grid (#141) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer vers AG Grid les tableaux encore en `dash_table.DataTable` (hors prévisualisation de l'observatoire) pour qu'ils suivent le mode sombre.

**Architecture:** Une fabrique `client_grid()` (grille AG Grid client-side au thème du site) sert de base à tous les tableaux migrés. Le mode sombre est obtenu sans code spécifique : les variables `--ag-*` sont déjà redéfinies sous `[data-bs-theme="dark"]`. Les deux tableaux interactifs changent de protocole de callback : le sélecteur de colonnes passe de `selected_rows` (index) à `selectedRows` (lignes identifiées par l'id de colonne), l'admin passe de `data`/`data_previous` à `cellValueChanged`.

**Tech Stack:** Dash 4.4, dash-ag-grid 35.2 (AG Grid 35), Dash Bootstrap Components, Polars, pytest + Selenium (`dash_duo`).

**Spec:** `docs/superpowers/specs/2026-09-19-tableaux-ag-grid-design.md`

## Global Constraints

- Branche `mode-sombre-118` (pas de nouvelle branche). Base de comparaison des tests : `f9c535a`.
- Hors périmètre : la prévisualisation de l'observatoire (`observatoire-preview-table`). Ne pas toucher à la classe `DataTable`, à `prepare_table_data`, au DSL `filter_query`, à `setup_table_columns` ni au CSS `.dash-table-container` : ils partent avec elle au chantier suivant.
- Toute grille ajoutée passe par `client_grid()` (thème `AG_GRID_THEME`, `localeText: AG_GRID_LOCALE_FR`). Aucune couleur en dur pour le mode sombre.
- AG Grid 35 : sélection de lignes via l'objet `rowSelection` (`{"mode": "multiRow", ...}`), pas via l'ancienne chaîne `"multiple"` ni `checkboxSelection` sur une colonne.
- Imports applicatifs préfixés `src.`.
- Textes UI en français.
- Tests : `uv run pytest <fichiers de la tâche>` uniquement ; suite complète seulement à la tâche 7. Jamais deux pytest en parallèle (conftest recopie les bases à l'import).
- Les tests unitaires décrits dans ce plan le sont par leur comportement attendu : c'est à l'implémenteur d'écrire des assertions qui échoueraient réellement si le comportement manquait. Toute assertion d'absence doit être accompagnée d'une assertion positive prouvant que le rendu a bien eu lieu.
- Avant tout `git add` : `pre-commit run --files <fichiers>` (ruff). Ne pas commiter sans le feu vert de Colin : chaque étape « Commit » prépare le commit et attend sa validation.

## Structure des fichiers

| Fichier                                                                                                                                                                                                                                                                                                                   | Rôle dans ce chantier                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/figures.py`                                                                                                                                                                                                                                                                                                          | `client_grid()` (nouveau) ; `get_top_org_ag_grid` (+ `limit`), `make_schema_grid`, `get_sources_tables`, `make_column_picker` réécrits ; `get_top_org_table`, `get_yearly_statistics` supprimés ; callback clientside du filtre rapide du sélecteur |
| `src/utils/table.py`                                                                                                                                                                                                                                                                                                      | Helpers purs du sélecteur : `hidden_columns_from_selection`, `selection_from_hidden_columns`                                                                                                                                                        |
| `src/pages/recherche.py`                                                                                                                                                                                                                                                                                                  | Résultats de recherche en `client_grid`                                                                                                                                                                                                             |
| `src/pages/tableau.py`, `acheteur.py`, `titulaire.py`, `observatoire.py`                                                                                                                                                                                                                                                  | Paires de callbacks du sélecteur de colonnes                                                                                                                                                                                                        |
| `src/pages/admin/liste.py`                                                                                                                                                                                                                                                                                                | Grille admin éditable                                                                                                                                                                                                                               |
| `src/admin/tables.py`                                                                                                                                                                                                                                                                                                     | Suppression de `find_changed_cell`                                                                                                                                                                                                                  |
| `tests/test_figures.py`, `tests/test_schema_champs.py`, `tests/test_page_loads.py`, `tests/test_main.py`, `tests/test_table.py`, `tests/test_selecteurs_colonnes_*.py`, `tests/test_tableau_colonnes_echo.py`, `tests/test_tableau_selecteur_colonnes.py`, `tests/test_tableau_mode_observatoire_css.py`, `tests/admin/*` | Tests                                                                                                                                                                                                                                               |

---

### Task 1: Fabrique `client_grid()` et bascule des deux grilles existantes

**Files:**

- Modify: `src/figures.py` (`make_schema_grid` ~l.1221, `get_top_org_ag_grid` ~l.1357, nouvelle fonction à placer juste après `AG_GRID_LOCALE_FR`)
- Test: `tests/test_figures.py`, `tests/test_schema_champs.py`

**Interfaces:**

- Produces :

  ```python
  def client_grid(
      grid_id: str,
      column_defs: list[dict],
      row_data: list[dict],
      *,
      page_size: int | None = None,
      dash_grid_options: dict | None = None,
      **ag_grid_kwargs,
  ) -> dag.AgGrid
  ```

  et `get_top_org_ag_grid(data, org_type, extra_columns, filters=True, limit: int | None = 100)`.

- [ ] **Step 1: Écrire les tests de `client_grid`** dans `tests/test_figures.py`. Comportements à couvrir :
  - la grille renvoyée est un `dag.AgGrid` avec l'id, les `columnDefs` et le `rowData` passés ;
  - `dashGridOptions` contient le thème (`AG_GRID_THEME`), `localeText == AG_GRID_LOCALE_FR`, `domLayout == "autoHeight"`, `suppressCellFocus` ; `dangerously_allow_code` est vrai et la persistance est désactivée ;
  - sans `page_size`, pas de pagination ; avec `page_size=10`, `pagination` est vrai et `paginationPageSize == 10` ;
  - `dash_grid_options` est fusionné dans `dashGridOptions` et peut surcharger une valeur commune (ex. `domLayout`) sans faire disparaître les autres ;
  - `ag_grid_kwargs` arrive tel quel sur le composant (ex. `defaultColDef`, `getRowId`).
- [ ] **Step 2: Écrire les tests de `limit` sur `get_top_org_ag_grid`**, en reprenant les trois tests existants de `get_top_org_table` (`test_get_top_org_table_truncates_to_limit`, `..._defaults_to_100_rows`, `..._limit_above_row_count_is_harmless`, ~l.526-560) : mêmes données, mais les assertions portent sur `grid.rowData`. Le test de troncature doit vérifier que ce sont bien les organisations les mieux classées qui restent.
- [ ] **Step 3: Lancer les tests, vérifier qu'ils échouent**
      Run: `uv run pytest tests/test_figures.py -k "client_grid or top_org_ag_grid" -v`
      Expected: FAIL (`client_grid` introuvable, `limit` inattendu).
- [ ] **Step 4: Implémenter `client_grid`**

  ```python
  def client_grid(
      grid_id,
      column_defs,
      row_data,
      *,
      page_size=None,
      dash_grid_options=None,
      **ag_grid_kwargs,
  ):
      """Grille AG Grid client-side (rowData directe) au thème du site.

      Pendant de ag_grid(), réservée au modèle `infinite` de /tableau et des
      fiches. Le mode sombre suit via les variables --ag-* redéfinies sous
      [data-bs-theme="dark"] (style.css).
      """
      options = {
          "domLayout": "autoHeight",  # row model client-side : OK
          "suppressCellFocus": True,
          "localeText": AG_GRID_LOCALE_FR,
          "theme": AG_GRID_THEME,
      }
      if page_size:
          options |= {"pagination": True, "paginationPageSize": page_size}
      options |= dash_grid_options or {}
      return dag.AgGrid(
          id=grid_id,
          columnDefs=column_defs,
          rowData=row_data,
          dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
          dashGridOptions=options,
          style={"width": "100%"},
          persistence=False,
          **ag_grid_kwargs,
      )
  ```

- [ ] **Step 5: Réécrire `get_top_org_ag_grid` et `make_schema_grid` sur `client_grid`.**
  - `get_top_org_ag_grid` : ajouter `limit: int | None = 100`, appliquer `dff = dff.head(limit)` après `_top_org_aggregate` et avant `add_links` (l'agrégat est trié par attributions décroissantes). Reporter dans sa docstring l'explication de `get_top_org_table` sur le volume (82 934 titulaires, 33,6 Mo). Appel : `client_grid(f"top10_{org_type}", column_defs, dff.to_dicts(), page_size=10, columnSize="responsiveSizeToFit")`. Supprimer le commentaire devenu faux sur « ag_grid() du Lot 1 ».
  - `make_schema_grid` : `client_grid("schema_champs_grid", [...mêmes columnDefs...], schema_field_rows(), dash_grid_options={"enableCellTextSelection": True, "ensureDomOrder": True}, defaultColDef={...inchangé...})`.
  - Aucune différence de rendu attendue : mêmes options qu'avant.
- [ ] **Step 6: Lancer les tests**
      Run: `uv run pytest tests/test_figures.py tests/test_schema_champs.py -v`
      Expected: PASS (les anciens tests de `get_top_org_table` passent toujours à ce stade).
- [ ] **Step 7: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/figures.py tests/test_figures.py
  git add src/figures.py tests/test_figures.py
  git commit -m "client_grid() : fabrique commune des grilles AG Grid client-side #141"
  ```

---

### Task 2: Top acheteurs/titulaires de l'observatoire en AG Grid, suppression du code mort

**Files:**

- Modify: `src/figures.py` (`build_dashboard_cards` ~l.1665-1690 ; suppression de `get_top_org_table` ~l.1317 et `get_yearly_statistics` ~l.104)
- Test: `tests/test_figures.py`, `tests/test_observatoire_cards_columns.py`

**Interfaces:**

- Consumes : `get_top_org_ag_grid(..., limit=100)` (tâche 1).

- [ ] **Step 1: Écrire le test** : `build_dashboard_cards` produit, pour les cards `top-acheteurs` et `top-titulaires`, un `dag.AgGrid` (et non plus un `DataTable`) avec des lignes. Chercher dans `tests/test_figures.py` / `tests/test_observatoire_cards_columns.py` comment les tests existants appellent `build_dashboard_cards` et parcourent son résultat, et suivre ce modèle.
- [ ] **Step 2: Vérifier qu'il échoue**
      Run: `uv run pytest tests/test_figures.py -k dashboard -v`
      Expected: FAIL (le composant trouvé est un `DataTable`).
- [ ] **Step 3: Implémenter.** Dans `build_dashboard_cards`, remplacer les deux appels `get_top_org_table(lff, org_type=..., filters=False, extra_columns=[])` par `get_top_org_ag_grid(lff, org_type=..., extra_columns=[], filters=False)`. Supprimer `get_top_org_table` et `get_yearly_statistics`. Mettre à jour la docstring de `_top_org_aggregate` (elle cite `get_top_org_table`).
- [ ] **Step 4: Supprimer les tests de `get_top_org_table`** (`test_get_top_org_table_still_returns_datatable_after_refactor` et les trois tests de `limit`, déjà reportés à la tâche 1). Vérifier qu'aucune autre référence ne subsiste :
      Run: `grep -rn "get_top_org_table\|get_yearly_statistics" src tests`
      Expected: aucune ligne.
- [ ] **Step 5: Lancer les tests**
      Run: `uv run pytest tests/test_figures.py tests/test_observatoire_cards_columns.py tests/test_theme_cache.py -v`
      Expected: PASS.
- [ ] **Step 6: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/figures.py tests/test_figures.py
  git add src/figures.py tests/test_figures.py
  git commit -m "Top acheteurs/titulaires de l'observatoire en AG Grid #141"
  ```

---

### Task 3: Tableau des sources (`/projet/donnees`)

**Files:**

- Modify: `src/figures.py` (`get_sources_tables` ~l.211)
- Test: `tests/test_page_loads.py`

- [ ] **Step 1: Écrire les tests** dans `tests/test_page_loads.py` (il en existe déjà trois sur `get_sources_tables`, dont un avec un CSV construit dans `tmp_path`, ~l.53 : s'en inspirer). Comportements :
  - avec un CSV valide : le résultat contient un `dag.AgGrid` d'id `source_table` ; ses lignes sont triées par `nb_marchés` décroissant ; la cellule « nom » contient le lien `<a href="…">` ; les colonnes `nom` et `organisation` ont `cellRenderer: "markdown"`, `wrapText` et `autoHeight` ; les colonnes de nombres sont alignées à droite ;
  - les trois tests existants (CSV non défini, CSV absent) passent toujours.
- [ ] **Step 2: Vérifier qu'ils échouent**
      Run: `uv run pytest tests/test_page_loads.py -v`
      Expected: FAIL sur les nouveaux tests.
- [ ] **Step 3: Implémenter.** Garder la préparation Polars existante (lien, tri, `format_number`). Remplacer le `DataTable` par :

  ```python
  column_defs = []
  for col in dff.columns:
      col_def = {"field": col, "headerName": columns[col], "sortable": True}
      if col in ("nom", "organisation"):
          col_def |= {
              "cellRenderer": "markdown",
              "wrapText": True,
              "autoHeight": True,
              "flex": 2,
              "minWidth": 220,
          }
      elif col in ("nb_marchés", "nb_acheteurs"):
          col_def |= {"type": "rightAligned", "flex": 1}
      else:
          col_def["flex"] = 1
      column_defs.append(col_def)

  return html.Div(
      client_grid(
          "source_table",
          column_defs,
          dff.to_dicts(),
          defaultColDef={"valueFormatter": {"function": "params.value ?? 'N/A'"}},
      )
  )
  ```

  Attention au tri : `nb_marchés` et `nb_acheteurs` sont des chaînes formatées après `format_number`, donc un tri AG Grid sur ces colonnes serait alphabétique. Soit garder les valeurs numériques dans le `rowData` et formater côté grille (`valueFormatter` avec `d3.format` ou `Intl.NumberFormat('fr-FR')`, cf. `src/assets/dashAgGridFunctions.js`), soit poser un `comparator` numérique. Choisir la première option si elle reste simple, et vérifier le tri dans le navigateur.

- [ ] **Step 4: Lancer les tests**
      Run: `uv run pytest tests/test_page_loads.py -v`
      Expected: PASS.
- [ ] **Step 5: Vérifier dans le navigateur** : `/projet/donnees`, en clair et en sombre (compte abonné avec le switch ☀/☾), tri par nombre de marchés dans les deux sens, liens cliquables.
- [ ] **Step 6: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/figures.py tests/test_page_loads.py
  git add src/figures.py tests/test_page_loads.py
  git commit -m "Tableau des sources de données en AG Grid #141"
  ```

---

### Task 4: Résultats de recherche (accueil)

**Files:**

- Modify: `src/pages/recherche.py` (~l.270-300 ; import de `DataTable` et `setup_table_columns` l.7 et l.13)
- Test: `tests/test_main.py` (`test_001_logo_and_search` ~l.36-60, test du lien observatoire ~l.230-250)

- [ ] **Step 1: Adapter les tests Selenium** de `tests/test_main.py` au DOM AG Grid, sans affaiblir ce qu'ils vérifient :
  - « une seule ligne de résultat » : compter les `.ag-center-cols-container .ag-row` de `#results_{org_type}_datatable` ;
  - « bon nom » : `.ag-cell[col-id="{org_type}_nom"]` ;
  - lien observatoire : `#results_acheteur_datatable .ag-cell[col-id="acheteur_nom"] a[href*="observatoire"]`.
    L'id `results_{org_type}_datatable` est conservé.
- [ ] **Step 2: Vérifier qu'ils échouent**
      Run: `uv run pytest tests/test_main.py -k "search or observatoire" -v`
      Expected: FAIL (aucun `.ag-row`).
- [ ] **Step 3: Implémenter.** Ajouter dans `recherche.py` un convertisseur local :

  ```python
  def _result_column_defs(dff: pl.DataFrame) -> list[dict]:
      """columnDefs des résultats de recherche (liens markdown, infobulle d'en-tête)."""
      defs = []
      for col in dff.columns:
          meta = DATA_SCHEMA.get(col, {})
          col_def = {
              "field": col,
              "headerName": meta.get("title", col),
              "cellRenderer": "markdown",
              "wrapText": True,
              "autoHeight": True,
          }
          if meta.get("description"):
              col_def["headerTooltip"] = meta["description"]
          defs.append(col_def)
      return defs
  ```

  Puis remplacer le `DataTable(...)` par `client_grid(f"results_{org_type}_datatable", _result_column_defs(results), results.to_dicts(), page_size=10, defaultColDef={"sortable": False, "filter": False, "flex": 1, "minWidth": 120})`. Retirer les imports devenus inutiles (`DataTable`, `setup_table_columns`). Vérifier d'abord quelles colonnes `search_org` renvoie (`src/utils/search.py`) : si une colonne technique (ex. `*_tooltip`) était masquée par l'ancien tableau, la masquer ici aussi.

- [ ] **Step 4: Lancer les tests**
      Run: `uv run pytest tests/test_main.py -v`
      Expected: PASS.
- [ ] **Step 5: Vérifier dans le navigateur** : recherche d'un acheteur et d'un titulaire, en clair et en sombre ; lien 📊 vers l'observatoire ; pagination quand il y a plus de 10 résultats.
- [ ] **Step 6: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/pages/recherche.py tests/test_main.py
  git add src/pages/recherche.py tests/test_main.py
  git commit -m "Résultats de recherche en AG Grid #141"
  ```

---

### Task 5: Sélecteur de colonnes (4 pages)

**Files:**

- Modify: `src/figures.py` (`make_column_picker` ~l.1174 ; callback clientside du filtre rapide)
- Modify: `src/utils/table.py` (helpers purs, à placer près de `get_default_hidden_columns`)
- Modify: `src/pages/tableau.py` (~l.681-740), `src/pages/acheteur.py` (~l.437-470), `src/pages/titulaire.py` (~l.473-506), `src/pages/observatoire.py` (~l.854-895)
- Test: `tests/test_table.py`, `tests/test_selecteurs_colonnes_sans_echo.py`, `tests/test_tableau_colonnes_echo.py`, `tests/test_selecteurs_colonnes_navigateur.py`, `tests/test_tableau_selecteur_colonnes.py`, `tests/test_tableau_mode_observatoire_css.py`

**Interfaces:**

- Consumes : `client_grid` (tâche 1).
- Produces (dans `src/utils/table.py`) :

  ```python
  def hidden_columns_from_selection(selected_rows: list[dict] | None) -> list[str]
  def selection_from_hidden_columns(hidden_columns: list[str]) -> dict  # {"ids": [...]}
  ```

- [ ] **Step 1: Tests unitaires des helpers** dans `tests/test_table.py` :
  - `hidden_columns_from_selection` : renvoie les colonnes de `COLUMNS` absentes de la sélection, dans l'ordre de `COLUMNS` ; `[]` et `None` donnent toutes les colonnes (tout décoché est un choix explicite) ; les lignes ne portent que la clé `id` utile.
  - `selection_from_hidden_columns` : renvoie `{"ids": [...]}` avec les colonnes visibles, dans l'ordre de `COLUMNS` ; `[]` donne toutes les colonnes.
  - Aller-retour : `hidden_columns_from_selection([{"id": i} for i in selection_from_hidden_columns(h)["ids"]]) == h` pour un `h` non trivial.
- [ ] **Step 2: Tests de structure et de garde anti-écho.**
  - Adapter `tests/test_selecteurs_colonnes_sans_echo.py` et `tests/test_tableau_colonnes_echo.py` : la sortie cherchée devient `Output("<cases>", "selectedRows")` ; ils continuent de vérifier que seule l'ouverture de la modale alimente les cases.
  - Ajouter, pour chacune des 4 pages (paramétré), un test du callback « cases → store » appelé directement : quand l'ensemble masqué calculé est identique au store courant, il renvoie `no_update` ; quand le store est `None`, la comparaison se fait avec `get_default_hidden_columns(<page du store>)` ; quand la sélection diffère, il renvoie la nouvelle liste.
- [ ] **Step 3: Vérifier qu'ils échouent**
      Run: `uv run pytest tests/test_table.py tests/test_selecteurs_colonnes_sans_echo.py tests/test_tableau_colonnes_echo.py -v`
      Expected: FAIL.
- [ ] **Step 4: Implémenter les helpers** dans `src/utils/table.py` :

  ```python
  def hidden_columns_from_selection(selected_rows):
      """Colonnes masquées déduites des lignes cochées du sélecteur (AG Grid).

      [] (tout décoché) est un choix explicite : toutes les colonnes masquées.
      """
      selected = {row["id"] for row in (selected_rows or [])}
      return [col for col in COLUMNS if col not in selected]


  def selection_from_hidden_columns(hidden_columns):
      """Valeur de `selectedRows` cochant les colonnes visibles (par id de ligne)."""
      hidden = set(hidden_columns)
      return {"ids": [col for col in COLUMNS if col not in hidden]}
  ```

- [ ] **Step 5: Réécrire `make_column_picker(page)`** dans `src/figures.py` :

  ```python
  def make_column_picker(page: str):
      rows = [
          {
              "id": col,
              "name": DATA_SCHEMA[col]["title"],
              "description": DATA_SCHEMA[col]["description"],
          }
          for col in schema.names()
      ]
      return html.Div(
          [
              dbc.Input(
                  id={"type": "column-search", "page": page},
                  type="search",
                  placeholder="Rechercher une colonne…",
                  className="mb-2",
                  debounce=False,
              ),
              client_grid(
                  f"{page}_column_list",
                  [
                      {"field": "name", "headerName": "Nom", "flex": 1, "minWidth": 200},
                      {
                          "field": "description",
                          "headerName": "Description",
                          "flex": 2,
                          "minWidth": 300,
                          "wrapText": True,
                          "autoHeight": True,
                      },
                  ],
                  rows,
                  dash_grid_options={
                      "rowSelection": {
                          "mode": "multiRow",
                          "checkboxes": True,
                          "headerCheckbox": True,
                          "selectAll": "filtered",
                          "enableClickSelection": True,
                      },
                  },
                  getRowId="params.data.id",
                  defaultColDef={"sortable": False, "filter": False},
              ),
          ]
      )
  ```

  Vérifier dans les imports de `figures.py` : `dbc`, `schema`, et depuis `dash` : `MATCH`, `Input`, `State`, `clientside_callback`. `autoHeight` (donc `domLayout: "autoHeight"`) rend les 63 lignes dans le DOM, ce qui est nécessaire aux tests Selenium qui parcourent toutes les cases.

  Filtre rapide : un seul callback clientside au niveau module dans `src/figures.py`, à côté de `make_column_picker` :

  ```python
  clientside_callback(
      """
      function (value, id) {
          const api = dash_ag_grid.getApi(id.page + "_column_list");
          if (api) { api.setGridOption("quickFilterText", value || ""); }
      }
      """,
      Input({"type": "column-search", "page": MATCH}, "value"),
      State({"type": "column-search", "page": MATCH}, "id"),
      prevent_initial_call=True,
  )
  ```

  Dash 4 accepte les callbacks sans `Output`. Si Dash refuse un callback `MATCH` sans sortie au démarrage, ajouter en sortie `Output({"type": "column-search", "page": MATCH}, "className")` et renvoyer `window.dash_clientside.no_update` : signaler ce choix dans le rapport de tâche.

- [ ] **Step 6: Réécrire les 4 paires de callbacks.** Même schéma sur chaque page, avec son store, sa modale et sa page de défauts :

  | Page (module)  | Cases                              | Modale (`is_open`)                   | Store                         | `get_default_hidden_columns(...)`                     |
  | -------------- | ---------------------------------- | ------------------------------------ | ----------------------------- | ----------------------------------------------------- |
  | `tableau`      | `tableau_column_list`              | `tableau_columns`                    | `tableau-hidden-columns`      | `"tableau"`                                           |
  | `acheteur`     | `acheteur_column_list`             | `acheteur_columns`                   | `acheteur-hidden-columns`     | `"acheteur"`                                          |
  | `titulaire`    | `titulaire_column_list`            | `titulaire_columns`                  | `titulaire-hidden-columns`    | `"titulaire"`                                         |
  | `observatoire` | `observatoire_preview_column_list` | `observatoire-preview-columns-modal` | `observatoire-hidden-columns` | reprendre la valeur actuelle du fichier (`"tableau"`) |

  Cases → store (exemple `tableau`) :

  ```python
  @callback(
      Output("tableau-hidden-columns", "data", allow_duplicate=True),
      Input("tableau_column_list", "selectedRows"),
      State("tableau-hidden-columns", "data"),
      prevent_initial_call=True,
  )
  def update_hidden_columns_from_checkboxes(selected_rows, current_hidden):
      hidden = hidden_columns_from_selection(selected_rows)
      # Garde anti-écho (#139, #141) : poser selectedRows depuis le serveur à
      # l'ouverture de la modale fait réémettre selectedRows par AG Grid. Si
      # l'état calculé est déjà celui du store, ne rien réécrire.
      reference = (
          current_hidden
          if current_hidden is not None
          else get_default_hidden_columns("tableau")
      )
      if set(hidden) == set(reference):
          return no_update
      return hidden
  ```

  Store → cases (exemple `tableau`) : conserver la docstring existante, remplacer la sortie par `Output("tableau_column_list", "selectedRows")` et le retour par `selection_from_hidden_columns(hidden_cols)`, en gardant la distinction `None` / `[]` déjà en place. Supprimer le calcul par index `COLUMNS.index(...)`. Dans `tableau.py`, garder le commentaire sur `[]` vs `None` en l'adaptant.

- [ ] **Step 7: Lancer les tests unitaires**
      Run: `uv run pytest tests/test_table.py tests/test_selecteurs_colonnes_sans_echo.py tests/test_tableau_colonnes_echo.py -v`
      Expected: PASS.
- [ ] **Step 8: Adapter les tests Selenium** (`tests/test_selecteurs_colonnes_navigateur.py`, `tests/test_tableau_selecteur_colonnes.py`, `tests/test_tableau_mode_observatoire_css.py`) : les cases deviennent `#<cases> .ag-row .ag-selection-checkbox input` (vérifier le sélecteur exact dans le DOM rendu), la case d'en-tête `#<cases> .ag-header-select-all input`. Ajouter dans `tests/test_tableau_selecteur_colonnes.py` :
  - filtre rapide : saisir un mot du titre d'une colonne dans le champ de recherche réduit le nombre de lignes affichées, et la ligne attendue est présente ;
  - « tout cocher » avec un filtre actif ne coche que les lignes filtrées (les autres colonnes gardent leur état après effacement du filtre) ;
  - pas d'écho : ouvrir la modale, la fermer sans rien toucher, recharger la page ; les colonnes affichées dans la grille `tableau_grid` sont inchangées.
- [ ] **Step 9: Lancer les tests Selenium de la tâche**
      Run: `uv run pytest tests/test_selecteurs_colonnes_navigateur.py tests/test_tableau_selecteur_colonnes.py tests/test_tableau_mode_observatoire_css.py -v`
      Expected: PASS.
- [ ] **Step 10: Vérifier dans le navigateur**, sur les 4 pages (`/tableau`, une fiche acheteur, une fiche titulaire, l'aperçu de l'observatoire), en clair et en sombre : ouverture (cases cochées = colonnes affichées), décocher une colonne (elle disparaît de la grille), recherche, « tout cocher », fermeture puis rechargement (choix conservé). Sur `/tableau`, appliquer une vue partagée puis ouvrir la modale : les cases reflètent la vue et ne l'écrasent pas.
- [ ] **Step 11: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/figures.py src/utils/table.py src/pages/tableau.py src/pages/acheteur.py src/pages/titulaire.py src/pages/observatoire.py tests/test_table.py tests/test_selecteurs_colonnes_sans_echo.py tests/test_tableau_colonnes_echo.py tests/test_selecteurs_colonnes_navigateur.py tests/test_tableau_selecteur_colonnes.py tests/test_tableau_mode_observatoire_css.py
  git add <mêmes fichiers>
  git commit -m "Sélecteur de colonnes en AG Grid, avec recherche et tout cocher #141"
  ```

---

### Task 6: Interface d'administration

**Files:**

- Modify: `src/pages/admin/liste.py`
- Modify: `src/admin/tables.py` (suppression de `find_changed_cell`)
- Test: `tests/admin/test_callback_guard.py`, `tests/admin/test_tables.py`, `tests/admin/test_liste_options.py`, nouveau `tests/admin/test_liste_grille.py`

**Interfaces:**

- Consumes : `client_grid` (tâche 1).
- Produces : `_update_table(selected_table, cell_changes)`, avec les sorties `rowData`, `columnDefs`, `admin-alerts.children`.

Format de `cellValueChanged` dans dash-ag-grid 35 : une **liste** de dicts portant notamment `rowIndex`, `rowId`, `data` (ligne complète après édition), `oldValue`, `value`, `colId`. Traiter le dernier élément.

- [ ] **Step 1: Écrire les tests** :
  - `tests/admin/test_callback_guard.py` : adapter les trois tests à la nouvelle signature `_update_table(selected_table, cell_changes)`. Le chemin écriture est simulé par une liste `cellValueChanged` ; le non-admin lève toujours `PreventUpdate` avant tout accès au `ctx` ou à la base ; le test « admin autorisé » garde son intention.
  - Nouveau `tests/admin/test_liste_grille.py` (s'inspirer des fixtures `users_db_path` de `test_liste_options.py`) :
    - le layout contient un `dag.AgGrid` d'id `admin-table` avec la pagination par 20 ;
    - `_columns_for(table)` : `editable` vrai seulement pour `cfg.editable_columns` ; les colonnes de `cfg.dropdowns` ont `cellEditor == "agSelectCellEditor"` et `cellEditorParams.values` égal aux valeurs déclarées ;
    - édition valide : `set_cell` est appelé avec la clé primaire lue dans `data`, la colonne et la nouvelle valeur ; `log_action` est appelé ; l'alerte est de succès et `rowData` n'est pas renvoyé (`no_update`) ;
    - édition refusée (`set_cell` lève `ValueError`) : l'alerte est de danger, et `rowData` renvoyé est relu en base (la valeur refusée n'y figure pas, l'ancienne oui) ;
    - changement de table : `rowData` et `columnDefs` correspondent à la table choisie.
  - `tests/admin/test_tables.py` : supprimer les tests de `find_changed_cell`.
- [ ] **Step 2: Vérifier qu'ils échouent**
      Run: `uv run pytest tests/admin -v`
      Expected: FAIL.
- [ ] **Step 3: Implémenter.**

  ```python
  def _columns_for(table: str) -> list[dict]:
      cfg = all_tables()[table]
      defs = []
      for col in cfg.columns:
          col_def = {"field": col, "headerName": col, "editable": col in cfg.editable_columns}
          if col in cfg.dropdowns:
              col_def |= {
                  "cellEditor": "agSelectCellEditor",
                  "cellEditorParams": {"values": list(cfg.dropdowns[col])},
              }
          defs.append(col_def)
      return defs
  ```

  Layout : remplacer le `dash_table.DataTable` par `client_grid("admin-table", _columns_for(DEFAULT_TABLE), get_rows(DEFAULT_TABLE), page_size=20, defaultColDef={"sortable": True, "filter": True, "floatingFilter": True, "resizable": True, "minWidth": 120})`. Supprimer `_dropdown_for` et l'import de `dash_table`.

  Callback :

  ```python
  @callback(
      Output("admin-table", "rowData"),
      Output("admin-table", "columnDefs"),
      Output("admin-alerts", "children"),
      Input("admin-table-select", "value"),
      Input("admin-table", "cellValueChanged"),
      prevent_initial_call=True,
  )
  def _update_table(selected_table, cell_changes):
      # (conserver le commentaire #110 existant)
      if not is_admin():
          raise PreventUpdate

      if ctx.triggered_id == "admin-table-select":
          return get_rows(selected_table), _columns_for(selected_table), None

      if not cell_changes:
          return no_update, no_update, None
      change = cell_changes[-1]
      column, old_value, new_value = change["colId"], change["oldValue"], change["value"]
      if old_value == new_value:
          return no_update, no_update, None

      cfg = all_tables()[selected_table]
      row = change["data"]
      try:
          set_cell(selected_table, row[cfg.pk], column, new_value)
      except ValueError as exc:
          # La cellule affiche encore la valeur refusée : on relit la base.
          return (
              get_rows(selected_table),
              no_update,
              dbc.Alert(str(exc), color="danger", dismissable=True),
          )

      log_action(
          current_user.email,
          f"edit_{selected_table}",
          cfg.target_user_id(row),
          f"{column}: {old_value!r} → {new_value!r}",
      )
      return (
          no_update,
          no_update,
          dbc.Alert("Modification enregistrée.", color="success", dismissable=True),
      )
  ```

  Supprimer `find_changed_cell` de `src/admin/tables.py` et de l'import de `liste.py`, puis vérifier :
  Run: `grep -rn "find_changed_cell\|data_previous\|_dropdown_for" src tests`
  Expected: aucune ligne.

- [ ] **Step 4: Lancer les tests**
      Run: `uv run pytest tests/admin -v`
      Expected: PASS.
- [ ] **Step 5: Vérifier dans le navigateur** (compte admin, `/admin`), en clair et en sombre : changer de table ; éditer une cellule texte ; éditer une cellule à liste déroulante ; provoquer un refus (valeur invalide pour `set_cell`) et constater le retour à l'ancienne valeur ; vérifier dans la table `admin_actions` que l'édition valide est journalisée.
- [ ] **Step 6: Commit (après feu vert)**
  ```bash
  pre-commit run --files src/pages/admin/liste.py src/admin/tables.py tests/admin/test_callback_guard.py tests/admin/test_tables.py tests/admin/test_liste_grille.py
  git add <mêmes fichiers>
  git commit -m "Interface d'administration en AG Grid #141"
  ```

---

### Task 7: Vérification finale

**Files:** aucun, sauf corrections.

- [ ] **Step 1: Vérifier qu'il ne reste que la prévisualisation en `dash_table`**
      Run: `grep -rn "dash_table\|DataTable(" src --include=*.py`
      Expected : uniquement la classe `DataTable` de `src/figures.py`, son usage `observatoire-preview-table` dans `src/pages/observatoire.py` et la docstring de `src/utils/table_sql.py`.
- [ ] **Step 2: Suite complète**
      Run: `uv run pytest`
      Expected : PASS. En cas d'échec, comparer avec la base : `git stash` n'est pas adapté (fichiers non suivis) ; utiliser un worktree sur `f9c535a` et y lancer le même test. Un échec présent aussi sur la base n'est pas imputable au chantier, mais il faut le signaler.
- [ ] **Step 3: Tests navigateur et intégration**
      Run: `uv run pytest -m "selenium or integration"`
      Expected : PASS, ou mêmes échecs que sur `f9c535a`.
- [ ] **Step 4: Passe visuelle finale** en clair et en sombre sur chaque tableau migré (observatoire : top acheteurs et titulaires ; `/projet/donnees` ; accueil ; les 4 sélecteurs ; `/admin`) : fond, en-tête, lignes alternées, filtres flottants, pagination, cases à cocher et leur état coché.
- [ ] **Step 5: Rapport à Colin** : ce qui est fait, résultats des tests (sortie réelle), écarts éventuels par rapport à la spec, et rappel de ce qui reste pour le chantier de suppression de la prévisualisation (classe `DataTable`, `prepare_table_data`, `_fetch_page_sql`, `filter_table_data`, `sort_table_data`, `filter_query_to_sql`, `setup_table_columns`, CSS `.dash-table-container`).
