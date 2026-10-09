# Suivi Matomo des actions utilisateurs (#149) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** suivre dans Matomo, une fois par geste réel et dans la visite du navigateur, les recherches, filtres, téléchargements, réinitialisations, ouvertures du mode d'emploi, bascules de mode et de thème et déplacements de tuiles listés par #149.

**Architecture :** les callbacks Python décident quoi envoyer et l'écrivent dans un `dcc.Store` global `suivi-matomo` ; un clientside callback unique le relaie à `window.colibreSuivi`, qui fait `_paq.push`. Les gestes que seul le navigateur voit (filtres saisis, bascule, thème, tuiles) appellent `colibreSuivi` directement. L'ancien envoi serveur (`track_search`, `track_download`) est supprimé.

**Tech Stack :** Dash 4.4, dash-ag-grid, Matomo JS (`_paq`), pytest, Selenium via `dash[testing]`.

**Spec :** `docs/superpowers/specs/2026-10-09-suivi-matomo-actions-design.md`

## Global Constraints

- Aucun id Colibre envoyé à Matomo (pas de `setUserId`, pas de dimension identifiante).
- Catégories exactes : `Tableau`, `Observatoire`, `Acheteur`, `Titulaire`, `Interface` ; Site search : catégorie `accueil`.
- Actions exactes : `filtres`, `telechargement`, `telechargement_filtre`, `reinitialisation`, `mode_emploi`, `mode`, `theme`, `tuile_deplacee`.
- Noms de téléchargement exacts : `xlsx`, `csv`, `csv-datagouv` ; CSV au-delà de `EXCEL_MAX_ROWS`, comme aujourd'hui.
- Sérialisation des filtres : colonnes triées, séparateur `|`, troncature à 500 caractères terminée par `…`, jeu vide jamais envoyé.
- Anti-rebond des filtres de grille : **3 s** par grille.
- `emettre()` écrit **toujours** dans le store ; la seule garde est `window._paq` côté navigateur.
- Ne pas modifier `CHANGELOG.md`.
- Mentions légales : aucune modification avant validation explicite du texte par Colin.
- Imports applicatifs en `src.…` (`CLAUDE.md`). Avant chaque `git add`, lancer `pre-commit` sur les fichiers concernés.
- Tests navigateur : désélectionnés par défaut (`addopts` de `pyproject.toml`) ; les lancer avec `uv run pytest -m selenium <fichier>`.

## Review Focus

1. Traqueur absent (dev, bloqueur) : aucun geste ne doit lever d'erreur JS → test Tâche 2 (`test_recherche_sans_traqueur_ne_leve_pas`).
2. Deux téléchargements identiques successifs : deux envois → test Tâche 1 (`test_emettre_deux_fois_le_meme_evenement_change_la_donnee`).
3. Filtre saisi puis réinitialisé avant 3 s : aucun événement `filtres` vide → test Tâche 5 (`test_filtre_puis_reinitialisation_rapide_n_envoie_rien`).
4. Jeu de filtres très long ou dans un autre ordre : chaîne tronquée et identique → test Tâche 5 (`test_serialiser_filtres_js`).
5. Visiteur sans abonnement avec un mode « observatoire » resté en localStorage : la restauration au chargement ne compte pas → test Tâche 7 (`test_restauration_du_mode_sans_abonnement_n_envoie_rien`).

---

### Tâche 1 : noyau Python `src/utils/suivi.py`

**Files :**

- Create : `src/utils/suivi.py`
- Test : `tests/test_suivi.py`

**Interfaces :**

- Produces :
  - `STORE_ID = "suivi-matomo"`
  - `emettre(categorie: str, action: str, nom: str | None = None, valeur: int | float | None = None) -> None` → `set_props(STORE_ID, {"data": {"type": "evenement", "categorie", "action", "nom", "valeur", "nonce"}})`
  - `emettre_recherche(mot_cle: str, categorie: str, nb_resultats: int) -> None` → `set_props(STORE_ID, {"data": {"type": "recherche", "mot_cle", "categorie", "nb_resultats", "nonce"}})`
  - `serialiser_filtres_observatoire(filtres: dict[str, object]) -> tuple[str, int]` → (chaîne, nombre de filtres non vides) ; `("", 0)` si aucun.
- `set_props` est importé au niveau module (`from dash import set_props`) pour que les tests le remplacent par `monkeypatch.setattr("src.utils.suivi.set_props", …)`.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
from src.utils import suivi


def _capturer(monkeypatch):
    envois = []
    monkeypatch.setattr(suivi, "set_props", lambda cid, props: envois.append((cid, props["data"])))
    return envois


def test_emettre_ecrit_l_evenement_dans_le_store(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre("Tableau", "telechargement", "xlsx", 12)
    (cid, data), = envois
    assert cid == "suivi-matomo"
    assert {k: data[k] for k in ("type", "categorie", "action", "nom", "valeur")} == {
        "type": "evenement", "categorie": "Tableau", "action": "telechargement", "nom": "xlsx", "valeur": 12,
    }


def test_emettre_deux_fois_le_meme_evenement_change_la_donnee(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre("Tableau", "reinitialisation")
    suivi.emettre("Tableau", "reinitialisation")
    assert envois[0][1]["nonce"] != envois[1][1]["nonce"]


def test_emettre_recherche(monkeypatch):
    envois = _capturer(monkeypatch)
    suivi.emettre_recherche("rennes", "accueil", 7)
    data = envois[0][1]
    assert (data["type"], data["mot_cle"], data["categorie"], data["nb_resultats"]) == ("recherche", "rennes", "accueil", 7)


def test_serialisation_observatoire_independante_de_l_ordre():
    a = {"marche_objet": "voirie", "annee": 2025, "acheteur_departement_code": ["44", "35"]}
    b = dict(reversed(list(a.items())))
    assert suivi.serialiser_filtres_observatoire(a) == suivi.serialiser_filtres_observatoire(b) == (
        'acheteur_departement_code [35, 44] | annee = 2025 | marche_objet = "voirie"', 3,
    )


def test_serialisation_observatoire_ignore_les_vides():
    assert suivi.serialiser_filtres_observatoire({"annee": None, "marche_objet": "", "marche_techniques": []}) == ("", 0)


def test_serialisation_observatoire_tronque_a_500():
    chaine, n = suivi.serialiser_filtres_observatoire({"marche_objet": "x" * 600})
    assert len(chaine) == 500 and chaine.endswith("…") and n == 1
```

- [ ] **Step 2 :** `uv run pytest tests/test_suivi.py -v` → FAIL (`ModuleNotFoundError: src.utils.suivi`).
- [ ] **Step 3 : implémenter `src/utils/suivi.py`.** `nonce = uuid.uuid4().hex`. Sérialisation : parties triées par clé ; liste → `<clé> [v1, v2]` (valeurs `str()` triées, sans guillemets) ; `str` → `<clé> = "<v>"` ; `bool` → `<clé> = true|false` ; autre → `<clé> = <v>` ; vide = `None`, `""`, `[]` ; jointure `|` ; au-delà de 500 caractères, couper à 499 et ajouter `…`.
- [ ] **Step 4 :** `uv run pytest tests/test_suivi.py -v` → PASS.
- [ ] **Step 5 : commit**

```bash
pre-commit run --files src/utils/suivi.py tests/test_suivi.py
git add src/utils/suivi.py tests/test_suivi.py
git commit -m "Noyau du suivi Matomo par le navigateur (#149)"
```

---

### Tâche 2 : relais navigateur et recherche d'accueil

**Files :**

- Create : `src/assets/suivi.js`
- Modify : `src/app.py:577-589` (store), après `src/app.py:734` (relais)
- Modify : `src/pages/recherche.py:334-372`, `src/utils/search.py:5,8-24`, `src/mcp/queries.py:184`
- Delete tests : `tests/mcp/test_queries.py:14-29`
- Modify : `tests/helpers.py` (espion `_paq`)
- Test : `tests/test_suivi.py`, `tests/test_suivi_navigateur.py` (nouveau)

**Interfaces :**

- Consumes : `emettre_recherche` (Tâche 1).
- Produces :

  - `window.colibreSuivi.evenement(categorie, action, nom, valeur)` → `_paq.push(['trackEvent', categorie, action, nom?, valeur?])`, `nom`/`valeur` omis s'ils valent `null`/`undefined` ; rien si `window._paq` absent.
  - `window.colibreSuivi.recherche(motCle, categorie, nbResultats)` → `_paq.push(['trackSiteSearch', motCle, categorie, nbResultats])`.
  - `tests/helpers.py` : `installer_espion_paq(driver)` (via `driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "window._paq = [];"})`, à appeler **avant** le premier chargement) et `appels_paq(driver, methode=None) -> list[list]` (copie JSON de `window._paq`, filtrée sur le premier élément).
  - `search_org(dff, query, org_type)` : paramètre `track` supprimé.

- [ ] **Step 1 : tests qui échouent.** Dans `tests/test_suivi.py` :

```python
def test_recherche_accueil_emet_une_seule_recherche_avec_la_somme(monkeypatch):
    from src.pages import recherche
    envois = []
    monkeypatch.setattr("src.utils.suivi.set_props", lambda cid, p: envois.append(p["data"]))
    recherche.update_search_results(1, None, "  ACHETEUR 1  ")
    (data,) = envois
    attendu = sum(recherche.search_org(df, "ACHETEUR 1", t).height
                  for df, t in ((recherche.DF_ACHETEURS, "acheteur"), (recherche.DF_TITULAIRES, "titulaire")))
    assert (data["mot_cle"], data["categorie"], data["nb_resultats"]) == ("ACHETEUR 1", "accueil", attendu)
```

Dans `tests/test_suivi_navigateur.py` (Selenium) : `test_recherche_accueil_pousse_un_trackSiteSearch` (espion installé, saisie `ACHETEUR 1` + Entrée dans `#search`, attendre les résultats → exactement un appel `trackSiteSearch` dont `[1:3] == ["ACHETEUR 1", "accueil"]`) et `test_recherche_sans_traqueur_ne_leve_pas` (sans espion, même geste → aucune entrée `SEVERE` dans `dash_duo.get_logs()`).

- [ ] **Step 2 :** `uv run pytest tests/test_suivi.py -v` → FAIL (aucun envoi) ; `uv run pytest -m selenium tests/test_suivi_navigateur.py -v` → FAIL.
- [ ] **Step 3 : implémenter.**
  - `src/assets/suivi.js` : IIFE, garde `if (!window._paq) return;` dans chaque fonction d'envoi.
  - `src/app.py` : `dcc.Store(id="suivi-matomo")` à côté de `theme-enregistre` ; `app.clientside_callback` (`Output("suivi-matomo", "id")`, `Input("suivi-matomo", "data")`, `prevent_initial_call=True`) qui appelle `colibreSuivi.recherche` si `data.type === "recherche"`, sinon `colibreSuivi.evenement`, et renvoie `window.dash_clientside.no_update`.
  - `update_search_results` : après la boucle, si `query.strip()`, `emettre_recherche(query.strip(), "accueil", <somme des count>)`.
  - `search_org` : retirer `track`, l'appel `track_search` et l'import ; `src/mcp/queries.py:184` sans `track=False` ; supprimer `tests/mcp/test_queries.py:14-29`.
- [ ] **Step 4 :** les deux commandes du Step 2 → PASS ; `uv run pytest tests/mcp -q` → PASS.
- [ ] **Step 5 : commit** (`pre-commit run --files …` puis `git add` des fichiers touchés), message « Recherche d'accueil suivie une fois, depuis le navigateur (#149) ».

---

### Tâche 3 : téléchargements

**Files :**

- Modify : `src/pages/tableau.py:691-729` (`download_data`), `src/pages/observatoire.py:686-702`, `src/pages/acheteur.py:44,457-482`, `src/pages/titulaire.py:43,494-519`, `src/utils/entity_grid.py:236-280` (`_download_filtered`)
- Modify : `src/utils/tracking.py:79-90` (suppression de `track_download`)
- Test : `tests/test_suivi_telechargements.py` (nouveau)

**Interfaces :**

- Consumes : `emettre` (Tâche 1).
- Produces : `download_data(n_clicks, filter_model, column_state, total=None)` avec une nouvelle `State("tableau-total", "data")` ; la valeur par défaut garde valides les appels existants des tests.

- [ ] **Step 1 : tests qui échouent.** Réutiliser `_FakeDF` / `_fake_writers` de `tests/test_export_format_switch.py` (les importer). Un test paramétré par export et par seuil (`EXCEL_MAX_ROWS` → `xlsx`, `EXCEL_MAX_ROWS + 1` → `csv`) qui capture `src.utils.suivi.set_props` et vérifie `(categorie, action, nom, valeur)` :

  - `tableau.download_data(1, _UN_FILTRE, None)` → `("Tableau", "telechargement", fmt, hauteur)`
  - `observatoire.download_observatoire(1, {"dashboard_year": "2025"})` → `("Observatoire", "telechargement", fmt, hauteur)`
  - `acheteur.download_acheteur_data(…)` / `titulaire.download_titulaire_data(…)` (mêmes arguments que dans `test_export_format_switch.py`) → `("Acheteur"|"Titulaire", "telechargement", fmt, hauteur)`
  - `_download_filtered` de la fiche acheteur, obtenu par `_get_download_filtered_callback("acheteur")` (`tests/test_entity_grid.py:155-175`, à importer), avec les mêmes doublures que `tests/test_entity_grid.py:219-…` → `("Acheteur", "telechargement_filtre", fmt, hauteur)`

  Plus `test_csv_datagouv_emet_le_total_sans_generer_de_fichier` : `export_dataframe` remplacé par une fonction qui lève ; `tableau.download_data(1, None, None, 3_190_000)` renvoie `no_update` et émet `("Tableau", "telechargement", "csv-datagouv", 3190000)`.

- [ ] **Step 2 :** `uv run pytest tests/test_suivi_telechargements.py -v` → FAIL.
- [ ] **Step 3 : implémenter.** Un `emettre(...)` par callback, après le choix de l'extension, avec la hauteur du DataFrame exporté ; branche sans filtre de `download_data` : `emettre("Tableau", "telechargement", "csv-datagouv", total or 0)` puis `return no_update`. Supprimer les appels `track_download` (4), l'appel `track_search(..., "tab download")` (`tableau.py:713`) et `track_search(..., f"{org_type} download")` (`entity_grid.py:255-260`), la fonction `track_download` et les imports devenus inutiles.
- [ ] **Step 4 :** `uv run pytest tests/test_suivi_telechargements.py tests/test_export_format_switch.py tests/test_tableau_download_button.py -v` → PASS.
- [ ] **Step 5 : commit**, « Téléchargements suivis avec format et nombre de lignes (#149) ».

---

### Tâche 4 : réinitialisation et mode d'emploi

**Files :**

- Modify : `src/pages/tableau.py:732-740` (`toggle_tableau_help`), `:827-840` (`reset_view`) ; `src/utils/entity_grid.py:218-227` (`_reset`)
- Test : `tests/test_suivi.py`

**Interfaces :** Consumes `emettre`.

- [ ] **Step 1 : tests qui échouent** (capture de `src.utils.suivi.set_props` ; `ctx` remplacé par `monkeypatch.setattr(tableau, "ctx", SimpleNamespace(triggered_id=…))`) :
  - `test_ouverture_du_mode_d_emploi_emet` : `triggered_id="tableau_help_open"`, `toggle_tableau_help(1, None, False)` → un envoi `("Tableau", "mode_emploi")`.
  - `test_fermeture_du_mode_d_emploi_n_emet_pas` : `triggered_id="tableau_help_close"`, `toggle_tableau_help(1, 1, True)` → aucun envoi.
  - `test_reinitialisation_tableau_emet` : `reset_view(1, [])` → `("Tableau", "reinitialisation")`.
  - `test_reinitialisation_fiche_emet` : `_reset` de la fiche titulaire, obtenu comme `_get_download_filtered_callback` (`tests/test_entity_grid.py:155-175`) mais en cherchant `__wrapped__.__name__ == "_reset"` et une sortie qui contient `titulaire` ; appel `_reset(1, [])` → `("Titulaire", "reinitialisation")`.
- [ ] **Step 2 :** `uv run pytest tests/test_suivi.py -v` → FAIL.
- [ ] **Step 3 : implémenter.** `toggle_tableau_help` : `emettre` seulement si `ctx.triggered_id == "tableau_help_open"`. `reset_view` / `_reset` : `emettre(<catégorie>, "reinitialisation")` (catégorie de fiche = `org_type.title()`).
- [ ] **Step 4 :** `uv run pytest tests/test_suivi.py -v` → PASS.
- [ ] **Step 5 : commit**, « Réinitialisations et mode d'emploi suivis (#149) ».

---

### Tâche 5 : filtres des grilles AG Grid

**Files :**

- Modify : `src/assets/suivi.js` (`serialiserFiltres`), `src/assets/dashAgGridFunctions.js` (`suivreFiltres`)
- Modify : `src/pages/tableau.py:107-110` (`_SHARE_DRIFT_LISTENERS`), `src/utils/entity_grid.py:117-130` (`build_entity_grid`)
- Modify : suppression de `track_search` — `src/pages/tableau.py:61,640-641,1196`, `src/utils/entity_grid.py:155-160`, `src/utils/table.py:17,559-560`, `src/utils/tracking.py:63-76` ; réécrire le commentaire `src/utils/tracking.py:39-41` (plus d'appelant synchrone dans une recherche)
- Delete tests : `tests/test_grid.py:114-124` (test « une fois par filtre »), `tests/test_table.py:35-…` et `:160-…` (deux tests `track_search`), `tests/test_tracking.py:93-119`
- Test : `tests/test_suivi_navigateur.py`

**Interfaces :**

- Consumes : `colibreSuivi.evenement` (Tâche 2), `installer_espion_paq` / `appels_paq`.
- Produces :
  - `colibreSuivi.serialiserFiltres(filterModel) -> string`
  - `dashAgGridFunctions.suivreFiltres(params, categorie)` ; chaînes d'écouteur : `"suivreFiltres(params, 'Tableau')"`, et `f"suivreFiltres(params, '{org_type.title()}')"` pour les fiches (`build_entity_grid` passe `event_listeners={"filterChanged": [...]}` à `ag_grid`).

`serialiserFiltres` — règles non déduites des tests :

- partie = `<colonne> <condition>` ; condition simple = `<opérateur> <valeur>` ; modèle combiné (`operator` + `conditions`) = `<colonne> (<cond1> ET|OU <cond2>)` ;
- texte : valeur entre guillemets ; nombre : `filter` brut ; `inRange` : `entre <filter> et <filterTo>` ; date : partie date de `dateFrom` (et `dateTo` pour `inRange`) ; `blank` / `notBlank` : pas de valeur ;
- opérateurs : table de la spec (`contains` → `contient`, …), identifiant AG Grid tel quel si inconnu ;
- colonnes triées, jointure `|`, troncature 500 (`…`).

`suivreFiltres` : ignorer `SHARE_PROGRAMMATIC_SOURCES` ; minuterie par grille dans une `WeakMap` indexée par `params.api`, relancée à chaque appel, **3000 ms** ; à l'échéance, `fm = params.api.getFilterModel()`, rien si vide, sinon `colibreSuivi.evenement(categorie, "filtres", colibreSuivi.serialiserFiltres(fm), Object.keys(fm).length)`.

- [ ] **Step 1 : tests Selenium qui échouent** (`tests/test_suivi_navigateur.py`) :
  - `test_serialiser_filtres_js` : sur `/tableau`, `execute_script` appelle `colibreSuivi.serialiserFiltres` sur : `{objet: contains "voirie", montant: greaterThan 10000}` et le même dans l'autre ordre → même chaîne `montant > 10000 | objet contient "voirie"` ; un `inRange` → `montant entre 1 et 10` ; un combiné `AND` → `objet (contient "a" ET contient "b")` ; un texte de 600 caractères → longueur 500, fin `…`.
  - `test_filtre_saisi_dans_le_tableau_envoie_un_evenement` : espion, saisie `voirie` dans le filtre flottant `objet`, attendre 4 s → exactement un `trackEvent` `["Tableau", "filtres", 'objet contient "voirie"', 1]`.
  - `test_filtre_saisi_dans_une_fiche_envoie_un_evenement` : idem sur `/acheteurs/123` → catégorie `Acheteur`.
  - `test_vue_partagee_et_filtre_d_url_n_envoient_rien` : `/tableau?acheteur_id=123` (filtre programmatique), attendre 4 s → aucun `trackEvent` d'action `filtres`.
  - `test_filtre_puis_reinitialisation_rapide_n_envoie_rien` : saisie puis clic `#btn-tableau-reset` en moins de 3 s, attendre 4 s → aucun `filtres`.
- [ ] **Step 2 :** `uv run pytest -m selenium tests/test_suivi_navigateur.py -v` → FAIL sur ces tests.
- [ ] **Step 3 : implémenter** les deux fonctions JS, les écouteurs, puis les suppressions listées (fonction, appels, imports, tests obsolètes).
- [ ] **Step 4 :** `uv run pytest -m selenium tests/test_suivi_navigateur.py tests/saved_views/test_tableau_share.py -v` → PASS (le second vérifie que `hideShareOnUserAction` marche toujours) ; `uv run pytest -q` → PASS.
- [ ] **Step 5 : commit**, « Filtres des grilles suivis en combinaisons, côté navigateur (#149) ».

---

### Tâche 6 : filtres de l'observatoire

**Files :**

- Modify : `src/pages/observatoire.py:582-607` (`update_dashboard_cards`)
- Test : `tests/test_suivi.py`

**Interfaces :** Consumes `emettre`, `serialiser_filtres_observatoire`. Le dict passé est indexé par `url_key` (2ᵉ élément de chaque tuple de `FILTER_PARAMS`).

- [ ] **Step 1 : tests qui échouent** (capture de `set_props` ; `observatoire._compute_dashboard_children` remplacé par `lambda *a: []` ; `observatoire.current_theme` par `lambda: "clair"` ; `observatoire.ctx` par un `SimpleNamespace`) :
  - `test_filtre_observatoire_emet` : `triggered_id="dashboard_marche_objet"`, valeurs de `FILTER_PARAMS` toutes `None` sauf `marche_objet="voirie"` → `("Observatoire", "filtres", 'marche_objet = "voirie"', 1)`.
  - `test_chargement_initial_n_emet_pas` : `triggered_id=None` → aucun envoi.
  - `test_changement_d_ordre_des_tuiles_n_emet_pas` : `triggered_id="observatoire-card-order"` → aucun envoi.
  - `test_jeu_vide_n_emet_pas` : `triggered_id="dashboard_marche_objet"`, toutes valeurs vides → aucun envoi.
- [ ] **Step 2 :** `uv run pytest tests/test_suivi.py -v` → FAIL.
- [ ] **Step 3 : implémenter** : si `ctx.triggered_id` ∈ ids de `FILTER_PARAMS`, sérialiser `{url_key: valeur}` et `emettre` si le nombre est non nul.
- [ ] **Step 4 :** `uv run pytest tests/test_suivi.py tests/test_observatoire_order.py -v` → PASS.
- [ ] **Step 5 : commit**, « Filtres de l'observatoire suivis (#149) ».

---

### Tâche 7 : bascule de mode, thème, tuiles

**Files :**

- Modify : `src/pages/tableau.py:1295-1304` (persistance du mode), `src/app.py:723-734` (rechargement du thème), `src/assets/observatoire-dragdrop.js:115-129` (`drop`)
- Test : `tests/test_suivi_navigateur.py`

**Interfaces :** Consumes `colibreSuivi.evenement` ; fixture `compte_abonne` et helpers `_se_connecter` / `_ouvrir_le_tableau` de `tests/test_tableau_mode_observatoire_abonne.py` (les importer).

- Mode : ajouter `State("tableau-mode-observatoire-persiste", "data")` et `State("tableau-mode-observatoire", "disabled")` ; émettre `("Tableau", "mode", value ? "observatoire" : "lignes")` seulement si `!desactive && value !== (stocke === true)` ; renvoyer `value` comme aujourd'hui.
- Thème : dans le clientside callback, juste avant `window.location.reload()`, `colibreSuivi.evenement("Interface", "theme", theme)` (`theme` vaut `"clair"` ou `"sombre"`, `src/theme.py:17-18`).
- Tuile : après `pushOrder`, `colibreSuivi.evenement(categorie, "tuile_deplacee", cardId(dragSrc), position)` — `categorie = "Tableau"` si `marker.getAttribute("data-card-order-store") === "tableau-card-order-nouveau"`, sinon `"Observatoire"` ; `position` = rang 1-based de `dragSrc` parmi les enfants de la liste portant `observatoire-card`. Lire `cardId(dragSrc)` avant que `dragend` ne remette `dragSrc` à `null`.

- [ ] **Step 1 : tests Selenium qui échouent :**
  - `test_bascule_manuelle_du_mode_envoie_un_evenement` (abonné) : espion, clic sur `#tableau-mode-observatoire` → un `["Tableau", "mode", "observatoire"]` ; `driver.refresh()` → le compteur d'événements `mode` n'augmente pas après rechargement (espion réinstallé à chaque document, donc tableau vide puis aucun `mode`).
  - `test_restauration_du_mode_sans_abonnement_n_envoie_rien` : anonyme, `localStorage["tableau-mode-observatoire-persiste"] = "true"`, rechargement → aucun `mode`.
  - `test_deplacement_d_une_tuile_envoie_un_evenement` (abonné, `/observatoire`) : déclencher `dragstart` / `dragover` / `drop` par `execute_script` avec un `DataTransfer` de la première vers la deuxième tuile → un `["Observatoire", "tuile_deplacee", <id de la première tuile>, 2]`.
- [ ] **Step 2 :** `uv run pytest -m selenium tests/test_suivi_navigateur.py -v` → FAIL sur ces tests.
- [ ] **Step 3 : implémenter** les trois points ci-dessus.
- [ ] **Step 4 :** `uv run pytest -m selenium tests/test_suivi_navigateur.py tests/test_tableau_mode_observatoire_abonne.py tests/test_observatoire_dragdrop_integration.py -v` → PASS.
- [ ] **Step 5 : commit**, « Bascule de mode, thème et tuiles suivis (#149) ».

---

### Tâche 8 : mentions légales

**Files :** Modify `src/pages/projet/mentions_legales.py:139-142`.

- [ ] **Step 1 :** présenter à Colin le texte exact de la section « Mentions légales » de la spec et **attendre sa validation explicite** (ou sa version corrigée).
- [ ] **Step 2 :** remplacer la liste par le texte validé, sans toucher au reste.
- [ ] **Step 3 :** `uv run pytest tests/test_mentions_legales.py -v` → PASS.
- [ ] **Step 4 : commit**, « Mentions légales : données suivies (#149) ».

---

### Tâche 9 : vérification

- [ ] **Step 1 :** `uv run pytest -q` → PASS ; `uv run pytest -m selenium tests/test_suivi_navigateur.py tests/test_main.py -q` → PASS.
- [ ] **Step 2 :** `uv run run.py`, ouvrir un vrai navigateur, poser `window._paq = []` avant chaque geste (ou via l'espion CDP) et exercer chaque ligne du catalogue de la spec ; relever `window._paq` et le comparer au catalogue (catégorie, action, nom, valeur). Inclure le thème (compte abonné) et le CSV complet de `/tableau`.
- [ ] **Step 3 :** `grep -rn "track_search\|track_download" src tests` → aucune occurrence.
- [ ] **Step 4 (après mise en production par Colin) :** lecture seule de l'API Matomo, site 14, `period=day&date=today` : `Events.getCategory`, `Events.getAction`, `Actions.getSiteSearchKeywords` → chaque catégorie exercée remonte.
