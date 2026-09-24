"""update_meta (/tableau) doit suivre la même règle que les autres pages :
le bouton et son infobulle passent par get_button_properties, pas par une
logique locale (#142)."""

from src.utils.frontend import EXCEL_MAX_ROWS


def test_update_meta_excel_sous_le_seuil():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau

    nb_rows, disabled, texte, titre = tableau.update_meta(10, 5)

    assert disabled is False
    assert texte == "Télécharger au format Excel"
    assert titre == ""
    assert "lignes" in nb_rows


def test_update_meta_csv_au_dela_du_seuil():
    from src.app import app  # noqa: F401
    from src.pages import tableau

    nb_rows, disabled, texte, titre = tableau.update_meta(
        EXCEL_MAX_ROWS + 1, EXCEL_MAX_ROWS + 1
    )

    assert disabled is False
    assert texte == "Télécharger au format CSV"
    assert titre == (
        "À partir de 100 000 lignes, le téléchargement se fait au format CSV, "
        "en raison des limites du serveur."
    )
    assert "lignes" in nb_rows


def test_update_meta_ne_desactive_plus_au_dela_de_65000():
    """Avant #142, le bouton était désactivé au-delà de 65 000 lignes sans
    filtre possible : /tableau neutralisait déjà ce plafond localement, mais
    maintenant la même règle (jamais désactivé hors 0) vient de
    get_button_properties."""
    from src.app import app  # noqa: F401
    from src.pages import tableau

    _nb_rows, disabled, _texte, _titre = tableau.update_meta(70_000, 70_000)

    assert disabled is False
