# Filtres et recherche d'organismes insensibles à la casse et aux accents (#150)

Date : 2026-11-10

## Objectif

`decp-processing` publie désormais `acheteur_nom` et `titulaire_nom` en casse
normale avec accents (« Mairie de Nîmes » au lieu de « MAIRIE DE NIMES ») —
**les données sont déjà déployées en production**, qui régresse donc
aujourd'hui :

- les filtres de nom des grilles (`acheteur_nom`, `titulaire_nom`) désaccentuent
  la saisie (`unidecode`, #138) et la comparent à des valeurs qui portent
  désormais des accents : « Nîmes » tapé devient « Nimes » et ne matche plus ;
- la recherche de la page d'accueil et du MCP (`search_org`) met la saisie en
  majuscules sans accents et la compare (sensible à la casse) à des colonnes
  qui ne sont plus en majuscules : plus aucun résultat.

Ce chantier adapte les deux chemins pour que « nimes », « Nîmes » et « NIMES »
retournent les mêmes organismes — dans les filtres de nom des grilles, l'API
REST, le MCP et la recherche de `/recherche`. À déployer dès que possible.

## Décisions de cadrage

| Sujet                                       | Décision                                                                                                                                                                                | Motif                                                                                                                                                                                              |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Filtres de nom                              | Réutiliser le mécanisme #147 : `acheteur_nom` et `titulaire_nom` entrent dans `NORMALIZED_COLUMNS`, colonnes précalculées `acheteur_nom_normalise` / `titulaire_nom_normalise`          | Une seule ligne à changer côté grille/API/MCP (`normalized_target`/`normalized_term`) ; la normalisation à la volée a été mesurée ×4 à ×6 en latence (#147)                                        |
| `search_org`                                | Colonne précalculée `recherche_normalisee` dans `DF_ACHETEURS`/`DF_TITULAIRES` (calculée dans `build_org_frame`, une fois au démarrage), comparée à une saisie normalisée identiquement | Normaliser à la volée 5 colonnes × 242 000 lignes de Polars à chaque recherche exigerait un UDF Python ; le précalcul est gratuit à l'usage                                                        |
| Casse de la recherche                       | `lower()` des deux côtés (plus de `.upper()`), accents/ligatures/apostrophe typographique retirés des deux côtés (`normalize_text` / `normalize_text_sql`)                              | La casse normale des futurs noms ne doit exclure aucune saisie ; l'ILIKE n'existe pas dans le chemin Polars                                                                                        |
| Traits d'union                              | Remplacés par des espaces des deux côtés (saisie comprise)                                                                                                                              | Aujourd'hui « saint-etienne » ne matche pas « SAINT-ETIENNE » (le foin a son tiret remplacé, pas la saisie) ; normaliser pareil des deux côtés ferme ce cas                                        |
| Correspondance                              | `str.contains(literal=True)` au lieu de l'expression régulière implicite d'aujourd'hui                                                                                                  | Une saisie contenant `(`, `*`… ne doit ni lever d'erreur ni changer de sens ; la sémantique de recherche n'a jamais voulu être regex                                                               |
| Tri                                         | Inchangé : ordre binaire DuckDB sur la colonne affichée                                                                                                                                 | Décision #147 pour `objet` (« un tri se fait sur le texte affiché ») ; la changer ici ferait dévier aussi le tri sur `objet`. « Éclairage » après « Zoo » est un défaut cosmétique, suivi éventuel |
| `equals`/`exact`                            | Restent exacts                                                                                                                                                                          | Une égalité doit pouvoir distinguer deux graphies, comme pour `objet` (#147)                                                                                                                       |
| Libellé `[Inconnu de l'INSEE (…)]`          | Inchangé                                                                                                                                                                                | Sans accents ni majuscules significatives, il traverse la normalisation telle quelle et reste cherchable                                                                                           |
| Affichage, SEO, JSON-LD, pastilles, exports | Inchangés                                                                                                                                                                               | Ils affichent le nom brut ; le changement de format côté données ne demande aucune adaptation colibre                                                                                              |

## Design

### 1. `src/utils/text_normalization.py`

- `NORMALIZED_COLUMNS` devient :

  ```python
  NORMALIZED_COLUMNS = {
      "objet": "objet_normalise",
      "acheteur_nom": "acheteur_nom_normalise",
      "titulaire_nom": "titulaire_nom_normalise",
  }
  ```

  Tout le reste (`normalize_text`, `normalize_text_sql`, `normalized_target`,
  `normalized_term`) est inchangé : la normalisation ne touche pas la casse,
  l'`ILIKE` s'en charge.

- Nouvelle constante `COLONNE_RECHERCHE = "recherche_normalisee"` : nom de la
  colonne technique de recherche des frames d'organismes, partagée entre
  `src/utils/data.py` (producteur) et `src/utils/search.py` (consommateur).

### 2. `src/utils/text_query.py`

- `_ACCENT_INSENSITIVE_COLUMNS` et l'import `unidecode` disparaissent :
  `normalize_text_term` délègue uniquement à `normalized_term`. Les colonnes
  de `NORMALIZED_COLUMNS` sont désormais les seules normalisées.
- `unidecode` reste une dépendance du projet (`src/saved_views/ui.py`
  `slugify`).

### 3. `src/db.py`

- `SCHEMA_VERSION` passe de 3 à 4 (commentaire : « 4 : #150 ajoute
  `acheteur_nom_normalise` et `titulaire_nom_normalise` à decp »).
- Rien d'autre : `build_database` itère déjà sur `NORMALIZED_COLUMNS`,
  `_TECHNICAL_COLUMNS` et `_load_schema` masquent déjà toute colonne
  précalculée, y compris sur une base ancienne qui en est dépourvue.

### 4. Grilles, observatoire, API REST et MCP — automatique

- Grilles (`query_ast._condition_to_sql` → `en_sql`/`text_filter_target`/
  `normalize_text_term`) : `contains`, `notContains`, `startsWith`, `endsWith`
  comparent `acheteur_nom_normalise`/`titulaire_nom_normalise` à la saisie
  normalisée. La garde « non vide » reste sur la colonne d'origine.
- API REST et MCP (`build_where`, `src/api/filters.py`) : `contains`,
  `notcontains`, `startswith` sur les noms deviennent insensibles à la casse
  et aux accents ; `exact`, `differs`, `in`, `notin`, `sort`, `isnull`
  restent sur la colonne d'origine. Le MCP passe par le même `build_where`.
- Les colonnes techniques restent invisibles : `schema`, `COLUMNS`,
  `query_marches()`, exports, sélecteur de colonnes, API (400 sur
  `acheteur_nom_normalise__contains`).

### 5. `build_org_frame` et `search_org`

`build_org_frame` (`src/utils/data.py`) ajoute à la frame une colonne
technique `recherche_normalisee` : concaténation des cinq champs cherchés
(`{type}_id`, `{type}_nom`, `{type}_departement_nom`, `{type}_departement_code`,
`{type}_commune_nom`), précédée d'une espace, traits d'union remplacés par des
espaces, le tout normalisé (`normalize_text_sql`) puis mis en minuscules.
Elle est calculée par DuckDB dans la même requête que le `GROUP BY`, donc une
seule fois au démarrage. `concat_ws` ignore les `NULL` : une ligne dont un
champ est manquant reste cherchable sur les autres (aujourd'hui, `concat_str`
la rend introuvable — amélioration assumée).

`search_org` (`src/utils/search.py`) :

- saisie : `normalize_text(query.strip()).lower()`, traits d'union → espaces,
  découpée en jetons préfixés d'une espace (sémantique de début de mot
  inchangée) ;
- correspondance : `str.contains(jeton, literal=True)` sur
  `recherche_normalisee`, tous les jetons doivent matcher ;
- le reste (sélection des colonnes, `add_links`, « Département », agrégation,
  tri par « Marchés ») est inchangé ; la colonne technique est retirée avant
  l'affichage comme les colonnes `token_*`.

La docstring de `search_org` documente l'exigence : la frame doit venir de
`build_org_frame` (donc porter `recherche_normalisee`).

### 6. Documentation visible

- `src/api/routes.py` (description des opérateurs `contains`/`notcontains`/
  `startswith`) et la docstring MCP de `rechercher_organisations`
  (`src/mcp/tools.py`) : l'insensibilité casse/accents s'étend de `objet` aux
  noms d'acheteur et de titulaire.
- `CHANGELOG.md`.

## Tests

Tous exécutent de vraies requêtes DuckDB ou Polars ; aucun ne fige le texte SQL.

- **Normalisation** (`tests/test_text_normalization.py`) :
  `normalized_term("acheteur_nom", "Nîmes") == "Nimes"`,
  `normalized_target("acheteur_nom", …) == '"acheteur_nom_normalise"'`. La
  parité Python/DuckDB existante couvre déjà les caractères concernés.
- **Fixture `con_objets`** (`tests/conftest.py`) : les noms passent en casse
  normale accentuée (« Nîmes Métropole », « Fréjus SARL ») et la table porte
  `acheteur_nom_normalise` / `titulaire_nom_normalise` calculées comme au
  build. C'est le format des données désormais en production.
- **Grilles** (`tests/test_filtre_objet_accents_oe.py`) : « nimes », « Nîmes »,
  « NIMES » retournent les mêmes lignes sur `acheteur_nom` et `titulaire_nom`
  (contains, startsWith, endsWith) ; « absent » ne retourne rien ; `equals`
  reste exact. L'ancien test `test_noms_stockes_sans_accents_saisie_desaccentuee`
  décrivait le comportement #138 supprimé : il est remplacé.
- **API/MCP** (`tests/api/test_filters_objet_normalise.py`) :
  `acheteur_nom__contains` retrouve « Nîmes Métropole » avec « nimes », « Nîmes »
  et « NIMES » ; `acheteur_nom__exact` reste exact. L'ancien
  `test_autre_colonne_non_normalisee` est remplacé.
- **Build et masquage** (`tests/test_db.py`) : la base construite porte
  `acheteur_nom_normalise` et `titulaire_nom_normalise` égales à
  `normalize_text` du nom ; `schema`, `COLUMNS` et `query_marches()` ne les
  contiennent pas.
- **`search_org`** (`tests/test_search.py`, nouveau) : via un `get_cursor`
  monkeypatché sur une table `decp` synthétique (noms « Mairie de Nîmes »,
  « Nîmes Métropole » et « Bordeaux Métropole »), `build_org_frame` produit
  la frame réelle, puis :
  - « nimes », « Nîmes », « NIMES », « mairie de nîmes » trouvent
    « Mairie de Nîmes » et « Nîmes Métropole » ;
  - « nimes gard » (nom + département) trouve ;
  - « saint-etienne » équivaut à « saint etienne » ;
  - une saisie avec métacaractère regex (« a(b ») ne lève pas ;
  - « absent » ne retourne rien ;
  - la colonne `recherche_normalisee` n'apparaît pas dans le résultat.
    Plus un test sur les frames réelles : `DF_ACHETEURS`/`DF_TITULAIRES`
    portent la colonne.
- **Régression** : suite complète (`uv run pytest`), puis `uv run pytest -m selenium` hors suite par défaut.

## Vérification de latence

Sur `decp_prod.parquet` (3,3 M lignes), après reconstruction :

- filtre de grille sur `acheteur_nom` contenant « nimes » : même ordre de
  grandeur que le filtre actuel (l'ILIKE porte sur une colonne précalculée,
  cf. mesures #147 : 0,57-0,63 s contre 0,59 s pour `objet`) ;
- `search_org("nimes", "acheteur")` : plus rapide qu'aujourd'hui (la
  concaténation et la mise en majuscules par ligne disparaissent).

## Déploiement

- `SCHEMA_VERSION` 4 : reconstruction au premier démarrage (≈ 20 s), sous
  verrou, comme #147. La base grossit d'environ deux colonnes de noms.
- Correctif **urgent** : les données accentuées étant déjà en production,
  chaque jour sans déploiement laisse les filtres de nom et `/recherche`
  cassés.
- Si la reconstruction échoue, l'ancienne base réutilisée n'a pas les colonnes :
  seuls les filtres de nom et la recherche d'organismes échouent (même mode de
  défaillance que #147, documenté dans `_load_schema`).

## Hors périmètre

- Le tri insensible à la casse/accents (décision : inchangé, voir tableau).
- `unidecode` reste installé (slugify des vues sauvegardées).
