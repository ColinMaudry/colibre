# Filtres texte booléens : OU, ET, PAS, parenthèses et guillemets (#97)

Date : 2026-10-09

## Objectif

Dans un filtre texte de colonne, l'utilisateur combine plusieurs critères avec
`OU`, `ET`, `PAS` et des parenthèses, et cherche une suite de mots exacte entre
guillemets doubles. Exemples de l'issue :

- `amo OU assistance` ; `35 OU 44` sur un département ;
- `"Clause sociale" ET "Critère social"` sur les considérations sociales ;
- `(béton OU ciment) ET brique` ;
- `travaux ET PAS construction`, `conseil ET PAS "étude de marché"` ;
- `"maintenance sur site"` : les trois mots groupés, dans cet ordre.

Les guillemets remplacent le groupage de mots par `+`, introduit du temps de
Dash DataTable, où les guillemets faisaient échouer les filtres.

## Décisions de cadrage

| Sujet                              | Décision                                                                                                                                                    | Motif                                                                                                                                                            |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Accès                              | `OU`, `ET`, `PAS` et parenthèses réservés aux abonné·es (essai compris, `current_user_has_subscription()`)                                                  | Choix de Colin ; déjà prévu par la spec AG Grid du 2026-07-09                                                                                                    |
| Gratuit                            | Guillemets, jokers `*` et ET implicite (espace) pour tout le monde                                                                                          | Équivalent fonctionnel d'aujourd'hui : `"…"` remplace `+`, aucune régression pour les non-abonnés                                                                |
| Non-abonné qui saisit un opérateur | Opérateurs et parenthèses cherchés comme des mots ordinaires, et bandeau d'invitation à s'abonner                                                           | Comportement actuel conservé ; le bandeau explique le résultat                                                                                                   |
| Portée                             | Syntaxe propre à chaque colonne, dans toute condition _contient_ et _ne contient pas_, saisie dans le champ principal ou dans le filtre complet (entonnoir) | L'issue parle d'une syntaxe « pour chaque champ ». Le compilateur ne sait pas d'où vient une condition : la restreindre au champ principal serait plus compliqué |
| Surfaces                           | Grilles `/tableau` (y compris le mode observatoire et les exports), grilles et tops des fiches acheteur et titulaire, champ Objet de `/observatoire`        | Tout ce qui passe aujourd'hui par `tokenize_text_filter`                                                                                                         |
| API REST et MCP                    | Inchangés                                                                                                                                                   | Moteur distinct (`build_where`), sémantique de sous-chaîne entière alignée sur data.gouv.fr                                                                      |
| Mots-clés                          | `OU`, `ET`, `PAS`, en majuscules uniquement, comme mots isolés                                                                                              | En minuscules, `ou`, `et`, `pas` restent cherchables ; `OUEST` n'est pas `OU`                                                                                    |
| Saisie incomplète                  | Réparation tolérante, signalée dans la pastille                                                                                                             | AG Grid applique le filtre pendant la frappe : `(béton OU` est un état normal. Une grille vide à chaque étape serait indiscernable d'une absence de résultat     |
| `OU PAS`                           | Logique stricte, sans avertissement                                                                                                                         | `béton OU PAS ciment` vaut `béton OU (PAS ciment)`                                                                                                               |
| Ancien `+`                         | Supprimé ; les vues sauvegardées sont migrées vers les guillemets                                                                                           | Le `+` reste ailleurs (localStorage, liens d'observatoire) un caractère littéral                                                                                 |
| Conception                         | La saisie reste une chaîne dans `Condition.value`, compilée par un sous-compilateur dédié                                                                   | Vues sauvegardées, `ast_to_filtermodel` et suivi Matomo inchangés (approche « A » retenue)                                                                       |

### Approches écartées

- **Éclater l'expression en nœuds `query_ast`** (`Or`, `And`, `Not` de
  `Condition('contains', mot)`) : les vues sauvegardées stockent cet AST, et
  `_child_to_filterspec` ne sait pas reconvertir `Not` ni une imbrication en
  `filterModel`. Une vue perdrait son filtre ; `Condition` devrait en plus
  distinguer les phrases.
- **Bibliothèque d'analyse syntaxique** (lark, pyparsing) : une dépendance pour
  six sortes de jetons, et une reprise sur erreur tolérante plus difficile à
  obtenir qu'avec un analyseur écrit à la main.
- **Champ de requête inter-colonnes** (spec AG Grid du 2026-07-09,
  `query_string_to_ast`) : hors périmètre. L'issue décrit une syntaxe par
  champ.

## Contexte : l'existant

- `tokenize_text_filter` (`src/utils/table_sql.py`) est aujourd'hui le seul
  interprète de saisie texte. Il découpe sur les blancs, relie les mots par
  `AND`, traite `+` comme une espace de phrase et `*` en tête ou en fin de mot
  comme joker. Il applique `normalize_text_term` et `text_filter_target`
  (colonne précalculée `objet_normalise`, #147 ; désaccentuation de la saisie
  pour `acheteur_nom` et `titulaire_nom`, #138).
- Il a deux appelants : `query_ast._condition_to_sql` (opérateurs `contains`
  et `notContains`, toutes les grilles) et `dashboard_filters_to_sql` (champ
  Objet de l'observatoire).
- `contains` produit `"col" IS NOT NULL AND col <> '' AND …` ; `notContains`
  produit `NOT (…)` de cette conjonction, donc inclut les valeurs nulles ou
  vides.
- `ast_to_sql` est appelé directement par `grid.fetch_grid_page`,
  `grid.export_dataframe`, `top_org_grid.top_org_filter_sql`, et dans
  `tableau.py` par `_cards_pour_filtre` et `get_top_org_rows_tableau`.
  `fetch_grid_page` et `export_dataframe` servent `/tableau` et les fiches
  (`entity_grid`).
- Deux caches sont indexés sur le filtre et non sur le SQL :
  `tableau._cards_pour_filtre(filter_model_json, theme)` et
  `observatoire._compute_dashboard_children(filter_params_normalized, theme)`.
  `_cached_count`, `_cached_unique_count` et `_cached_top_count` sont indexés
  sur le SQL.
- Les pastilles (`src/utils/filter_pills.py`, #148) sont rendues côté serveur
  par un callback sur `filterModel` ; elles affichent l'opérateur et la valeur
  saisie.
- `src/migrations.py` n'accepte que du SQL (`_MIGRATIONS : list[tuple[str, str]]`).
- Les vues sauvegardées stockent `{"ast": ast_to_dict(...), "columnState": ...}`
  en JSON dans `saved_views.query` ; une condition y est
  `{"t": "cond", "column", "operator", "value", "value2"}`.

## Design

### 1. Syntaxe et sémantique

#### Jetons (drapeau `operateurs` actif)

- `(` et `)` ;
- `"…"` : phrase exacte. Tout y est littéral, y compris `OU`, `ET`, `PAS`, les
  parenthèses et `*` ;
- `OU`, `ET`, `PAS` : opérateurs s'ils sont écrits en majuscules et isolés
  (délimités par des blancs, des parenthèses, des guillemets ou les bords de
  la saisie) ;
- tout autre suite de caractères non blancs est un **mot**. `+` est un
  caractère ordinaire.

#### Priorité

`PAS` > `ET` (explicite, ou implicite entre deux termes juxtaposés) > `OU`.

- `béton ciment OU brique` = `(béton ET ciment) OU brique` ;
- `PAS a b` = `(PAS a) ET b` ;
- `béton OU PAS ciment` = `béton OU (PAS ciment)`.

#### Feuilles

Chaque feuille est un `ILIKE` paramétré sur la colonne cible
(`text_filter_target`), insensible à la casse. Le terme passe par
`normalize_text_term` : insensible aux accents, ligatures et apostrophes
typographiques sur `objet`, désaccentué pour `acheteur_nom` et `titulaire_nom`.

- **Mot** : sémantique actuelle. Sous-chaîne `%mot%` ; si le mot commence ou
  finit par `*`, tous ses `*` deviennent `%` sans `%` ajouté autour
  (`distri*` : préfixe de la valeur, `*rue` : suffixe). Un `*` au milieu seul
  reste littéral.
- **Phrase** : sous-chaîne `%phrase%`, `*` littéral.

Les jokers `%` et `_` de `LIKE` saisis par l'utilisateur ne sont pas échappés
(comportement actuel, hors périmètre).

#### Valeurs vides

- _contient_ : `"col" IS NOT NULL AND col <> '' AND (expression)`. Exemple :
  `PAS construction` retourne les lignes non vides qui ne contiennent pas
  « construction ».
- _ne contient pas_ : `NOT (…)` de la conjonction précédente, comme
  aujourd'hui : les valeurs nulles ou vides sont incluses.
- Expression vide après réparation (saisie vide, `ET` seul, `()`) : seule la
  garde est appliquée (_contient_ = « n'est pas vide »), comme une saisie vide
  aujourd'hui.
- _commence par_, _se termine par_, _égal à_, _différent de_ : aucune syntaxe,
  la valeur est prise telle quelle (inchangé).

#### Non-abonnés (`operateurs=False`)

- Guillemets, `*` et ET implicite actifs ;
- `OU`, `ET`, `PAS` sont des mots ordinaires ; `(` et `)` sont des caractères
  des mots qui les portent ;
- si la saisie contient un de ces mots-clés en majuscules ou une parenthèse
  hors guillemets, `operateurs_ignores` est vrai et déclenche le bandeau
  (section 4).

#### Réparations (abonnés)

L'analyseur ne rejette jamais une saisie. Il la répare et note chaque
correction par un libellé court. Pour un non-abonné, les guillemets sont
réparés de la même façon (fermés en fin de saisie, `""` ignorés) mais sans
correction notée : sa pastille reste neutre.

| Cas                                                                                    | Réparation                                             | Libellé                        |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------ |
| `(` sans `)`                                                                           | fermée en fin de saisie                                | parenthèse manquante           |
| `)` sans `(`                                                                           | ignorée                                                | parenthèse en trop             |
| Opérateur binaire sans terme d'un côté (`béton OU`, `ET ciment`, `béton OU OU ciment`) | opérateur ignoré                                       | ET orphelin / OU orphelin      |
| `PAS` sans terme à sa suite (`travaux ET PAS`)                                         | ignoré, avec l'opérateur qui le précède le cas échéant | PAS orphelin                   |
| `"` non fermé                                                                          | fermé en fin de saisie                                 | guillemet manquant             |
| `()`                                                                                   | ignorées                                               | parenthèses vides              |
| `""`                                                                                   | ignorés                                                | guillemets vides               |
| Plus de 10 niveaux d'imbrication                                                       | parenthèses au-delà ignorées                           | trop de parenthèses imbriquées |

Les libellés sont dédoublonnés et ordonnés selon la position, dans la saisie,
du jeton en cause (pour une parenthèse manquante : la `(` non fermée). La
limite d'imbrication protège l'analyseur récursif (limite de récursion
Python : 1 000).

Une paire vide dont la `)` a été ajoutée par réparation (`béton (`) ne
produit que « parenthèse manquante », pas « parenthèses vides ». Une phrase
qui ne contient que des blancs (`" "`) est traitée comme `""`.

Exemples :

| Saisie             | Expression appliquée    | Corrections                       |
| ------------------ | ----------------------- | --------------------------------- |
| `(béton OU`        | `béton`                 | parenthèse manquante, OU orphelin |
| `(béton OU ciment` | `béton OU ciment`       | parenthèse manquante              |
| `béton) ET brique` | `béton ET brique`       | parenthèse en trop                |
| `travaux ET PAS`   | `travaux`               | PAS orphelin                      |
| `"maintenance sur` | `"maintenance sur"`     | guillemet manquant                |
| `ET`               | (vide : n'est pas vide) | ET orphelin                       |

### 2. Module `src/utils/text_query.py` (nouveau)

Dépend seulement de `src/utils/text_normalization.py` et de `unidecode`.
`normalize_text_term`, `text_filter_target` et `_ACCENT_INSENSITIVE_COLUMNS`
y sont déplacés depuis `src/utils/table_sql.py` : `table_sql` importe
`text_query` (filtre Objet de l'observatoire), l'inverse créerait un import
circulaire. `query_ast` les importe désormais depuis `text_query`.

- Arbre privé : `Mot(texte)`, `Phrase(texte)`, `Et(enfants)`, `Ou(enfants)`,
  `Pas(enfant)`.
- `Expression` (dataclass) : `arbre` (ou `None` si vide), `corrections`
  (liste ordonnée de libellés), `operateurs_ignores` (bool), `saisie` (texte
  d'origine).
- `analyser(texte: str, operateurs: bool) -> Expression` : analyseur lexical
  et descente récursive écrits à la main, avec les réparations de la section 1.
- `en_sql(expression, colonne: str, col_is_date: bool = False) -> tuple[str, list]` :
  garde des valeurs vides puis expression, valeurs toujours en paramètres `?`.
  Le nom de colonne est validé par l'appelant (comme aujourd'hui).
- `en_texte(expression) -> str` : texte affiché dans les pastilles et sous le
  champ Objet. Sans correction : la saisie, blancs consécutifs réduits. Avec
  corrections : forme canonique, `ET` explicite entre termes, parenthèses
  seulement là où la priorité l'exige, phrases entre guillemets. Chaîne vide
  si l'arbre est vide.
- `libelle_corrections(expression) -> str` : `"parenthèse manquante, OU orphelin"`,
  ou chaîne vide.

`tokenize_text_filter` est **supprimée**. Ses deux appelants utilisent
`analyser` puis `en_sql`.

### 3. Transmission du drapeau `operateurs`

- `ast_to_sql(node, schema, *, operateurs: bool)` : argument nommé
  **obligatoire**, propagé à `_join` et `_condition_to_sql`. Un appelant
  oublié échoue bruyamment au lieu de prendre une valeur par défaut.
  `_condition_to_sql` appelle `analyser(str(cond.value), operateurs)` puis
  `en_sql` pour `contains`, et `NOT (…)` du même résultat pour `notContains`.
- Même argument nommé obligatoire sur `grid.fetch_grid_page`,
  `grid.export_dataframe`, `entity_grid.fetch_entity_page`,
  `entity_grid.export_entity_dataframe`, `top_org_grid.top_org_filter_sql`,
  `top_org_grid.fetch_top_org_page`, `table_sql.dashboard_filters_to_sql` et
  `data.prepare_dashboard_data`.
- Les callbacks des pages (`tableau.py`, `observatoire.py`, `acheteur.py`,
  `titulaire.py` et les callbacks enregistrés par `entity_grid` et
  `top_org_grid`) calculent le drapeau par `current_user_has_subscription()`,
  importé depuis `src.pages._compte_shell` comme le font déjà `theme.py` et
  `mcp/account.py`. Les modules de `src/utils/` ne lisent jamais
  `current_user` pour le SQL.
- Caches : `_cards_pour_filtre(filter_model_json, theme, operateurs)` et
  `_compute_dashboard_children(filter_params_normalized, theme, operateurs)`
  ajoutent le drapeau à leur clé, sans quoi un non-abonné pourrait recevoir le
  résultat calculé pour un abonné (et inversement). Les caches indexés sur le
  SQL n'ont rien à changer : le SQL diffère déjà.

### 4. Interface

#### Pastilles (`src/utils/filter_pills.py`)

- `_render` lit `current_user_has_subscription()` et le passe à
  `filter_pills(filter_model, context, operateurs)`.
- Pour une condition `contains` ou `notContains` de type texte, l'expression
  affichée est `en_texte(analyser(valeur, operateurs))` ; si
  `libelle_corrections` n'est pas vide, il suit entre parenthèses. Si
  l'expression appliquée est vide, l'opérateur affiché devient « n'est pas
  vide » pour _contient_ et « est vide » pour _ne contient pas_.
- La pastille prend la classe `filter-pill-warning` dès qu'une de ses
  conditions a été corrigée : fond `--bs-warning-bg-subtle`, bordure
  `--bs-warning-border-subtle`, texte `--bs-warning-text-emphasis` (compatible
  avec le mode sombre). Pas d'icône, pas d'infobulle.
- Exemples :
  - `[ Objet contient béton (parenthèse manquante, OU orphelin) × ]`
  - `[ Objet contient béton (ET orphelin) × ]`
  - `[ Objet n'est pas vide (ET orphelin) × ]`
  - `[ Objet contient béton (OU orphelin) ou contient brique × ]` (deux
    conditions AG Grid reliées par OU)
- Bandeau non-abonné : si une condition a `operateurs_ignores`, le même
  callback ajoute à la suite des pastilles un `html.Span` (classe
  `filter-pills-banniere`, couleurs d'avertissement ; un `div` comme
  `dbc.Alert` serait invalide dans le `span` des pastilles) : « Les
  opérateurs OU, ET, PAS et les parenthèses sont réservés aux abonné·es.
  [S'abonner](/projet/abonnement) ». Couvre
  `/tableau`, acheteur et titulaire sans nouvel identifiant de layout. La
  pastille d'un non-abonné affiche la saisie telle quelle, sans classe
  d'avertissement.

#### Observatoire (`src/pages/observatoire.py`)

- Un `dbc.FormText` (id `dashboard_marche_objet_aide`) sous le champ
  `dashboard_marche_objet`, vide par défaut.
- Un callback sur la valeur du champ y écrit, selon le cas :
  - corrections : « Filtre appliqué : béton (parenthèse manquante) », avec
    les couleurs d'avertissement ;
  - non-abonné avec `operateurs_ignores` : le message du bandeau ;
  - sinon : rien.

#### Limite acceptée

Les tops des fiches acheteur et titulaire ont des filtres de colonne mais pas
de pastilles : la syntaxe s'y applique, sans affichage des corrections ni
bandeau.

### 5. Documentation

- Mode d'emploi de `/tableau` (`tableau.py`, section « Filtrer les colonnes »)
  : nouveau bloc « Syntaxe des champs texte », valable pour _contient_ et
  _ne contient pas_, dans le champ principal comme dans le filtre complet :
  - pour tous : espace = ET, `"maintenance sur site"` pour une suite de mots
    exacte, `béton*` et `*béton` pour un début ou une fin ;
  - abonné·es : `OU`, `ET`, `PAS` en majuscules et parenthèses, avec les
    exemples `(béton OU ciment) ET brique`, `travaux ET PAS construction`,
    `conseil ET PAS "étude de marché"`, `"Clause sociale" ET "Critère social"`.
    `PAS` n'est illustré qu'avec `ET` ;
  - les pastilles montrent le filtre réellement appliqué et signalent les
    corrections.
- `/projet/abonnement` (`abonnement_features`) : puce « combinez vos filtres
  texte avec OU, ET, PAS et des parenthèses (Tableau, fiches, Observatoire) ».
- Docstring de `query_ast.py` (l. 3-4) : #97 passe par le texte des
  conditions `contains`, pas par un second producteur d'AST.
- `CLAUDE.md`, section « Migrations de schéma SQLite » : une migration peut
  être une fonction Python (section 6).
- `CHANGELOG.md` : non modifié par ce chantier (tenu par Colin à la
  publication).

### 6. Migration des vues sauvegardées

- `_MIGRATIONS` devient `list[tuple[str, str | Callable[[sqlite3.Connection], None]]]`.
  `apply_pending` exécute le SQL comme aujourd'hui, ou appelle la fonction
  avec la connexion entre un `BEGIN` et un `COMMIT` explicites (`get_conn`
  est en autocommit), avec l'enregistrement de l'id dans `schema_migrations`
  ; en cas d'erreur, `ROLLBACK` puis l'exception remonte.
- Migration `0017_saved_views_plus_vers_guillemets` : pour chaque ligne de
  `saved_views`, lit `query` (JSON), parcourt `ast` et réécrit la `value` des
  nœuds `{"t": "cond"}` dont l'`operator` est `contains` ou `notContains` et
  la valeur une chaîne. N'écrit la ligne que si elle change.
  Une `query` qui n'est pas du JSON, ou sans clé `ast` (anciennes vues, que
  `saved_views/resolve.py` tolère déjà), est laissée telle quelle.
- Règle de réécriture, mot par mot (découpage sur les blancs) :
  - un mot contenant `+` devient une phrase : `maitrise+d'oeuvre` →
    `"maitrise d'oeuvre"` ;
  - sauf s'il commence ou finit par `*` (aujourd'hui le `+` y est littéral) ;
  - sauf s'il contient déjà `"`.
- La table peut ne pas exister sur une base fraîche : la fonction ne fait
  rien dans ce cas.
- Non couverts : filtres persistés dans le navigateur et liens d'observatoire
  `?objet=…+…`. Leur `+` devient littéral.

## Tests

Tous exécutent de vraies requêtes DuckDB ; aucun ne fige le texte SQL.

- **`tests/test_text_query.py`** (nouveau), sur une petite table DuckDB en
  mémoire :
  - résultats : `béton OU ciment`, `(béton OU ciment) ET brique`,
    `béton ciment OU brique` (priorité), `travaux ET PAS construction`,
    `conseil ET PAS "étude de marché"`, `béton OU PAS ciment` (garde « Béton
    et ciment » et « Entretien des espaces verts », exclut « Fourniture de
    ciment ») ;
  - `"maintenance sur site"` exige l'ordre des mots ;
    `"Clause sociale" ET "Critère social"` sur une colonne multivaluée ;
  - `OUEST` et `ou` en minuscules sont des mots ; `OU` entre guillemets est
    littéral ; `*` en tête et en fin ; `+` littéral ;
  - normalisation dans une phrase : `"maitrise d'oeuvre"` retrouve
    « Maîtrise d’œuvre » ;
  - _contient_ ne retourne jamais `NULL` ni `''`, même avec `PAS x` ;
    _ne contient pas_ les inclut ;
  - chaque réparation, combinaisons ordonnées et dédoublonnées, imbrication
    au-delà de 10 niveaux, `ET` seul ; `en_texte` et `libelle_corrections` ;
  - non-abonné : `béton OU ciment` cherché comme trois mots,
    `operateurs_ignores` vrai, guillemets et `*` actifs ;
  - une valeur `x' OR 1=1 --` ne retrouve qu'elle-même.
- **Tests existants adaptés** : les cas `+` de `test_query_ast.py`
  (`test_text_contains_wildcard_and_phrase`) et de
  `test_filtre_objet_accents_oe.py`
  (`test_contains_joker_et_phrase_gardent_leur_semantique`) passent aux
  guillemets. L'argument `operateurs` est ajouté dans
  `test_dashboard_filters_to_sql.py`, `test_grid.py`, `test_top_org_grid.py`,
  `test_entity_grid.py` et dans les doublures de `test_theme_cache.py`.
- **Caches** : un même filtre avec `operateurs` vrai puis faux donne deux
  résultats différents via `_cards_pour_filtre` et via
  `_compute_dashboard_children`.
- **Pastilles** (`tests/test_filter_pills.py`) : condition corrigée → texte
  appliqué suivi des corrections et classe d'avertissement ; condition propre
  → pas de classe ; non-abonné avec opérateur → bandeau ; abonné → pas de
  bandeau.
- **Migration** (`tests/saved_views/`) : une vue avec `maitrise+d'oeuvre`
  devient `"maitrise d'oeuvre"` ; `a+b*`, un mot contenant `"` et les
  conditions non textuelles sont inchangés ; une seconde exécution est sans
  effet ; une migration SQL existante s'applique toujours.
- **Selenium**, sur le modèle de `test_tableau_mode_observatoire_abonne.py`
  (connexion par le formulaire, `TOUS_ABONNES`) : un abonné saisit `(béton OU`
  dans le champ principal de la colonne Objet → pastille jaune « Objet
  contient béton (parenthèse manquante, OU orphelin) » ; un non-abonné saisit
  `béton OU ciment` → bandeau.
- **Régression** : `uv run pytest`, puis `uv run pytest -m selenium`.
- **Smoke** : sur `decp_prod.parquet`, `fetch_grid_page` avec
  `(béton OU ciment) ET brique` retourne un total plausible, dans un temps
  comparable à un filtre de trois mots.

## Hors périmètre

- API REST et MCP.
- Champ de requête inter-colonnes.
- Filtres numériques et de date.
- Échappement des jokers `%` et `_` de `LIKE`.
- Migration des filtres persistés dans le navigateur et des liens
  d'observatoire contenant `+`.
- Affichage des corrections dans les tops des fiches acheteur et titulaire.
