# Filtres booléens appliqués par une vue partagée, sans abonnement (#97)

Date : 2026-10-18

## Objectif

Les opérateurs `OU`, `ET`, `PAS` et les parenthèses des filtres texte sont
réservés aux abonné·es (spec du 2026-10-09). Exception : quand un non-abonné
ouvre une vue partagée (`/tableau?vue=<jeton>`), les filtres booléens de cette
vue s'appliquent comme pour un abonné. Dès qu'il modifie un filtre, le régime
non-abonné reprend pour tous les filtres de la grille.

## Décisions de cadrage

| Sujet                                    | Décision                                                                                                    | Motif                                                                                                 |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Critère                                  | Le `filterModel` courant est identique à celui de la vue ouverte par `?vue=`                                | Le serveur ne fait pas confiance au navigateur : il relit la vue par son jeton et compare             |
| Modification d'un filtre                 | Tout écart avec la vue (filtre modifié, ajouté, supprimé, réinitialisé) désactive tous les filtres booléens | Simplification retenue par Colin, au lieu d'un suivi colonne par colonne                              |
| Tri, colonnes affichées                  | Sans effet                                                                                                  | Ils ne changent pas le filtre ; un tri ne doit pas faire disparaître les résultats d'une vue partagée |
| Retour au filtre exact de la vue         | Les opérateurs sont de nouveau actifs                                                                       | Conséquence directe de la comparaison, sans état à mémoriser ; rien n'est obtenu qu'on n'avait déjà   |
| Abonnement de l'auteur de la vue         | Non vérifié                                                                                                 | Un lien publié reste stable ; on ne peut que reproduire la vue telle quelle                           |
| Rechargement (F5)                        | `?vue=` reste dans l'URL : la vue est réappliquée, exception comprise                                       | Comportement existant de `store_vue_resolution`                                                       |
| Retour sur `/tableau` sans `?vue=`       | Exception perdue : les filtres restaurés du localStorage suivent le régime non-abonné, avec le bandeau      | Le jeton n'est connu que par l'URL                                                                    |
| Surfaces                                 | Grille de `/tableau` (lignes et compteurs), export, pastilles                                               | Tout ce qu'un non-abonné voit du filtre sur `/tableau`                                                |
| Mode observatoire et top des organismes  | Inchangés : réservés aux abonné·es                                                                          | Fonctionnalité d'abonnement distincte des opérateurs                                                  |
| Fiches, `/observatoire`, API REST et MCP | Inchangés                                                                                                   | Pas de vues sur ces surfaces                                                                          |
| Mode d'emploi                            | Non modifié                                                                                                 | Choix de Colin                                                                                        |

### Approches écartées

- **Filtre identique à une vue quelconque en base**, sans exiger son
  ouverture : demande une colonne dérivée indexée dans `saved_views`
  (empreinte du filtre normalisé), une migration de remplissage et sa mise à
  jour à chaque enregistrement. Si la forme normalisée évolue
  (`filtermodel_to_ast`, format de l'AST), les empreintes enregistrées
  deviennent fausses sans que rien ne le signale.
- **Store dédié, vidé à la première modification de filtre** : inutile, la
  comparaison avec la vue suffit et ne dépend d'aucun événement côté client.
- **Réutiliser `active-view`** : ce store est vidé au premier tri
  (`hideShareOnUserAction`), ce qui désactiverait les filtres sur un simple
  tri.

## Contexte : l'existant

- `store_vue_resolution` (`tableau.py`) écrit dans le store `vue-resolution`
  (mémoire) le résultat de `saved_views.resolve.resolve_vue_param` pour le
  `?vue=` de l'URL : `found`, `filter_model`, `column_state`, `token`, etc.
  Il ne change que si l'URL change ; aucune action de l'utilisateur ne le vide.
  Il reste à `None` sans `?vue=`, ou quand `?acheteur_id=` / `?titulaire_id=`
  prime.
- `apply_vue_resolution` pose le `filterModel` de la vue sur `tableau_grid`
  (source AG Grid `api`).
- Le drapeau `operateurs` vaut aujourd'hui `current_user_has_subscription()`
  dans `get_rows_tableau`, `download_data`, et dans `_render` de
  `register_filter_pills_callbacks` (`src/utils/filter_pills.py`), partagé
  avec les fiches acheteur et titulaire.
- Une vue stocke `{"ast": ast_to_dict(...), "columnState": ...}` en JSON dans
  `saved_views.query` ; `db.get_by_token(token)` la relit.

## Design

### 1. Règle (`src/saved_views/resolve.py`)

Nouvelle fonction pure (aucune dépendance à Dash ni à `current_user`) :

```python
def vue_autorise_operateurs(vue_resolution: dict | None, filter_model: dict | None, schema) -> bool
```

- Faux si `vue_resolution` est `None`, si `found` est faux, si `token` est
  absent, ou si `filter_model` est vide (`None` ou `{}`).
- Relit la vue par `db.get_by_token(vue_resolution["token"])`. Le
  `filter_model` contenu dans `vue_resolution` n'est **jamais** utilisé : il
  vient du navigateur. Faux si la vue est introuvable ou si sa `query` n'est
  pas lisible (mêmes cas que `resolve_vue_param`).
- Compare des formes canoniques, insensibles à l'ordre des colonnes et aux
  écarts d'écriture du `filterModel` renvoyé par AG Grid :

  ```python
  def _forme_canonique(filter_model, schema) -> dict:
      return {
          col: ast_to_dict(filtermodel_to_ast({col: entree}, schema))
          for col, entree in (filter_model or {}).items()
      }
  ```

  Côté vue, le `filterModel` est reconstruit comme dans `resolve_vue_param`
  (`ast_to_filtermodel(ast_from_dict(view["ast"]), schema)`) avant de passer
  par `_forme_canonique` : les deux côtés suivent le même chemin. Vrai si les
  deux formes sont égales.

### 2. Calcul du drapeau sur `/tableau` (`src/pages/tableau.py`)

Fonction locale :

```python
def _operateurs(filter_model, vue_resolution) -> bool:
    return current_user_has_subscription() or saved_views_resolve.vue_autorise_operateurs(
        vue_resolution, filter_model, schema
    )
```

L'abonnement est testé en premier : la lecture SQLite n'a lieu que pour un
non-abonné.

- `get_rows_tableau` : ajoute `State("vue-resolution", "data")` ;
  `operateurs=_operateurs(filter_model, vue_resolution)`, où `filter_model`
  est celui de la requête. Couvre les lignes et les compteurs.
- `download_data` : ajoute `State("vue-resolution", "data")`, même calcul
  sur le `filterModel` en `State`. L'export contient les lignes affichées.
- `update_mode_observatoire_cards` et `get_top_org_rows_tableau` : inchangés.

### 3. Pastilles (`src/utils/filter_pills.py`)

- `register_filter_pills_callbacks(context, grid_id, clear_active_view=False, vue_resolution_id=None)`.
  Le Tableau passe `vue_resolution_id="vue-resolution"` ; les fiches ne
  changent pas.
- Si `vue_resolution_id` est fourni, `_render` reçoit aussi
  `State(vue_resolution_id, "data")` et calcule
  `current_user_has_subscription() or vue_autorise_operateurs(...)`. Sinon,
  comportement actuel.
- Conséquence : tant que le filtre est celui de la vue, la pastille d'un
  non-abonné affiche l'expression appliquée, sans bandeau ; dès qu'il diffère,
  le bandeau d'invitation à s'abonner apparaît, comme aujourd'hui.

`_render` est déclenché par `filterModel` ; `vue-resolution` est posé avant le
`filterModel` de la vue (`apply_vue_resolution` en dépend), donc le `State`
est à jour lors du rendu des pastilles de la vue.

## Tests

- **`tests/saved_views/test_resolve.py`**, sur une vue enregistrée avec
  `objet` contient `béton OU ciment` et une seconde colonne filtrée :
  - `filterModel` identique → vrai ; identique avec les colonnes dans l'autre
    ordre → vrai ;
  - filtre booléen modifié → faux ; colonne ajoutée → faux ; colonne retirée
    → faux ;
  - jeton inconnu, `vue_resolution` à `None` ou `found` faux → faux ;
  - `filter_model` de `vue_resolution` falsifié pour correspondre au filtre
    courant alors que la vue en base diffère → faux ;
  - `filterModel` vide → faux.
- **Selenium** (`tests/saved_views/test_tableau_share.py`, sur le modèle de
  `test_open_shared_view_applies_and_shows_box`), utilisateur non connecté.
  `tests/test.parquet` n'a qu'une ligne (objet « Objet test ») : la vue filtre
  `objet` contient `test OU zzz`, qui trouve 1 ligne avec les opérateurs et 0
  sans (les trois mots sont alors exigés) :
  - ouverture de `?vue=` : 1 ligne, pas de bandeau `filter-pills-banniere` ;
  - ajout d'un caractère au filtre (`test OU zzzz`) : 0 ligne et bandeau.
- **Régression** : `uv run pytest`, puis `uv run pytest -m selenium`.

## Hors périmètre

- Mode d'emploi de `/tableau` et page Abonnement.
- Mode observatoire et top des organismes de `/tableau`.
- Fiches acheteur et titulaire, `/observatoire`, API REST et MCP.
- Conservation de l'exception sans `?vue=` dans l'URL.
