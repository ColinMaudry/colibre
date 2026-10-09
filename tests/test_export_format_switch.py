"""Bascule Excel → CSV des quatre exports au-delà de EXCEL_MAX_ROWS (#142).

Chaque callback d'export choisit `write_styled_excel` ou `write_csv` selon la
hauteur du DataFrame produit, et nomme le fichier avec l'extension
correspondante. Les sources de données et les fonctions d'écriture sont
monkeypatchées pour ne fabriquer ni 100 001 vraies lignes, ni écriture disque.

Pour `download_data` (/tableau), un filterModel non vide est fourni : depuis
le renvoi vers le CSV complet de data.gouv.fr (#142, passe de correction 2),
un filterModel vide fait sortir `download_data` en `no_update` avant même de
regarder le format — cf. tests/test_tableau_download_button.py pour ce cas.
"""

import pytest

from src.utils.frontend import EXCEL_MAX_ROWS

_UN_FILTRE = {"objet": {"filterType": "text", "type": "contains", "filter": "voirie"}}


pytestmark = pytest.mark.usefixtures("sans_abonnement")


class _FakeDF:
    """DataFrame minimal, avec une hauteur contrôlée."""

    def __init__(self, height):
        self.height = height

    def fill_null(self, _value):
        return self


def _fake_writers(captured):
    def fake_write_styled_excel(_df, buffer, **_kwargs):
        captured["used"] = "xlsx"
        buffer.write(b"xlsx-data")

    def fake_write_csv(_df, buffer):
        captured["used"] = "csv"
        buffer.write(b"csv-data")

    return fake_write_styled_excel, fake_write_csv


# --- /tableau : download_data -------------------------------------------


def test_download_data_uses_excel_under_threshold(monkeypatch):
    from src.pages import tableau
    from src.utils import grid as grid_module

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        grid_module, "export_dataframe", lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS)
    )
    monkeypatch.setattr(tableau, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(tableau, "write_csv", fake_csv)

    result = tableau.download_data(1, _UN_FILTRE, None)

    assert captured["used"] == "xlsx"
    assert result["filename"].endswith(".xlsx")


def test_download_data_uses_csv_above_threshold(monkeypatch):
    from src.pages import tableau
    from src.utils import grid as grid_module

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        grid_module,
        "export_dataframe",
        lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS + 1),
    )
    monkeypatch.setattr(tableau, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(tableau, "write_csv", fake_csv)

    result = tableau.download_data(1, _UN_FILTRE, None)

    assert captured["used"] == "csv"
    assert result["filename"].endswith(".csv")


# --- /acheteur : download_acheteur_data ----------------------------------


def test_download_acheteur_data_uses_excel_under_threshold(monkeypatch):
    from src.pages import acheteur

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        acheteur, "query_marches", lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS)
    )
    monkeypatch.setattr(acheteur, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(acheteur, "write_csv", fake_csv)

    result = acheteur.download_acheteur_data(1, "/acheteurs/123", "2025", "ACHETEUR 1")

    assert captured["used"] == "xlsx"
    assert result["filename"].endswith(".xlsx")


def test_download_acheteur_data_uses_csv_above_threshold(monkeypatch):
    from src.pages import acheteur

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        acheteur, "query_marches", lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS + 1)
    )
    monkeypatch.setattr(acheteur, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(acheteur, "write_csv", fake_csv)

    result = acheteur.download_acheteur_data(1, "/acheteurs/123", "2025", "ACHETEUR 1")

    assert captured["used"] == "csv"
    assert result["filename"].endswith(".csv")


# --- /titulaire : download_titulaire_data --------------------------------


def test_download_titulaire_data_uses_excel_under_threshold(monkeypatch):
    from src.pages import titulaire

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        titulaire, "query_marches", lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS)
    )
    monkeypatch.setattr(titulaire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(titulaire, "write_csv", fake_csv)

    result = titulaire.download_titulaire_data(
        1, "/titulaires/345", "2025", "TITULAIRE 1"
    )

    assert captured["used"] == "xlsx"
    assert result["filename"].endswith(".xlsx")


def test_download_titulaire_data_uses_csv_above_threshold(monkeypatch):
    from src.pages import titulaire

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        titulaire, "query_marches", lambda *a, **kw: _FakeDF(EXCEL_MAX_ROWS + 1)
    )
    monkeypatch.setattr(titulaire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(titulaire, "write_csv", fake_csv)

    result = titulaire.download_titulaire_data(
        1, "/titulaires/345", "2025", "TITULAIRE 1"
    )

    assert captured["used"] == "csv"
    assert result["filename"].endswith(".csv")


# --- /observatoire : download_observatoire --------------------------------


def test_download_observatoire_uses_excel_under_threshold(monkeypatch):
    from src.pages import observatoire

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        observatoire, "prepare_dashboard_data", lambda **kw: _FakeDF(EXCEL_MAX_ROWS)
    )
    monkeypatch.setattr(observatoire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(observatoire, "write_csv", fake_csv)

    result = observatoire.download_observatoire(1, {"dashboard_year": "2025"})

    assert captured["used"] == "xlsx"
    assert result["filename"].endswith(".xlsx")


def test_download_observatoire_uses_csv_above_threshold(monkeypatch):
    from src.pages import observatoire

    captured = {}
    fake_xlsx, fake_csv = _fake_writers(captured)

    monkeypatch.setattr(
        observatoire,
        "prepare_dashboard_data",
        lambda **kw: _FakeDF(EXCEL_MAX_ROWS + 1),
    )
    monkeypatch.setattr(observatoire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(observatoire, "write_csv", fake_csv)

    result = observatoire.download_observatoire(1, {"dashboard_year": "2025"})

    assert captured["used"] == "csv"
    assert result["filename"].endswith(".csv")
