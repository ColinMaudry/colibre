"""Mode observatoire de la page Tableau (issue #137).

Un interrupteur bascule l'affichage des lignes de la grille vers les cards de
l'observatoire, alimentées par les filtres AG Grid en cours.
"""

import pytest


@pytest.fixture
def layout_str():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau

    return str(tableau.layout)


def test_la_barre_doutils_porte_linterrupteur(layout_str):
    assert "tableau-mode-observatoire" in layout_str


def test_linterrupteur_est_encadre_des_deux_icones(layout_str):
    assert "☰" in layout_str
    assert "📊" in layout_str


def test_linterrupteur_annonce_quil_est_reserve_aux_abonnes(layout_str):
    assert "Fonctionnalité accessible en vous abonnant" in layout_str


def test_le_layout_porte_la_modale_montants(layout_str):
    """La card Résumé rend un « ? » qui ouvre montant-modal via un callback
    pattern-matching global : sans la modale dans ce layout, Dash lèverait une
    erreur d'Output introuvable au clic."""
    assert "montant-modal" in layout_str


def test_le_conteneur_des_cards_suit_la_grille(layout_str):
    assert "tableau-observatoire-cards" in layout_str


@pytest.fixture
def tableau_abonne(monkeypatch):
    """Page Tableau vue par une personne abonnée."""
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: True)
    return tableau


FILTRE_ACHETEUR = {
    "acheteur_nom": {"filterType": "text", "type": "contains", "filter": "ACHETEUR"}
}


def test_mode_inactif_masque_les_cards_sans_les_recalculer(tableau_abonne):
    from dash import no_update

    children, classe = tableau_abonne.update_mode_observatoire_cards(
        False, FILTRE_ACHETEUR, None
    )

    # Les cards restent montées : repasser en mode observatoire ne relance
    # aucune requête tant que le filtre n'a pas changé.
    assert children is no_update
    assert "d-none" in classe


def test_sans_filtre_le_mode_invite_a_en_appliquer_un(tableau_abonne):
    children, classe = tableau_abonne.update_mode_observatoire_cards(True, None, None)

    assert "Appliquez au moins un filtre" in str(children)
    assert "d-none" not in classe


def test_avec_un_filtre_les_cards_de_lobservatoire_sont_affichees(tableau_abonne):
    children, classe = tableau_abonne.update_mode_observatoire_cards(
        True, FILTRE_ACHETEUR, None
    )

    assert "d-none" not in classe
    # Les mêmes cards que /observatoire : la card « Résumé » en tête.
    assert "Résumé" in str(children)


def test_le_filtre_de_la_grille_restreint_bien_les_cards(tableau_abonne):
    """Un filtre qui ne retient aucune ligne ne doit pas produire les mêmes
    cards qu'un filtre qui retient tout : c'est la preuve que le filterModel
    est bien transmis à la requête."""
    aucun_resultat = {
        "acheteur_nom": {
            "filterType": "text",
            "type": "contains",
            "filter": "zzzzz-inexistant",
        }
    }

    avec, _ = tableau_abonne.update_mode_observatoire_cards(True, FILTRE_ACHETEUR, None)
    sans, _ = tableau_abonne.update_mode_observatoire_cards(True, aucun_resultat, None)

    assert str(avec) != str(sans)


def test_le_mode_est_refuse_sans_abonnement(monkeypatch):
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)

    children, _classe = tableau.update_mode_observatoire_cards(
        True, FILTRE_ACHETEUR, None
    )

    assert "Résumé" not in str(children)
    assert "abonnant" in str(children)


def test_linterrupteur_est_actif_pour_un_abonne(tableau_abonne):
    desactive, _title = tableau_abonne.toggle_mode_observatoire_control("/tableau")

    assert desactive is False


def test_linterrupteur_est_desactive_sans_abonnement(monkeypatch):
    from src.app import app  # noqa: F401
    from src.pages import tableau

    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: False)

    desactive, title = tableau.toggle_mode_observatoire_control("/tableau")

    assert desactive is True
    assert title == "Fonctionnalité accessible en vous abonnant"


@pytest.fixture
def feuille_de_style():
    from pathlib import Path

    return Path("src/assets/css/style.css").read_text()


def test_le_css_masque_le_corps_de_la_grille_pas_son_entete(feuille_de_style):
    """L'en-tête et ses filtres flottants restent visibles et actionnables :
    c'est ce qui permet d'affiner les filtres sans quitter le mode."""
    assert ".mode-observatoire .marches_table .ag-body" in feuille_de_style
    assert ".mode-observatoire .marches_table .ag-header" not in feuille_de_style


def test_le_css_libere_la_hauteur_figee_de_la_grille(feuille_de_style):
    """ag_grid impose height:70vh en style inline ; sans !important la grille
    garderait sa hauteur et laisserait un grand vide sous l'en-tête."""
    assert "height: auto !important" in feuille_de_style


def test_le_css_reserve_la_place_des_cards(feuille_de_style):
    """La page ne doit pas se rétracter puis se redéployer une seconde plus
    tard : le conteneur des cards tient la hauteur qu'occupait la grille."""
    assert ".mode-observatoire-cards" in feuille_de_style
    assert "min-height: 70vh" in feuille_de_style


def test_le_css_anime_lapparition_des_cards(feuille_de_style):
    assert "@keyframes mode-observatoire-apparition" in feuille_de_style


def test_lanimation_est_conditionnee_a_prefers_reduced_motion(feuille_de_style):
    """Comme les transitions de .btn déjà en place, l'apparition des cards est
    déclarée en opt-in : rien ne bouge si le système demande moins d'animation."""
    blocs = feuille_de_style.split("@media (prefers-reduced-motion: no-preference)")

    assert any("mode-observatoire-apparition" in bloc for bloc in blocs[1:])


def test_le_mode_demploi_documente_linterrupteur(layout_str):
    """La légende du mode d'emploi reproduit chaque bouton de la barre d'outils
    en face de sa fonction : un contrôle de plus doit y figurer aussi."""
    assert "mode-observatoire-legende" in layout_str
