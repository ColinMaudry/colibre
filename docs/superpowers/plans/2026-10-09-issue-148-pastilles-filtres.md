# Pastilles des filtres appliqués au-dessus des tableaux (issue #148) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher, dans la ligne `.table-meta` de la page Tableau et des fiches acheteur/titulaire, une pastille par filtre actif (« **Libellé** opérateur valeur × ») : la croix supprime le filtre, un clic sur la pastille affiche la colonne si elle est masquée puis place le curseur dans son filtre flottant.

**Architecture:** Un module partagé `src/utils/filter_pills.py` porte les fonctions pures (description d'un filtre, filterModel sans une colonne, colonnes masquées sans une colonne) et `register_filter_pills_callbacks(context, grid_id)`, appelé par `tableau.py` et par `register_entity_grid_callbacks` (fiches). Rendu et suppression sont des callbacks serveur sur le `filterModel` de la grille ; le dévoilement de colonne écrit le store `{context}-hidden-columns` existant (même chemin que le sélecteur « Colonnes ») ; le focus est un callback clientside sans sortie (`src/assets/filter_pills.js`) qui attend que la colonne soit visible. Le forçage d'affichage de colonne de #146 (commit 423a0c7) est supprimé.

**Tech Stack:** Dash 4.4, dash-ag-grid 35.2.0 (AG Grid 35, `rowModelType="infinite"`, filtres flottants), polars, pytest + `dash[testing]` (Selenium, marqués `selenium`).

**Spec:** GitHub issue ColinMaudry/colibre#148 :

> Avec le nombre de colonnes pouvant être affiché, et certaines colonnes pouvant être filtrées mais masquées, il peut être pratique de voir d'un coup d'oeil les filtres appliqués aux données et de donner la possibilité de les supprimer d'un clic.
> **Affichage** — Dans la continuité de la ligne de texte indiquant la date de mise à jour des données, avec la même taille de caractères, afficher une pastille par filtre au format "[nom colonne en gras] [= > < contient entre...] [valeur]" terminé par une croix. Le fond des pastilles est gris clair et le texte est gris foncé.
> **Interactions** — Si réalisable, cliquer sur un pastille amène le curseur dans le champ de saisie du filtre (ex : id = ag-198-input). Cliquer sur la croix du filtre supprime le filtre pour ce champ (et donc la pastille disparaît). Par conséquent, forcer l'affichage d'un colonne tel que codé dans le commit #423a0c7b5 pour l'issue #146 n'est plus utile puisque ce filtre devient visible et facilement supprimable.

## Décisions arbitrées avec l'auteur (2026-10-09)

1. **Périmètre** : page Tableau **et** fiches acheteur/titulaire, via un composant partagé (à terme, les contrôles des fiches rejoindront ceux du Tableau — hors de cette issue).
2. **Colonne masquée** : cliquer sur la pastille d'une colonne masquée **affiche la colonne puis positionne le curseur** dans son filtre.
3. Un filtre multi-conditions (`conditions` + `operator`) = **une seule** pastille.
4. Supprimer un filtre via la croix sur la page Tableau efface `active-view` (masque le bloc de partage), comme une modification de filtre faite dans la grille. Le dévoilement de colonne ne l'efface pas (même règle que le sélecteur « Colonnes », cf. commentaire `_SHARE_DRIFT_LISTENERS` dans `tableau.py`).

## Global Constraints

- UI en français. Contextes : `"tableau"`, `"acheteur"`, `"titulaire"` (mêmes valeurs que `get_default_hidden_columns(page)`).
- Libellé de colonne : `DATA_SCHEMA.get(col, {}).get("title", col)` (`DATA_SCHEMA` de `src.figures`, même source que `headerName` dans `grid_column_defs`).
- Opérateurs affichés : `equals` `=` · `notEqual` `≠` · `lessThan` `<` · `lessThanOrEqual` `≤` · `greaterThan` `>` · `greaterThanOrEqual` `≥` · `inRange` `entre A et B` · `contains` `contient` · `notContains` `ne contient pas` · `startsWith` `commence par` · `endsWith` `se termine par` · `blank` `est vide` · `notBlank` `n'est pas vide`. Opérateur inconnu : le `type` brut.
- Valeurs : nombres via `format_number` (séparateur de milliers `\u00a0`) sauf `0` → `"0"` ; dates `dateFrom`/`dateTo` (`"AAAA-MM-JJ hh:mm:ss"`) → `JJ/MM/AAAA` ; texte tel quel.
- Multi-conditions : expressions jointes par `et` (`AND`) / `ou` (`OR`).
- Ids Dash : conteneur `f"{context}-filter-pills"` ; corps de pastille `{"type": f"{context}-filter-pill", "col": col}` ; croix `{"type": f"{context}-filter-pill-remove", "col": col}` (deux `html.Button` frères dans un `html.Span.filter-pill`, pour que le clic sur la croix ne compte pas comme un clic sur la pastille).
- Style : même taille que `.table-meta` (14px), fond `#e9ecef`, texte `#343a40`, `display: inline-flex`, retour à la ligne naturel ; ne pas passer `.table-meta` en flex (les « · » perdraient leurs espaces). Variante `[data-bs-theme="dark"]` à côté de `[data-bs-theme="dark"] .table-meta` dans `src/assets/css/style.css`.
- Imports en `src.…` (CLAUDE.md). Avant tout `git add` : `pre-commit` (ruff). Ne `git add` que les fichiers listés par la tâche.
- Travail dans le worktree `.worktrees/issue-148-pastilles-filtres`, branche `issue-148-pastilles-filtres` (depuis `dev`). Le checkout principal contient du travail MCP non commité : ne pas y toucher.

## Review Focus

1. Filtre `montant = 0` → la pastille affiche `= 0` (`format_number(0)` renvoie `""`) (test Tâche 1).
2. `filterModel` persisté en localStorage sur une colonne disparue du schéma → pastille avec l'id brut comme libellé, pas d'exception (test Tâche 1).
3. Re-rendu des pastilles (nouveaux composants, `n_clicks=None`) après une suppression → ne déclenche ni suppression ni dévoilement (test Tâche 3).
4. Store `{context}-hidden-columns` à `None` (aucune préférence) + clic sur une colonne masquée par défaut → seules les colonnes par défaut moins celle-là sont masquées (test Tâche 4).
5. Suppression du dernier filtre → `filterModel == {}` : le bouton de téléchargement du Tableau repasse sur « Télécharger toutes les données » (`update_meta` teste `not filter_model`) (test Tâche 3).

---

### Task 0: Worktree et base de tests

Le `git worktree add .worktrees/issue-148-pastilles-filtres -b issue-148-pastilles-filtres dev` du 2026-10-09 a été tué au bout de 300 s : l'état est incertain.

- [ ] **Step 1: Constater l'état** — `git worktree list` et `git branch --list issue-148-pastilles-filtres`, depuis `/home/colin/git/colibre`.
- [ ] **Step 2: Terminer ou recréer** — worktree listé mais incomplet : `git -C .worktrees/issue-148-pastilles-filtres checkout -f issue-148-pastilles-filtres` (sans limite de durée). Non listé : `git worktree prune`, puis `git worktree add .worktrees/issue-148-pastilles-filtres issue-148-pastilles-filtres` (ou `-b … dev` si la branche n'existe pas), sans limite de durée. Attendu : `git -C .worktrees/issue-148-pastilles-filtres status -sb` → `## issue-148-pastilles-filtres`, arbre propre, HEAD `423a0c7`.
- [ ] **Step 3: Dépendances** — `uv sync` dans le worktree.
- [ ] **Step 4: Base** — `uv run pytest` dans le worktree. Attendu : tout passe ; sinon, rapporter les échecs à l'auteur avant de continuer.

### Task 1: Description d'un filtre

**Files:**

- Create: `src/utils/filter_pills.py`
- Test: `tests/test_filter_pills.py`

**Interfaces:**

- Produces: `describe_filter(col: str, spec: dict) -> tuple[str, str]` → `(libellé, expression)`, l'expression étant tout ce qui suit le libellé dans la pastille.

- [ ] **Step 1: Écrire le test échouant** (paramétré, valeurs littérales ; titres du fixture `tests/schema.fixture.json` : `acheteur_id` → « SIRET acheteur », `montant` → « Montant attribué », `dateNotification` → « Date notification »)

```python
import pytest

import src.app  # noqa: F401
from src.utils.filter_pills import describe_filter

NB = "\u00a0"


@pytest.mark.parametrize(
    ("col", "spec", "attendu"),
    [
        ("acheteur_id", {"filterType": "text", "type": "equals", "filter": "123"}, ("SIRET acheteur", "= 123")),
        ("acheteur_id", {"filterType": "text", "type": "notEqual", "filter": "123"}, ("SIRET acheteur", "≠ 123")),
        ("acheteur_id", {"filterType": "text", "type": "contains", "filter": "12"}, ("SIRET acheteur", "contient 12")),
        ("acheteur_id", {"filterType": "text", "type": "notContains", "filter": "12"}, ("SIRET acheteur", "ne contient pas 12")),
        ("acheteur_id", {"filterType": "text", "type": "startsWith", "filter": "12"}, ("SIRET acheteur", "commence par 12")),
        ("acheteur_id", {"filterType": "text", "type": "endsWith", "filter": "12"}, ("SIRET acheteur", "se termine par 12")),
        ("montant", {"filterType": "number", "type": "greaterThan", "filter": 1000}, ("Montant attribué", f"> 1{NB}000")),
        ("montant", {"filterType": "number", "type": "greaterThanOrEqual", "filter": 5}, ("Montant attribué", "≥ 5")),
        ("montant", {"filterType": "number", "type": "lessThan", "filter": 5}, ("Montant attribué", "< 5")),
        ("montant", {"filterType": "number", "type": "lessThanOrEqual", "filter": 5}, ("Montant attribué", "≤ 5")),
        ("montant", {"filterType": "number", "type": "equals", "filter": 0}, ("Montant attribué", "= 0")),
        ("montant", {"filterType": "number", "type": "inRange", "filter": 1000, "filterTo": 5000}, ("Montant attribué", f"entre 1{NB}000 et 5{NB}000")),
        ("montant", {"filterType": "number", "type": "blank"}, ("Montant attribué", "est vide")),
        ("montant", {"filterType": "number", "type": "notBlank"}, ("Montant attribué", "n'est pas vide")),
        ("dateNotification", {"filterType": "date", "type": "equals", "dateFrom": "2025-01-15 00:00:00", "dateTo": None}, ("Date notification", "= 15/01/2025")),
        ("dateNotification", {"filterType": "date", "type": "inRange", "dateFrom": "2025-01-01 00:00:00", "dateTo": "2025-12-31 00:00:00"}, ("Date notification", "entre 01/01/2025 et 31/12/2025")),
        ("montant", {"filterType": "number", "operator": "AND", "conditions": [
            {"filterType": "number", "type": "greaterThan", "filter": 1000},
            {"filterType": "number", "type": "lessThan", "filter": 5000},
        ]}, ("Montant attribué", f"> 1{NB}000 et < 5{NB}000")),
        ("acheteur_id", {"filterType": "text", "operator": "OR", "conditions": [
            {"filterType": "text", "type": "equals", "filter": "1"},
            {"filterType": "text", "type": "equals", "filter": "2"},
        ]}, ("SIRET acheteur", "= 1 ou = 2")),
        ("colonne_disparue", {"filterType": "text", "type": "contains", "filter": "x"}, ("colonne_disparue", "contient x")),
    ],
)
def test_describe_filter(col, spec, attendu):
    assert describe_filter(col, spec) == attendu
```

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest tests/test_filter_pills.py -v` → échec à l'import (`describe_filter` inexistant).
- [ ] **Step 3: Implémenter `describe_filter`** dans `src/utils/filter_pills.py` selon les tables des Global Constraints (dict opérateur → symbole/mot ; fonction de formatage de valeur par `filterType`).
- [ ] **Step 4: Vérifier le succès** — même commande → PASS.
- [ ] **Step 5: Commit** — `pre-commit`, puis `git add src/utils/filter_pills.py tests/test_filter_pills.py && git commit -m "Description textuelle d'un filtre AG Grid pour les pastilles (#148)"`.

### Task 2: Rendu des pastilles (Tableau + fiches) et style

**Files:**

- Modify: `src/utils/filter_pills.py`
- Modify: `src/pages/tableau.py` (`.table-meta` l. ~560-568 ; appel d'enregistrement en bas de module)
- Modify: `src/pages/acheteur.py` (`.table-meta` l. ~249-252), `src/pages/titulaire.py` (l. ~265-268)
- Modify: `src/utils/entity_grid.py` (`register_entity_grid_callbacks`)
- Modify: `src/assets/css/style.css` (après `.table-meta .dl-hint` l. ~368 et dans le bloc sombre l. ~1542)
- Test: `tests/test_filter_pills.py`

**Interfaces:**

- Consumes: `describe_filter` (Tâche 1).
- Produces:

  - `filter_pills(filter_model: dict | None, context: str) -> list` : un `html.Span(className="filter-pill")` par clé, dans l'ordre du filterModel, contenant `html.Button(id={"type": f"{context}-filter-pill", "col": col}, className="filter-pill-body", title="Modifier ce filtre", children=[html.Strong(libellé), " " + expression])` et `html.Button("×", id={"type": f"{context}-filter-pill-remove", "col": col}, className="filter-pill-remove", title=f"Supprimer le filtre {libellé}")`.
  - `register_filter_pills_callbacks(context: str, grid_id: str | dict, clear_active_view: bool = False) -> None` : la Tâche 2 y enregistre le rendu, les Tâches 3 et 4 y ajoutent leurs callbacks. `grid_id` vaut `"tableau_grid"`, ou `{"type": grid_type(org_type), "entity_id": ALL, "year": ALL}` pour les fiches (les callbacks reçoivent alors des listes : prendre le premier élément, ou `None` si la liste est vide, comme `_download_filtered`).

- [ ] **Step 1: Écrire les tests échouants**

```python
from src.utils.filter_pills import filter_pills


def test_filter_pills_sans_filtre():
    assert filter_pills(None, "tableau") == []
    assert filter_pills({}, "tableau") == []


def test_filter_pills_ids_par_colonne():
    fm = {
        "montant": {"filterType": "number", "type": "greaterThan", "filter": 5},
        "acheteur_id": {"filterType": "text", "type": "equals", "filter": "123"},
    }
    pills = filter_pills(fm, "acheteur")
    body, remove = pills[0].children
    assert body.id == {"type": "acheteur-filter-pill", "col": "montant"}
    assert remove.id == {"type": "acheteur-filter-pill-remove", "col": "montant"}
    assert pills[1].children[0].id["col"] == "acheteur_id"
```

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest tests/test_filter_pills.py -v` → ImportError sur `filter_pills`.
- [ ] **Step 3: Implémenter `filter_pills` et `register_filter_pills_callbacks`** (callback de rendu : `Output(f"{context}-filter-pills", "children")`, `Input(grid_id, "filterModel")`). Ajouter `html.Span(id="tableau-filter-pills", className="filter-pills")` après le span « · Données mises à jour le … », et `html.Span(id=f"{org}-filter-pills", className="filter-pills")` après `{org}_nb_rows` (le `html.Div` de `.table-meta` des fiches prend alors une liste d'enfants). Appeler `register_filter_pills_callbacks("tableau", "tableau_grid", clear_active_view=True)` dans `tableau.py` et `register_filter_pills_callbacks(org_type, {"type": gtype, "entity_id": ALL, "year": ALL})` à la fin de `register_entity_grid_callbacks`. CSS : `.filter-pill` (inline-flex, fond `#e9ecef`, texte `#343a40`, `border-radius`, marge gauche), `.filter-pill-body` / `.filter-pill-remove` (boutons sans bordure ni fond hérités, `font: inherit`, `color: inherit`, curseur pointeur), plus la variante sombre.
- [ ] **Step 4: Vérifier le succès** — `uv run pytest tests/test_filter_pills.py tests/test_entity_grid.py tests/test_tableau_filtre_organisme.py -v` → PASS.
- [ ] **Step 5: Commit** — `pre-commit` ; `git add` des 7 fichiers listés ; message « Pastilles des filtres appliqués au-dessus des tableaux (#148) ».

### Task 3: Suppression d'un filtre par la croix

**Files:**

- Modify: `src/utils/filter_pills.py`
- Test: `tests/test_filter_pills.py`

**Interfaces:**

- Consumes: `register_filter_pills_callbacks` (Tâche 2).
- Produces:

  - `filter_model_sans(filter_model: dict | None, col: str) -> dict` : copie sans la clé `col`.
  - `col_cliquee(triggered_id, triggered_value) -> str | None` : `triggered_id["col"]` si `triggered_id` est un dict et `triggered_value` vaut au moins 1, sinon `None`. Réutilisé par la Tâche 4.

- [ ] **Step 1: Écrire les tests échouants**

```python
from src.utils.filter_pills import col_cliquee, filter_model_sans

GT5 = {"filterType": "number", "type": "greaterThan", "filter": 5}
EQ123 = {"filterType": "text", "type": "equals", "filter": "123"}


def test_filter_model_sans_retire_la_colonne():
    assert filter_model_sans({"montant": GT5, "acheteur_id": EQ123}, "montant") == {"acheteur_id": EQ123}


def test_filter_model_sans_dernier_filtre_donne_un_modele_vide():
    assert filter_model_sans({"montant": GT5}, "montant") == {}


def test_col_cliquee_ignore_le_rerendu():
    assert col_cliquee({"type": "tableau-filter-pill-remove", "col": "montant"}, None) is None
    assert col_cliquee(None, 1) is None


def test_col_cliquee_renvoie_la_colonne():
    assert col_cliquee({"type": "tableau-filter-pill-remove", "col": "montant"}, 1) == "montant"
```

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest tests/test_filter_pills.py -v` → ImportError.
- [ ] **Step 3: Implémenter** les deux fonctions, puis le callback dans `register_filter_pills_callbacks` : `Input({"type": f"{context}-filter-pill-remove", "col": ALL}, "n_clicks")`, `State(grid_id, "filterModel")`, `Output(grid_id, "filterModel", allow_duplicate=True)` (pour les fiches : liste, comme `_reset`), plus `Output("active-view", "data", allow_duplicate=True)` → `None` si `clear_active_view` ; `prevent_initial_call=True` ; `col_cliquee(ctx.triggered_id, ctx.triggered[0]["value"])` à `None` → `no_update` partout.
- [ ] **Step 4: Vérifier le succès** — même commande → PASS.
- [ ] **Step 5: Commit** — `pre-commit` ; `git add src/utils/filter_pills.py tests/test_filter_pills.py` ; « Suppression d'un filtre depuis sa pastille (#148) ».

### Task 4: Clic sur la pastille — dévoile la colonne puis focus du filtre

**Files:**

- Modify: `src/utils/filter_pills.py`
- Create: `src/assets/filter_pills.js`
- Test: `tests/test_filter_pills.py`

**Interfaces:**

- Consumes: `col_cliquee` (Tâche 3), `register_filter_pills_callbacks` (Tâche 2), `get_default_hidden_columns` (`src.utils.table`).
- Produces: `colonnes_masquees_sans(col: str, colonnes_masquees: list | None, context: str) -> list | None` : liste de référence (store, ou `get_default_hidden_columns(context)` si `None`) sans `col` ; `None` si `col` n'y est pas (callback → `no_update`). `window.dash_clientside.filterPills.focusFilter(n_clicks_list, gridIds)`.

- [ ] **Step 1: Écrire les tests échouants**

```python
from src.utils.filter_pills import colonnes_masquees_sans
from src.utils.table import get_default_hidden_columns


def test_colonnes_masquees_sans_devoile_la_colonne():
    assert colonnes_masquees_sans("acheteur_id", ["acheteur_id", "montant"], "tableau") == ["montant"]


def test_colonnes_masquees_sans_colonne_deja_visible():
    assert colonnes_masquees_sans("acheteur_id", ["montant"], "tableau") is None


def test_colonnes_masquees_sans_preference_part_des_defauts():
    defauts = get_default_hidden_columns("tableau")
    assert "acheteur_id" in defauts  # précondition du fixture
    out = colonnes_masquees_sans("acheteur_id", None, "tableau")
    assert "acheteur_id" not in out
    assert set(out) == set(defauts) - {"acheteur_id"}
```

- [ ] **Step 2: Vérifier l'échec** — `uv run pytest tests/test_filter_pills.py -v` → ImportError.
- [ ] **Step 3: Implémenter `colonnes_masquees_sans`** et le callback serveur : `Input({"type": f"{context}-filter-pill", "col": ALL}, "n_clicks")`, `State(f"{context}-hidden-columns", "data")` → `Output(f"{context}-hidden-columns", "data", allow_duplicate=True)`, avec la garde `col_cliquee`.
- [ ] **Step 4: Vérifier le succès** — même commande → PASS.
- [ ] **Step 5: Focus clientside** — dans `register_filter_pills_callbacks`, ajouter un `clientside_callback(ClientsideFunction("filterPills", "focusFilter"), Input({"type": f"{context}-filter-pill", "col": ALL}, "n_clicks"), State(grid_id, "id"), prevent_initial_call=True)` sans Output (convention de `src/figures.py:1211`). Algorithme de `src/assets/filter_pills.js` :

```js
// col = callback_context.triggered_id.col ; ignorer si triggered[0].value est vide.
// gridId = Array.isArray(gridIds) ? gridIds[0] : gridIds ; api = dash_ag_grid.getApi(gridId) dans un try.
// Toutes les 50 ms, pendant 5 s au plus : dès que api.getColumn(col)?.isVisible() →
//   api.ensureColumnVisible(col) ; au requestAnimationFrame suivant, dans
//   document.getElementById(stringifyId(gridId)) (même algorithme que le stringifyId de Dash : clés triées,
//   '{' + '"clé":' + JSON.stringify(valeur) jointes par ',' + '}'), chercher l'input du filtre flottant
//   de la colonne ; s'il existe et n'est ni disabled ni readOnly → input.focus(),
//   sinon → api.showColumnFilter(col) (filtres multi-conditions, inRange, vide : flottant en lecture seule).
```

- [ ] **Step 6: Vérifier le sélecteur et l'API dans le navigateur** — `uv run run.py`, ouvrir `/tableau`, dans la console : `typeof dash_ag_grid.getApi("tableau_grid").showColumnFilter === "function"`, et relever le sélecteur de l'input flottant d'une colonne (attribut `col-id` porté par la cellule de filtre flottant ou par son conteneur). Reporter le sélecteur constaté dans `filter_pills.js`.
- [ ] **Step 7: Commit** — `pre-commit` ; `git add src/utils/filter_pills.py src/assets/filter_pills.js tests/test_filter_pills.py` ; « Clic sur une pastille : affiche la colonne et place le curseur dans son filtre (#148) ».

### Task 5: Retrait du forçage de colonne de #146

**Files:**

- Modify: `src/pages/tableau.py` (`devoiler_colonnes_filtre_org` l. ~890-908, `afficher_colonnes_du_filtre_org` l. ~947-957, commentaire d'`apply_org_filter` l. ~940-943)
- Modify: `tests/test_tableau_filtre_organisme.py` (5 tests `test_devoiler_colonnes_filtre_org_*`, l. ~83-114)

- [ ] **Step 1: Supprimer** les deux fonctions et leurs tests ; réécrire le commentaire d'`apply_org_filter` : le filtre d'organisme est visible et supprimable par sa pastille (#148), la colonne n'est pas affichée d'office.
- [ ] **Step 2: Vérifier** — `uv run pytest tests/test_tableau_filtre_organisme.py tests/test_filter_pills.py -v` → PASS ; plus aucune occurrence de `devoiler_colonnes_filtre_org` dans `src/` et `tests/`.
- [ ] **Step 3: Commit** — `pre-commit` ; `git add src/pages/tableau.py tests/test_tableau_filtre_organisme.py` ; « Retire l'affichage forcé de la colonne du filtre d'organisme, remplacé par les pastilles (#148) ».

### Task 6: Tests Selenium

**Files:**

- Create: `tests/test_filter_pills_selenium.py` (structure de `tests/saved_views/test_tableau_share.py:157` : `dash_duo.start_server(app)`, `wait_for_page`, `WebDriverWait`)

- [ ] **Step 1: Écrire les tests**
  - `test_tableau_pastille_du_filtre_org_puis_suppression` : `/tableau?acheteur_id=123` → `#tableau-filter-pills` contient `SIRET acheteur` et `= 123` ; clic sur `.filter-pill-remove` → `#tableau-filter-pills` vide et le bouton `#btn-download-data` affiche « Télécharger toutes les données ».
  - `test_tableau_clic_pastille_colonne_masquee_affiche_et_focus` : `/tableau?acheteur_id=123` (colonne `acheteur_id` masquée par défaut) ; clic sur `.filter-pill-body` → l'en-tête `acheteur_id` est rendu et `document.activeElement` est l'input du filtre flottant de cette colonne (sélecteur de la Tâche 4, Step 6).
  - `test_fiche_acheteur_pastille_et_suppression` : `/acheteur/123`, saisie d'un texte dans le premier filtre flottant visible (helper inspiré de `_type_in_first_filter`) → une `.filter-pill` apparaît dans `#acheteur-filter-pills` ; clic sur sa croix → conteneur vide.
- [ ] **Step 2: Lancer** — `uv run pytest tests/test_filter_pills_selenium.py -v -m selenium` → PASS (Chrome requis).
- [ ] **Step 3: Commit** — `pre-commit` ; `git add tests/test_filter_pills_selenium.py` ; « Tests navigateur des pastilles de filtres (#148) ».

### Task 7: Smoke, CHANGELOG, suite complète

**Files:**

- Modify: `CHANGELOG.md` (section `#### 3.3.0`)

- [ ] **Step 1: Smoke navigateur** — `uv run run.py` dans le worktree ; sur `/tableau` : filtre texte, nombre `inRange`, date, deux conditions ; vérifier libellés, retour à la ligne, focus (colonne visible hors écran, colonne masquée, filtre en lecture seule → popup), suppression, bloc de partage masqué après suppression sur une vue `?vue=` ; thème sombre ; même parcours sur une fiche acheteur.
- [ ] **Step 2: CHANGELOG** — sous `#### 3.3.0` : `- Au-dessus des tableaux, une pastille par filtre appliqué permet de voir les filtres actifs, d'en supprimer un d'un clic ou d'aller à son champ de saisie ([#148](https://github.com/colinmaudry/colibre/issues/148))`.
- [ ] **Step 3: Suite complète** — `uv run pytest` puis `uv run pytest -m selenium` → PASS ; tout échec est rapporté par son nom.
- [ ] **Step 4: Commit** — `pre-commit` ; `git add CHANGELOG.md` ; « CHANGELOG : pastilles des filtres (#148) ».
