# Mode sombre (#118) — design

## Objectif

Proposer aux abonné·es une interface sombre, basée sur le thème
[Earthsong](https://cmuxthemes.com/themes/earthsong/), activable par un switch
soleil / lune dans le menu « Mon compte ».

## Décisions

| Sujet       | Choix                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| Persistance | Préférence stockée par compte (SQLite), appliquée côté serveur ; basculer recharge la page              |
| Droits      | Réservé aux abonné·es (`current_user_has_subscription()`, essai et `TOUS_ABONNES` compris)              |
| Cartes      | Tuiles OSM inchangées, assombries par un filtre CSS sur le seul calque de tuiles (pas de nouveau tiers) |
| Périmètre   | Pages, alertes, AG Grid, composants dcc, graphiques Plotly, cartes Leaflet, frise de `etapes.py`        |

## Palette

Earthsong : fond `#292520`, noir `#121418`, gris `#675f54`, rouge `#c94234`,
vert `#85c54c`, jaune `#f5ae2e`, bleu `#1398b9`, magenta `#d0633d`, cyan
`#509552` ; variantes claires `#ff645a #98e036 #e0d561 #5fdaff #ff9269 #84f088`.

Spécifiques colibre (issue) :

- texte : `#e5c7a9`
- couleur primaire : `#e06c57` (remplace le terracotta `#b33821`)
- liens : `#eb8c82`

## 1. Stockage et droits — `src/theme.py`

- Migration `0016_create_user_preferences` :
  `user_preferences(user_id INTEGER PRIMARY KEY, theme TEXT NOT NULL DEFAULT 'clair', updated_at TEXT NOT NULL)`.
  Table dédiée plutôt qu'une colonne de `users`, que `src/auth/db.py` sait
  reconstruire.
- Constantes `CLAIR = "clair"`, `SOMBRE = "sombre"`.
- Les lignes sont créées paresseusement : uniquement au premier usage du
  switch (upsert), ni à l'abonnement ni par migration. Absence de ligne =
  `CLAIR`. Un retour en clair met la ligne à jour sans la supprimer.
- `get_theme(user_id) -> str` : préférence enregistrée, `CLAIR` par défaut.
- `save_theme(user_id, theme)` : upsert ; lève `ValueError` sur une valeur
  inconnue.
- `current_theme() -> str` : `SOMBRE` seulement si une requête Flask est en
  cours, l'utilisateur connecté, abonné (`current_user_has_subscription()`) et
  sa préférence est `SOMBRE`. Sinon `CLAIR`.

Les droits sont vérifiés à la lecture : à la fin de l'abonnement l'affichage
repasse en clair, la préférence est conservée pour un réabonnement.

## 2. Application côté serveur

- `_interpolate_index_per_request` (`src/app.py`) remplace `<html>` par
  `<html data-bs-theme="dark">` quand `current_theme() == SOMBRE`. Bootstrap
  5.3 (Simplex 5.3.6) bascule nativement ses composants ; pas de flash clair.
- Menu « Mon compte » (`_auth_nav`) : pour les abonné·es, un `dbc.Switch`
  (`id="theme-switch"`) encadré de ☀ et ☾, placé avant le séparateur, valeur
  initiale = préférence. Masqué pour les non-abonné·es (comme les sections
  réservées, #133).
- Callback serveur : `theme-switch.value` → `save_theme` (revérifie
  l'abonnement ; refuse sinon) → écrit dans un `dcc.Store` ; un callback
  clientside sur ce store recharge la page.

## 3. CSS — `src/assets/css/style.css`

Bloc `[data-bs-theme="dark"]` :

- variables Bootstrap `--bs-body-bg #292520`, `--bs-body-color #e5c7a9`,
  `--bs-link-color #eb8c82`, `--bs-emphasis-color`, `--bs-border-color`,
  `--bs-secondary-bg`, `--bs-tertiary-bg` (tons dérivés de `#292520`) ;
- variables colibre : `--primary-color`, `--primary-color-text`,
  `--btn-terracotta` → `#e06c57`, variables `--btn-secondary-*` ;
- composants dcc : `--Dash-*` (fonds, textes, bordures) ;
- AG Grid : `--ag-background-color`, `--ag-foreground-color`,
  `--ag-header-background-color`, `--ag-odd-row-background-color`,
  `--ag-border-color`, `--ag-row-hover-color` ;
- alertes : `.alert-warning` (jaune `#f5ae2e`), `.alert-info` (bleu
  `#1398b9`), `.alert-danger` (rouge `#c94234`) — fond sombre teinté, bordure
  de la couleur, texte clair ;
- surcharge des couleurs codées en dur de `style.css` (fond rosé du `body`,
  navbar `color="light"`, etc.), une à une ;
- cartes : `dl.TileLayer(className="tuiles")` et
  `[data-bs-theme="dark"] .tuiles { filter: invert(1) hue-rotate(180deg) brightness(.9) sepia(.25); }` ;
  boutons de zoom et attribution Leaflet sur fond `--earth-bg-2` / `--earth-bg`
  à 80 % ; marqueurs individuels (classe `org-point`) et pastilles de légende
  cerclés de blanc 1px. En mode cluster, dash-leaflet impose aux points un
  style par défaut `{weight: 1.5, color: "#222", opacity: 0.5}`, d'où une
  règle CSS (`stroke`, `stroke-opacity`, `stroke-width`) plutôt que les
  options du `circleMarker` ;
- composants dcc (Dash 4) : `--Dash-Fill-Inverse-Strong` est aussi le fond des
  `dcc.Input` et `dcc.Dropdown` (`#fff` par défaut), redéfinie en
  `--earth-bg-2` ;
- logo : beige Earthsong `#e5c7a9` (`--earth-fg`) ;
- drag & drop des cards de l'observatoire : plus d'opacité réduite sur la card
  déplacée. Déplacer une carte Leaflet déclenche un `dragstart` sur la card,
  que Leaflet annule ensuite : faute de `dragend`, la classe `dragging`
  restait posée et ternissait la card.

## 4. Graphiques Plotly — `src/figures.py`

- `PALETTE_SOMBRE` : `#c94234 #1398b9 #85c54c #f5ae2e #d0633d #509552 #e0d561 #5fdaff #ff9269 #84f088 #ff645a #98e036`.
- `ECHELLE_SOMBRE` (choroplèthe) : `#292520 → #e06c57`.
- `ORG_COLORS_SOMBRE` : jaune `#f5ae2e` et bleu `#1398b9` Earthsong assombris
  de 15 % par `_assombrir`, soit acheteur `#d09427`, titulaire `#10819d` ; couleurs
  des considérations sociales / environnementales et de la barre de
  progression neutre également déclinées.
- `appliquer_theme(fig, theme)` : en sombre, `paper_bgcolor`/`plot_bgcolor`
  `#292520`, police `#e5c7a9`, grille et axes `#675f54`, barre d'outils
  (`modebar`) sur fond transparent, icônes `#968c83` et `#e5c7a9` au survol ;
  sans effet en clair.
- Chaque fonction de figure reçoit `theme: str | None = None`, résolu par
  `current_theme()` si absent, et choisit palette / échelle en conséquence.
- Caches : `_compute_dashboard_children` (observatoire) et
  `_cards_pour_filtre` (tableau) prennent `theme` en paramètre (donc dans la
  clé) et le transmettent à `build_dashboard_cards`. Sans cela une figure
  sombre en cache serait servie à un visiteur en clair.

## 5. Frise des étapes — `src/pages/etapes.py`

Les couleurs codées en dur (`#7c5cff`, `#f79009`, `#1570ef`, `#0e9384`,
`#12b76a`) deviennent des variables CSS (`--etape-approch`, `--etape-jal`,
`--etape-boamp`, `--etape-joue`, `--etape-decp`) définies dans `:root` et
redéfinies en sombre. Aucune logique serveur.

## 6. Tests

- `tests/test_theme.py` : défaut `clair` ; `save`/`get` ; valeur inconnue
  refusée ; `current_theme()` = `clair` hors requête, non connecté, non abonné
  avec préférence sombre ; `sombre` pour un abonné qui l'a choisi.
- `tests/test_migrations.py` : table `user_preferences` créée.
- Index HTML : `data-bs-theme="dark"` présent / absent selon le cas.
- `tests/test_figures.py` : `appliquer_theme` ; une figure en sombre utilise
  `PALETTE_SOMBRE`, en clair la palette actuelle.
- Navbar : switch présent pour un abonné, absent sinon (`tests/test_nav_compte.py`).
- Cache : `_compute_dashboard_children` distingue les thèmes.
- `etapes.py` : plus aucune couleur hexadécimale en inline.

## Hors périmètre

- Suivre `prefers-color-scheme` du système (possible plus tard).
- Mode sombre pour les visiteurs non abonnés.
- Tuiles sombres dédiées (Protomaps auto-hébergé) si le filtre CSS déçoit.
