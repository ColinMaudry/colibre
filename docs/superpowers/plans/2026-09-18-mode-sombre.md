# Mode sombre (#118) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux abonné·es de basculer colibre en thème sombre Earthsong via un switch ☀/☾ dans le menu « Mon compte ».

**Architecture:** Préférence stockée par compte dans une table SQLite `user_preferences` ; `current_theme()` la combine avec le droit d'abonnement. Le serveur pose `data-bs-theme="dark"` sur `<html>` (Bootstrap 5.3 natif + surcharges CSS) et les figures Plotly / cartes Leaflet choisissent leurs couleurs selon le thème. Basculer enregistre puis recharge la page.

**Tech Stack:** Dash 4.4, Dash Bootstrap Components (Bootswatch Simplex 5.3.6), Plotly, dash-leaflet, dash-ag-grid, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-mode-sombre-design.md`

## Global Constraints

- Valeurs de thème : `"clair"` et `"sombre"` (constantes `CLAIR` / `SOMBRE` de `src/theme.py`), jamais d'autres chaînes en dur.
- Fond sombre `#292520`, texte `#e5c7a9`, primaire `#e06c57`, liens `#eb8c82`, grille/bordures `#675f54`.
- Réservé aux abonné·es : `current_user_has_subscription()` de `src/pages/_compte_shell.py` (essai et `TOUS_ABONNES` compris).
- Aucun nouveau tiers réseau (pas de tuiles externes, pas de CDN) ; polices via Bunny Fonts si besoin.
- Imports applicatifs préfixés `src.` ; `src.pages._compte_shell` importé localement dans `src/app.py` et `src/theme.py` (les pages sont découvertes après `app.py`).
- Tests : `uv run pytest <fichier>` limité aux fichiers de la tâche ; suite complète uniquement à la tâche 7. Jamais deux pytest en parallèle.
- Toute assertion d'absence (« X n'est pas dans le rendu ») doit être accompagnée d'une assertion positive prouvant que le rendu a bien eu lieu.
- Avant tout `git add` : `pre-commit run --files <fichiers>` (ruff). Ne pas commiter sans le feu vert de Colin : chaque étape « Commit » prépare le commit et attend sa validation.
- Textes UI en français.

## Structure des fichiers

| Fichier                                                                                                                                                                                         | Rôle                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `src/theme.py` (nouveau)                                                                                                                                                                        | Constantes, lecture/écriture de la préférence, `current_theme()`                                 |
| `src/migrations.py`                                                                                                                                                                             | Migration `0016_create_user_preferences`                                                         |
| `src/app.py`                                                                                                                                                                                    | Attribut `data-bs-theme` dans l'index, switch du menu, callbacks d'enregistrement / rechargement |
| `src/assets/css/style.css`                                                                                                                                                                      | Bloc `[data-bs-theme="dark"]`, variables des étapes, filtre des tuiles                           |
| `src/figures.py`                                                                                                                                                                                | Palettes sombres, `appliquer_theme`, paramètre `theme` des figures et cartes                     |
| `src/pages/observatoire.py`, `src/pages/tableau.py`                                                                                                                                             | Thème dans la clé des caches memoizés                                                            |
| `src/pages/etapes.py`                                                                                                                                                                           | Couleurs → variables CSS                                                                         |
| `tests/test_theme.py` (nouveau), `tests/test_migrations.py`, `tests/test_nav_compte.py`, `tests/test_figures.py`, `tests/test_etapes_theme.py` (nouveau), `tests/test_theme_cache.py` (nouveau) | Tests                                                                                            |

---

### Task 1: Stockage de la préférence et droits

**Files:**

- Create: `src/theme.py`
- Modify: `src/migrations.py` (fin de `_MIGRATIONS`, après `0015_create_observatoire_card_order`)
- Test: `tests/test_theme.py`, `tests/test_migrations.py`

**Interfaces:**

- Produces: `CLAIR: str = "clair"`, `SOMBRE: str = "sombre"`, `THEMES = (CLAIR, SOMBRE)`, `get_theme(user_id: int) -> str`, `save_theme(user_id: int, theme: str) -> None` (lève `ValueError` si `theme not in THEMES`), `current_theme() -> str`.

- [ ] **Step 1: Écrire les tests (qui échouent)**

S'inspirer de `tests/test_observatoire_order.py` (fixture autouse qui appelle `apply_pending()`) et de `tests/test_migrations.py` (fixture `users_db_path`). Ce qu'il faut prouver :

- migration 0016 : la table `user_preferences` existe avec exactement les colonnes `user_id, theme, updated_at` ; `apply_pending()` appelé deux fois ne lève pas.
- `get_theme` renvoie `CLAIR` pour un utilisateur sans ligne.
- `save_theme(u, SOMBRE)` puis `get_theme(u) == SOMBRE` ; un second `save_theme(u, CLAIR)` remplace la valeur (upsert, une seule ligne pour `u` en base).
- `save_theme(u, "bleu")` lève `ValueError` et n'écrit rien (vérifier que `get_theme` renvoie toujours la valeur précédente, pas seulement que l'exception est levée).
- `current_theme()` :

  - hors contexte de requête Flask → `CLAIR` ;
  - dans `app.server.test_request_context()`, utilisateur non connecté → `CLAIR` ;
  - connecté, préférence `SOMBRE`, **non abonné** → `CLAIR` ;
  - connecté, préférence `SOMBRE`, abonné → `SOMBRE` (ce cas positif ancre les trois négatifs : sans lui les tests passeraient avec une fonction qui renvoie toujours `CLAIR`) ;
  - connecté, abonné, sans préférence → `CLAIR`.

  Pour l'utilisateur et l'abonnement, monkeypatcher `src.theme.current_user` (objet avec `is_authenticated` et `id`) et `src.pages._compte_shell.current_user_has_subscription`, comme `tests/test_nav_compte.py`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_theme.py tests/test_migrations.py -v`
Expected: FAIL (`ModuleNotFoundError: src.theme`, table absente).

- [ ] **Step 3: Migration**

Ajouter à la fin de `_MIGRATIONS` dans `src/migrations.py` :

```python
    (
        "0016_create_user_preferences",
        "CREATE TABLE IF NOT EXISTS user_preferences ("
        "user_id INTEGER PRIMARY KEY, "
        "theme TEXT NOT NULL DEFAULT 'clair', "
        "updated_at TEXT NOT NULL)",
    ),
```

- [ ] **Step 4: Module `src/theme.py`**

```python
"""Préférence de thème clair / sombre, par utilisateur (#118).

Les lignes de `user_preferences` (migration 0016) sont créées paresseusement,
au premier usage du switch ; l'absence de ligne vaut « clair ». Le mode sombre
est réservé aux abonné·es : le droit est vérifié à la lecture, dans
`current_theme()`, si bien qu'à la fin d'un abonnement l'affichage repasse en
clair tout en conservant la préférence pour un éventuel réabonnement.
"""

from datetime import datetime, timezone

from flask import has_request_context
from flask_login import current_user

from src.auth.db import get_conn

CLAIR = "clair"
SOMBRE = "sombre"
THEMES = (CLAIR, SOMBRE)


def get_theme(user_id: int) -> str:
    """Thème enregistré par l'utilisateur, CLAIR s'il n'en a jamais choisi."""
    row = (
        get_conn()
        .execute("SELECT theme FROM user_preferences WHERE user_id = ?", (user_id,))
        .fetchone()
    )
    return row[0] if row else CLAIR


def save_theme(user_id: int, theme: str) -> None:
    """Enregistre (ou remplace) le thème choisi par l'utilisateur."""
    if theme not in THEMES:
        raise ValueError(f"Thème inconnu : {theme!r}")
    now = datetime.now(timezone.utc).isoformat()
    get_conn().execute(
        "INSERT INTO user_preferences (user_id, theme, updated_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET theme = ?, updated_at = ?",
        (user_id, theme, now, theme, now),
    )


def current_theme() -> str:
    """Thème à appliquer à la requête en cours.

    SOMBRE seulement pour un·e abonné·e connecté·e qui l'a choisi. Hors
    requête (tests, import de module) : CLAIR.
    """
    if not has_request_context() or not current_user.is_authenticated:
        return CLAIR
    # Import local : les pages sont découvertes après le chargement de src.app.
    from src.pages._compte_shell import current_user_has_subscription

    if not current_user_has_subscription():
        return CLAIR
    return get_theme(current_user.id)
```

Vérifier dans `src/observatoire_order.py` si `get_conn()` est en autocommit (pas de `commit()` explicite là-bas) et faire pareil.

- [ ] **Step 5: Vérifier le succès**

Run: `uv run pytest tests/test_theme.py tests/test_migrations.py -v`
Expected: PASS.

- [ ] **Step 6: Commit (après feu vert)**

```bash
pre-commit run --files src/theme.py src/migrations.py tests/test_theme.py tests/test_migrations.py
git add src/theme.py src/migrations.py tests/test_theme.py tests/test_migrations.py
git commit -m "Préférence de thème par utilisateur, réservée aux abonné·es #118"
```

---

### Task 2: Attribut `data-bs-theme` sur `<html>`

**Files:**

- Modify: `src/app.py` — `_interpolate_index_per_request` (vers la ligne 444)
- Test: `tests/test_theme.py` (ajout)

**Interfaces:**

- Consumes: `current_theme()`, `SOMBRE` (Task 1).

- [ ] **Step 1: Écrire les tests (qui échouent)**

Prouver, via `app.server.test_client()` sur `/` (ou un appel direct à `_interpolate_index_per_request` sous `test_request_context`) avec `src.app.current_theme` monkeypatché :

- thème `SOMBRE` → le HTML contient `<html lang="fr" data-bs-theme="dark">` ;
- thème `CLAIR` → le HTML contient `<html lang="fr">` (assertion positive) et pas `data-bs-theme`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_theme.py -v`
Expected: FAIL sur le cas sombre.

- [ ] **Step 3: Implémentation**

Dans `src/app.py`, importer en tête `from src.theme import SOMBRE, current_theme`, puis remplacer la dernière ligne de `_interpolate_index_per_request` :

```python
    html_page = _default_interpolate_index(**kwargs)
    # Thème posé côté serveur : pas de flash clair avant le chargement du JS.
    # Bootstrap 5.3 bascule ses composants sur cet attribut (#118).
    if current_theme() == SOMBRE:
        html_page = html_page.replace(
            '<html lang="fr">', '<html lang="fr" data-bs-theme="dark">', 1
        )
    return html_page
```

Attention (mémoire projet) : `src/app.py` appelle `load_dotenv` après ses imports ; `src.theme` ne lit aucune variable d'environnement au niveau module, donc l'import en tête est sûr.

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_theme.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (après feu vert)**

```bash
pre-commit run --files src/app.py tests/test_theme.py
git add src/app.py tests/test_theme.py
git commit -m "Thème sombre posé sur <html> côté serveur #118"
```

---

### Task 3: Switch ☀/☾ dans « Mon compte »

**Files:**

- Modify: `src/app.py` — `_auth_nav` (vers la ligne 606), nouveaux callbacks sous `_auth_nav`, `dcc.Store(id="theme-enregistre")` dans `app.layout`
- Modify: `src/assets/css/style.css` — style de l'item du switch
- Test: `tests/test_nav_compte.py` (ajout)

**Interfaces:**

- Consumes: `get_theme`, `save_theme`, `CLAIR`, `SOMBRE` (Task 1).
- Produces: composant `id="theme-switch"` (`dbc.Switch`, `value=True` ⇔ sombre), store `id="theme-enregistre"`, fonction de callback `_enregistrer_theme(sombre: bool | None) -> str`.

- [ ] **Step 1: Écrire les tests (qui échouent)**

Dans `tests/test_nav_compte.py`, avec l'helper `_menu` existant (monkeypatcher aussi `src.app.get_theme`) :

- abonné → le rendu contient `theme-switch`, et `value` vaut `True` quand `get_theme` renvoie `SOMBRE`, `False` quand il renvoie `CLAIR` (trouver le `dbc.Switch` dans `menu.children`, pas via `str()`) ;
- non abonné → le rendu contient la déconnexion (assertion positive) mais pas `theme-switch` ;
- le switch est placé avant le séparateur (index du switch < index du `DropdownMenuItem(divider=True)`).
- `_enregistrer_theme(True)` pour un abonné appelle `save_theme(user_id, SOMBRE)` (monkeypatcher `save_theme` pour enregistrer l'appel) ; `False` → `CLAIR` ;
- `_enregistrer_theme(True)` pour un non-abonné n'appelle pas `save_theme` et lève `PreventUpdate` (prouver les deux : l'exception ET l'absence d'appel).

Note : `test_mon_compte_ouvre_un_menu_au_lieu_de_naviguer` attend actuellement le libellé « Espace abonné » alors que le code dit « Mon compte » (commit 8f19774 / f38db67). Le lancer d'abord ; s'il échoue déjà sur `dev`, le signaler à Colin sans le corriger dans cette tâche.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_nav_compte.py -v`
Expected: FAIL sur les nouveaux tests.

- [ ] **Step 3: Implémentation**

Dans `_auth_nav`, pour un utilisateur connecté, après le calcul de `sections` :

```python
    abonne = current_user_has_subscription()
    sections = [
        dbc.DropdownMenuItem(section["label"], href=section["href"])
        for section in visible_sections(abonne)
    ]
    # Mode sombre réservé aux abonné·es (#118) : masqué plutôt que grisé,
    # comme les sections réservées (#133).
    if abonne:
        sections.append(
            html.Div(
                [
                    html.Span("☀", **{"aria-hidden": "true"}),
                    dbc.Switch(
                        id="theme-switch",
                        value=get_theme(current_user.id) == SOMBRE,
                        label="Mode sombre",
                        className="theme-switch mb-0",
                    ),
                    html.Span("☾", **{"aria-hidden": "true"}),
                ],
                className="dropdown-item-text d-flex align-items-center gap-2",
            )
        )
```

(la liste `children=sections + [divider, logout]` reste inchangée ; `current_user_has_subscription()` n'est plus appelé qu'une fois.)

Importer en tête `from src.theme import CLAIR, SOMBRE, current_theme, get_theme, save_theme`.

Ajouter `dcc.Store(id="theme-enregistre")` dans `app.layout`, à côté de `dcc.Store(id="csrf-token")`.

Callbacks, sous `_auth_nav` :

```python
@callback(
    Output("theme-enregistre", "data"),
    Input("theme-switch", "value"),
    prevent_initial_call=True,
)
def _enregistrer_theme(sombre):
    """Enregistre le thème choisi ; le rechargement est fait côté client.

    Le switch n'est affiché qu'aux abonné·es, mais un callback se déclenche
    aussi à la main : le droit est revérifié ici.
    """
    from src.pages._compte_shell import current_user_has_subscription

    if not current_user.is_authenticated or not current_user_has_subscription():
        raise PreventUpdate
    theme = SOMBRE if sombre else CLAIR
    save_theme(current_user.id, theme)
    return theme


app.clientside_callback(
    """
    function(theme) {
        // Le thème s'applique côté serveur (<html>, figures) : on recharge.
        if (theme) { window.location.reload(); }
        return window.dash_clientside.no_update;
    }
    """,
    Output("theme-enregistre", "id"),
    Input("theme-enregistre", "data"),
    prevent_initial_call=True,
)
```

Vérifier l'import de `PreventUpdate` (`from dash.exceptions import PreventUpdate`) dans `src/app.py`. Si Dash refuse `Output("theme-enregistre", "id")` (même composant en Input et Output), utiliser un `html.Div(id="theme-rechargement", hidden=True)` comme sortie factice.

CSS (`style.css`), pour que le label et le curseur restent lisibles dans le dropdown :

```css
/* Switch clair / sombre du menu « Mon compte » (#118) */
.theme-switch .form-check-input {
  cursor: pointer;
}
```

- [ ] **Step 4: Vérifier le succès**

Run: `uv run pytest tests/test_nav_compte.py -v`
Expected: PASS (hors éventuel échec préexistant signalé en Step 1).

- [ ] **Step 5: Commit (après feu vert)**

```bash
pre-commit run --files src/app.py src/assets/css/style.css tests/test_nav_compte.py
git add src/app.py src/assets/css/style.css tests/test_nav_compte.py
git commit -m "Switch soleil / lune dans Mon compte #118"
```

---

### Task 4: Feuille de style sombre et tuiles des cartes

**Files:**

- Modify: `src/assets/css/style.css` — nouveau bloc en fin de fichier
- Modify: `src/figures.py` — les deux `dl.TileLayer()` (`make_clusters_map`, `get_org_location_map`)
- Test: `tests/test_figures.py` (ajout)

**Interfaces:**

- Produces: classe CSS `tuiles` sur les calques de tuiles.

- [ ] **Step 1: Test (qui échoue)**

Prouver que la carte renvoyée par `get_org_location_map` (et une carte de `make_clusters_map`) contient un `dl.TileLayer` dont `className == "tuiles"` — trouver le composant par son type, pas par `str()`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL.

- [ ] **Step 3: `className` des tuiles**

Remplacer les deux `dl.TileLayer()` de `src/figures.py` par `dl.TileLayer(className="tuiles")`.

- [ ] **Step 4: Inventaire des couleurs en dur**

Run: `grep -nE "#[0-9a-fA-F]{3,6}\b|rgb\(" src/assets/css/style.css`
Pour chaque règle qui fixe un fond, un texte ou une bordure visible sur les pages (hors `:root` déjà traité par variables), ajouter une surcharge dans le bloc sombre ci-dessous. Noter la liste traitée dans le message de commit.

- [ ] **Step 5: Bloc sombre**

Ajouter en fin de `style.css` (compléter avec les surcharges de l'inventaire) :

```css
/* ==========================================================================
   Mode sombre (#118) — palette Earthsong
   Posé côté serveur sur <html data-bs-theme="dark"> pour les abonné·es.
   ========================================================================== */
[data-bs-theme="dark"] {
  --earth-bg: #292520;
  --earth-bg-2: #332e28;
  --earth-bg-3: #3d372f;
  --earth-fg: #e5c7a9;
  --earth-muted: #968c83;
  --earth-border: #675f54;
  --earth-primary: #e06c57;
  --earth-link: #eb8c82;

  --bs-body-bg: var(--earth-bg);
  --bs-body-bg-rgb: 41, 37, 32;
  --bs-body-color: var(--earth-fg);
  --bs-body-color-rgb: 229, 199, 169;
  --bs-emphasis-color: #f6f7ec;
  --bs-secondary-color: var(--earth-muted);
  --bs-secondary-bg: var(--earth-bg-2);
  --bs-tertiary-bg: var(--earth-bg-3);
  --bs-border-color: var(--earth-border);
  --bs-link-color: var(--earth-link);
  --bs-link-color-rgb: 235, 140, 130;
  --bs-link-hover-color: #f6f7ec;
  --bs-primary: var(--earth-primary);
  --bs-primary-rgb: 224, 108, 87;

  --primary-color: var(--earth-primary);
  --primary-color-text: var(--earth-primary);
  --btn-terracotta: var(--earth-primary);
  --btn-terracotta-text: #121418;
  --btn-secondary-text: var(--earth-fg);
  --btn-secondary-border: var(--earth-border);
  --btn-secondary-hover-bg: var(--earth-bg-3);

  /* AG Grid */
  --ag-background-color: var(--earth-bg);
  --ag-foreground-color: var(--earth-fg);
  --ag-header-background-color: var(--earth-bg-2);
  --ag-header-foreground-color: var(--earth-fg);
  --ag-odd-row-background-color: var(--earth-bg-2);
  --ag-row-hover-color: var(--earth-bg-3);
  --ag-border-color: var(--earth-border);
  --ag-secondary-foreground-color: var(--earth-muted);
}

[data-bs-theme="dark"] body {
  background-color: var(--earth-bg);
  color: var(--earth-fg);
}

[data-bs-theme="dark"] .navbar {
  background-color: var(--earth-bg-2) !important;
}

[data-bs-theme="dark"] a {
  color: var(--earth-link);
}

/* Alertes : fond sombre teinté, bordure et titre à la couleur Earthsong */
[data-bs-theme="dark"] .alert-warning {
  --bs-alert-bg: #3a2f1c;
  --bs-alert-border-color: #f5ae2e;
  --bs-alert-color: #f6e3bf;
  --bs-alert-link-color: #f5ae2e;
}
[data-bs-theme="dark"] .alert-info {
  --bs-alert-bg: #1b2e33;
  --bs-alert-border-color: #1398b9;
  --bs-alert-color: #cde9f0;
  --bs-alert-link-color: #5fdaff;
}
[data-bs-theme="dark"] .alert-danger {
  --bs-alert-bg: #3a211d;
  --bs-alert-border-color: #c94234;
  --bs-alert-color: #f3cfc8;
  --bs-alert-link-color: #ff645a;
}

/* Tuiles OSM assombries ; marqueurs et popups non filtrés */
[data-bs-theme="dark"] .tuiles {
  filter: invert(1) hue-rotate(180deg) brightness(0.9) sepia(0.25);
}
[data-bs-theme="dark"] .leaflet-container {
  background: var(--earth-bg);
}
```

Composants dcc de Dash 4 : lister les variables `--Dash-*` réellement utilisées (`grep -o "\-\-Dash-[A-Za-z-]*" -r .venv/lib/python*/site-packages/dash/dcc/ | sort -u`) et redéfinir dans le bloc sombre celles de fond, texte et bordure (`--Dash-Fill-*`, `--Dash-Text-*`, `--Dash-Stroke-*`) avec `--earth-bg*`, `--earth-fg`, `--earth-border`.

- [ ] **Step 6: Vérifier le succès**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS.

- [ ] **Step 7: Contrôle visuel**

Lancer `uv run run.py`, se connecter avec un compte abonné en local, passer en sombre, et parcourir `/`, `/tableau`, `/observatoire`, une fiche acheteur, `/compte/abonnement` (alertes), `/projet/presentation`. Noter tout texte illisible ou fond resté clair et le corriger dans le bloc sombre. Joindre des captures à la revue.

- [ ] **Step 8: Commit (après feu vert)**

```bash
pre-commit run --files src/assets/css/style.css src/figures.py tests/test_figures.py
git add src/assets/css/style.css src/figures.py tests/test_figures.py
git commit -m "Feuille de style sombre Earthsong et tuiles assombries #118"
```

---

### Task 5: Graphiques Plotly et marqueurs en thème sombre

**Files:**

- Modify: `src/figures.py` — `get_barchart_sources`, `get_duplicate_matrix`, `ORG_COLORS` / `build_org_markers`, `make_chloropleth_map`, `make_clusters_map`, `get_org_location_map`, `get_distance_histogram`, `CONSIDERATIONS_RENSEIGNEES` / `get_considerations_card_content`, `make_donut`, `build_dashboard_cards`, `get_geographic_maps`
- Test: `tests/test_figures.py` (ajout)

**Interfaces:**

- Consumes: `current_theme`, `CLAIR`, `SOMBRE` (Task 1).
- Produces: `PALETTE_SOMBRE: list[str]` (12), `PALETTE_SOMBRE_24: list[str]` (24), `ECHELLE_SOMBRE: list[str]`, `ORG_COLORS_SOMBRE: dict[str, str]`, `appliquer_theme(fig, theme: str) -> go.Figure`, `org_colors(theme: str) -> dict[str, str]`, et un paramètre `theme: str | None = None` sur chaque fonction listée ci-dessus. `build_dashboard_cards(dff, order=None, theme=None)` résout le thème une fois et le transmet à toutes les figures qu'il construit.

- [ ] **Step 1: Tests (qui échouent)**

Prouver :

- `appliquer_theme(fig, SOMBRE)` pose `paper_bgcolor`, `plot_bgcolor` à `#292520` et la couleur de police à `#e5c7a9` ; `appliquer_theme(fig, CLAIR)` laisse ces trois propriétés à leur valeur d'origine (comparer avec la figure avant l'appel, pas avec `None`).
- `make_donut(..., theme=SOMBRE)` utilise des couleurs de `PALETTE_SOMBRE` et `theme=CLAIR` celles de `px.colors.qualitative.Safe` (lire `figure.layout.colorway` ou les couleurs des traces, selon l'implémentation).
- `get_barchart_sources(..., theme=SOMBRE)` : les traces utilisent `PALETTE_SOMBRE_24`.
- `build_org_markers(lff, "acheteur", theme=SOMBRE)` : `marker_color == ORG_COLORS_SOMBRE["acheteur"]` ; en clair `ORG_COLORS["acheteur"]`.
- `PALETTE_SOMBRE_24` : 24 couleurs distinctes.
- sans argument `theme` et hors requête, les fonctions produisent le rendu clair actuel (non-régression).

Utiliser les LazyFrame de test existants de `tests/test_figures.py`.

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL.

- [ ] **Step 3: Palettes et helpers**

En haut de `src/figures.py` (après les imports, ajouter `from src.theme import CLAIR, SOMBRE, current_theme`) :

```python
# Mode sombre (#118) : palette Earthsong, plus sombre que les palettes du
# thème clair mais contrastée entre ses teintes.
FOND_SOMBRE = "#292520"
TEXTE_SOMBRE = "#e5c7a9"
GRILLE_SOMBRE = "#675f54"

PALETTE_SOMBRE = [
    "#c94234", "#1398b9", "#85c54c", "#f5ae2e", "#d0633d", "#509552",
    "#e0d561", "#5fdaff", "#ff9269", "#84f088", "#ff645a", "#98e036",
]


def _assombrir(hex_color: str, facteur: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(
        *(round(c * (1 - facteur)) for c in (r, g, b))
    )


# ~24 sources dans le graphique des sources : la palette Earthsong puis ses
# variantes assombries, pour 24 teintes distinctes (équivalent sombre de Dark24).
PALETTE_SOMBRE_24 = PALETTE_SOMBRE + [_assombrir(c, 0.4) for c in PALETTE_SOMBRE]

ECHELLE_SOMBRE = [FOND_SOMBRE, "#e06c57"]

ORG_COLORS_SOMBRE = {
    "acheteur": "#f5ae2e",  # jaune Earthsong
    "titulaire": "#1398b9",  # bleu Earthsong
}


def _theme(theme: str | None) -> str:
    return theme or current_theme()


def org_colors(theme: str) -> dict[str, str]:
    return ORG_COLORS_SOMBRE if theme == SOMBRE else ORG_COLORS


def appliquer_theme(fig: go.Figure, theme: str) -> go.Figure:
    """Fond, police et grille Earthsong en sombre ; sans effet en clair."""
    if theme != SOMBRE:
        return fig
    fig.update_layout(
        paper_bgcolor=FOND_SOMBRE,
        plot_bgcolor=FOND_SOMBRE,
        font_color=TEXTE_SOMBRE,
    )
    fig.update_xaxes(gridcolor=GRILLE_SOMBRE, linecolor=GRILLE_SOMBRE, zerolinecolor=GRILLE_SOMBRE)
    fig.update_yaxes(gridcolor=GRILLE_SOMBRE, linecolor=GRILLE_SOMBRE, zerolinecolor=GRILLE_SOMBRE)
    fig.update_geos(bgcolor=FOND_SOMBRE)
    return fig
```

`ORG_COLORS` doit être défini avant `org_colors` : placer ce bloc juste après `ORG_COLORS`, ou déplacer `ORG_COLORS` en haut du module.

- [ ] **Step 4: Appliquer aux figures**

Pour chaque fonction, ajouter `theme: str | None = None` en dernier paramètre, `theme = _theme(theme)` en première ligne, puis :

- `get_barchart_sources` : `color_discrete_sequence=PALETTE_SOMBRE_24 if theme == SOMBRE else px.colors.qualitative.Dark24` ; `fig = appliquer_theme(fig, theme)` avant `dcc.Graph`.
- `make_donut` : `PALETTE_SOMBRE if theme == SOMBRE else px.colors.qualitative.Safe` ; `appliquer_theme`.
- `get_duplicate_matrix` : en sombre, `colorscale=[[0.0, FOND_SOMBRE], [0.10, "#d0633d"], [1.0, "#ff9269"]]` ; `appliquer_theme`.
- `make_chloropleth_map(region, theme=None)` : `color_continuous_scale=ECHELLE_SOMBRE if theme == SOMBRE else "Reds"` ; `appliquer_theme`.
- `get_distance_histogram` : en sombre `marker_color="#e06c57"` sur la `go.Bar` ; `appliquer_theme`.
- `build_org_markers(lff, org_type, theme=None)` : `org_colors(theme)[org_type]`.
- `make_clusters_map(region, theme=None)` et `get_org_location_map(dff, home_type, map_id, theme=None)` : `org_colors(theme)` pour `fillColor` et la légende ; transmettre `theme` à `build_org_markers`.
- `get_geographic_maps(dff, theme=None)` : transmettre `theme` à `make_clusters_map` / `make_chloropleth_map` et aux `build_org_markers` qu'il appelle.
- Considérations : ajouter une couleur sombre à chaque tuple de `CONSIDERATIONS_RENSEIGNEES` (`("sociales_renseignees", "Considérations sociales", "#CC6677", "#d0633d")`, `("environnementales_renseignees", "Considérations environnementales", "#117733", "#85c54c")`) ; `get_considerations_card_content(lff, theme=None)` choisit la couleur selon le thème, et la barre neutre passe de `"#6c757d"` à `GRILLE_SOMBRE` en sombre. Mettre à jour tout autre lecteur de `CONSIDERATIONS_RENSEIGNEES` (`grep -rn CONSIDERATIONS_RENSEIGNEES src tests`).
- `build_dashboard_cards(dff, order=None, theme=None)` : `theme = _theme(theme)` puis passer `theme=theme` à `make_donut`, `get_considerations_card_content`, `get_distance_histogram`, `get_geographic_maps`, `get_barchart_sources`.

Les appelants de `src/pages/acheteur.py` et `src/pages/titulaire.py` (`get_org_location_map`, `get_distance_histogram`) n'ont rien à changer : ils tournent dans un callback, `current_theme()` y résout le thème.

- [ ] **Step 5: Vérifier le succès**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS.

- [ ] **Step 6: Commit (après feu vert)**

```bash
pre-commit run --files src/figures.py tests/test_figures.py
git add src/figures.py tests/test_figures.py
git commit -m "Graphiques et marqueurs en palette Earthsong sombre #118"
```

---

### Task 6: Thème dans la clé des caches, et frise des étapes

**Files:**

- Modify: `src/pages/observatoire.py` — `_compute_dashboard_children` (l. ~666) et son appel dans `update_dashboard_cards`
- Modify: `src/pages/tableau.py` — `_cards_pour_filtre` (l. ~1013) et son appelant
- Modify: `src/pages/etapes.py` — couleurs de `_bar(...)` et `STAGES_MOBILE`
- Modify: `src/assets/css/style.css` — variables `--etape-*`
- Test: `tests/test_theme_cache.py`, `tests/test_etapes_theme.py`

**Interfaces:**

- Consumes: `current_theme` (Task 1), `build_dashboard_cards(dff, order=None, theme=None)` (Task 5).
- Produces: `_compute_dashboard_children(filter_params_normalized: tuple, theme: str)`, `_cards_pour_filtre(filter_model_json: str, theme: str)`.

- [ ] **Step 1: Tests (qui échouent)**

`tests/test_theme_cache.py` — prouver, pour chacune des deux fonctions memoizées (monkeypatcher `build_dashboard_cards` dans le module de la page pour compter les appels et renvoyer une valeur marquée par le thème reçu) :

- deux appels avec les mêmes filtres et le même thème → un seul calcul (le cache fonctionne toujours) ;
- mêmes filtres, `CLAIR` puis `SOMBRE` → deux calculs, et le second résultat est celui du thème sombre (c'est le bug que l'on prévient : une figure sombre servie à un visiteur clair) ;
- `build_dashboard_cards` reçoit bien `theme=` égal au thème passé.

Vider le cache en début de test (`cache.clear()`, voir `tests/test_cache_purge.py`).

`tests/test_etapes_theme.py` — prouver que le layout de la page étapes (desktop et mobile) ne contient plus aucune couleur hexadécimale inline (regex `#[0-9a-fA-F]{6}` sur `str(layout)`) ET qu'il contient les `var(--etape-...)` attendus (assertion positive).

- [ ] **Step 2: Vérifier l'échec**

Run: `uv run pytest tests/test_theme_cache.py tests/test_etapes_theme.py -v`
Expected: FAIL.

- [ ] **Step 3: Caches**

`src/pages/observatoire.py` :

```python
@cache.memoize()
def _compute_dashboard_children(filter_params_normalized: tuple, theme: str):
    # `theme` fait partie de la clé de cache : les figures sont colorées
    # côté serveur (#118).
    ...
    return build_dashboard_cards(dff, theme=theme)
```

et dans `update_dashboard_cards` : `children = _compute_dashboard_children(filter_params_normalized, current_theme())` (import `from src.theme import current_theme`).

`src/pages/tableau.py` : même traitement pour `_cards_pour_filtre(filter_model_json: str, theme: str)` → `build_dashboard_cards(dff, theme=theme)`, et l'appelant passe `current_theme()`.

- [ ] **Step 4: Étapes**

Dans `src/pages/etapes.py`, remplacer chaque couleur en dur par une variable CSS :

| Couleur   | Variable               |
| --------- | ---------------------- |
| `#7c5cff` | `var(--etape-approch)` |
| `#f79009` | `var(--etape-jal)`     |
| `#1570ef` | `var(--etape-boamp)`   |
| `#0e9384` | `var(--etape-joue)`    |
| `#12b76a` | `var(--etape-decp)`    |

Vérifier comment `_bar` et la vue mobile utilisent la couleur (`background`, `borderLeft`…) : une `var()` fonctionne partout où une couleur CSS est acceptée, mais pas si la couleur est concaténée avec une opacité (`"#7c5cff33"`) — dans ce cas, utiliser `color-mix(in srgb, var(--etape-approch) 20%, transparent)`.

Dans `style.css`, section `:root` :

```css
:root {
  /* Frise des étapes (etapes.py) */
  --etape-approch: #7c5cff;
  --etape-jal: #f79009;
  --etape-boamp: #1570ef;
  --etape-joue: #0e9384;
  --etape-decp: #12b76a;
}
```

et dans le bloc sombre :

```css
[data-bs-theme="dark"] {
  --etape-approch: #d0633d;
  --etape-jal: #f5ae2e;
  --etape-boamp: #1398b9;
  --etape-joue: #509552;
  --etape-decp: #85c54c;
}
```

- [ ] **Step 5: Vérifier le succès**

Run: `uv run pytest tests/test_theme_cache.py tests/test_etapes_theme.py tests/test_tableau_mode_observatoire.py tests/test_tableau_mode_observatoire_abonne.py -v`
Expected: PASS.

- [ ] **Step 6: Commit (après feu vert)**

```bash
pre-commit run --files src/pages/observatoire.py src/pages/tableau.py src/pages/etapes.py src/assets/css/style.css tests/test_theme_cache.py tests/test_etapes_theme.py
git add src/pages/observatoire.py src/pages/tableau.py src/pages/etapes.py src/assets/css/style.css tests/test_theme_cache.py tests/test_etapes_theme.py
git commit -m "Thème dans la clé des caches de figures ; frise des étapes thémable #118"
```

---

### Task 7: Vérification finale

Pas de CHANGELOG : Colin l'écrit lui-même. Ne pas toucher à `CHANGELOG.md`.

- [ ] **Step 1: Suite complète**

Run: `uv run pytest`
Expected: PASS (signaler tout échec, y compris préexistant, avec sa sortie).

- [ ] **Step 2: Contrôle visuel de bout en bout**

`uv run run.py`, compte abonné : basculer clair → sombre → clair depuis le menu, sur `/observatoire` (vérifier que les graphiques changent bien après rechargement, donc que le cache distingue les thèmes), `/tableau` en mode observatoire, une fiche titulaire (carte), `/etapes` (desktop et largeur mobile). Compte non abonné : aucun switch, thème clair même si une préférence sombre existe en base.
