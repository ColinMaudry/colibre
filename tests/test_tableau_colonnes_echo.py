"""Écho du sélecteur de colonnes (issue #139).

Le store `tableau-hidden-columns` et les cases à cocher étaient liés dans les
deux sens en permanence. Au chargement, l'écho « cases → store » partait avec
l'état par défaut et pouvait arriver APRÈS l'application d'une vue partagée,
écrasant silencieusement ses colonnes.

Les cases vivent dans une modale : les tenir à jour tant qu'elle est fermée ne
sert à rien et coûte cette course. Elles ne sont donc plus alimentées que par
l'ouverture de la modale.
"""

import pytest
from dash import no_update


@pytest.fixture
def tableau():
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import tableau as module

    return module


def _declaration_du_callback_des_cases() -> str:
    """Le bloc @callback qui produit `tableau_column_list.selectedRows`.

    Lu dans la source plutôt que dans `dash._callback.GLOBAL_CALLBACK_MAP` :
    cette table est un état global partagé par toute la session de test, et
    d'autres fichiers la vident — le test passait seul et échouait en suite
    complète.
    """
    from pathlib import Path

    source = Path("src/pages/tableau.py").read_text()
    debut = source.rindex(
        "@callback", 0, source.index('Output("tableau_column_list", "selectedRows")')
    )
    fin = source.index("def ", debut)
    return source[debut:fin]


def test_les_cases_ne_sont_plus_alimentees_par_le_store():
    """La cause racine : tant que le store déclenche les cases, l'écho existe
    au chargement et peut courir contre l'application d'une vue."""
    assert (
        'Input("tableau-hidden-columns", "data")'
        not in _declaration_du_callback_des_cases()
    )


def test_les_cases_sont_alimentees_par_louverture_de_la_modale():
    assert 'Input("tableau_columns", "is_open")' in _declaration_du_callback_des_cases()


def test_louverture_de_la_modale_vide_la_recherche_de_colonnes():
    assert (
        'Output({"type": "column-search", "page": "tableau"}, "value")'
        in _declaration_du_callback_des_cases()
    )


def test_modale_fermee_naecrit_rien(tableau):
    """Le callback part aussi à la fermeture : il ne doit alors rien écrire,
    sinon on réintroduit une écriture non sollicitée de `selectedRows`."""
    coches, recherche = tableau.update_checkboxes_from_hidden_columns(
        False, ["montant"]
    )
    assert coches is no_update
    assert recherche is no_update


def test_modale_ouverte_coche_les_colonnes_visibles(tableau):
    from src.utils.table import COLUMNS

    coches, recherche = tableau.update_checkboxes_from_hidden_columns(True, ["montant"])

    assert coches == {"ids": [c for c in COLUMNS if c != "montant"]}
    # La grille recréée à l'ouverture n'a pas de filtre rapide : le champ de
    # recherche est vidé pour rester cohérent avec elle.
    assert recherche == ""
    assert "montant" in COLUMNS


def test_aucune_preference_retombe_sur_le_defaut(tableau):
    """None = première visite (pas de préférence enregistrée), distinct de []
    qui est un choix explicite de tout afficher. La distinction a déjà causé
    une régression, elle doit survivre au changement de déclencheur."""
    from src.utils.table import COLUMNS, get_default_hidden_columns

    defaut = get_default_hidden_columns("tableau")

    coches, _recherche = tableau.update_checkboxes_from_hidden_columns(True, None)

    assert defaut, "le défaut du Tableau masque des colonnes : sinon rien n'est testé"
    assert coches == {"ids": [c for c in COLUMNS if c not in defaut]}


def test_liste_vide_affiche_toutes_les_colonnes(tableau):
    from src.utils.table import COLUMNS

    coches, _recherche = tableau.update_checkboxes_from_hidden_columns(True, [])

    assert coches == {"ids": COLUMNS}
