"""Garde-fou sur les colonnes dont les cards de l'observatoire ont besoin.

`build_dashboard_cards` est alimenté par une requête projetée sur
OBSERVATOIRE_CARDS_COLUMNS (au lieu d'un SELECT * sur les 63 colonnes du
schéma). Si une future card lit une colonne absente de cette liste, Polars
lèvera ColumnNotFoundError ici plutôt qu'en production.
"""

import datetime

import polars as pl
import pytest


def _frame(columns: list[str]) -> pl.DataFrame:
    """Deux marchés synthétiques, restreints aux colonnes demandées."""
    from src.utils.data import DATA_SCHEMA

    rows = []
    for i in (1, 2):
        row = {}
        for col in columns:
            field_type = DATA_SCHEMA[col]["type"]
            if col == "uid":
                row[col] = str(i)
            elif field_type in ("number", "integer"):
                row[col] = float(i * 10)
            elif field_type == "date":
                row[col] = datetime.date(2025, 1, i)
            elif field_type == "boolean":
                row[col] = False
            else:
                row[col] = f"{col}_{i}"
        rows.append(row)
    return pl.DataFrame(rows)


@pytest.mark.parametrize("liste", ["declarees", "projetees"])
def test_cards_se_construisent_avec_les_seules_colonnes_declarees(liste):
    """« declarees » : la liste complète, celle de la production.
    « projetees » : la liste réellement passée au SELECT, intersectée avec la
    table — en test elle perd latitude et longitude, absentes de test.parquet,
    et c'est ce jeu réduit qui alimente les cards."""
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.figures import (
        OBSERVATOIRE_CARDS_COLUMNS,
        build_dashboard_cards,
        observatoire_cards_columns,
    )

    colonnes = (
        OBSERVATOIRE_CARDS_COLUMNS
        if liste == "declarees"
        else observatoire_cards_columns()
    )

    cards = build_dashboard_cards(_frame(colonnes))

    assert cards, "aucune card produite"


def test_les_colonnes_declarees_existent_dans_le_schema_du_jeu_de_donnees():
    from src.figures import OBSERVATOIRE_CARDS_COLUMNS
    from src.utils.data import DATA_SCHEMA

    inconnues = [c for c in OBSERVATOIRE_CARDS_COLUMNS if c not in DATA_SCHEMA]

    assert inconnues == []


def test_projection_restreinte_aux_colonnes_presentes_dans_duckdb():
    """tests/test.parquet ne porte qu'un sous-ensemble du schéma (ni latitude ni
    longitude, par exemple). Projeter une colonne absente de la table ferait
    échouer le SELECT : la projection doit donc s'intersecter avec la table."""
    from src.db import schema
    from src.figures import observatoire_cards_columns

    projetees = observatoire_cards_columns()

    assert projetees, "projection vide"
    assert all(c in schema.names() for c in projetees)
    assert "uid" in projetees
    assert "acheteur_latitude" not in projetees  # absente de test.parquet


def test_observatoire_projette_les_colonnes_des_cards(monkeypatch):
    """Les cards de /observatoire sont alimentées par une requête projetée, pas
    par un SELECT * sur les 63 colonnes du schéma."""
    from src.app import app  # noqa: F401
    from src.pages import observatoire
    from src.theme import CLAIR
    from src.utils import data as data_module

    vues = {}

    def _espion(**filter_params):
        vues["columns"] = filter_params.pop("columns", None)
        return data_module.prepare_dashboard_data(**filter_params)

    monkeypatch.setattr(observatoire, "prepare_dashboard_data", _espion)

    observatoire._compute_dashboard_children.uncached(tuple(), CLAIR, False)

    from src.figures import observatoire_cards_columns

    assert vues["columns"] == observatoire_cards_columns()
