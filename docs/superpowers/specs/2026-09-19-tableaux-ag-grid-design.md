# Migration des derniers tableaux vers AG Grid (#141) — design

## Contexte

Plusieurs tableaux utilisent encore `dash_table.DataTable` et ne suivent donc
pas le mode sombre (#118), alors que les grilles AG Grid le suivent déjà via
les variables `--ag-*` redéfinies sous `[data-bs-theme="dark"]`.

Travail mené sur la branche `mode-sombre-118` (lié à #118).

## Périmètre

Migrés vers AG Grid :

| Tableau                                                            | Emplacement actuel                            |
| ------------------------------------------------------------------ | --------------------------------------------- |
| Top acheteurs / Top titulaires de l'observatoire                   | `build_dashboard_cards` → `get_top_org_table` |
| Tableau des sources (`/projet/donnees`)                            | `get_sources_tables`                          |
| Résultats de recherche (accueil)                                   | `recherche.py`                                |
| Sélecteur de colonnes (tableau, acheteur, titulaire, observatoire) | `make_column_picker`                          |
| Interface d'administration                                         | `admin/liste.py`                              |

Supprimés (code mort) : `get_yearly_statistics`, `get_top_org_table`,
`find_changed_cell` (une fois l'admin migrée).

### Hors périmètre

La **prévisualisation des données de l'observatoire** (`observatoire-preview-table`)
sera supprimée dans le chantier suivant. Elle reste en `DataTable` d'ici là,
ainsi que tout ce dont elle dépend : classe `DataTable` de `src/figures.py`,
DSL `filter_query` (`prepare_table_data`, `_fetch_page_sql`,
`filter_query_to_sql`, …) et CSS `.dash-table-container`. Leur suppression
appartient à ce chantier suivant.

Le sélecteur de colonnes de la prévisualisation est migré malgré tout, parce que
`make_column_picker` est partagé : sa paire de callbacks est adaptée comme les
trois autres.

## Brique commune : `client_grid()`

Nouvelle fonction dans `src/figures.py`, pendant client-side de `ag_grid()`
(qui reste dédiée au modèle `infinite`) :

```python
def client_grid(grid_id, column_defs, row_data, page_size=None, **dash_grid_options) -> dag.AgGrid
```

Elle centralise ce que `get_top_org_ag_grid` et `make_schema_grid` recopient
chacune : `AG_GRID_THEME`, `localeText: AG_GRID_LOCALE_FR`,
`domLayout: "autoHeight"`, `suppressCellFocus`, `dangerously_allow_code=True`,
`persistence=False`, `style={"width": "100%"}`. `page_size` active la
pagination. Les options supplémentaires sont fusionnées dans `dashGridOptions`.

`get_top_org_ag_grid` et `make_schema_grid` sont réécrites sur `client_grid`,
sans changement visible.

## Tableaux statiques

### Top acheteurs / titulaires (observatoire)

- `get_top_org_ag_grid` gagne le paramètre `limit: int | None = 100` de
  `get_top_org_table` (troncature après tri, pour ne pas expédier des dizaines
  de milliers de lignes au navigateur).
- `build_dashboard_cards` l'appelle à la place de `get_top_org_table`.
- `get_top_org_table` est supprimée. Ses tests (troncature, défaut à 100,
  limite supérieure au nombre de lignes) sont reportés sur `get_top_org_ag_grid`.

### Sources (`/projet/donnees`)

- `get_sources_tables` renvoie une `client_grid` triable.
- « Nom de la source » et « Responsable de publication » en
  `cellRenderer: "markdown"`, retour à la ligne et hauteur automatique.
- Nombres alignés à droite, cellules vides affichées « N/A ».
- Les cas sans CSV ou avec un CSV absent se comportent comme aujourd'hui
  (tests `test_page_loads`).

### Résultats de recherche (accueil)

- `client_grid` paginée par 10, sans tri ni filtre (comme aujourd'hui).
- Noms rendus en liens markdown.
- La recherche construit ses `columnDefs` avec un petit convertisseur dédié et
  n'utilise plus `setup_table_columns`. Celui-ci reste en place : la
  prévisualisation de l'observatoire l'utilise via `prepare_table_data`, et il
  partira avec elle.
- `tests/test_main.py` : les sélecteurs `td[data-dash-column=…]` deviennent
  `[col-id=…]`.

## Sélecteur de colonnes

### Composant

`make_column_picker(page)` renvoie :

- un `dbc.Input` « Rechercher une colonne… », id `{page}_column_search` ;
- une `client_grid` d'id `{page}_column_list` (id conservé) :
  - colonnes Nom et Description (Description avec retour à la ligne) ;
  - `getRowId: params.data.id` (l'id de colonne du schéma) ;
  - sélection multiple par cases, avec case « tout cocher » dans l'en-tête,
    limitée aux lignes filtrées ;
  - pas de pagination (la modale garde son défilement).

Un callback **clientside** relie `{page}_column_search.value` à
`dashGridOptions.quickFilterText` de la grille, sans aller-retour serveur. Le
filtre rapide porte sur le nom et la description.

### Callbacks (4 pages, même schéma)

**Cases → store**

- L'entrée passe de `selected_rows` (index) à `selectedRows` (lignes).
- `hidden = [c for c in COLUMNS if c not in {r["id"] for r in selectedRows}]`.
- On conserve la distinction entre `[]` (tout décoché, à respecter) et `None`
  (pas encore de préférence) établie dans `tableau.py`.
- **Garde anti-écho** : si l'ensemble masqué calculé est identique au contenu
  du store (`State`), `no_update`. Quand on pose `selectedRows` depuis le serveur,
  AG Grid en renvoie un nouveau `selectedRows`. Sans cette garde, un renvoi
  partiel (grille montée en même temps que la modale s'ouvre) pourrait écraser
  le store (cf. #139).

**Store → cases (à l'ouverture de la modale seulement)**

- La sortie passe de `selected_rows` (index) à
  `selectedRows = {"ids": [colonnes visibles]}`.
- Le déclenchement reste limité à `is_open` (comportement de #139 inchangé).

Les callbacks travaillent sur des identifiants de colonnes et non plus sur des
index dans `COLUMNS`, ce qui les rend robustes aux évolutions du schéma.

### Tests

- Les tests Selenium qui cliquent `#…_column_list input[type='checkbox']`
  passent aux cases AG Grid (`.ag-selection-checkbox input`) :
  `test_selecteurs_colonnes_navigateur`, `test_tableau_selecteur_colonnes`,
  `test_tableau_mode_observatoire_css`.
- `test_selecteurs_colonnes_sans_echo` et `test_tableau_colonnes_echo` sont
  adaptés au nouveau prop sans perdre ce qu'ils vérifient.
- Nouveaux tests : garde anti-écho (unitaire), filtre rapide et case « tout
  cocher » (navigateur).

## Interface d'administration

### Grille

- `client_grid("admin-table", …)` paginée par 20, triable, filtres flottants.
- `getRowId` : la clé primaire de la table (`cfg.pk`).
- `_columns_for(table)` produit des `columnDefs` :
  - `editable: col in cfg.editable_columns` ;
  - colonnes de `cfg.dropdowns` : `cellEditor: "agSelectCellEditor"`,
    `cellEditorParams: {"values": [...]}`.
- `_dropdown_for` disparaît (les valeurs sont portées par la définition de
  colonne).

### Callbacks

- **Changement de table** (`admin-table-select`) : sorties `rowData` et
  `columnDefs`.
- **Édition** : l'entrée `cellValueChanged` remplace `data` et `data_previous`.
  On lit `colId`, `oldValue`, `value` et `data` (ligne complète, qui contient la
  clé primaire).
  - La garde `is_admin()` reste la première instruction (#110).
  - `set_cell`, `log_action` et les alertes sont inchangés.
  - **En cas de `ValueError`** : on renvoie
    `rowTransaction = {"update": [ligne avec l'ancienne valeur]}` pour que la
    cellule reprenne sa valeur (aujourd'hui, elle garde la valeur refusée).
- `find_changed_cell` est supprimée avec ses tests.

### Tests

- Tests unitaires du callback au nouveau format (`cellValueChanged`), dont le
  retour arrière après une erreur et le refus pour un non-admin.
- Revoir tout test de `tests/` qui ciblerait le DOM de `admin-table`.

## Lots

Chaque lot est livrable seul :

1. `client_grid()`, puis `get_top_org_ag_grid` et `make_schema_grid` basculées
   dessus.
2. Top acheteurs/titulaires de l'observatoire (`limit`), puis suppression de
   `get_top_org_table` et de `get_yearly_statistics`.
3. Tableau des sources.
4. Résultats de recherche.
5. Sélecteur de colonnes (4 pages, recherche, garde anti-écho).
6. Admin.

## Vérification

- TDD : tests unitaires sur les composants (type `AgGrid`, `columnDefs`,
  `rowData`, options) et sur les callbacks.
- Chaque lot ne lance que ses propres fichiers de tests. En fin de chantier
  seulement : `uv run pytest` complet, puis `-m "selenium or integration"`,
  comparés à la base (`074127a`) et non au lot précédent.
- Contrôle visuel dans un navigateur, en clair et en sombre, pour chaque
  tableau migré : fond, en-tête, lignes alternées, filtres, pagination.
- Sélecteur de colonnes : rejouer le scénario d'écho dans un vrai navigateur
  (ouvrir, décocher, fermer, recharger).
