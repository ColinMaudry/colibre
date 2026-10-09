# Filtres Objet insensibles aux accents, aux ligatures et aux apostrophes (#147)

Date : 2026-10-09

## Objectif

Un filtre sur le champ `objet` (interface, API REST, connecteur MCP) retrouve les mêmes marchés quelle que soit la
graphie saisie : accents présents ou non, « œ » ou « oe », « æ » ou « ae »,
apostrophe droite `'` ou typographique `’`. La casse est déjà ignorée.

Exemple de l'issue : chercher « maîtrise d'oeuvre » doit retourner les objets
« Maîtrise d'œuvre », « maitrise d'œuvre » et « maîtrise d'oeuvre ».

Le filtre ne doit pas devenir sensiblement plus lent qu'aujourd'hui.

## Décisions de cadrage

| Sujet                | Décision                                                                                                            | Motif                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Normalisation        | Colonne **précalculée** `objet_normalise` dans `decp`, construite au build                                          | Normaliser à la volée multiplie par 4 à 6 la latence d'un appel de grille (≈ 1 s → 4 à 8 s sur 3,3 M de lignes, mesuré sous charge). Choix de Colin       |
| Apostrophes          | `’` (U+2019) est normalisée en `'` des deux côtés                                                                   | 1 143 889 objets contiennent `’`, 14 057 contiennent `'` : sans cela, l'exemple de l'issue tapé avec `'` ne retourne rien. Choix de Colin                 |
| Périmètre des champs | `objet` seulement                                                                                                   | `acheteur_nom` et `titulaire_nom` changeront de format côté `decp-processing` : traités dans une issue séparée, que ce mécanisme prépare (voir « Suite ») |
| Opérateurs           | `contains`, `notContains`, `startsWith`, `endsWith` sont normalisés. `equals` et `notEqual` restent exacts          | Une égalité exacte doit pouvoir distinguer deux graphies                                                                                                  |
| Surfaces             | Grilles `/tableau`, acheteur, titulaire ; filtre Objet de l'observatoire ; API REST `/data` ; MCP                   | Interface : `tokenize_text_filter` et `query_ast`. API et MCP : `build_where` (`src/api/filters.py`). Élargissement demandé par Colin le 2026-10-09       |
| API et MCP           | `contains`, `notcontains` et `startswith` sur `objet` sont normalisés ; sémantique de sous-chaîne entière conservée | L'API n'a pas de découpage en mots ni de jokers ; on ne change que la comparaison                                                                         |

## Contexte : l'existant et les mesures

- `tokenize_text_filter` (`src/utils/table_sql.py`) est le point commun : il sert
  la grille via `query_ast.ast_to_sql` et le filtre Objet de l'observatoire via
  `dashboard_filters_to_sql`. Avant ce chantier il ne désaccentuait que la
  saisie, et seulement pour `acheteur_nom` et `titulaire_nom` (#138), dont les
  valeurs sont stockées sans accents.
- `objet` contient de vrais accents : 1 558 843 lignes sur 3 302 188 portent au
  moins un caractère accentué.
- Les opérateurs `startsWith` et `endsWith` de `query_ast.py` n'utilisaient pas
  `tokenize_text_filter` : ils étaient eux aussi sensibles aux accents.
- L'API REST `/data` (`src/api/filters.py`, `build_where`) et le MCP
  (`rechercher_marches`, paramètre `objet_contient`) utilisent un `ILIKE` distinct, sur
  la sous-chaîne entière (`%valeur%`), sans normalisation : ils étaient sensibles aux
  accents et aux ligatures. Le MCP appelle le même `build_where` que l'API.
- Le chemin Polars historique (`prepare_table_data`, `filter_table_data`,
  `filter_query_to_sql`) n'était appelé par aucune page : c'était du code mort,
  supprimé dans ce chantier (voir « Code mort supprimé »).

Mesures sur `decp_prod.parquet` (3 306 481 lignes), DuckDB, 16 threads. Les
lignes « `ILIKE` » du haut ont été prises machine au repos ; celles de la grille et
de la colonne précalculée pendant que la suite Selenium tournait en parallèle.
Seuls les ordres de grandeur et les rapports comptent, pas les dixièmes de seconde.

| Mesure                                                             | Valeur                               |
| ------------------------------------------------------------------ | ------------------------------------ |
| `ILIKE` sur `objet` brut (lu dans le parquet)                      | 0,22 s                               |
| `ILIKE` avec `strip_accents` + `replace` à la volée                | 0,86 à 1,11 s (×4 à ×5)              |
| Appel de grille (`fetch_grid_page`), sans normalisation            | 1,0 à 1,6 s (sous charge)            |
| Appel de grille, normalisation à la volée                          | 4,2 à 7,7 s (sous charge)            |
| `ILIKE` sur la colonne `objet` de la table / sur `objet_normalise` | 0,59 s / 0,57 à 0,63 s (sous charge) |
| Taille de la base : sans / avec `objet_normalise`                  | 1 020 Mo / 1 317 Mo (+ 29 %)         |
| Construction de `decp` : sans / avec `objet_normalise`             | 15,6 s / 20,2 s                      |
| `%d'oeuvre%` sur `objet_normalise` (apostrophe droite saisie)      | 114 901 lignes (0 sur `objet` brut)  |

## Design

### 1. `src/utils/text_normalization.py` (nouveau)

Module sans dépendance interne, importable par `src/db.py` comme par
`src/utils/`.

- `NORMALIZED_COLUMNS = {"objet": "objet_normalise"}` : correspondance entre une
  colonne filtrable et sa colonne précalculée. C'est le seul endroit à modifier
  pour étendre le mécanisme à un autre champ.
- `normalize_text(text: str) -> str` : décomposition Unicode NFD, suppression des
  marques combinantes (accents, cédille), puis `œ→oe`, `Œ→OE`, `æ→ae`, `Æ→AE`
  et `’→'`. Ne change pas la casse : l'`ILIKE` s'en charge.
- `normalize_text_sql(expr: str) -> str` : expression DuckDB équivalente, à base
  de `strip_accents` et de `replace` imbriqués.
- `normalized_target(column: str, quoted_col: str) -> str` : renvoie la colonne
  précalculée (entre guillemets) si `column` figure dans `NORMALIZED_COLUMNS`, et
  `quoted_col` sinon. Utilisée par la grille et par l'API.
- `normalized_term(column: str, term: str) -> str` : applique `normalize_text` si
  `column` figure dans `NORMALIZED_COLUMNS`, et renvoie `term` sinon.

`normalize_text` et `normalize_text_sql` doivent produire le même résultat : la
colonne est calculée par DuckDB, la saisie par Python. Un test de parité le vérifie
(voir « Tests »).

### 2. `src/db.py`

- `build_database` crée `decp` avec la colonne :
  `SELECT *, {normalize_text_sql('objet')} AS objet_normalise FROM read_parquet(...)`.
  Une valeur `NULL` ou vide de `objet` donne `NULL` ou vide dans la colonne.
- `SCHEMA_VERSION` passe de 2 à 3 (commentaire : « 3 : #147 ajoute
  `objet_normalise` à `decp` »). `schema_est_perime` provoque la reconstruction
  au premier démarrage suivant.
- La colonne est technique : elle ne doit apparaître ni dans la grille, ni dans
  les exports, ni dans le sélecteur de colonnes, ni dans le décompte « N colonnes
  filtrables », ni dans l'API ou le MCP. Pour cela :
  - `schema` est lu avec `SELECT * EXCLUDE (objet_normalise) FROM decp LIMIT 0` ;
  - `query_marches(columns=None)` utilise `SELECT * EXCLUDE (objet_normalise)`.
- L'API REST et le MCP valident déjà les colonnes contre `schema`
  (`col not in schema` → 400) : `objet_normalise` y est donc inconnue, sans
  changement de leur code.

Les tables `acheteurs_marches`, `titulaires_marches`, `acheteurs_departement` et
`titulaires_departement` ne changent pas.

### 3. `src/utils/table_sql.py` et `src/utils/query_ast.py`

- `text_filter_target(column, quoted_col)` délègue à `normalized_target` ; elle ne
  contient plus de cas particulier pour `objet`.
- `normalize_text_term(column, term)` délègue à `normalized_term` pour les colonnes
  de `NORMALIZED_COLUMNS`, applique `unidecode` pour `_ACCENT_INSENSITIVE_COLUMNS`
  (`acheteur_nom`, `titulaire_nom`, inchangé), et ne touche pas les autres.
- `tokenize_text_filter` garde ses conditions `IS NOT NULL` et `<> ''` sur la
  colonne d'origine et compare la colonne cible à la saisie normalisée. Les
  jokers `*` et les phrases `+` gardent leur sémantique.
- `query_ast._condition_to_sql` utilise les deux helpers pour `startsWith` et
  `endsWith`.
- Le code actuel de `table_sql.py` qui normalise la colonne à la volée
  (`_strip_accents_sql`, `_strip_accents`, `_LIGATURES`,
  `_ACCENT_NORMALIZED_COLUMNS`) est remplacé : il n'en reste rien.

### 4. `src/api/filters.py` (API REST et MCP)

Le MCP passe par le même `build_where` que l'API : `objet_contient` devient
`objet__contains` (`src/mcp/queries.py`, `_NAMED_FILTERS`), et `filtres_avances`
accepte aussi `objet__contains`, `objet__notcontains` et `objet__startswith`. Un seul
changement couvre donc les deux.

- Pour les opérateurs `contains`, `notcontains` et `startswith`, si la colonne figure
  dans `NORMALIZED_COLUMNS`, `build_where` compare la colonne précalculée
  (`normalized_target`) à la valeur normalisée (`normalized_term`).
- La sémantique reste celle de l'API : sous-chaîne **entière** (`%valeur%`), sans
  découpage en mots ni jokers `*` et `+` (qui sont propres à la grille).
- `exact`, `differs`, `in`, `notin`, les comparaisons, `isnull`, `isnotnull` et `sort`
  restent sur la colonne d'origine : une égalité exacte doit pouvoir distinguer deux
  graphies, et un tri se fait sur le texte affiché.
- `objet_normalise` reste inconnue de l'API (`col not in schema` → 400) : elle n'est
  pas filtrable ni sélectionnable directement.

### 5. Code mort supprimé (déjà fait dans ce chantier)

Aucune page n'appelait `prepare_table_data` : l'ancien chemin `dash_table`, remplacé
par AG Grid, ne servait plus qu'aux tests. Supprimés :

- `src/utils/table.py` : `prepare_table_data`, `_fetch_page_sql`,
  `filter_table_data`, `sort_table_data`, `_deaccent_col`, `_ACCENT_REPLACEMENTS`,
  `split_filter_part`, `dates_to_strings`, `numbers_to_strings`,
  `normalize_sort_by`, `setup_table_columns`, `invert_columns`,
  `build_view_query`, et les imports devenus inutiles ;
- `src/utils/table_sql.py` : `filter_query_to_sql` ;
- `src/figures.py` : la classe `DataTable` ;
- `tests/saved_views/test_build_view_query.py` et les tests des fonctions
  ci-dessus dans `tests/test_table.py` et `tests/test_table_sql.py`.

Conservés car utilisés : `sort_by_to_sql`, `tokenize_text_filter`,
`dashboard_filters_to_sql`, `postprocess_page`, `add_links`, `format_values`,
`get_default_hidden_columns`, `COLUMNS` et les fonctions de sélection de colonnes.

## Tests

Tous exécutent de vraies requêtes DuckDB ; aucun ne fige le texte SQL.

- **Comportement** (`tests/test_filtre_objet_accents_oe.py`, existant, adapté pour
  construire `objet_normalise` avec `normalize_text_sql`) :
  - les 3 graphies de l'issue sont retrouvées avec chacune des saisies
    (accents ou non, œ ou oe, majuscules), apostrophe droite ou typographique ;
  - `notContains`, `startsWith`, `endsWith` ; `equals` reste exact ;
  - jokers et phrases ; `NULL` et chaîne vide jamais retournés ;
  - le filtre Objet de l'observatoire ;
  - `acheteur_nom` et `titulaire_nom` inchangés.
- **API REST et MCP** (`tests/api/`, `tests/mcp/`) : exécutés dans un DuckDB avec
  `objet_normalise`, via `build_where` :
  - `objet__contains`, `objet__notcontains` et `objet__startswith` retrouvent les
    3 graphies de l'issue avec chacune des saisies ; `objet__exact` reste exact ;
  - `search_marches(objet_contient="maitrise d'oeuvre")` retourne les marchés
    attendus ;
  - `acheteur_nom__contains` garde son comportement actuel ;
  - les tests de `tests/api/test_filters.py` qui figent le texte SQL de `objet`
    (`'"objet" ILIKE ?'`, `'"objet" NOT ILIKE ?'`) sont remplacés par ces tests de
    comportement, car ils décrivent l'implémentation et non le résultat.
- **Parité** : `normalize_text` (Python) et `normalize_text_sql` (DuckDB) donnent le
  même résultat sur un échantillon couvrant é è ê ë à ç î ï ô ù û ü ñ, majuscules
  accentuées, œ Œ æ Æ, `’`, caractères non latins et chaîne vide.
- **Schéma** : après `build_database`, `decp` contient `objet_normalise` ;
  `schema.names()`, `COLUMNS` et `query_marches()` ne la contiennent pas ; l'API
  répond 400 à `objet_normalise__contains=x` et à `columns=objet_normalise`.
- **Version** : `test_schema_version.py` couvre déjà la reconstruction ; le test
  `test_la_base_construite_porte_la_version_courante` couvre la version 3.
- **Régression** : suite complète (`uv run pytest`) et, hors suite par défaut,
  `uv run pytest -m selenium`.
- **Smoke** : sur `decp_prod.parquet`, `fetch_grid_page` avec « maitrise d'oeuvre »,
  « MAÎTRISE D’ŒUVRE » et « maîtrise d’œuvre » retourne le même total, dans un
  temps comparable à un filtre sans normalisation. `GET /data?objet__contains=…`
  et `search_marches(objet_contient=…)` retournent le même total pour ces trois
  saisies.

## Déploiement

- Le premier démarrage après déploiement reconstruit la base (≈ 20 s sur la
  machine de développement, ≈ 5 s de plus qu'avant). La reconstruction se fait
  sous verrou ; les autres workers attendent.
- La base grossit de ≈ 300 Mo. Pendant la construction coexistent la base
  temporaire, le parquet intermédiaire et l'ancienne base : prévoir la place.
- Si la reconstruction échoue, `_ensure_database` réutilise l'ancienne base (comportement
  existant). Celle-ci n'a pas `objet_normalise` : les filtres sur `objet` lèvent alors
  une erreur DuckDB tant que la base n'est pas reconstruite. Même mode de défaillance
  que l'incident du 2026-07-30 décrit dans `src/db.py`.
- `CHANGELOG.md` : « les filtres sur l'objet (interface, API REST, connecteur MCP) ne
  sont plus sensibles aux accents, à œ/oe ni à l'apostrophe typographique (#147) ».
- Documentation : `src/api/routes.py` (description des opérateurs `contains`,
  `notcontains`, `startswith`) et la docstring de l'outil MCP `rechercher_marches`
  (`objet_contient`, `src/mcp/tools.py`) précisent que la comparaison ignore casse,
  accents, ligatures et apostrophes typographiques sur `objet`.

## Hors périmètre

- Les opérateurs de l'API qui doivent rester exacts (`exact`, `differs`, `in`,
  `notin`, `sort`) et les filtres de l'API sur les autres colonnes
  (`acheteur_nom__contains`, etc.) : inchangés.
- `¿` (U+00BF, 15 888 objets) : défaut d'encodage des données sources (« D¿OEUVRE »),
  à corriger en amont dans `decp-processing`, pas ici.
- Autres apostrophes : `‘` apparaît dans 399 objets, `´` dans 20, `` ` `` dans 7.
  Seule `’` est normalisée.
- Le test Selenium `test_le_mode_observatoire_persiste_apres_rechargement` échoue déjà
  sur `HEAD` ; il n'est pas lié à ce chantier.

## Suite : `acheteur_nom` et `titulaire_nom` (issue séparée)

Ces noms sont aujourd'hui en majuscules sans accents (seules 380 lignes de
`acheteur_nom` et ~7 000 de `titulaire_nom` en diffèrent). `decp-processing` les
publiera bientôt en casse normale avec accents. Ce mécanisme est conçu pour que
l'extension soit une modification de `NORMALIZED_COLUMNS` : ajouter
`acheteur_nom` et `titulaire_nom`, construire leurs colonnes précalculées et
retirer `_ACCENT_INSENSITIVE_COLUMNS`. L'issue séparée traite aussi `search_org`
(`src/utils/search.py`), qui compare une saisie en majuscules sans accents à des
colonnes supposées l'être, pour `/recherche` et le MCP.
