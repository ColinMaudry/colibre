# Personnalisation de l'affichage de l'observatoire (drag & drop des tuiles)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux abonné·es connecté·es de réordonner les tuiles (cards) de l'observatoire par drag & drop HTML5 natif, avec persistance de l'ordre en SQLite. Fonctionnalité disponible sur `/observatoire` et le mode observatoire de `/tableau`. Désactivé sur interfaces tactiles et petits écrans.

**Architecture:** L'ordre des cards est stocké par utilisateur dans une table SQLite `observatoire_card_order`. Chaque card reçoit un `card_id` stable dans `build_dashboard_cards`. Le drag & drop est géré côté client par un asset JS qui réordonne les nœuds DOM et met à jour un `dcc.Store`. Un callback serveur persiste l'ordre en base. Au rendu, `reorder_cards` réordonne les cards déjà construites selon l'ordre stocké — ceci APRÈS le cache mémoïsé, pour éviter l'explosion de cardinalité du cache.

**Tech Stack:** Dash 4.4, Dash Bootstrap Components, HTML5 Drag & Drop API, SQLite (via `src.auth.db.get_conn`), clientside JS (asset statique dans `src/assets/`).

**Spec:** Issue #107 — « Permettre de ranger les tuiles dans un certain ordre grâce à un système de drag & drop. L'ordre par défaut est l'ordre actuel. L'ordre choisi par l'utilisateur est stocké dans une table dédiée de la base de données. Cette table apparaît dans l'interface d'administration de colibre. »

## Global Constraints

- **UI en français** — tous les textes visibles par l'utilisateur sont en français.
- **Imports** — toujours importer depuis `src.` (ex. `from src.figures import ...`), jamais `from figures import ...`.
- **Tests** — `uv run pytest` ; les tests Selenium nécessitent Chrome/Chromium headless.
- **Pre-commit** — exécuter `pre-commit` (ruff format) avant tout `git add`.
- **Pas de nouvelles dépendances externes** — HTML5 DnD natif uniquement, pas de `dash-draggable`.
- **Gating** — `current_user_has_subscription()` contrôle l'accès ; les anonymes/non-abonnés voient l'ordre par défaut sans drag.
- **Table auto-découverte admin** — `all_tables()` dans `src/admin/tables.py` découvre les tables SQLite automatiquement ; la nouvelle table apparaîtra dans l'admin sans modification de code.
- **Cache** — `_compute_dashboard_children` et `_cards_pour_filtre` sont mémoïsés ; l'ordre doit être appliqué APRÈS le cache, pas dans la fonction cachée.

## Cartes et card_ids stables

Les cards produites par `build_dashboard_cards` (`src/figures.py:1403`) sont, dans l'ordre par défaut :

| card_id           | Title actuel                    | Source                             |
| ----------------- | ------------------------------- | ---------------------------------- |
| `resume`          | Résumé                          | `get_dashboard_summary_table`      |
| `cat-acheteur`    | Catégorie d'acheteur            | `make_donut` (acheteur_categorie)  |
| `cat-entreprise`  | Catégorie d'entreprise          | `make_donut` (titulaire_categorie) |
| `type-achat`      | Type d'achat                    | `make_donut` (type)                |
| `considerations`  | Considérations sociales et env. | `get_considerations_card_content`  |
| `distance`        | Distance acheteur–titulaire     | `get_distance_histogram`           |
| `top-acheteurs`   | Top acheteurs                   | `get_top_org_table` (acheteur)     |
| `top-titulaires`  | Top titulaires                  | `get_top_org_table` (titulaire)    |
| `sources-donnees` | Sources de données              | `get_barchart_sources`             |

Les cartes géographiques (`get_geographic_maps`, `src/figures.py:388`) sont dynamiques : 0 à 6 cartes selon les données (Hexagone + DOM-TOM). Elles sont insérées entre `top-titulaires` et `sources-donnees` par `build_dashboard_cards` (ligne 1502 : `return cards + geographic_maps + other_cards`). Elles reçoivent des card_ids de la forme `carte-<code>` (ex. `carte-Hexagone`, `carte-971`).

---

## File Structure

| File                                                      | Responsibility                                                                                                                 |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `src/migrations.py`                                       | Migration `0015_create_observatoire_card_order`                                                                                |
| `src/observatoire_order.py` (créer)                       | Couche de persistance : `get_card_order`, `save_card_order`                                                                    |
| `src/figures.py`                                          | `make_card` accepte `card_id` ; `build_dashboard_cards` assigne les card_ids ; `reorder_cards` réordonne les cards construites |
| `src/assets/js/observatoire-dragdrop.js` (créer)          | Logique drag & drop côté client                                                                                                |
| `src/assets/css/style.css`                                | Styles drag & drop                                                                                                             |
| `src/pages/observatoire.py`                               | `dcc.Store`, callbacks de persistance/chargement, `reorder_cards`                                                              |
| `src/pages/tableau.py`                                    | `dcc.Store`, callbacks de persistance/chargement, `reorder_cards`                                                              |
| `tests/test_migrations.py` (créer/étendre)                | Test de la migration                                                                                                           |
| `tests/test_observatoire_order.py` (créer)                | Tests de la couche de persistance                                                                                              |
| `tests/test_figures.py` (étendre)                         | Tests de `card_id` et `reorder_cards`                                                                                          |
| `tests/test_observatoire_dragdrop_integration.py` (créer) | Tests d'intégration + admin                                                                                                    |

---

## Task 1: Migration SQLite pour la table `observatoire_card_order`

**Files:**

- Modify: `src/migrations.py:89` (ajouter après la migration 0014, à la fin de `_MIGRATIONS`)
- Test: `tests/test_migrations.py` (créer)

**Interfaces:**

- Produces: table SQLite `observatoire_card_order(user_id INTEGER PRIMARY KEY, card_order TEXT NOT NULL, updated_at TEXT NOT NULL)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrations.py
"""Test que la migration 0015 crée la table observatoire_card_order."""

import sqlite3


def test_migration_0015_creates_observatoire_card_order(users_db_path):
    from src.migrations import apply_pending

    apply_pending()

    conn = sqlite3.connect(str(users_db_path))
    conn.row_factory = sqlite3.Row
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "observatoire_card_order" in tables

    cols = [row[1] for row in conn.execute("PRAGMA table_info(observatoire_card_order)")]
    assert "user_id" in cols
    assert "card_order" in cols
    assert "updated_at" in cols
    conn.close()


def test_migration_0015_is_idempotent(users_db_path):
    from src.migrations import apply_pending

    apply_pending()
    apply_pending()  # ne doit pas lever d'erreur
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: FAIL — `observatoire_card_order` n'existe pas encore.

- [ ] **Step 3: Add the migration**

```python
# src/migrations.py — ajouter à la fin de _MIGRATIONS, après 0014
    (
        "0015_create_observatoire_card_order",
        "CREATE TABLE IF NOT EXISTS observatoire_card_order ("
        "user_id INTEGER PRIMARY KEY, "
        "card_order TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/migrations.py tests/test_migrations.py
git add src/migrations.py tests/test_migrations.py
git commit -m "feat: migration 0015 — table observatoire_card_order (issue #107)"
```

---

## Task 2: Couche de persistance `observatoire_order.py`

**Files:**

- Create: `src/observatoire_order.py`
- Test: `tests/test_observatoire_order.py` (créer)

**Interfaces:**

- Consumes: `src.auth.db.get_conn` (connexion SQLite)
- Produces:

  - `get_card_order(user_id: int) -> list[str] | None`
  - `save_card_order(user_id: int, order: list[str]) -> None`
  - `DEFAULT_CARD_ORDER: list[str]` — l'ordre par défaut des card_ids fixes

- [ ] **Step 1: Write the failing test**

```python
# tests/test_observatoire_order.py
"""Tests de la couche de persistance de l'ordre des cards."""


def test_get_card_order_returns_none_for_new_user(users_db_path):
    from src.observatoire_order import get_card_order

    assert get_card_order(999) is None


def test_save_and_get_card_order(users_db_path):
    from src.observatoire_order import get_card_order, save_card_order

    order = ["resume", "top-acheteurs", "cat-acheteur"]
    save_card_order(42, order)

    result = get_card_order(42)
    assert result == order


def test_save_card_order_upserts(users_db_path):
    from src.observatoire_order import get_card_order, save_card_order

    save_card_order(1, ["resume", "top-acheteurs"])
    save_card_order(1, ["top-acheteurs", "resume"])

    assert get_card_order(1) == ["top-acheteurs", "resume"]


def test_default_card_order_is_complete():
    """DEFAULT_CARD_ORDER contient tous les card_ids fixes (hors cartes géo)."""
    from src.observatoire_order import DEFAULT_CARD_ORDER

    expected = [
        "resume",
        "cat-acheteur",
        "cat-entreprise",
        "type-achat",
        "considerations",
        "distance",
        "top-acheteurs",
        "top-titulaires",
        "sources-donnees",
    ]
    assert DEFAULT_CARD_ORDER == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observatoire_order.py -v`
Expected: FAIL — `src.observatoire_order` n'existe pas.

- [ ] **Step 3: Create the module**

```python
# src/observatoire_order.py
"""Persistance de l'ordre des cards de l'observatoire par utilisateur."""

import json
from datetime import datetime, timezone

from src.auth.db import get_conn

DEFAULT_CARD_ORDER = [
    "resume",
    "cat-acheteur",
    "cat-entreprise",
    "type-achat",
    "considerations",
    "distance",
    "top-acheteurs",
    "top-titulaires",
    "sources-donnees",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_card_order(user_id: int) -> list[str] | None:
    row = get_conn().execute(
        "SELECT card_order FROM observatoire_card_order WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def save_card_order(user_id: int, order: list[str]) -> None:
    get_conn().execute(
        "INSERT INTO observatoire_card_order (user_id, card_order, updated_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET card_order = ?, updated_at = ?",
        (user_id, json.dumps(order), _now(), json.dumps(order), _now()),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_observatoire_order.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/observatoire_order.py tests/test_observatoire_order.py
git add src/observatoire_order.py tests/test_observatoire_order.py
git commit -m "feat: couche de persistance observatoire_card_order (issue #107)"
```

---

## Task 3: `make_card` et `build_dashboard_cards` avec card_ids + `reorder_cards`

**Files:**

- Modify: `src/figures.py` — `make_card` (~ligne 931), `build_dashboard_cards` (~ligne 1403), `get_geographic_maps` (~ligne 388)
- Test: `tests/test_figures.py` (étendre)

**Interfaces:**

- Produces:

  - `make_card(title, subtitle=None, fig=None, paragraphs=None, lg=6, xl=4, card_id=None) -> dbc.Col` — pose `id={"type": "observatoire-card", "index": card_id}` et `data-card-id` sur le `dbc.Col` si `card_id` est fourni.
  - `build_dashboard_cards(dff, order=None) -> list` — assigne un `card_id` à chaque card ; si `order` est fourni, réordonne.
  - `reorder_cards(cards: list, order: list[str]) -> list` — réordonne des cards déjà construites selon leurs `card_id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_figures.py — ajouter à la fin du fichier


def test_build_dashboard_cards_assigns_card_ids():
    """Chaque card fixe reçoit un card_id via le pattern-matching index."""
    from src.figures import build_dashboard_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    cards = build_dashboard_cards(_frame(observatoire_cards_columns()))

    card_ids = []
    for card in cards:
        cid = getattr(card, "id", None)
        if isinstance(cid, dict) and cid.get("type") == "observatoire-card":
            card_ids.append(cid["index"])

    for expected_id in (
        "resume",
        "cat-acheteur",
        "cat-entreprise",
        "type-achat",
        "considerations",
        "top-acheteurs",
        "top-titulaires",
        "sources-donnees",
    ):
        assert expected_id in card_ids, f"card_id manquant : {expected_id}"


def test_build_dashboard_cards_with_order_reorders_cards():
    """L'ordre passé en paramètre contrôle l'ordre des cards retournées."""
    from src.figures import build_dashboard_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    dff = _frame(observatoire_cards_columns())
    order = ["top-acheteurs", "resume", "cat-acheteur"]
    cards = build_dashboard_cards(dff, order=order)

    card_ids = [
        card.id["index"]
        for card in cards
        if isinstance(getattr(card, "id", None), dict)
        and card.id.get("type") == "observatoire-card"
    ]

    assert card_ids[:3] == order


def test_build_dashboard_cards_order_none_keeps_default_order():
    """Sans order, l'ordre par défaut est conservé."""
    from src.figures import build_dashboard_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    dff = _frame(observatoire_cards_columns())
    cards_default = build_dashboard_cards(dff)
    cards_none = build_dashboard_cards(dff, order=None)

    ids_default = [c.id["index"] for c in cards_default if isinstance(getattr(c, "id", None), dict)]
    ids_none = [c.id["index"] for c in cards_none if isinstance(getattr(c, "id", None), dict)]

    assert ids_default == ids_none


def test_build_dashboard_cards_unknown_card_ids_in_order_ignored():
    """Les card_ids dans order qui n'existent pas sont ignorés sans erreur."""
    from src.figures import build_dashboard_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    dff = _frame(observatoire_cards_columns())
    cards = build_dashboard_cards(dff, order=["inexistant", "resume"])

    card_ids = [
        c.id["index"]
        for c in cards
        if isinstance(getattr(c, "id", None), dict)
        and c.id.get("type") == "observatoire-card"
    ]
    assert "resume" in card_ids
    assert "inexistant" not in card_ids


def test_reorder_cards_reorders_built_cards():
    """reorder_cards réordonne des cards déjà construites."""
    from src.figures import build_dashboard_cards, reorder_cards, observatoire_cards_columns
    from tests.test_observatoire_cards_columns import _frame

    dff = _frame(observatoire_cards_columns())
    cards = build_dashboard_cards(dff)

    # Extraire l'ordre original
    original_ids = [
        c.id["index"] for c in cards
        if isinstance(getattr(c, "id", None), dict)
        and c.id.get("type") == "observatoire-card"
    ]

    # Inverser l'ordre
    reversed_order = list(reversed(original_ids))
    reordered = reorder_cards(cards, reversed_order)

    reordered_ids = [
        c.id["index"] for c in reordered
        if isinstance(getattr(c, "id", None), dict)
        and c.id.get("type") == "observatoire-card"
    ]

    assert reordered_ids == reversed_order
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_figures.py -v -k "card_id or reorder or default_order or unknown_card"`
Expected: FAIL

- [ ] **Step 3: Modify `make_card` to accept `card_id`**

```python
# src/figures.py — modifier make_card (~ligne 931)

def make_card(
    title: str, subtitle=None, fig=None, paragraphs=None, lg=6, xl=4, card_id=None
) -> dbc.Col:
    children = []
    if title:
        children.append(html.H5(title, className="card-title"))
    if subtitle:
        children.append(html.H6(subtitle, className="card-subtitle mb-2 text-muted"))
    if fig is not None:
        children.append(fig)
    if paragraphs:
        for p in paragraphs:
            p.className = "card-text"
            children.append(p)

    col_kwargs = {}
    if card_id is not None:
        col_kwargs["id"] = {"type": "observatoire-card", "index": card_id}
        col_kwargs["data-card-id"] = card_id

    card = dbc.Col(
        html.Div(html.Div(className="card-body", children=children), className="card"),
        lg=lg,
        xl=xl,
        **col_kwargs,
    )
    return card
```

- [ ] **Step 4: Modify `build_dashboard_cards` to assign card_ids and accept `order`**

```python
# src/figures.py — remplacer build_dashboard_cards (~ligne 1403)

def build_dashboard_cards(dff: pl.DataFrame, order: list[str] | None = None) -> list:
    """Cards de l'observatoire pour un jeu de marchés déjà filtré.

    Paramètres
    ----------
    dff : DataFrame contenant les colonnes listées dans OBSERVATOIRE_CARDS_COLUMNS.
    order : liste de card_ids dans l'ordre souhaité par l'utilisateur.
            Les card_ids inconnus sont ignorés. Les cards dont le card_id
            n'est pas dans ``order`` sont placées à la fin, dans l'ordre
            par défaut.
    """
    lff = dff.lazy()

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )
    nb_marches = df_per_uid.height

    # Chaque card est un tuple (card_id, dbc.Col)
    cards_with_ids: list[tuple[str | None, dbc.Col]] = []

    card_summary_table = get_dashboard_summary_table(dff, df_per_uid, nb_marches)
    cards_with_ids.append((
        "resume",
        make_card(title="Résumé", paragraphs=card_summary_table, card_id="resume"),
    ))

    donut_acheteur_categorie, nb_acheteur_categories = make_donut(
        lff,
        "acheteur_categorie",
        nulls="Autres",
        per_uid=True,
        potentially_many_names=True,
    )
    cards_with_ids.append((
        "cat-acheteur",
        make_card(
            title="Catégorie d'acheteur",
            subtitle="en nombre de marchés attribués",
            fig=donut_acheteur_categorie,
            lg=12 if nb_acheteur_categorie > 4 else 6,
            xl=8 if nb_acheteur_categorie > 4 else 4,
            card_id="cat-acheteur",
        ),
    ))

    donut_titulaire_categorie = make_donut(
        lff, "titulaire_categorie", per_uid=False, nulls="?"
    )
    cards_with_ids.append((
        "cat-entreprise",
        make_card(
            title="Catégorie d'entreprise",
            subtitle="en nombre de titulaires",
            fig=donut_titulaire_categorie,
            card_id="cat-entreprise",
        ),
    ))

    donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?")
    cards_with_ids.append((
        "type-achat",
        make_card(
            title="Type d'achat",
            subtitle="en nombre de marchés attribués",
            fig=donut_marche_type,
            card_id="type-achat",
        ),
    ))

    considerations_content = get_considerations_card_content(lff)
    cards_with_ids.append((
        "considerations",
        make_card(
            title="Considérations sociales et environnementales",
            subtitle="part des marchés concernés",
            fig=considerations_content,
            card_id="considerations",
        ),
    ))

    distance_histogram = get_distance_histogram(lff)
    cards_with_ids.append((
        "distance",
        make_card(
            title="Distance acheteur–titulaire",
            subtitle="en nombre de marchés, échelle logarithmique",
            fig=distance_histogram,
            card_id="distance",
        ),
    ))

    top_acheteurs = get_top_org_table(
        lff, org_type="acheteur", filters=False, extra_columns=[]
    )
    cards_with_ids.append((
        "top-acheteurs",
        make_card(title="Top acheteurs", fig=top_acheteurs, lg=12, xl=8, card_id="top-acheteurs"),
    ))

    top_titulaires = get_top_org_table(
        lff, org_type="titulaire", filters=False, extra_columns=[]
    )
    cards_with_ids.append((
        "top-titulaires",
        make_card(title="Top titulaires", fig=top_titulaires, lg=12, xl=8, card_id="top-titulaires"),
    ))

    geographic_maps: list[dbc.Col] | None = get_geographic_maps(dff)
    if geographic_maps:
        for col in geographic_maps:
            card_id = col.id["index"] if isinstance(getattr(col, "id", None), dict) else None
            cards_with_ids.append((card_id, col))

    sources_barchart = get_barchart_sources(lff, type_date="dateNotification")
    cards_with_ids.append((
        "sources-donnees",
        make_card(
            title="Sources de données",
            subtitle="Nombre de marchés attribués par mois de notification et source de données",
            fig=sources_barchart,
            lg=12,
            xl=8,
            card_id="sources-donnees",
        ),
    ))

    if order is None:
        return [col for _id, col in cards_with_ids]

    order_index = {card_id: i for i, card_id in enumerate(order)}
    ordered = sorted(
        cards_with_ids,
        key=lambda pair: order_index.get(pair[0], len(order)),
    )
    return [col for _id, col in ordered]
```

- [ ] **Step 5: Modify `get_geographic_maps` to assign card_ids**

Dans `get_geographic_maps` (~ligne 388), modifier l'appel `make_card` dans la boucle `for code in regions.keys()` :

```python
        col = make_card(
            regions[code]["name"],
            fig=map_graph,
            lg=lg,
            xl=xl,
            card_id=f"carte-{code}",
        )
```

- [ ] **Step 6: Add `reorder_cards` function**

```python
# src/figures.py — ajouter après build_dashboard_cards

def reorder_cards(cards: list, order: list[str]) -> list:
    """Réordonne une liste de cards déjà construites selon les card_ids.

    Les cards sans card_id ou dont le card_id n'est pas dans ``order``
    restent à la fin, dans l'ordre original.
    """
    def get_card_id(card):
        cid = getattr(card, "id", None)
        if isinstance(cid, dict) and cid.get("type") == "observatoire-card":
            return cid["index"]
        return None

    cards_with_ids = [(get_card_id(c), c) for c in cards]
    order_index = {card_id: i for i, card_id in enumerate(order)}

    return [
        card
        for _id, card in sorted(
            cards_with_ids,
            key=lambda pair: order_index.get(pair[0], len(order)),
        )
    ]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_figures.py -v -k "card_id or reorder or default_order or unknown_card"`
Expected: PASS

Vérifier aussi les tests existants :
Run: `uv run pytest tests/test_figures.py tests/test_observatoire_cards_columns.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
pre-commit run --files src/figures.py tests/test_figures.py
git add src/figures.py tests/test_figures.py
git commit -m "feat: card_ids stables, paramètre order et reorder_cards (issue #107)"
```

---

## Task 4: Asset JavaScript pour le drag & drop

**Files:**

- Create: `src/assets/js/observatoire-dragdrop.js`

**Interfaces:**

- Consumes: éléments DOM avec `data-card-id` dans un conteneur `[data-observatoire-cards]`
- Produces: met à jour le `data` d'un `dcc.Store` Dash identifié par `data-card-order-store`

Le script :

1. Détecte si l'appareil est tactile (`pointer: coarse`) ou si l'écran est petit (< 768px) → ne fait rien.
2. Pour chaque conteneur `[data-observatoire-cards]`, pose `draggable=true` sur les enfants `[data-card-id]`.
3. Branche `dragstart`, `dragover`, `dragleave`, `drop`, `dragend`.
4. Au drop : réordonne les nœuds DOM, lit le nouvel ordre des `data-card-id`, et met à jour le `dcc.Store` via `dash_clientside`.

**Note sur la communication JS → Dash :** Dash 4.4 expose `window.dash_clientside` et permet de mettre à jour les props d'un composant via un `clientside_callback`. La méthode la plus fiable est d'utiliser un callback côté client qui écoute un événement DOM et met à jour le Store. Le JS dispatch un `CustomEvent("card-order-change")` sur le conteneur, et un `clientside_callback` dans le code Python l'écoute.

- [ ] **Step 1: Create the JS asset**

```javascript
// src/assets/js/observatoire-dragdrop.js
/* Drag & drop des cards de l'observatoire (issue #107).
 *
 * Réordonne visuellement les cards par drag & drop HTML5 natif, puis
 * synchronise l'ordre avec Dash via un CustomEvent. Désactivé sur
 * interfaces tactiles (pointer: coarse) et petits écrans (< 768px).
 */
(function () {
  "use strict";

  var MIN_WIDTH = 768;

  function isTouchOrSmall() {
    var coarse = window.matchMedia("(pointer: coarse)").matches;
    var narrow = window.innerWidth < MIN_WIDTH;
    return coarse || narrow;
  }

  function getOrderFromDom(container) {
    return Array.from(container.querySelectorAll("[data-card-id]")).map(
      function (el) {
        return el.getAttribute("data-card-id");
      }
    );
  }

  function applyDragHandlers(container) {
    if (isTouchOrSmall()) return;
    if (container.dataset.dragEnabled === "true") return;
    container.dataset.dragEnabled = "true";

    var dragSrc = null;

    container.querySelectorAll("[data-card-id]").forEach(function (card) {
      card.draggable = true;
      card.classList.add("observatoire-card-draggable");
    });

    container.addEventListener("dragstart", function (e) {
      var card = e.target.closest("[data-card-id]");
      if (!card) return;
      dragSrc = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", card.getAttribute("data-card-id"));
    });

    container.addEventListener("dragend", function (e) {
      var card = e.target.closest("[data-card-id]");
      if (!card) return;
      card.classList.remove("dragging");
      container.querySelectorAll(".drag-over").forEach(function (el) {
        el.classList.remove("drag-over");
      });
      dragSrc = null;
    });

    container.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      var target = e.target.closest("[data-card-id]");
      if (!target || target === dragSrc) return;
      target.classList.add("drag-over");
    });

    container.addEventListener("dragleave", function (e) {
      var target = e.target.closest("[data-card-id]");
      if (target) target.classList.remove("drag-over");
    });

    container.addEventListener("drop", function (e) {
      e.preventDefault();
      var target = e.target.closest("[data-card-id]");
      if (!target || !dragSrc || target === dragSrc) return;

      var cards = Array.from(container.children);
      var srcIdx = cards.indexOf(dragSrc);
      var tgtIdx = cards.indexOf(target);
      if (srcIdx < tgtIdx) {
        container.insertBefore(dragSrc, target.nextSibling);
      } else {
        container.insertBefore(dragSrc, target);
      }

      var order = getOrderFromDom(container);
      container.dispatchEvent(
        new CustomEvent("card-order-change", {
          bubbles: true,
          detail: { order: order },
        })
      );
    });
  }

  function init() {
    document
      .querySelectorAll("[data-observatoire-cards]")
      .forEach(applyDragHandlers);
  }

  var observer = new MutationObserver(function () {
    init();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: Commit**

```bash
pre-commit run --files src/assets/js/observatoire-dragdrop.js
git add src/assets/js/observatoire-dragdrop.js
git commit -m "feat: asset JS drag & drop des cards de l'observatoire (issue #107)"
```

---

## Task 5: Styles CSS pour le drag & drop

**Files:**

- Modify: `src/assets/css/style.css` (ajouter à la fin du fichier)

- [ ] **Step 1: Add CSS styles**

```css
/* --- Drag & drop des cards de l'observatoire (#107) --- */

.observatoire-card-draggable {
  cursor: grab;
}

.observatoire-card-draggable:active {
  cursor: grabbing;
}

.observatoire-card-draggable.dragging {
  opacity: 0.4;
}

.observatoire-card-draggable.drag-over {
  border: 2px dashed #007bff;
  border-radius: 4px;
}

@media (pointer: coarse) {
  .observatoire-card-draggable {
    cursor: default;
  }
}
```

- [ ] **Step 2: Commit**

```bash
pre-commit run --files src/assets/css/style.css
git add src/assets/css/style.css
git commit -m "feat: styles CSS drag & drop des cards (issue #107)"
```

---

## Task 6: Intégration dans la page `/observatoire`

**Files:**

- Modify: `src/pages/observatoire.py`

**Interfaces:**

- Consumes: `get_card_order`, `save_card_order` from `src.observatoire_order` ; `current_user_has_subscription` from `src.pages._compte_shell` ; `reorder_cards` from `src.figures`
- Produces:

  - `dcc.Store(id="observatoire-card-order")` dans le layout
  - Conteneur `#cards` avec attributs `data-observatoire-cards` et `data-card-order-store="observatoire-card-order"`
  - `clientside_callback` qui écoute `card-order-change` et met à jour le Store
  - Callback `persist_card_order` qui persiste l'ordre en base
  - Callback `load_card_order` qui charge l'ordre au rendu
  - `update_dashboard_cards` applique `reorder_cards` après le cache

- [ ] **Step 1: Add `dcc.Store` and data attributes to layout**

Ajouter le Store après les autres Stores (~ligne 36) :

```python
    dcc.Store(id="observatoire-card-order"),
```

Modifier le conteneur `#cards` (~ligne 428) — remplacer :

```python
                            dbc.Col(
                                width=12,
                                lg=8,
                                xl=9,
                                id="cards",
                                children=[],
                            ),
```

Par :

```python
                            dbc.Col(
                                width=12,
                                lg=8,
                                xl=9,
                                id="cards",
                                children=[],
                                **{
                                    "data-observatoire-cards": "",
                                    "data-card-order-store": "observatoire-card-order",
                                },
                            ),
```

- [ ] **Step 2: Modify `update_dashboard_cards` to apply order after cache**

Remplacer le callback `update_dashboard_cards` (~ligne 664) :

```python
@callback(
    Output("cards", "children"),
    Output("observatoire-filters", "data"),
    Input("observatoire-card-order", "data"),
    *[Input(fp[0], "value") for fp in FILTER_PARAMS],
)
def update_dashboard_cards(card_order, *filter_values):
    filter_params = {}
    for (input_id, _url_key, _is_multi, _default), value in zip(
        FILTER_PARAMS, filter_values
    ):
        filter_params[input_id] = value

    filter_params_normalized = _normalize_filter_params(filter_params)
    children = _compute_dashboard_children(filter_params_normalized)

    if card_order:
        children = reorder_cards(children, card_order)

    return dbc.Row(children=children, **{
        "data-observatoire-cards": "",
        "data-card-order-store": "observatoire-card-order",
    }), filter_params
```

Ajouter l'import en haut du fichier :

```python
from src.figures import (
    DataTable,
    build_dashboard_cards,
    make_column_picker,
    montant_modal,
    observatoire_cards_columns,
    reorder_cards,
)
```

- [ ] **Step 3: Add clientside_callback to sync JS → Store**

```python
# src/pages/observatoire.py — ajouter après les imports

from dash import clientside_callback

clientside_callback(
    """
    function(_, detail) {
        if (detail && detail.order) {
            return detail.order;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("observatoire-card-order", "data"),
    Input("cards", "n_clicks"),
    Input({"type": "observatoire-card", "index": ALL}, "n_clicks"),
)
```

Note : `clientside_callback` ne peut pas écouter un `CustomEvent` directement. Alternative : utiliser un élément caché qui reçoit l'événement. Ou plus simple : utiliser un callback serveur normal avec un `State` sur le conteneur et un trigger artificiel.

Révision : la méthode la plus fiable avec Dash 4.4 est d'utiliser un hidden div qui sert de récepteur d'événement :

```python
# Layout : ajouter un div caché qui intercepte le card-order-change
    html.Div(id="observatoire-card-order-trigger", style={"display": "none"}),
```

Et un callback serveur qui écoute cet élément. Mais le CustomEvent n'est pas capturable par Dash.

Méthode retenue : le JS met à jour directement le Store via l'API Dash callbacks. Dash 4.4 permet de déclencher une mise à jour de prop via `dashjs.callback_api` ou en assignant `component-props` via un pattern. La méthode la plus simple et fiable : le JS écrit l'ordre dans un input caché dont la valeur est lue par un callback.

```python
# Layout : ajouter un input caché
    dcc.Input(id="observatoire-card-order-input", type="hidden", style={"display": "none"}),
```

Le JS écrit dans cet input via `document.getElementById("observatoire-card-order-input").value = JSON.stringify(order)` et déclenche un event `input`.

Le callback écoute cet input :

```python
@callback(
    Output("observatoire-card-order", "data"),
    Input("observatoire-card-order-input", "value"),
    prevent_initial_call=True,
)
def sync_card_order_from_input(value):
    if not value:
        return no_update
    import json
    return json.loads(value)
```

Et le JS `observatoire-dragdrop.js` modifie la fin du handler `drop` :

```javascript
var order = getOrderFromDom(container);
var input = document.getElementById("observatoire-card-order-input");
if (input) {
  input.value = JSON.stringify(order);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
```

- [ ] **Step 4: Add load and persist callbacks**

```python
# src/pages/observatoire.py — ajouter

@callback(
    Output("observatoire-card-order", "data", allow_duplicate=True),
    Input("dashboard_url", "pathname"),
    prevent_initial_call=False,
)
def load_card_order(_pathname):
    """Charge l'ordre des cards depuis la base au chargement de la page."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return None
    from src.pages._compte_shell import current_user_has_subscription
    if not current_user_has_subscription():
        return None
    from src.observatoire_order import get_card_order
    return get_card_order(current_user.id)


@callback(
    Output("observatoire-card-order", "data", allow_duplicate=True),
    Input("observatoire-card-order", "data"),
    State("dashboard_url", "pathname"),
    prevent_initial_call=True,
)
def persist_card_order(card_order, _pathname):
    """Persiste l'ordre des cards en base pour l'utilisateur connecté."""
    if not card_order:
        return no_update
    from flask_login import current_user
    if not current_user.is_authenticated:
        return no_update
    from src.pages._compte_shell import current_user_has_subscription
    if not current_user_has_subscription():
        return no_update
    from src.observatoire_order import save_card_order
    save_card_order(current_user.id, card_order)
    return no_update
```

- [ ] **Step 5: Run existing tests to check for regressions**

Run: `uv run pytest tests/test_observatoire_cards_columns.py tests/test_observatoire_button.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/pages/observatoire.py src/assets/js/observatoire-dragdrop.js
git add src/pages/observatoire.py src/assets/js/observatoire-dragdrop.js
git commit -m "feat: intégration drag & drop dans /observatoire (issue #107)"
```

---

## Task 7: Intégration dans la page `/tableau` (mode observatoire)

**Files:**

- Modify: `src/pages/tableau.py`

**Interfaces:**

- Consumes: mêmes fonctions que Task 6
- Produces:

  - `dcc.Store(id="tableau-card-order")` dans le layout
  - `dcc.Input(id="tableau-card-order-input", type="hidden")` dans le layout
  - Conteneur `#tableau-observatoire-cards` avec attributs `data-observatoire-cards` et `data-card-order-store`
  - `update_mode_observatoire_cards` applique `reorder_cards` après `_cards_pour_filtre`
  - Callbacks de chargement et persistance identiques à Task 6

- [ ] **Step 1: Add `dcc.Store` and hidden input to the layout**

Ajouter près des autres Stores du tableau :

```python
    dcc.Store(id="tableau-card-order"),
    dcc.Input(id="tableau-card-order-input", type="hidden", style={"display": "none"}),
```

- [ ] **Step 2: Add data attributes to the cards container**

Modifier le conteneur `#tableau-observatoire-cards` (~ligne 569) :

```python
                    html.Div(
                        id="tableau-observatoire-cards",
                        className="mode-observatoire-cards d-none",
                        **{
                            "data-observatoire-cards": "",
                            "data-card-order-store": "tableau-card-order",
                        },
                    ),
```

- [ ] **Step 3: Modify `update_mode_observatoire_cards` to apply order**

Ajouter `Input("tableau-card-order", "data")` au callback (~ligne 1020) :

```python
@callback(
    Output("tableau-observatoire-cards", "children"),
    Output("tableau-observatoire-cards", "className"),
    Input("tableau-mode-observatoire", "value"),
    Input("tableau_grid", "filterModel"),
    Input("tableau-card-order", "data"),
    prevent_initial_call=True,
)
def update_mode_observatoire_cards(mode_actif, filter_model, card_order):
    if not mode_actif:
        return no_update, f"{MODE_OBSERVATOIRE_CLASSES} d-none"

    if not current_user_has_subscription():
        return (
            dbc.Alert(
                "Fonctionnalité accessible en vous abonnant.",
                color="secondary",
                className="w-100",
            ),
            MODE_OBSERVATOIRE_CLASSES,
        )

    if not filter_model:
        return (
            dbc.Alert(SANS_FILTRE, color="secondary", className="w-100"),
            MODE_OBSERVATOIRE_CLASSES,
        )

    track_search(json.dumps(filter_model), "tab observatoire")
    cards = _cards_pour_filtre(_normalize_filter_model(filter_model))

    if card_order:
        from src.figures import reorder_cards
        cards = reorder_cards(cards, card_order)

    return cards, MODE_OBSERVATOIRE_CLASSES
```

- [ ] **Step 4: Add load and persist callbacks**

```python
# src/pages/tableau.py — ajouter

@callback(
    Output("tableau-card-order", "data", allow_duplicate=True),
    Input("tableau_url", "pathname"),
    prevent_initial_call=False,
)
def load_tableau_card_order(_pathname):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return None
    from src.pages._compte_shell import current_user_has_subscription
    if not current_user_has_subscription():
        return None
    from src.observatoire_order import get_card_order
    return get_card_order(current_user.id)


@callback(
    Output("tableau-card-order", "data", allow_duplicate=True),
    Input("tableau-card-order", "data"),
    State("tableau_url", "pathname"),
    prevent_initial_call=True,
)
def persist_tableau_card_order(card_order, _pathname):
    if not card_order:
        return no_update
    from flask_login import current_user
    if not current_user.is_authenticated:
        return no_update
    from src.pages._compte_shell import current_user_has_subscription
    if not current_user_has_subscription():
        return no_update
    from src.observatoire_order import save_card_order
    save_card_order(current_user.id, card_order)
    return no_update
```

- [ ] **Step 5: Update JS to handle both containers**

Le JS `observatoire-dragdrop.js` utilise `data-card-order-store` pour trouver l'id du Store. Le input caché doit être nommé de manière cohérente. Modifier le handler `drop` dans le JS pour écrire dans le bon input :

```javascript
var order = getOrderFromDom(container);
var storeId = container.getAttribute("data-card-order-store");
var inputId = storeId ? storeId + "-input" : null;
var input = inputId ? document.getElementById(inputId) : null;
if (input) {
  input.value = JSON.stringify(order);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
```

Assurer que le input caché du Tableau a l'id `tableau-card-order-input`.

- [ ] **Step 6: Run existing tests to check for regressions**

Run: `uv run pytest tests/ -v -k "tableau" --ignore=tests/test_main.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
pre-commit run --files src/pages/tableau.py src/assets/js/observatoire-dragdrop.js
git add src/pages/tableau.py src/assets/js/observatoire-dragdrop.js
git commit -m "feat: intégration drag & drop dans le mode observatoire du Tableau (issue #107)"
```

---

## Task 8: Tests d'intégration et vérification admin

**Files:**

- Create: `tests/test_observatoire_dragdrop_integration.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_observatoire_dragdrop_integration.py
"""Tests d'intégration du drag & drop des cards de l'observatoire (issue #107)."""


def test_observatoire_card_order_in_admin_tables(users_db_path):
    """La table observatoire_card_order est auto-découverte par l'admin."""
    from src.admin.tables import all_tables
    from src.migrations import apply_pending

    apply_pending()

    tables = all_tables()
    assert "observatoire_card_order" in tables


def test_anonyme_cards_not_draggable(dash_duo):
    """Un utilisateur anonyme ne voit pas d'attribut draggable sur les cards."""
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get("http://localhost:8050/observatoire")

    dash_duo.wait_for_element("#cards", timeout=10)
    dash_duo.wait_for_element("[data-card-id]", timeout=10)

    cards = dash_duo.find_elements("[data-card-id]")
    assert len(cards) > 0

    for card in cards:
        draggable = card.get_attribute("draggable")
        assert not draggable or draggable == "false"
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_observatoire_dragdrop_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
pre-commit run --files tests/test_observatoire_dragdrop_integration.py
git add tests/test_observatoire_dragdrop_integration.py
git commit -m "test: intégration drag & drop et visibilité admin (issue #107)"
```

---

## Self-Review

**1. Spec coverage:**

- ✅ Drag & drop pour réordonner les tuiles → Tasks 4-7
- ✅ Ordre par défaut = ordre actuel → `build_dashboard_cards(order=None)` conserve l'ordre ; `reorder_cards` non appelée si pas d'ordre stocké
- ✅ Ordre stocké dans une table dédiée → Task 1 (migration), Task 2 (persistance)
- ✅ Utilisé à chaque connexion → Task 6/7 (`load_card_order` au chargement)
- ✅ Table visible dans l'admin → Task 8 (auto-découverte vérifiée)
- ✅ Disponible sur `/observatoire` ET `/tableau` mode observatoire → Tasks 6-7
- ✅ Abonnés uniquement → gating via `current_user_has_subscription()` dans les callbacks ; le JS ne pose `draggable` que sur les conteneurs `[data-observatoire-cards]`, qui ne sont présents que dans le rendu serveur (le rendu ne change pas pour les non-abonnés, mais le JS ne pose pas draggable si l'élément n'a pas l'attribut `data-observatoire-cards`)

Note : le rendu serveur pose toujours `data-observatoire-cards` sur le conteneur, même pour les anonymes. Le JS pose donc `draggable` sur les cards même pour les anonymes. Pour respecter le gating, il faut soit :

- Ne pas poser `data-observatoire-cards` pour les non-abonnés (côté serveur)
- Ou vérifier le statut d'abonnement côté JS (peu fiable)

Correction : poser `data-observatoire-cards` uniquement si `current_user_has_subscription()` dans le callback `update_dashboard_cards`. Le conteneur rendu par le callback est un `dbc.Row` — c'est lui qui porte l'attribut. Si l'utilisateur n'est pas abonné, ne pas poser l'attribut.

Mais le conteneur `#cards` dans le layout statique a déjà `data-observatoire-cards`. C'est le children (le `dbc.Row`) qui est remplacé par le callback. Donc le conteneur parent garde l'attribut. Le JS cherche `[data-observatoire-cards]` — il trouvera le `#cards` parent, pas le `dbc.Row` enfant.

Solution : déplacer `data-observatoire-cards` du `#cards` statique vers le `dbc.Row` retourné par `update_dashboard_cards`. Ne le poser que si l'utilisateur est abonné. Le JS ne trouvera pas le conteneur pour les non-abonnés.

**2. Placeholder scan:**

- Le test Selenium pour utilisateur abonné n'est pas écrit car il nécessite une fixture d'auth Selenium qui n'existe pas encore. Le test anonyme est complet.
- La communication JS → Dash via input caché est explicite et complète.

**3. Type consistency:**

- `get_card_order(user_id: int) -> list[str] | None` — cohérent
- `save_card_order(user_id: int, order: list[str]) -> None` — cohérent
- `build_dashboard_cards(dff, order=None) -> list` — cohérent
- `reorder_cards(cards: list, order: list[str]) -> list` — cohérent
- `make_card(..., card_id=None) -> dbc.Col` — cohérent
