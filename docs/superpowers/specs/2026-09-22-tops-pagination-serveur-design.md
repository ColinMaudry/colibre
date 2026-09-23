# Tops acheteurs/titulaires : pagination et filtrage côté serveur (#142)

## Contexte

Les grilles « Top acheteurs » / « Top titulaires » sont des AG Grid
client-side construites par `get_top_org_ag_grid` (`src/figures.py`) :

- observatoire et mode observatoire de `/tableau` (via
  `build_dashboard_cards`) : classement tronqué à 100 lignes, sans filtre ;
- fiches acheteur (top titulaires) et titulaire (top acheteurs) : classement
  complet envoyé au navigateur (jusqu'à ~2 Mo).

Mesure sur `decp_prod.parquet`, périmètre par défaut de l'observatoire
(365 derniers jours) : 14 019 acheteurs, 77 319 titulaires ; `COUNT` de
l'agrégat, page de 100 lignes et filtre `ILIKE` ≈ 100 ms chacun. Aucun id
n'a plusieurs noms.

## Objectif

Classement complet consultable, triable et filtrable dans les quatre
contextes ; volume transmis borné à la page affichée.

## Décisions

- Filtre texte sur le nom activé **aussi dans l'observatoire** (et le mode
  observatoire de `/tableau`).
- **Pagination par 10 conservée** (pas de défilement infini), en modèle
  `infinite` avec `pagination: true`.
- Un callback de datasource **par contexte**, qui reconstruit le périmètre
  SQL depuis l'état de la page, et une fonction de requête partagée (même
  schéma que `src/utils/entity_grid.py`). Le client n'envoie jamais de SQL.
- « Attributions » (et « Distance » sur les fiches) passent en filtre
  numérique ; le tri devient numérique.
- Tri par défaut : Attributions décroissantes, puis id (pagination stable).

## Couche données — `src/utils/top_org_grid.py`

### `aggregate_marches` (`src/db.py`)

Ajout d'un argument `having: str | None = None`, inséré entre `GROUP BY` et
`ORDER BY`. Les paramètres liés du `HAVING` suivent ceux du `WHERE` dans
`params`. Appelants existants inchangés.

### Requête

```sql
SELECT "<org>_id", "<org>_nom" [, "titulaire_typeIdentifiant"] [, extra...],
       COUNT(*) AS "Attributions"
FROM decp
WHERE (<périmètre>) AND (<filtre colonnes non agrégées>)
GROUP BY <colonnes sélectionnées sauf Attributions>
HAVING <filtre Attributions>
ORDER BY <sortModel>, "<org>_id"
LIMIT <endRow - startRow> OFFSET <startRow>
```

Regroupement identique à l'actuel `_top_org_aggregate` :
`titulaire_typeIdentifiant` est ajouté pour `org_type == "titulaire"` (requis
par `add_links` pour ne lier que les SIRET) ; `extra_columns` vaut
`["titulaire_distance"]` sur les fiches, `[]` ailleurs. Compte = `COUNT(*)`
sur les lignes, comme aujourd'hui.

### Fonctions

- `top_org_filter_sql(filter_model, org_type, extra_columns) -> (where_sql, where_params, having_sql, having_params)` :
  - clés `<org>_nom` et `extra_columns` → `filtermodel_to_ast` +
    `ast_to_sql` existants (désaccentuage #138 conservé via
    `tokenize_text_filter`) ;
  - clé `Attributions` → convertisseur numérique dédié vers
    `COUNT(*) <op> ?` : `equals`, `notEqual`, `greaterThan`,
    `greaterThanOrEqual`, `lessThan`, `lessThanOrEqual`, `inRange`, et
    conditions combinées `AND`/`OR` ; valeur non numérique ignorée ;
  - toute autre clé : ignorée et journalisée (liste blanche).
- `top_org_sort_sql(sort_model, allowed_columns) -> str` : liste blanche,
  défaut `"Attributions" DESC`, `"<org>_id"` toujours en dernier critère.
- `_cached_top_count(sql, params)` (`@cache.memoize()`) :
  `SELECT COUNT(*) FROM (<agrégat sans ORDER BY/LIMIT>)`. Un seul calcul
  pour toutes les pages d'un même filtre.
- `fetch_top_org_page(org_type, where_sql, params, request, extra_columns)`
  → `{"rowData": ..., "rowCount": total}`, ou `no_update` si
  `request is None`. Les lignes sont castées en texte, `fill_null("")`, puis
  passées par `add_links` avant `to_dicts()`.

## Composant — `top_org_grid`

`top_org_grid(context, org_type, scope_key, extra_columns=())` dans
`src/utils/top_org_grid.py`. Remplace `get_top_org_ag_grid` et
`_top_org_aggregate`, supprimées avec leurs tests.

- `dag.AgGrid`, `rowModelType="infinite"`, `dashGridOptions` :
  `pagination: True`, `paginationPageSize: 10`, `cacheBlockSize: 10`,
  `localeText: AG_GRID_LOCALE_FR` (plus traduction de l'overlay « aucune
  ligne »), `theme: AG_GRID_THEME`, `suppressCellFocus: True` ; pas de
  persistance ; `dangerously_allow_code=True` pour les liens.
- Hauteur fixe (pas de `domLayout: "autoHeight"`, incompatible avec
  `infinite`) couvrant en-tête, filtre flottant, 10 lignes et barre de
  pagination ; valeur mesurée dans le navigateur, clair et sombre.
- `columnDefs` statiques :
  - `<org>_id` : absent de l'affichage ;
  - `<org>_nom` : `cellRenderer: "markdown"`, `flex: 1`,
    `agTextColumnFilter` ;
  - `titulaire_distance` (si présent) et `Attributions` :
    `agNumberColumnFilter` ;
  - `headerName` depuis `DATA_SCHEMA` comme aujourd'hui ; toutes triables ;
    filtre flottant.
- Id : `{"type": "top-org-grid", "context": <ctx>, "org_type": <org>, "scope": <scope_key>}`, `ctx ∈ {observatoire, tableau, acheteur, titulaire}`. `scope_key` force le remontage de la grille quand le
  périmètre change (sans quoi React peut réutiliser l'instance et AG Grid ne
  relance pas sa requête) ; il ne sert jamais à construire du SQL.
  - observatoire : hash court des filtres normalisés ;
  - tableau : hash court du `filterModel` JSON normalisé ;
  - fiches : `f"{entity_id}|{year}"`.
- Périmètre vide : la grille s'affiche avec l'overlay « aucune ligne »
  (plus de `html.Div()` vide).

## Construction des cards

- `build_dashboard_cards(dff, order=None, theme=None, context="observatoire", scope_key="")` : les cards « Top acheteurs » /
  « Top titulaires » utilisent `top_org_grid(context, ..., scope_key)` ;
  `dff` ne leur sert plus.
- `_compute_dashboard_children` (observatoire) et `_cards_pour_filtre`
  (tableau) passent leur contexte fixe et le `scope_key` dérivé de leur clé
  de cache existante : pas d'entrée de cache supplémentaire ; les cards en
  cache ne portent plus de lignes.
- Fiches : `get_top_titulaires` / `get_top_acheteurs` renvoient la même card
  avec `top_org_grid("acheteur", "titulaire", ..., ["titulaire_distance"])`
  et `top_org_grid("titulaire", "acheteur", ..., ["titulaire_distance"])`,
  sans plus appeler `query_marches`.

## Callbacks de datasource

Un par contexte, dans la page concernée :
`Output(id, "getRowsResponse")`, `Input(id, "getRowsRequest")`, avec
`org_type` et `scope` en `MATCH`, `context` fixé.

| Contexte     | `State`                                    | Périmètre                             |
| ------------ | ------------------------------------------ | ------------------------------------- |
| observatoire | valeurs des `FILTER_PARAMS`                | `dashboard_filters_to_sql(**filtres)` |
| tableau      | `("tableau_grid", "filterModel")`          | `filtermodel_to_ast` + `ast_to_sql`   |
| acheteur     | `acheteur_url.pathname`, `acheteur_year`   | `_acheteur_scope`                     |
| titulaire    | `titulaire_url.pathname`, `titulaire_year` | `_titulaire_scope`                    |

Les filtres de l'observatoire sont relus à la source plutôt que dans le store
`observatoire-filters`, écrit par le même callback que les cards.

## Tests

- `tests/test_top_org_grid.py` (nouveau, `tests/test.parquet`) : périmètre
  respecté ; `rowCount` = nombre de groupes ; pages successives sans
  doublon ; filtre texte trouvant une organisation au-delà du 10ᵉ rang ;
  `HAVING` sur Attributions ; tri numérique (9 < 10) ; clés de filtre/tri
  inconnues ignorées ; `COUNT` calculé une seule fois sur plusieurs pages ;
  `request=None` → `no_update` ; ids distincts par contexte et `scope`.
- `tests/api/test_db_aggregate.py` : `aggregate_marches` avec `having`.
- `tests/test_figures.py` et `tests/test_fiches_top_org.py` : tests
  `get_top_org_ag_grid` supprimés ou adaptés à `top_org_grid`.
- Selenium : une grille top de l'observatoire et une de fiche affichent des
  lignes (datasource effectivement branchée).
- Vérification manuelle locale sur données de prod : filtre, tri,
  pagination, mode sombre, changement de fiche/année (remontage).

## Hors périmètre

- Changer la métrique « Attributions » (reste `COUNT(*)` sur les lignes).
- Export des tops.
- Infobulles sur le nom (`*_tooltip`) : non affichées aujourd'hui, inchangé.
