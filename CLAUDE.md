# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**colibre** is a French public procurement data explorer — a Dash (Python) web app for browsing, filtering, and visualizing _Données Essentielles de la Commande Publique_ (DECP). The UI is in French.

## Commands

### Setup

Environment variables:

```bash
cp .template.env .env   # then customize .env
```

### Development

```bash
uv run run.py         # starts Dash app
```

### Production

```bash
gunicorn run:server
```

### Tests

```bash
uv run pytest                  # run all tests (some are Selenium-based integration tests)
uv run pytest tests/test_main.py::test_001_logo_and_search   # run a single test
```

Tests require a running Chrome/Chromium browser. They use `DashComposite` from `dash[testing]` with Selenium WebDriver.

## Ajouts git

Avant d'ajouter des fichier dans git (`git add` ou `git commit -a`), exécute `pre-commit` pour que ruff formate les fichiers.

## Architecture

### Multi-page Dash app

- `src/app.py` — creates the Dash app instance, navbar, SEO endpoints (robots.txt, sitemap.xml), Matomo analytics
- `src/pages/*.py` — each page registers itself with `@register_page()` and o.wns its own layout and callbacks
- `run.py` — dev entry point; exports `server` (Flask) for gunicorn

### Module imports

- always import modules from the app starting with `src.` (e.g. `src.utils.`, `src.pages.recherche`, etc.), NOT `utils.cache` or `pages.observatoire`.

### Key pages

| Page              | URL             | Purpose                                |
| ----------------- | --------------- | -------------------------------------- |
| `recherche.py`    | `/`             | Search homepage for buyers/contractors |
| `acheteur.py`     | `/acheteur`     | Buyer detail with stats, charts, maps  |
| `titulaire.py`    | `/titulaire`    | Contractor detail                      |
| `tableau.py`      | `/tableau`      | Filterable data table with exports     |
| `marche.py`       | `/marche`       | Individual contract detail             |
| `observatoire.py` | `/observatoire` | An interactive analytics dashboard     |

### Data layer

- Data is stored as **Parquet** at rest, possibly in DuckDB, loaded in DuckDB, served from DuckDB for big queries and manipulated with **Polars** for the remaining steps
- Path set via `DATA_FILE_PARQUET_PATH` env var; tests use `tests/test.parquet`
- `src/util/*.py` — helpers shared by other modules, search (`search_org`), link generation, geographic data loading
- `src/callbacks.py` — shared Dash callbacks (e.g. `get_top_org_table`)
- `src/figures.py` — chart and map components (Plotly Express, Dash Leaflet with marker clustering)
- a Parquet file with production data is located at `../decp-processing/decp_prod.parquet` (~ 1,5 million records)
- the TableSchema of the dataset with the list of field and their definition is located at `../decp-processing/reference/base_schema.json`
- `tests/test.parquet` is very small and may not contain all possible columns, only those necessary for testing

### UI stack

- **Dash 4.4** + **Dash Bootstrap Components** for layout
- **Plotly Express** for charts
- **Dash Leaflet** + **Dash Extensions** for interactive maps with clustering
- Custom CSS in `src/assets/css/`

### Environment

- `DEVELOPMENT=true` enables debug logging and is set automatically during tests
- `DEVELOPMENT=true` désactive aussi tout le suivi Matomo (`tracking_enabled()`
  dans `src/utils/matomo.py`), pour que les instances de test n'alimentent pas
  le site de production
- `.env` file is required at runtime (copy from `template.env`)

### Migrations de schéma SQLite

Les migrations sont gérées dans `src/migrations.py` via une liste `_MIGRATIONS` de tuples `(id, sql)`. Elles sont appliquées automatiquement au démarrage de l'app (via `init_subscriptions`).

Pour ajouter une migration :

```python
# src/migrations.py
_MIGRATIONS = [
    ("0001_add_prix_ht_to_subscriptions", "ALTER TABLE subscriptions ADD COLUMN prix_ht REAL"),
    ("0002_ma_nouvelle_migration", "ALTER TABLE ... "),  # ajouter ici
]
```

- L'ID doit être unique et croissant (convention `NNNN_description`)
- Les migrations appliquées sont tracées dans la table `schema_migrations`
- `apply_pending()` est idempotent : sans effet si la migration est déjà enregistrée, et tolère le cas où la colonne existe déjà dans le schéma (DB fraîche)

Une migration peut aussi être une fonction Python `(conn) -> None` (réécriture de données) ; `apply_pending` l'exécute entre `BEGIN` et `COMMIT` avec son enregistrement. Elle doit tolérer une table absente (base fraîche : `init_schema` des modules tourne après).

### Deployment

- `main` branch → manual deploy to colibre.fr via GitHub Actions
- `dev` branch → auto-deploy to test.colibre.fr via GitHub Actions

#### Redirection decp.info → colibre.fr

Deux configurations nginx selon le serveur :

- nginx **standalone** : `deploy/nginx-colibre.conf` (vhost complet, à lier dans
  `sites-enabled`)
- **YunoHost** : `deploy/nginx-yunohost-decp-info.conf` (301) et
  `deploy/nginx-yunohost-test-decp-info.conf` (302), à déposer dans
  `/etc/nginx/conf.d/<domaine>.d/`

L'app YunoHost `redirect_ynh` n'est pas utilisable : son template code en dur
`return 302`, et le choix 301 n'existe que dans la PR amont #69, non fusionnée.

Sous YunoHost, aucune app ne doit occuper la racine `/` du domaine redirigé
(`yunohost app map`), sinon nginx échoue sur `duplicate location "/"`.

#### Sauvegarde de la base utilisateurs

`users.sqlite` est sauvegardée toutes les heures sur S3 par un timer systemd
(voir `deploy/colibre-backup.{service,timer}`). Installation initiale (une fois,
sur le serveur, en root) :

```bash
cp deploy/colibre-backup.service deploy/colibre-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now colibre-backup.timer
systemctl list-timers colibre-backup.timer # vérifier le prochain déclenchement
```

Restauration manuelle :

```bash
cd /var/www/colibre && source .venv/bin/activate
python -m src.backup list
systemctl stop colibre
python -m src.backup restore backups/users-YYYYMMDDTHHMMSSZ.sqlite.gz.enc
systemctl start colibre
```
