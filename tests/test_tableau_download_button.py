"""update_meta (/tableau) doit suivre la même règle que les autres pages :
le bouton et son infobulle passent par get_button_properties, pas par une
logique locale (#142).

Sans filtre, le bouton renvoie plutôt vers le CSV complet publié sur
data.gouv.fr au lieu de faire générer un export de plusieurs millions de
lignes côté serveur (#142, passe de correction 2)."""

import pytest

from src.utils.frontend import EXCEL_MAX_ROWS

_UN_FILTRE = {"objet": {"filterType": "text", "type": "contains", "filter": "voirie"}}

_MESSAGE_DATA_GOUV = (
    "Le jeu de données complet est téléchargé depuis data.gouv.fr au format CSV."
)


pytestmark = pytest.mark.usefixtures("sans_abonnement")


def test_update_meta_excel_sous_le_seuil():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau

    nb_rows, disabled, texte, titre, href = tableau.update_meta(10, 5, _UN_FILTRE)

    assert disabled is False
    assert texte == "Télécharger au format Excel"
    assert titre == ""
    assert href is None
    assert "lignes" in nb_rows


def test_update_meta_csv_au_dela_du_seuil():
    from src.app import app  # noqa: F401
    from src.pages import tableau

    nb_rows, disabled, texte, titre, href = tableau.update_meta(
        EXCEL_MAX_ROWS + 1, EXCEL_MAX_ROWS + 1, _UN_FILTRE
    )

    assert disabled is False
    assert texte == "Télécharger au format CSV"
    assert titre == (
        "À partir de 100 000 lignes, le téléchargement se fait au format CSV, "
        "en raison des limites du serveur."
    )
    assert href is None
    assert "lignes" in nb_rows


def test_update_meta_ne_desactive_plus_au_dela_de_65000():
    """Avant #142, le bouton était désactivé au-delà de 65 000 lignes sans
    filtre possible : /tableau neutralisait déjà ce plafond localement, mais
    maintenant la même règle (jamais désactivé hors 0) vient de
    get_button_properties."""
    from src.app import app  # noqa: F401
    from src.pages import tableau

    _nb_rows, disabled, _texte, _titre, _href = tableau.update_meta(
        70_000, 70_000, _UN_FILTRE
    )

    assert disabled is False


def test_update_meta_filtre_vide_renvoie_vers_data_gouv_fr():
    from src.app import app  # noqa: F401
    from src.pages import tableau

    nb_rows, disabled, texte, titre, href = tableau.update_meta(
        3_190_000, 3_190_000, None
    )

    assert disabled is False
    assert texte == "Télécharger toutes les données"
    assert titre == _MESSAGE_DATA_GOUV
    assert href == tableau.DECP_CSV_COMPLET_URL
    assert "lignes" in nb_rows


def test_update_meta_filtre_vide_avec_colonnes_masquees_renvoie_quand_meme_vers_data_gouv_fr():
    """La condition ne porte que sur le filterModel : des colonnes masquées
    (columnState) n'empêchent pas le renvoi vers le CSV complet."""
    from src.app import app  # noqa: F401
    from src.pages import tableau

    # update_meta ne reçoit pas columnState (il n'influence pas la décision) ;
    # on vérifie simplement qu'un filterModel vide/falsy suffit à déclencher
    # le renvoi, quelle que soit la sélection de colonnes par ailleurs.
    for filtre_vide in (None, {}):
        _nb_rows, disabled, texte, titre, href = tableau.update_meta(
            3_190_000, 3_190_000, filtre_vide
        )
        assert disabled is False
        assert texte == "Télécharger toutes les données"
        assert titre == _MESSAGE_DATA_GOUV
        assert href == tableau.DECP_CSV_COMPLET_URL


def test_download_data_filtre_vide_ne_genere_rien(monkeypatch):
    """Sans filtre, le bouton pointe déjà (href) vers data.gouv.fr : un clic
    ne doit déclencher ni écriture Excel ni écriture CSV côté serveur."""
    from src.pages import tableau

    appels = []
    monkeypatch.setattr(
        tableau, "write_styled_excel", lambda *a, **kw: appels.append("xlsx")
    )
    monkeypatch.setattr(tableau, "write_csv", lambda *a, **kw: appels.append("csv"))

    from dash import no_update

    resultat = tableau.download_data(1, None, None)

    assert resultat is no_update
    assert appels == []


def test_download_data_filtre_present_comportement_inchange(monkeypatch):
    """Avec un filtre, download_data génère toujours le fichier (comportement
    actuel inchangé) — cf. aussi tests/test_export_format_switch.py pour la
    bascule Excel/CSV selon le volume."""
    from src.pages import tableau
    from src.utils import grid as grid_module

    class _FakeDF:
        height = 5

    appels = []
    monkeypatch.setattr(grid_module, "export_dataframe", lambda *a, **kw: _FakeDF())
    monkeypatch.setattr(
        tableau, "write_styled_excel", lambda *a, **kw: appels.append("xlsx")
    )
    monkeypatch.setattr(tableau, "write_csv", lambda *a, **kw: appels.append("csv"))

    resultat = tableau.download_data(1, _UN_FILTRE, None)

    assert appels == ["xlsx"]
    assert resultat["filename"].endswith(".xlsx")
