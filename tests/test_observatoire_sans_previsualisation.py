"""Suppression du tiroir de prévisualisation de l'observatoire (#142).

Le tiroir « Voir les données » était très peu utilisé — /tableau remplace
désormais cet usage. On vérifie qu'il ne reste aucune trace du tiroir dans le
layout, que le bouton d'export et le compteur de lignes ont bien été déplacés
dans le panneau de filtres (mêmes identifiants), et que l'export ne retire
plus aucune colonne.
"""

import polars as pl
import pytest

from tests.helpers import walk_components


@pytest.fixture(autouse=True)
def _sans_abonnement(monkeypatch):
    """Callbacks appelés hors requête : pas d'utilisateur courant (#97)."""
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import observatoire

    monkeypatch.setattr(observatoire, "current_user_has_subscription", lambda: False)


def _layout_nodes():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import observatoire

    nodes = []
    for element in observatoire.layout:
        nodes.extend(walk_components(element))
    return nodes


def test_aucun_composant_du_tiroir_ne_subsiste():
    noeuds = _layout_nodes()
    ids = [str(getattr(n, "id", "")) for n in noeuds if getattr(n, "id", None)]

    orphelins = [
        i for i in ids if "observatoire-preview" in i or "observatoire_preview" in i
    ]
    assert orphelins == []


def test_le_panneau_de_filtres_porte_le_bouton_et_le_compteur():
    from src.app import app  # noqa: F401
    from src.pages import observatoire

    noeuds = []
    for element in observatoire.layout:
        noeuds.extend(walk_components(element))

    filtres = next(n for n in noeuds if getattr(n, "id", None) == "filters")
    ids_filtres = [getattr(n, "id", None) for n in walk_components(filtres)]

    assert "btn-download-observatoire" in ids_filtres
    assert "nb_rows_observatoire" in ids_filtres


def test_export_ne_retire_plus_aucune_colonne(monkeypatch):
    from src.app import app  # noqa: F401
    from src.db import schema
    from src.pages import observatoire

    capture = {}

    def _espion(dff, _buffer):
        capture["dataframe"] = dff

    monkeypatch.setattr(observatoire, "write_styled_excel", _espion)

    resultat = observatoire.download_observatoire(1, {"dashboard_year": "2025"})

    assert resultat is not None
    dff = capture["dataframe"]
    assert isinstance(dff, pl.DataFrame)
    assert sorted(dff.columns) == sorted(schema.names())


def test_le_compteur_et_le_bouton_pour_un_perimetre_non_vide():
    from src.app import app  # noqa: F401
    from src.pages import observatoire

    nb_rows, disabled, texte, titre = observatoire.update_download_button_observatoire(
        {"dashboard_year": "2025"}
    )

    assert "1" in nb_rows
    assert "ligne" in nb_rows
    assert "marché" in nb_rows
    assert disabled is False
    assert texte == "Télécharger au format Excel"
    # Le bouton Excel n'a aucune infobulle (#142) : il se suffit à lui-même.
    assert titre == ""


@pytest.mark.parametrize(
    "signature",
    [
        "toggle_observatoire_preview",
        "populate_preview_table",
        "update_hidden_columns_from_checkboxes",
        "store_hidden_columns",
        "update_checkboxes_from_hidden_columns",
        "toggle_tableau_columns",
    ],
)
def test_les_callbacks_du_tiroir_nexistent_plus(signature):
    from src.app import app  # noqa: F401
    from src.pages import observatoire

    assert not hasattr(observatoire, signature)
