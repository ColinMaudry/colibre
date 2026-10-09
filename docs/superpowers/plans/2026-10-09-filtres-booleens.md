# Filtres texte booléens : OU, ET, PAS, parenthèses et guillemets (#97) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dans les filtres texte _contient_ / _ne contient pas_ des grilles et le champ Objet de l'observatoire, les abonné·es combinent les critères avec `OU`, `ET`, `PAS` et des parenthèses ; tout le monde cherche une phrase exacte entre guillemets, qui remplace `+`.

**Architecture:** La saisie reste une chaîne dans `Condition.value`. Un nouveau module `src/utils/text_query.py` l'analyse (analyseur écrit à la main, réparation tolérante) et la compile en SQL DuckDB paramétré ; il remplace `tokenize_text_filter`. Un drapeau `operateurs: bool`, calculé dans les callbacks par `current_user_has_subscription()`, descend explicitement jusqu'au compilateur et entre dans les clés des deux caches indexés sur le filtre. Les pastilles affichent l'expression appliquée et ses corrections.

**Tech Stack:** Python, DuckDB, Polars, Dash, dash-bootstrap-components, pytest, Selenium (`dash[testing]`), ruff.

**Spec:** `docs/superpowers/specs/2026-10-09-filtres-booleens-design.md`

## Global Constraints

- Imports toujours en `src.…` (jamais `utils.…`).
- Valeurs utilisateur toujours en paramètres `?`, jamais concaténées dans le SQL.
- Mots-clés : `OU`, `ET`, `PAS`, en majuscules, isolés. Priorité `PAS` > `ET` (explicite ou implicite) > `OU`.
- Libellés de correction, mot pour mot : `parenthèse manquante`, `parenthèse en trop`, `ET orphelin`, `OU orphelin`, `PAS orphelin`, `guillemet manquant`, `parenthèses vides`, `guillemets vides`, `trop de parenthèses imbriquées`. Imbrication maximale : 10.
- Bandeau non-abonné, mot pour mot : « Les opérateurs OU, ET, PAS et les parenthèses sont réservés aux abonné·es. » suivi d'un lien « S'abonner » vers `/projet/abonnement`.
- `operateurs` est un argument nommé **obligatoire** partout où il est ajouté (pas de valeur par défaut).
- Les modules de `src/utils/` ne lisent jamais `current_user` pour construire du SQL ; seuls les callbacks appellent `current_user_has_subscription()` (importé depuis `src.pages._compte_shell`).
- API REST et MCP (`src/api/`, `src/mcp/`) : aucun changement.
- Tests : vraies requêtes DuckDB, jamais de texte SQL figé ; un test qui décrit l'implémentation plutôt que le résultat est supprimé, pas réécrit.
- Avant chaque `git add` : `uv run pre-commit run --files <fichiers>` (CLAUDE.md).
- `CHANGELOG.md` : ne pas modifier.
- Référence : `uv run pytest -q` → `1431 passed, 62 deselected` avant le chantier.

## Review Focus

- Phrase blanche `" "` : traitée comme `""` (« guillemets vides »), sinon elle deviendrait `% %` et retiendrait presque tout (test Task 1).
- Mots-clés collés à une parenthèse ou à un guillemet : `(béton)OU(ciment)` et `béton OU"ciment"` valent `béton OU ciment` (test Task 2).
- Colonne date filtrée en texte (`CAST AS VARCHAR`) : `2024 OU 2025` fonctionne sur `dateNotification` (test Task 2).
- Guillemets qui protègent : un non-abonné qui saisit `"béton OU ciment"` ne voit pas le bandeau (tests Task 1 et Task 4).
- Export cohérent avec la grille : `export_dataframe` applique les opérateurs pour un abonné et les traite en mots pour un non-abonné (test Task 3).

---

### Task 1: `text_query` — analyse, réparations, affichage

**Files:**

- Create: `src/utils/text_query.py`
- Modify: `src/utils/table_sql.py` (retirer `_ACCENT_INSENSITIVE_COLUMNS`, `text_filter_target`, `normalize_text_term` et l'import `unidecode` s'il devient inutile)
- Modify: `src/utils/query_ast.py` (importer `normalize_text_term`, `text_filter_target` depuis `src.utils.text_query`)
- Test: `tests/test_text_query.py`

**Interfaces:**

- Produces (dans `src/utils/text_query.py`) :

  - `_ACCENT_INSENSITIVE_COLUMNS`, `text_filter_target(column: str, quoted_col: str) -> str`, `normalize_text_term(column: str, term: str) -> str` : déplacés tels quels de `table_sql.py`.
  - Dataclasses privées `Mot(texte: str)`, `Phrase(texte: str)`, `Et(enfants: list)`, `Ou(enfants: list)`, `Pas(enfant)`.
  - `@dataclass Expression` : `saisie: str`, `arbre` (nœud ou `None`), `corrections: list[str]`, `operateurs_ignores: bool`.
  - `analyser(texte: str, operateurs: bool) -> Expression`
  - `en_texte(expression: Expression) -> str`
  - `libelle_corrections(expression: Expression) -> str`

- [ ] **Step 1: Écrire les tests en échec** dans `tests/test_text_query.py`

```python
@pytest.mark.parametrize("saisie, texte, corrections", [
    ("(béton OU", "béton", "parenthèse manquante, OU orphelin"),
    ("(béton OU ciment", "béton OU ciment", "parenthèse manquante"),
    ("béton) ET brique", "béton ET brique", "parenthèse en trop"),
    ("travaux ET PAS", "travaux", "PAS orphelin"),
    ('"maintenance sur', '"maintenance sur"', "guillemet manquant"),
    ("ET", "", "ET orphelin"),
    ("béton OU OU ciment", "béton OU ciment", "OU orphelin"),
    ("béton () ciment", "béton ET ciment", "parenthèses vides"),
    ('béton "" ciment', "béton ET ciment", "guillemets vides"),
    ('béton " " ciment', "béton ET ciment", "guillemets vides"),
    ("(béton PAS)", "béton", "PAS orphelin"),
    ("((béton OU", "béton", "parenthèse manquante, OU orphelin"),
    ("béton (", "béton", "parenthèse manquante"),
    ("(a OU b) c PAS (d OU e) )", "(a OU b) ET c ET PAS (d OU e)", "parenthèse en trop"),
])
def test_reparations(saisie, texte, corrections):
    expr = analyser(saisie, operateurs=True)
    assert en_texte(expr) == texte
    assert libelle_corrections(expr) == corrections
```

- `test_sans_correction_texte_tel_que_saisi` : `analyser(" (béton OU ciment) brique", True)` → `en_texte == "(béton OU ciment) brique"`, `libelle_corrections == ""`.
- `test_imbrication_limitee` : 10 niveaux `"(" * 10 + "béton" + ")" * 10` → aucune correction ; 12 niveaux → `en_texte == "béton"`, `libelle_corrections == "trop de parenthèses imbriquées"` ; `"(" * 2000 + "x"` → pas d'exception, `en_texte == "x"`, `libelle_corrections == "parenthèse manquante, trop de parenthèses imbriquées"`.
- `test_mots_cles_en_majuscules_seulement` : `analyser("béton ou", True)` et `analyser("OUEST", True)` → `libelle_corrections == ""` ; `analyser("béton OU", True)` → `"OU orphelin"`.
- `test_saisie_vide` : `analyser(" ", True).arbre is None` et `analyser("", False).arbre is None`.
- `test_non_abonne` : `analyser("(béton OU ciment", False)` → `libelle_corrections == ""`, `operateurs_ignores is True`, `en_texte == "(béton OU ciment"` ; `analyser('"béton OU ciment"', False).operateurs_ignores is False` ; `analyser("béton ou ciment", False).operateurs_ignores is False` ; `analyser('"maintenance sur', False)` → `libelle_corrections == ""`.
- `test_abonne_n_ignore_rien` : `analyser("béton OU ciment", True).operateurs_ignores is False`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_text_query.py -v` — Expected: FAIL `ModuleNotFoundError: No module named 'src.utils.text_query'`.

- [ ] **Step 3: Déplacer les trois helpers** de `table_sql.py` vers `text_query.py` ; `table_sql.tokenize_text_filter` et `query_ast` les importent depuis `src.utils.text_query` (sans autre changement à ce stade).

- [ ] **Step 4: Implémenter `analyser`, `en_texte`, `libelle_corrections`**

Algorithme (les étapes 2 à 4 ne concernent que `operateurs=True`) :

1. **Lexique.** Parcours caractère par caractère, chaque jeton garde sa position de départ. Les blancs séparent. `"` ouvre une phrase jusqu'au `"` suivant ; sans fermeture, la phrase va jusqu'à la fin (`guillemet manquant`, position du `"`). Une phrase vide ou blanche est ignorée (`guillemets vides`). Avec `operateurs=True`, `(` et `)` sont des jetons même collés à un mot, et un mot exactement égal à `OU`, `ET` ou `PAS` est un mot-clé. Avec `operateurs=False`, les parenthèses font partie des mots, les mots-clés sont des mots, `operateurs_ignores` vaut vrai si un mot est `OU`/`ET`/`PAS` ou contient `(`/`)`, et **aucune correction n'est notée** (les guillemets sont réparés silencieusement).
2. **Parenthèses** (une passe, pile) : `)` sans `(` ouverte → supprimée (`parenthèse en trop`) ; une `(` qui porterait la profondeur à 11 → supprimée avec sa `)` correspondante (`trop de parenthèses imbriquées`) ; en fin, une `)` synthétique est ajoutée pour chaque `(` restante (`parenthèse manquante`, position de la `(`).
3. **Nettoyage itératif jusqu'à stabilité** : début d'opérande = mot, phrase, `(`, `PAS` ; fin d'opérande = mot, phrase, `)`. Un `ET`/`OU` non précédé d'une fin d'opérande ou non suivi d'un début d'opérande est supprimé (`ET orphelin` / `OU orphelin`). Un `PAS` non suivi d'un début d'opérande est supprimé (`PAS orphelin`), ainsi que le `ET`/`OU` qui le précède éventuellement, sans libellé. Une paire `(` `)` adjacente est supprimée (`parenthèses vides`, sauf si la `)` est synthétique).
4. **Descente récursive** sur un flux désormais grammatical, sans erreur possible : `ou := et (OU et)*` ; `et := pas ((ET)? pas)*` (juxtaposition = ET) ; `pas := PAS pas | atome` ; `atome := mot | phrase | "(" ou ")"`. Les nœuds à un seul enfant sont aplatis.
5. Avec `operateurs=False` : `Et` de tous les mots et phrases (ou l'unique feuille).
6. `corrections` : triées par position, dédoublonnées en gardant la première occurrence.

`en_texte` : sans correction, `" ".join(saisie.split())` ; avec corrections, forme canonique : `Ou` joint par `OU`, `Et` par `ET`, `Pas` → `PAS x`, parenthèses autour d'un `Ou` enfant d'un `Et` ou d'un `Pas` et d'un `Et` enfant d'un `Pas`, phrase entre guillemets ; `""` si `arbre is None`. `libelle_corrections` : `", ".join(corrections)`.

- [ ] **Step 5: Vérifier le succès**

Run: `uv run pytest tests/test_text_query.py tests/test_query_ast.py tests/test_filtre_objet_accents_oe.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run --files src/utils/text_query.py src/utils/table_sql.py src/utils/query_ast.py tests/test_text_query.py
git add src/utils/text_query.py src/utils/table_sql.py src/utils/query_ast.py tests/test_text_query.py
git commit -m "text_query : analyse tolérante des filtres booléens (#97)"
```

---

### Task 2: `text_query.en_sql` — compilation et résultats DuckDB

**Files:**

- Modify: `src/utils/text_query.py`
- Modify: `tests/conftest.py` (fixture `con_booleens`)
- Test: `tests/test_text_query.py`

**Interfaces:**

- Consumes: `analyser`, `Expression`, `normalize_text_term`, `text_filter_target` (Task 1).
- Produces: `en_sql(expression: Expression, colonne: str, col_is_date: bool = False) -> tuple[str, list]`.

- [ ] **Step 1: Ajouter la fixture `con_booleens`** dans `tests/conftest.py`, sur le modèle de `con_objets` : DuckDB en mémoire, table `decp (objet VARCHAR, objet_normalise VARCHAR, "considerationsSociales" VARCHAR, "dateNotification" DATE)`, `objet_normalise` calculée par `normalize_text_sql('objet')`. Lignes (`objet`, `considerationsSociales`, `dateNotification`) — date `2023-06-01` sauf mention :

  - `Travaux de béton`, `Clause sociale, Critère social`, `2024-03-01`
  - `Béton et ciment` ; `Béton ou ciment au choix` ; `Fourniture de ciment` ; `Brique et béton` ; `Ciment et brique`
  - `Entretien des espaces verts` ; `Travaux de construction`
  - `Travaux de voirie`, `Critère social`
  - `Conseil en étude de marché` ; `Conseil juridique`, `Clause sociale`, `2025-01-01`
  - `Maintenance sur site` ; `Site de maintenance` ; `Maîtrise d’œuvre` ; `Réseau OUEST` ; `Prix 3+4` ; `x' OR 1=1 --`
  - `NULL` ; `''`

- [ ] **Step 2: Écrire les tests en échec** dans `tests/test_text_query.py`, avec un helper

```python
def _filtre(con, saisie, operateurs=True, colonne="objet", col_is_date=False, negation=False):
    where, params = en_sql(analyser(saisie, operateurs), colonne, col_is_date)
    if negation:
        where = f"NOT ({where})"
    rows = con.execute(f"SELECT objet FROM decp WHERE {where}", params).fetchall()
    return sorted((r[0] for r in rows), key=lambda v: (v is None, v or ""))
```

- `test_ou` : `"béton OU ciment"` → `Béton et ciment`, `Béton ou ciment au choix`, `Brique et béton`, `Ciment et brique`, `Fourniture de ciment`, `Travaux de béton`.
- `test_groupage` : `"(béton OU ciment) ET brique"` → `Brique et béton`, `Ciment et brique`.
- `test_priorite_et_sur_ou` : `"béton ciment OU brique"` → `Brique et béton`, `Béton et ciment`, `Béton ou ciment au choix`, `Ciment et brique`.
- `test_et_pas` : `"travaux ET PAS construction"` → `Travaux de béton`, `Travaux de voirie` ; `'conseil ET PAS "étude de marché"'` → `Conseil juridique`.
- `test_ou_pas_logique_stricte` : `"béton OU PAS ciment"` contient `Béton et ciment` et `Entretien des espaces verts`, ne contient ni `Fourniture de ciment` ni `Ciment et brique`.
- `test_phrase_exige_l_ordre` : `'"maintenance sur site"'` → `Maintenance sur site` ; `"maintenance site"` → `Maintenance sur site`, `Site de maintenance`.
- `test_phrases_colonne_multivaluee` : `'"Clause sociale" ET "Critère social"'`, `colonne="considerationsSociales"` → `Travaux de béton`.
- `test_mots_cles_litteraux` : `"OUEST"` → `Réseau OUEST` ; `'"béton OU ciment"'` (phrase, ILIKE insensible à la casse) → `Béton ou ciment au choix` seulement, contre six lignes sans guillemets ; `"béton ou ciment"` (abonné) → `Béton ou ciment au choix`.
- `test_mots_cles_colles` : `"(béton)OU(ciment)"` et `'béton OU"ciment"'` donnent le même résultat que `"béton OU ciment"`.
- `test_jokers_et_plus` : `"maint*"` → `Maintenance sur site` ; `'"maint*"'` → `[]` ; `"3+4"` → `Prix 3+4`.
- `test_normalisation_dans_une_phrase` : `'"maitrise d\'oeuvre"'` → `Maîtrise d’œuvre`.
- `test_colonne_date` : `"2024 OU 2025"`, `colonne="dateNotification"`, `col_is_date=True` → `Conseil juridique`, `Travaux de béton`.
- `test_contient_exclut_null_et_vide` : `"PAS construction"` ne contient ni `None` ni `""`, et compte 16 lignes (les 17 non vides moins `Travaux de construction`).
- `test_ne_contient_pas_inclut_null_et_vide` : `"construction"` avec `negation=True` contient `None` et `""`.
- `test_expression_vide_garde_seulement` : `"ET"` → les 17 lignes non vides.
- `test_non_abonne_mots_ordinaires` : `"béton OU ciment"`, `operateurs=False` → `Béton ou ciment au choix`.
- `test_valeur_liee` : `"x' OR 1=1 --"` (sans opérateur, phrase de mots) → `x' OR 1=1 --` seulement.

- [ ] **Step 3: Vérifier l'échec**

Run: `uv run pytest tests/test_text_query.py -v` — Expected: FAIL `ImportError: cannot import name 'en_sql'`.

- [ ] **Step 4: Implémenter `en_sql`**

`quoted_col` = `CAST("col" AS VARCHAR)` si `col_is_date`, sinon `"col"` ; garde `"col" IS NOT NULL AND {quoted_col} <> ''` ; cible `text_filter_target(colonne, quoted_col)`. Feuille : terme passé par `normalize_text_term`, puis `Mot` → `t.replace("*", "%")` si `t` commence ou finit par `*`, sinon `%t%` ; `Phrase` → `%t%`. `Et` → `(a) AND (b)`, `Ou` → `(a) OR (b)`, `Pas` → `NOT (a)`. Résultat : `garde AND (expression)`, ou la garde seule si `arbre is None`.

- [ ] **Step 5: Vérifier le succès**

Run: `uv run pytest tests/test_text_query.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run --files src/utils/text_query.py tests/conftest.py tests/test_text_query.py
git add src/utils/text_query.py tests/conftest.py tests/test_text_query.py
git commit -m "text_query : compilation SQL des expressions booléennes (#97)"
```

---

### Task 3: Bascule du compilateur et transmission du drapeau `operateurs`

`operateurs` devient obligatoire dans toute la chaîne ; la tâche ne se termine qu'avec la suite complète verte.

**Files:**

- Modify: `src/utils/query_ast.py` (`ast_to_sql`, `_join`, `_condition_to_sql`, docstring l. 1-7)
- Modify: `src/utils/table_sql.py` (`dashboard_filters_to_sql`, suppression de `tokenize_text_filter`)
- Modify: `src/utils/grid.py`, `src/utils/entity_grid.py`, `src/utils/top_org_grid.py`, `src/utils/data.py`
- Modify: `src/pages/tableau.py`, `src/pages/observatoire.py`, `src/pages/acheteur.py`, `src/pages/titulaire.py`
- Modify (tests) : `tests/test_query_ast.py`, `tests/test_filtre_objet_accents_oe.py`, `tests/test_dashboard_filters_to_sql.py`, `tests/test_tableau_filtre_organisme.py`, `tests/test_grid.py`, `tests/test_entity_grid.py`, `tests/test_top_org_grid.py`, `tests/test_fiches_top_org.py`, `tests/test_theme_cache.py`, `tests/test_observatoire_cards_columns.py`, `tests/test_export_format_switch.py`, `tests/test_suivi_telechargements.py`, `tests/test_tableau_download_button.py`, `tests/test_observatoire_sans_previsualisation.py`
- Test: `tests/test_filtre_booleen_drapeau.py` (nouveau)

**Interfaces:**

- Consumes: `analyser`, `en_sql` (Tasks 1-2).
- Produces (signatures exactes) :

  - `ast_to_sql(node, schema: pl.Schema, *, operateurs: bool) -> tuple[str, list]`
  - `dashboard_filters_to_sql(<17 paramètres inchangés>, *, operateurs: bool) -> tuple[str, list]`
  - `fetch_grid_page(filter_model, sort_model, start_row, end_row, base_where_sql="TRUE", base_params=(), *, operateurs: bool)`
  - `export_dataframe(filter_model, sort_model, hidden_columns, base_where_sql="TRUE", base_params=(), *, operateurs: bool)`
  - `fetch_entity_page(org_type, entity_id, year, request, *, operateurs: bool)`
  - `export_entity_dataframe(org_type, entity_id, year, filter_model, column_state, *, operateurs: bool)`
  - `top_org_filter_sql(filter_model, org_type, extra_columns=(), *, operateurs: bool)`
  - `fetch_top_org_page(org_type, where_sql, params, request, extra_columns=(), *, operateurs: bool)`
  - `prepare_dashboard_data(columns=None, *, operateurs: bool, **filter_params)`
  - `tableau._cards_pour_filtre(filter_model_json: str, theme: str, operateurs: bool)`
  - `observatoire._compute_dashboard_children(filter_params_normalized: tuple, theme: str, operateurs: bool)`

- [ ] **Step 1: Écrire les tests en échec** dans `tests/test_filtre_booleen_drapeau.py`. La base de test (`tests/conftest.py`, `_TEST_DATA`) a une seule ligne, d'objet `Objet test`. Filtre : `FM = {"objet": {"filterType": "text", "type": "contains", "filter": "test OU zzzznope"}}`.

  - `test_grille_applique_le_ou_pour_un_abonne` : `fetch_grid_page(FM, None, 0, 20, operateurs=True)[1] == 1` ; avec `operateurs=False` (trois mots `test`, `OU`, `zzzznope`) → `0`.
  - `test_export_coherent_avec_la_grille` : `export_dataframe(FM, None, [], operateurs=True).height == 1` ; `operateurs=False` → `0`.
  - `test_cache_des_cards_distingue_le_drapeau` (fixtures `flask_app`/`reset_cache` de `test_theme_cache.py`, à factoriser dans `tests/conftest.py` si besoin) : `query_marches` stubbé pour enregistrer `params` ; deux appels `_cards_pour_filtre(json, CLAIR, True)` puis `(json, CLAIR, False)` déclenchent deux calculs avec des `params` différents.
  - `test_cache_de_l_observatoire_distingue_le_drapeau` : même principe sur `_compute_dashboard_children((("dashboard_marche_objet", "test OU zzzznope"),), CLAIR, True)` puis `False`, avec `prepare_dashboard_data` stubbé (enregistre `operateurs`) → deux calculs, `[True, False]`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_filtre_booleen_drapeau.py -v` — Expected: FAIL `TypeError: ... unexpected keyword argument 'operateurs'`.

- [ ] **Step 3: Compilateur.** `ast_to_sql` / `_join` / `_condition_to_sql` propagent `operateurs` ; `contains` → `en_sql(analyser(str(cond.value), operateurs), col, col_is_date)`, `notContains` → `NOT (…)` du même. `dashboard_filters_to_sql` : `en_sql(analyser(dashboard_marche_objet, operateurs), "objet")`. Supprimer `tokenize_text_filter`. Docstring de `query_ast.py` : remplacer « futur champ de requête booléenne #97 » par « syntaxe booléenne #97, portée par la valeur des conditions `contains` (voir `src/utils/text_query.py`) ».

- [ ] **Step 4: Couche `src/utils/`.** Ajouter `*, operateurs: bool` aux fonctions de l'Interface et le transmettre. `entity_grid.py` : importer `current_user_has_subscription` depuis `src.pages._compte_shell` ; les closures `_get_rows` et `_download_filtered` passent `operateurs=current_user_has_subscription()`.

- [ ] **Step 5: Pages.** Chaque callback calcule `operateurs = current_user_has_subscription()` et le passe :

  - `tableau.py` : `get_rows_tableau`, `download_data`, `update_mode_observatoire_cards` (vers `_cards_pour_filtre`), `get_top_org_rows_tableau` ;
  - `observatoire.py` : `update_dashboard_cards` (vers `_compute_dashboard_children`), `get_top_org_rows`, `download_observatoire`, `update_download_button_observatoire`. Ne pas ajouter `operateurs` au dict `filter_params` renvoyé dans le store `observatoire-filters` ;
  - `acheteur.py` (`get_top_titulaires_rows`) et `titulaire.py` (`get_top_acheteurs_rows`) : importer `current_user_has_subscription` depuis `src.pages._compte_shell`.

- [ ] **Step 6: Tests existants.**

  - `test_query_ast.py` : `_run`, `_roundtrip_sql` et les appels directs passent `operateurs=True` ; `test_text_contains_wildcard_and_phrase` devient `Condition("objet", "contains", 'distri* "metropole rennes"')` → `params == ["distri%", "%metropole rennes%"]`.
  - `test_filtre_objet_accents_oe.py` : remplacer `tokenize_text_filter(col, saisie)` par `en_sql(analyser(saisie, True), col)` ; dans `test_contains_joker_et_phrase_gardent_leur_semantique`, `"maitrise+d'oeuvre"` devient `'"maitrise d\'oeuvre"'` ; `ast_to_sql(..., operateurs=True)` ; `dashboard_filters_to_sql(..., operateurs=True)`.
  - `test_dashboard_filters_to_sql.py`, `test_tableau_filtre_organisme.py`, `test_grid.py`, `test_entity_grid.py`, `test_top_org_grid.py` : ajouter `operateurs=False` aux appels (aucun ne teste d'opérateur).
  - `test_theme_cache.py` : doublures `lambda ast, schema, *, operateurs: ("1=1", [])` et `lambda **kw: "dff-stub"` (inchangée) ; appels `_cards_pour_filtre(json, CLAIR, False)` et `_compute_dashboard_children(filtres, CLAIR, False)`.
  - `test_observatoire_cards_columns.py` : `.uncached(tuple(), CLAIR, False)`.
  - `test_fiches_top_org.py` : `faux_fetch(..., extra_columns=(), *, operateurs)` et `monkeypatch.setattr(page, "current_user_has_subscription", lambda: False)`.
  - Callbacks appelés hors requête : `monkeypatch.setattr(<module>, "current_user_has_subscription", lambda: False)` dans `test_export_format_switch.py` (`tableau`, `observatoire`), `test_suivi_telechargements.py` (`tableau`, `src.utils.entity_grid`), `test_tableau_download_button.py` (`tableau`), `test_observatoire_sans_previsualisation.py` (`observatoire`), `test_entity_grid.py` (`src.utils.entity_grid`).

- [ ] **Step 7: Vérifier le succès**

Run: `uv run pytest -q` — Expected: tous les tests passent (1431 + les nouveaux), `62 deselected`. `uv run ruff check src tests` sans erreur.

- [ ] **Step 8: Commit**

```bash
uv run pre-commit run --files $(git diff --name-only) tests/test_filtre_booleen_drapeau.py
git add -u && git add tests/test_filtre_booleen_drapeau.py
git commit -m "Filtres booléens : compilateur et drapeau abonné jusqu'aux grilles et à l'observatoire (#97)"
```

---

### Task 4: Pastilles — expression appliquée, avertissement, bandeau

**Files:**

- Modify: `src/utils/filter_pills.py`
- Modify: `src/assets/css/style.css` (après `.filter-pill-remove:hover`, l. ~399, et bloc mode sombre l. ~1577)
- Test: `tests/test_filter_pills.py`

**Interfaces:**

- Consumes: `analyser`, `en_texte`, `libelle_corrections` (Task 1).
- Produces :

  - `class Description(NamedTuple)` : `label: str`, `expression: str`, `corrigee: bool`, `operateurs_ignores: bool`
  - `describe_filter(col: str, spec: dict, operateurs: bool) -> Description`
  - `filter_pills(filter_model: dict | None, context: str, operateurs: bool) -> list`
  - `BANNIERE_OPERATEURS = "Les opérateurs OU, ET, PAS et les parenthèses sont réservés aux abonné·es."`
  - `banniere_operateurs() -> html.Span` : `[BANNIERE_OPERATEURS, " ", html.A("S'abonner", href="/projet/abonnement")]`, classe `filter-pills-banniere`. Réutilisé par Task 5.

- [ ] **Step 1: Écrire les tests en échec** dans `tests/test_filter_pills.py`

  - Adapter `test_describe_filter` (19 cas) : `describe_filter(col, spec, True)[:2] == attendu` — le libellé et l'expression des cas existants ne changent pas.
  - `test_pastille_corrigee` : `describe_filter("objet", _txt("contains", "(béton OU"), True)` → `expression == "contient béton (parenthèse manquante, OU orphelin)"`, `corrigee is True` ; `filter_pills({"objet": _txt("contains", "(béton OU")}, "tableau", True)[0].className == "filter-pill filter-pill-warning"`.
  - `test_pastille_propre_sans_classe` : `"béton OU ciment"` → `expression == "contient béton OU ciment"`, pastille `className == "filter-pill"`.
  - `test_expression_vide` : `_txt("contains", "ET")` → `"n'est pas vide (ET orphelin)"` ; `_txt("notContains", "ET")` → `"est vide (ET orphelin)"`.
  - `test_deux_conditions` : `{"filterType": "text", "operator": "OR", "conditions": [_txt("contains", "béton OU"), _txt("contains", "brique")]}` → `"contient béton (OU orphelin) ou contient brique"`, `corrigee is True`.
  - `test_non_abonne_saisie_telle_quelle` : `describe_filter("objet", _txt("contains", "(béton OU"), False)` → `expression == "contient (béton OU"`, `corrigee is False`, `operateurs_ignores is True`.
  - `test_bandeau_non_abonne` : `filter_pills({"objet": _txt("contains", "béton OU ciment")}, "tableau", False)` → 2 éléments, le dernier a `className == "filter-pills-banniere"` et contient `BANNIERE_OPERATEURS` ; avec `True` → 1 élément ; avec `False` et `'"béton OU ciment"'` → 1 élément.
  - Autres tests du fichier appelant `filter_pills(fm, ctx)` : ajouter `True`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_filter_pills.py -v` — Expected: FAIL (`TypeError` sur l'argument `operateurs`).

- [ ] **Step 3: Implémenter.** `_condition(spec, operateurs)` renvoie `(texte, corrigee, operateurs_ignores)` ; seules les conditions `filterType == "text"` et `type` `contains`/`notContains` passent par `analyser`. Texte : `f"{operateur} {en_texte}"`, suivi de `f" ({libelle})"` si corrections ; si `en_texte` est vide, l'opérateur devient `"n'est pas vide"` (contains) ou `"est vide"` (notContains). `filter_pills` pose `className="filter-pill filter-pill-warning"` si `corrigee`, et ajoute `banniere_operateurs()` en fin de liste si `not operateurs` et une description a `operateurs_ignores`. `_render` : `filter_pills(_premier(filter_model), context, current_user_has_subscription())`, import local depuis `src.pages._compte_shell`.

CSS : `.filter-pill-warning { background: var(--bs-warning-bg-subtle); color: var(--bs-warning-text-emphasis); box-shadow: inset 0 0 0 1px var(--bs-warning-border-subtle); }` et `.filter-pills-banniere` (mêmes couleurs, `display: inline-block; margin: 2px 0 2px 8px; padding: 1px 10px; border-radius: 4px;`) ; reprendre `.filter-pill-warning` après la règle `[data-bs-theme="dark"] .filter-pill` pour qu'elle l'emporte en mode sombre.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_filter_pills.py -v` — Expected: PASS.

- [ ] **Step 5: Vérifier visuellement** : `uv run run.py`, `/tableau`, saisir `(béton OU` dans le filtre Objet (session abonnée, `TOUS_ABONNES=true` dans `.env`) → pastille jaune « Objet contient béton (parenthèse manquante, OU orphelin) » en mode clair et sombre ; sans abonnement, `béton OU ciment` → bandeau.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run --files src/utils/filter_pills.py src/assets/css/style.css tests/test_filter_pills.py
git add src/utils/filter_pills.py src/assets/css/style.css tests/test_filter_pills.py
git commit -m "Pastilles : filtre réellement appliqué, corrections et bandeau abonné (#97)"
```

---

### Task 5: Aide sous le champ Objet de l'observatoire

**Files:**

- Modify: `src/pages/observatoire.py` (layout l. ~215-226, nouveau callback)
- Modify: `src/assets/css/style.css`
- Test: `tests/test_observatoire_aide_objet.py`

**Interfaces:**

- Consumes: `analyser`, `en_texte`, `libelle_corrections` (Task 1) ; `banniere_operateurs` (Task 4).
- Produces : `aide_objet(texte: str | None, operateurs: bool) -> list | None` (fonction pure, dans `observatoire.py`) et le callback `afficher_aide_objet(objet)` → `Output("dashboard_marche_objet_aide", "children")`, `Input("dashboard_marche_objet", "value")`.

- [ ] **Step 1: Écrire les tests en échec**

  - `test_aide_correction` : `aide_objet("(béton OU", True) == ["Filtre appliqué : béton (parenthèse manquante, OU orphelin)"]`.
  - `test_aide_rien_si_propre` : `aide_objet("béton OU ciment", True) is None` ; `aide_objet(None, True) is None` ; `aide_objet("", False) is None`.
  - `test_aide_non_abonne` : `aide_objet("béton OU ciment", False)` contient un `html.Span` de classe `filter-pills-banniere` ; `aide_objet('"béton OU ciment"', False) is None`.
  - `test_callback_lit_l_abonnement` : `monkeypatch.setattr(observatoire, "current_user_has_subscription", lambda: False)` → `afficher_aide_objet("béton OU ciment")` renvoie le bandeau.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_observatoire_aide_objet.py -v` — Expected: FAIL `AttributeError: ... 'aide_objet'`.

- [ ] **Step 3: Implémenter.** Sous le `dcc.Input(id="dashboard_marche_objet")`, dans la même `dbc.Col`, `dbc.FormText(id="dashboard_marche_objet_aide", className="filtre-objet-aide")`. CSS `.filtre-objet-aide { color: var(--bs-warning-text-emphasis); }`. Callback : `aide_objet(objet, current_user_has_subscription())`.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_observatoire_aide_objet.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/pages/observatoire.py src/assets/css/style.css tests/test_observatoire_aide_objet.py
git add src/pages/observatoire.py src/assets/css/style.css tests/test_observatoire_aide_objet.py
git commit -m "Observatoire : aide sous le champ Objet (corrections, bandeau abonné) (#97)"
```

---

### Task 6: Migration Python des vues sauvegardées (`+` → guillemets)

**Files:**

- Modify: `src/migrations.py`
- Modify: `CLAUDE.md` (section « Migrations de schéma SQLite »)
- Test: `tests/saved_views/test_migration_plus_guillemets.py`

**Interfaces:**

- Produces (dans `src/migrations.py`) :

  - `_MIGRATIONS: list[tuple[str, str | Callable[[sqlite3.Connection], None]]]`
  - `_plus_vers_guillemets(valeur: str) -> str`
  - `_migrer_vues_plus(conn: sqlite3.Connection) -> None`, enregistrée sous `"0017_saved_views_plus_vers_guillemets"`.

- [ ] **Step 1: Écrire les tests en échec** (fixture `users_db_path` comme `tests/test_migrations.py` ; créer `saved_views` par `saved_views_db.init_schema()` avant d'insérer)

```python
@pytest.mark.parametrize("avant, apres", [
    ("maitrise+d'oeuvre", '"maitrise d\'oeuvre"'),
    ("distri* metropole+rennes", 'distri* "metropole rennes"'),
    ("a+b*", "a+b*"),
    ('a+"b', 'a+"b'),
    ("sans plus", "sans plus"),
])
def test_plus_vers_guillemets(avant, apres):
    assert _plus_vers_guillemets(avant) == apres
```

- `test_migration_reecrit_les_vues` : une vue dont `query` vaut `json.dumps({"ast": {"t": "and", "children": [cond("objet", "contains", "maitrise+d'oeuvre"), cond("objet", "equals", "a+b"), cond("montant", "greaterThan", 5)]}, "columnState": []})` → après `apply_pending()`, la première valeur est `'"maitrise d\'oeuvre"'`, les deux autres inchangées, `columnState` conservé.
- `test_migration_ignore_les_anciennes_vues` : `query` non JSON (`"objet icontains a+b"`) et JSON sans `ast` → inchangées.
- `test_migration_sans_table` : base sans `saved_views` → `apply_pending()` ne lève pas et enregistre `0017_…` dans `schema_migrations`.
- `test_migration_idempotente` : second `apply_pending()` sans effet (même `query`, une seule ligne `0017_…`).
- `test_migration_en_echec_annulee` : une migration fonction qui écrit puis lève → rien n'est écrit, l'id n'est pas enregistré, l'exception remonte (monkeypatcher `_MIGRATIONS`).

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_migration_plus_guillemets.py -v` — Expected: FAIL `ImportError: cannot import name '_plus_vers_guillemets'`.

- [ ] **Step 3: Implémenter.** `apply_pending` : si la migration est appelable, `BEGIN`, appel, `INSERT` dans `schema_migrations`, `COMMIT` ; sur exception `ROLLBACK` puis `raise`. Branche SQL inchangée. `_migrer_vues_plus` : sort sans rien faire si `saved_views` n'existe pas (`sqlite_master`) ; pour chaque ligne, `json.loads(query)` (ignorer `JSONDecodeError`/`TypeError` et l'absence de clé `ast`), parcours récursif des nœuds `{"t": "cond"}` à `operator` `contains`/`notContains` et `value` `str`, `UPDATE` seulement si la `query` change. `_plus_vers_guillemets` : mot par mot sur `split()`, rejoint par une espace. Docstring du module : une migration est un SQL ou une fonction `(conn) -> None`.

CLAUDE.md, après les trois puces existantes : « Une migration peut aussi être une fonction Python `(conn) -> None` (réécriture de données) ; `apply_pending` l'exécute entre `BEGIN` et `COMMIT` avec son enregistrement. Elle doit tolérer une table absente (base fraîche : `init_schema` des modules tourne après). »

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/saved_views/ tests/test_migrations.py tests/api/test_migrations.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run --files src/migrations.py CLAUDE.md tests/saved_views/test_migration_plus_guillemets.py
git add src/migrations.py CLAUDE.md tests/saved_views/test_migration_plus_guillemets.py
git commit -m "Migration 0017 : vues sauvegardées, phrases + vers guillemets (#97)"
```

---

### Task 7: Documentation utilisateur, Selenium, régression et smoke

**Files:**

- Modify: `src/pages/tableau.py` (mode d'emploi, après le paragraphe « Dans le filtre complet… », l. ~333)
- Modify: `src/pages/projet/abonnement.py` (`abonnement_features`)
- Test: `tests/test_filtres_booleens_selenium.py`

- [ ] **Step 1: Mode d'emploi.** Ajouter sous « Filtrer les colonnes » :

```markdown
##### Syntaxe des champs texte

Dans les conditions « contient » et « ne contient pas », dans le champ sous l'en-tête comme dans le filtre complet :

- plusieurs mots séparés par des espaces doivent tous être présents ;
- `"maintenance sur site"` cherche ces mots groupés, dans cet ordre ;
- `béton*` cherche un texte qui commence par « béton », `*béton` un texte qui finit par « béton ».

Abonné·es : combinez vos critères avec **OU**, **ET**, **PAS** (en majuscules) et des parenthèses :

- `amo OU assistance`
- `(béton OU ciment) ET brique`
- `travaux ET PAS construction`
- `conseil ET PAS "étude de marché"`
- `"Clause sociale" ET "Critère social"`

La pastille au-dessus du tableau montre le filtre réellement appliqué. Si une expression est incomplète (parenthèse ou guillemet manquant, opérateur sans mot), elle est corrigée et la pastille, en jaune, indique la correction.
```

- [ ] **Step 2: Page abonnement.** Dans `abonnement_features`, après la puce des vues : `- combinez vos filtres texte avec **OU**, **ET**, **PAS** et des parenthèses (Tableau, fiches, Observatoire)`.

- [ ] **Step 3: Écrire les tests Selenium** dans `tests/test_filtres_booleens_selenium.py`, en reprenant `compte_abonne`, `compte_sans_abonnement`, `_se_connecter` et `_ouvrir_le_tableau` de `tests/test_tableau_mode_observatoire_abonne.py` (les déplacer dans `tests/conftest.py` plutôt que les dupliquer ; une seule définition). Champ : `.ag-floating-filter[col-id="objet"] input`, comme `tests/test_filter_pills_selenium.py` (faire défiler dans la vue comme `_filter_input_in_view` de `tests/test_main.py`). La base de test n'a qu'une ligne : la grille sera vide, seules les pastilles comptent.

  - `test_abonne_voit_la_correction` : saisir `(béton OU` → `dash_duo.wait_for_contains_text("#tableau-filter-pills", "contient béton (parenthèse manquante, OU orphelin)", timeout=10)` et la pastille porte `filter-pill-warning`.
  - `test_non_abonne_voit_le_bandeau` : saisir `béton OU ciment` → `#tableau-filter-pills .filter-pills-banniere` contient `BANNIERE_OPERATEURS`.

- [ ] **Step 4: Lancer les tests Selenium**

Run: `uv run pytest tests/test_filtres_booleens_selenium.py tests/test_tableau_mode_observatoire_abonne.py tests/test_filter_pills_selenium.py -m selenium -v` — Expected: PASS.

- [ ] **Step 5: Régression complète**

Run: `uv run pytest -q` puis `uv run pytest -m selenium -q` — Expected: tout passe, hormis `test_le_mode_observatoire_persiste_apres_rechargement`, déjà en échec avant le chantier (spec #147) ; si un autre test Selenium échoue, vérifier sur `dev` qu'il échouait déjà avant de conclure.

- [ ] **Step 6: Smoke sur la production**

Run: avec `DATA_FILE_PARQUET_PATH=../decp-processing/decp_prod.parquet` (ou `./decp_prod.parquet`), un script jetable appelle `fetch_grid_page({"objet": {"filterType": "text", "type": "contains", "filter": "(béton OU ciment) ET brique"}}, None, 0, 20, operateurs=True)` puis le même filtre avec `béton ciment brique`, et chronomètre les deux — Expected: total plausible (non nul, inférieur au total de `béton OU ciment`), temps du même ordre de grandeur. Supprimer le script.

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run --files src/pages/tableau.py src/pages/projet/abonnement.py tests/test_filtres_booleens_selenium.py tests/conftest.py tests/test_tableau_mode_observatoire_abonne.py
git add src/pages/tableau.py src/pages/projet/abonnement.py tests/test_filtres_booleens_selenium.py tests/conftest.py tests/test_tableau_mode_observatoire_abonne.py
git commit -m "Filtres booléens : mode d'emploi, page abonnement et tests Selenium (#97)"
```
