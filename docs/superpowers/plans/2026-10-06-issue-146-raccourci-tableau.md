# Raccourci « Tableau » depuis les tableaux de marchés (issue #146) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter, à côté de l'icône Observatoire (📊) dans toutes les grilles de marchés, une icône « tableau » qui ouvre `/tableau?acheteur_id=<id>` ou `/tableau?titulaire_id=<id>`, et faire appliquer par la page Tableau ce filtre d'identifiant en remplacement des filtres courants.

**Architecture:** Le lien est posé au même endroit que le lien Observatoire : `add_links()` dans `src/utils/table.py`, appelé par `postprocess_page()` — il couvre donc d'un coup la grille Tableau, les résultats de recherche et les grilles d'organismes (`src/utils/top_org_grid.py`). Côté page Tableau, le paramètre d'URL est traduit en `filterModel` AG Grid par une fonction pure, puis appliqué via un `dcc.Store` + callback, sur le même schéma que la résolution `?vue=` existante. Le filtrage étant serveur (`filtermodel_to_ast` → SQL DuckDB), la colonne `acheteur_id`/`titulaire_id` n'a pas besoin d'être affichée.

**Tech Stack:** Dash 4.4, dash-ag-grid 35.2.0 (renderer markdown avec HTML brut autorisé), polars, pytest (tests purs sans navigateur ; les tests Selenium sont marqués `selenium` et exclus par défaut).

**Spec:** GitHub issue ColinMaudry/colibre#146 :

> Depuis tout tableau de marchés publics, ajouter une icône à côté des noms d'organismes qui d'un clic permet de filtrer dans la page Tableau les marchés remportés ou attribués par cet organisme, via un filtre sur son numéro SIRET. C'est l'équivalent du bouton 📊 dans les tableaux, mais pour ouvrir la page Tableau au lieu de la page Observatoire. […] dans la page Tableau, de permettre la réinitialisation des filtres (pas des tris ou des noms de colonnes) et l'application d'un filtre sur `acheteur_id` ou `titulaire_id` en fonction du paramètre d'URL. La colonne correspondante n'a pas besoin d'être affichée. […] ajouter, à côté de l'icône Observatoire (📊), une nouvelle icône à créer en SVG. Cette icône représente un tableau de manière très simplifiée, un quadrillage gris au contenu transparent et un en-tête orange plein. Cette icône porte le lien vers Tableau avec le bon paramètre d'URL.

## Décisions arbitées avec l'auteur de l'issue (2026-10-06)

1. **Format d'URL** : query string `?acheteur_id=...` / `?titulaire_id=...` (pas le chemin littéral `/tableau/acheteur_id=...` de l'issue). Cohérent avec `/observatoire?acheteur_id=...` et le parsing existant de `?vue=`.
2. **Reset** : le bouton « Réinitialiser » garde son comportement actuel (filtres + tris). En revanche, ouvrir `/tableau` avec `?acheteur_id` ou `?titulaire_id` **réinitialise les filtres avant d'appliquer le filtre d'identifiant** : le `filterModel` persisté en localStorage (AG Grid `persisted_props=("filterModel", "columnState")`) est remplacé, sans toucher aux tris ni aux colonnes.
3. **Couleur de l'en-tête de l'icône** : `rgb(179, 56, 33)` (`#b33821`, couleur primaire du site et des en-têtes de grilles — le « orange » de l'issue). Quadrillage gris, contenu transparent.

## Global Constraints

- UI en français : infobulle du lien « Voir dans le tableau ».
- Icône : SVG 16×16, quadrillage gris (`#999`), contenu transparent, en-tête plein `#b33821`, servie depuis `src/assets/` (URL `/assets/icone-tableau.svg`, même mécanisme que `/assets/copy.svg`).
- Le HTML des cellules est rendu par le renderer markdown d'AG Grid (HTML brut autorisé) : le lien porte un `<img>` vers le SVG, avec `style` inline (`height:14px;vertical-align:middle;`) — valable aussi pour les `dash_table` des pages acheteur/titulaire qui partagent `postprocess_page`.
- `add_links` ne pose des liens que si `titulaire_typeIdentifiant` est null ou `"SIRET"` (condition existante) : la nouvelle icône suit la même condition.
- Le filterModel d'identifiant : `{"acheteur_id": {"filterType": "text", "type": "equals", "filter": "<id>"}}` — opérateur `equals` supporté par `filtermodel_to_ast` (`_TEXT_TYPE`).
- Avant tout `git add`/`git commit` : exécuter `pre-commit` (ruff), cf. CLAUDE.md.
- Le working tree contient du travail non lié non commité : ne `git add` **que** les fichiers listés par chaque tâche.
- Branche : `feature/146-raccourci-tableau` (déjà créée depuis `dev`).

## Review Focus

1. `?vue=<token>` + `?acheteur_id=...` dans la même URL → le filtre d'organisme prime, la vue partagée est ignorée (test Tâche 3).
2. `?acheteur_id=...` + `?titulaire_id=...` ensemble → les deux filtres s'appliquent (AND naturel de `filtermodel_to_ast`) (test Tâche 2).
3. Valeur vide ou blanche (`?acheteur_id=%20`) → paramètre ignoré, aucun filtre appliqué (test Tâche 2).
4. Titulaire avec `typeIdentifiant` ≠ SIRET → aucune icône (le lien suit la garde existante d'`add_links`) (test Tâche 1).
5. Filtre persisté en localStorage puis arrivée avec `?acheteur_id=...` → le callback remplace le `filterModel` restauré : même mécanisme Dash que l'application de `?vue=` (prouvé par `test_open_shared_view_applies_and_shows_box`), le remplacement est ici porté par le test unitaire du callback `apply_org_filter` (Tâche 3) qui renvoie le filterModel d'organisme seul.

---

### Task 1: Icône SVG et raccourci dans `add_links`

**Files:**

- Create: `src/assets/icone-tableau.svg`
- Modify: `src/utils/table.py` (`add_links`, lignes ~60-115 : branches `acheteur_nom` et `titulaire_nom`)
- Test: `tests/test_table.py` (ajouts à la fin)

**Interfaces:**

- Consumes: rien de nouveau.
- Produces: cellules `acheteur_nom`/`titulaire_nom` contenant `<a href="/tableau?acheteur_id=<id>" title="Voir dans le tableau"><img src="/assets/icone-tableau.svg" ...></a>` (idem `titulaire_id`). Rien n'est consommé par les tâches suivantes.

- [ ] **Step 1: Écrire les tests échouants** (à la fin de `tests/test_table.py`)

```python
def test_add_links_ajoute_le_raccourci_tableau(sample_lff):
    from src.utils.table import add_links

    dff = add_links(sample_lff.collect())
    cell_acheteur = dff["acheteur_nom"][0]
    cell_titulaire = dff["titulaire_nom"][0]
    # Lien vers la page Tableau avec le bon paramètre d'URL
    assert 'href="/tableau?acheteur_id=12345678900011"' in cell_acheteur
    assert 'href="/tableau?titulaire_id=98765432100022"' in cell_titulaire
    # L'icône porte le lien, avec une infobulle explicite
    assert "/assets/icone-tableau.svg" in cell_acheteur
    assert 'title="Voir dans le tableau"' in cell_acheteur
    # Le raccourci Observatoire est conservé à côté
    assert 'href="/observatoire?acheteur_id=12345678900011"' in cell_acheteur
    assert 'href="/observatoire?titulaire_id=98765432100022"' in cell_titulaire


def test_add_links_sans_raccourci_si_identifiant_non_siret():
    from src.utils.table import add_links

    dff = pl.DataFrame(
        {
            "titulaire_id": ["98765432100022"],
            "titulaire_nom": ["Entreprise Test"],
            "titulaire_typeIdentifiant": ["SIREN"],
        }
    )
    out = add_links(dff)
    assert "/tableau?" not in out["titulaire_nom"][0]
```

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_table.py::test_add_links_ajoute_le_raccourci_tableau tests/test_table.py::test_add_links_sans_raccourci_si_identifiant_non_siret -v`
Expected: FAIL — aucun `/tableau?` dans les cellules.

- [ ] **Step 3: Créer `src/assets/icone-tableau.svg`**

16×16, en-tête plein `#b33821` (~1/4 de la hauteur), quadrillage gris `#999`, contenu transparent :

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" role="img">
  <rect x="0.5" y="0.5" width="15" height="15" fill="none" stroke="#999"/>
  <rect x="0.5" y="0.5" width="15" height="4" fill="#b33821" stroke="#999"/>
  <line x1="0.5" y1="8" x2="15.5" y2="8" stroke="#999"/>
  <line x1="0.5" y1="11.5" x2="15.5" y2="11.5" stroke="#999"/>
  <line x1="5.5" y1="4.5" x2="5.5" y2="15.5" stroke="#999"/>
  <line x1="10.5" y1="4.5" x2="10.5" y2="15.5" stroke="#999"/>
</svg>
```

- [ ] **Step 4: Implémenter dans `add_links` (`src/utils/table.py`)**

Pour `acheteur_nom`, prolonger `detail_link` après le lien Observatoire :

```python
detail_link = detail_link + (
    ' <a href="/tableau?acheteur_id=' + pl.col("acheteur_id")
    + '" title="Voir dans le tableau">'
    + '<img src="/assets/icone-tableau.svg" alt="Voir dans le tableau" '
    + 'style="height:14px;vertical-align:middle;" /></a>'
)
```

Même chose pour `titulaire_nom` avec `titulaire_id` (les deux dans la garde `typeIdentifiant` existante). Style : chaînes concaténées comme le lien 📊 voisin, pas de f-string (cohérence avec l'existant).

- [ ] **Step 5: Vérifier le passage**

Run: `uv run pytest tests/test_table.py -v -m "not selenium"`
Expected: PASS (tous, y compris les tests `add_links`/`fetch_page` existants).

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/assets/icone-tableau.svg src/utils/table.py tests/test_table.py || pre-commit run --all-files
git add src/assets/icone-tableau.svg src/utils/table.py tests/test_table.py
git commit -m "Raccourci vers la page Tableau depuis les tableaux de marchés (#146)"
```

### Task 2: Traduction du paramètre d'URL en filterModel

**Files:**

- Modify: `src/pages/tableau.py` (fonction pure, à côté de `resolve_vue_from_url` ~l.853)
- Test: `tests/test_tableau_filtre_organisme.py` (create)

**Interfaces:**

- Consumes: rien.
- Produces: `filtre_org_depuis_url(search: str) -> dict | None` — filterModel AG Grid (`{"acheteur_id": {"filterType": "text", "type": "equals", "filter": "<id>"}}`, les deux colonnes possibles combinées dans le même dict) ou `None` si aucun paramètre d'organisme exploitable. Valeurs trimées. Consommée par la Tâche 3.

- [ ] **Step 1: Écrire les tests échouants** (`tests/test_tableau_filtre_organisme.py`)

```python
import dash

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.pages import tableau


def test_filtre_org_depuis_url_acheteur():
    fm = tableau.filtre_org_depuis_url("?acheteur_id=21590350100017")
    assert fm == {
        "acheteur_id": {"filterType": "text", "type": "equals", "filter": "21590350100017"}
    }


def test_filtre_org_depuis_url_titulaire():
    fm = tableau.filtre_org_depuis_url("?titulaire_id=54202182900123")
    assert fm == {
        "titulaire_id": {"filterType": "text", "type": "equals", "filter": "54202182900123"}
    }


def test_filtre_org_depuis_url_les_deux():
    fm = tableau.filtre_org_depuis_url("?acheteur_id=1&titulaire_id=2")
    assert fm == {
        "acheteur_id": {"filterType": "text", "type": "equals", "filter": "1"},
        "titulaire_id": {"filterType": "text", "type": "equals", "filter": "2"},
    }


def test_filtre_org_depuis_url_sans_parametre():
    assert tableau.filtre_org_depuis_url("") is None
    assert tableau.filtre_org_depuis_url("?vue=abc123") is None


def test_filtre_org_depuis_url_valeur_vide_ignoree():
    assert tableau.filtre_org_depuis_url("?acheteur_id=%20") is None


def test_filtre_org_depuis_url_trimme_la_valeur():
    fm = tableau.filtre_org_depuis_url("?acheteur_id= 123 ")
    assert fm["acheteur_id"]["filter"] == "123"


def test_le_filtre_d_identifiant_passe_par_le_chemin_serveur():
    """La colonne n'a pas besoin d'être affichée : le filterModel est traduit
    en SQL côté serveur quel que soit l'état des columnDefs."""
    from src.db import schema
    from src.utils.query_ast import ast_to_sql, filtermodel_to_ast

    ast = filtermodel_to_ast(
        {"acheteur_id": {"filterType": "text", "type": "equals", "filter": "123"}},
        schema,
    )
    sql, params = ast_to_sql(ast, schema)
    assert "acheteur_id" in sql
    assert params == ["123"]
```

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_tableau_filtre_organisme.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'filtre_org_depuis_url'`.

- [ ] **Step 3: Implémenter `filtre_org_depuis_url` dans `src/pages/tableau.py`**

Même parsing que `resolve_vue_from_url` (`parse_qs((search or "").lstrip("?"))`) ; itérer sur `("acheteur_id", "titulaire_id")`, garder la première valeur trimée non vide, `filterType: "text"`, `type: "equals"` ; renvoyer `None` si vide.

- [ ] **Step 4: Vérifier le passage**

Run: `uv run pytest tests/test_tableau_filtre_organisme.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py tests/test_tableau_filtre_organisme.py || pre-commit run --all-files
git add src/pages/tableau.py tests/test_tableau_filtre_organisme.py
git commit -m "Filtre d'organisme depuis les paramètres d'URL de la page Tableau (#146)"
```

### Task 3: Câblage Dash — application du filtre et priorité sur `?vue=`

**Files:**

- Modify: `src/pages/tableau.py` (layout : `dcc.Store` à côté de `vue-resolution` ~l.475 ; callbacks à côté de `store_vue_resolution`/`apply_vue_resolution_cb` ~l.853-925)
- Test: `tests/test_tableau_filtre_organisme.py` (ajouts)

**Interfaces:**

- Consumes: `filtre_org_depuis_url` (Tâche 2).
- Produces: `dcc.Store(id="org-filter-resolution")` dans le layout ; callbacks `store_org_filter(search)` (Input `tableau_url.search` → Output `org-filter-resolution.data`) et `apply_org_filter(filtre)` (Input `org-filter-resolution.data` → Output `tableau_grid.filterModel` avec `allow_duplicate=True`, `prevent_initial_call=True`). `store_vue_resolution` ignore `?vue=` quand un paramètre d'organisme est présent.

- [ ] **Step 1: Écrire les tests échouants** (ajouts à `tests/test_tableau_filtre_organisme.py` ; ajouter `import dash` en tête du fichier, il sert à `dash.no_update`)

```python
def test_store_vue_resolution_ecartee_si_filtre_org_present():
    # Les paramètres d'organisme priment sur une éventuelle vue partagée
    assert tableau.store_vue_resolution("?vue=abc123_ma-vue&acheteur_id=123") is dash.no_update


def test_apply_org_filter_renvoie_le_filtermodel():
    fm = {"acheteur_id": {"filterType": "text", "type": "equals", "filter": "123"}}
    assert tableau.apply_org_filter(fm) == fm


def test_apply_org_filter_sans_filtre_est_un_noop():
    assert tableau.apply_org_filter(None) is dash.no_update
```

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_tableau_filtre_organisme.py -v -m "not selenium"`
Expected: FAIL — `apply_org_filter` n'existe pas ; `store_vue_resolution` tente de résoudre `?vue=`.

- [ ] **Step 3: Implémenter le câblage dans `src/pages/tableau.py`**

- `dcc.Store(id="org-filter-resolution")` dans `_layout` près des autres stores.
- En tête de `store_vue_resolution` : `if filtre_org_depuis_url(search) is not None: return no_update` (priorité organisme, documentée en commentaire).
- Callbacks sur le modèle exact de `store_vue_resolution`/`apply_vue_resolution_cb` :

```python
@callback(
    Output("org-filter-resolution", "data"),
    Input("tableau_url", "search"),
)
def store_org_filter(search):
    filtre = filtre_org_depuis_url(search)
    return filtre if filtre is not None else no_update


@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Input("org-filter-resolution", "data"),
    prevent_initial_call=True,
)
def apply_org_filter(filtre):
    # Réinitialise les filtres (remplace le filterModel persisté) puis
    # applique le filtre d'identifiant. Tris et colonnes ne sont pas touchés.
    return filtre if filtre else no_update
```

- [ ] **Step 4: Vérifier le passage**

Run: `uv run pytest tests/test_tableau_filtre_organisme.py tests/saved_views -v -m "not selenium"`
Expected: PASS (y compris les tests `?vue=` existants).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py tests/test_tableau_filtre_organisme.py || pre-commit run --all-files
git add src/pages/tableau.py tests/test_tableau_filtre_organisme.py
git commit -m "La page Tableau applique le filtre d'organisme de l'URL en remplacement des filtres (#146)"
```

### Task 4: Vérification d'ensemble

**Files:**

- Test: aucune modification ; exécution seule.

- [ ] **Step 1: Suite ciblée**

Run: `uv run pytest tests/test_table.py tests/test_tableau_filtre_organisme.py tests/test_tableau_ag_grid.py tests/test_grid.py tests/test_top_org_grid.py tests/test_observatoire_button.py tests/saved_views -m "not selenium" -q`
Expected: PASS intégral. Toute casse, y compris préexistante, est nommée dans le compte-rendu.

- [ ] **Step 2: Lint**

Run: `pre-commit run --all-files` (ou `uv run ruff check src tests` si pre-commit n'est pas installé)
Expected: pas de modification requise sur les fichiers de la branche.
