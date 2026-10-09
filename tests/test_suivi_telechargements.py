"""Suivi Matomo des téléchargements : format et nombre de lignes (#149)."""

import pytest
from dash import no_update

import src.app  # noqa: F401  (register_page des pages importées)
from src.utils.frontend import EXCEL_MAX_ROWS
from tests.test_entity_grid import _get_download_filtered_callback
from tests.test_export_format_switch import _UN_FILTRE, _fake_writers, _FakeDF


@pytest.fixture
def evenements(monkeypatch):
    captures = []
    monkeypatch.setattr(
        "src.utils.suivi.set_props",
        lambda _id, props: captures.append(props["data"]),
    )
    return captures


def _tuples(evenements):
    return [(e["categorie"], e["action"], e["nom"], e["valeur"]) for e in evenements]


def _export_tableau(monkeypatch, hauteur, captured):
    from src.pages import tableau
    from src.utils import grid as grid_module

    fake_xlsx, fake_csv = _fake_writers(captured)
    monkeypatch.setattr(
        grid_module, "export_dataframe", lambda *a, **kw: _FakeDF(hauteur)
    )
    monkeypatch.setattr(tableau, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(tableau, "write_csv", fake_csv)
    tableau.download_data(1, _UN_FILTRE, None)
    return ("Tableau", "telechargement")


def _export_observatoire(monkeypatch, hauteur, captured):
    from src.pages import observatoire

    fake_xlsx, fake_csv = _fake_writers(captured)
    monkeypatch.setattr(
        observatoire, "prepare_dashboard_data", lambda **kw: _FakeDF(hauteur)
    )
    monkeypatch.setattr(observatoire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(observatoire, "write_csv", fake_csv)
    observatoire.download_observatoire(1, {"dashboard_year": "2025"})
    return ("Observatoire", "telechargement")


def _export_acheteur(monkeypatch, hauteur, captured):
    from src.pages import acheteur

    fake_xlsx, fake_csv = _fake_writers(captured)
    monkeypatch.setattr(acheteur, "query_marches", lambda *a, **kw: _FakeDF(hauteur))
    monkeypatch.setattr(acheteur, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(acheteur, "write_csv", fake_csv)
    acheteur.download_acheteur_data(1, "/acheteurs/123", "2025", "ACHETEUR 1")
    return ("Acheteur", "telechargement")


def _export_titulaire(monkeypatch, hauteur, captured):
    from src.pages import titulaire

    fake_xlsx, fake_csv = _fake_writers(captured)
    monkeypatch.setattr(titulaire, "query_marches", lambda *a, **kw: _FakeDF(hauteur))
    monkeypatch.setattr(titulaire, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(titulaire, "write_csv", fake_csv)
    titulaire.download_titulaire_data(1, "/titulaires/345", "2025", "TITULAIRE 1")
    return ("Titulaire", "telechargement")


def _export_filtre_acheteur(monkeypatch, hauteur, captured):
    from src.utils import entity_grid as entity_grid_module
    from src.utils import table as table_module

    download_filtered = _get_download_filtered_callback("acheteur")
    fake_xlsx, fake_csv = _fake_writers(captured)
    monkeypatch.setattr(
        entity_grid_module,
        "export_entity_dataframe",
        lambda *a, **kw: _FakeDF(hauteur),
    )
    monkeypatch.setattr(table_module, "write_styled_excel", fake_xlsx)
    monkeypatch.setattr(table_module, "write_csv", fake_csv)
    download_filtered(1, "/acheteurs/123", "2025", "ACHETEUR 1", [None], [None])
    return ("Acheteur", "telechargement_filtre")


@pytest.mark.parametrize(
    "exporter",
    [
        _export_tableau,
        _export_observatoire,
        _export_acheteur,
        _export_titulaire,
        _export_filtre_acheteur,
    ],
)
@pytest.mark.parametrize(
    "hauteur, fmt", [(EXCEL_MAX_ROWS, "xlsx"), (EXCEL_MAX_ROWS + 1, "csv")]
)
def test_telechargement_emet_format_et_hauteur(
    monkeypatch, evenements, exporter, hauteur, fmt
):
    captured = {}
    categorie, action = exporter(monkeypatch, hauteur, captured)

    assert captured["used"] == fmt
    assert _tuples(evenements) == [(categorie, action, fmt, hauteur)]


def test_csv_datagouv_emet_le_total_sans_generer_de_fichier(monkeypatch, evenements):
    from src.pages import tableau
    from src.utils import grid as grid_module

    def interdit(*a, **kw):
        raise AssertionError("export_dataframe ne doit pas être appelé")

    monkeypatch.setattr(grid_module, "export_dataframe", interdit)

    resultat = tableau.download_data(1, None, None, 3_190_000)

    assert resultat is no_update
    assert _tuples(evenements) == [
        ("Tableau", "telechargement", "csv-datagouv", 3190000)
    ]
