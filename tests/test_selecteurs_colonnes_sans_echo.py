"""Le liage store ⇄ cases sur les autres sélecteurs de colonnes (#139).

Aucune de ces trois pages n'a aujourd'hui de second écrivain de son store, donc
l'écho n'y écrase rien — le bug de #139 ne les touche pas. Mais il part quand
même à chaque chargement : un aller-retour serveur pour rien, et la course
réapparaîtrait le jour où un second écrivain serait ajouté (des vues
sauvegardées étendues à /acheteur, par exemple).

Comme pour le Tableau, les cases ne sont plus alimentées que par l'ouverture de
leur modale.
"""

from pathlib import Path

import pytest

# (module, id des cases, id de la modale, id du store)
SELECTEURS = [
    ("acheteur", "acheteur_column_list", "acheteur_columns", "acheteur-hidden-columns"),
    (
        "titulaire",
        "titulaire_column_list",
        "titulaire_columns",
        "titulaire-hidden-columns",
    ),
    (
        "observatoire",
        "observatoire_preview_column_list",
        "observatoire-preview-columns-modal",
        "observatoire-hidden-columns",
    ),
]


def _declaration(module: str, cases: str) -> str:
    """Le bloc @callback qui produit `<cases>.selectedRows`.

    Lu dans la source plutôt que dans dash._callback.GLOBAL_CALLBACK_MAP :
    cette table est un état global que d'autres tests vident en cours de
    session.
    """
    source = Path(f"src/pages/{module}.py").read_text()
    sortie = f'Output("{cases}", "selectedRows")'
    debut = source.rindex("@callback", 0, source.index(sortie))
    return source[debut : source.index("def ", debut)]


@pytest.mark.parametrize("module,cases,modale,store", SELECTEURS)
def test_les_cases_sont_alimentees_par_la_modale(module, cases, modale, store):
    assert f'Input("{modale}", "is_open")' in _declaration(module, cases)


@pytest.mark.parametrize("module,cases,modale,store", SELECTEURS)
def test_aucun_declencheur_permanent(module, cases, modale, store):
    """Ni le store, ni le miroir de ses colonnes masquées sur la table, ne
    doivent déclencher les cases : c'est ce qui crée l'écho au chargement."""
    declaration = _declaration(module, cases)

    assert f'Input("{store}", "data")' not in declaration
    assert '"hidden_columns"' not in declaration


# Garde anti-écho du callback « cases → store » (#141). Poser `selectedRows`
# depuis le serveur à l'ouverture de la modale fait réémettre `selectedRows`
# par AG Grid : si l'état qu'il en déduit est celui du store, rien ne doit être
# réécrit (sinon l'écho redevient une écriture concurrente, cf. #139).

# (module, page de get_default_hidden_columns)
PAGES_DU_STORE = [
    ("tableau", "tableau"),
    ("acheteur", "acheteur"),
    ("titulaire", "titulaire"),
    ("observatoire", "tableau"),
]


def _module(nom):
    import importlib

    from src.app import app  # noqa: F401  (instancie Dash avant les pages)

    return importlib.import_module(f"src.pages.{nom}")


def _lignes_cochees(masquees):
    """Les lignes telles qu'AG Grid les réémet (dict complet par ligne)."""
    from src.utils.table import COLUMNS

    return [
        {"id": c, "name": f"titre {c}", "description": "…"}
        for c in COLUMNS
        if c not in masquees
    ]


@pytest.mark.parametrize("module,page", PAGES_DU_STORE)
def test_selection_identique_au_store_nest_pas_reecrite(module, page):
    from dash import no_update

    from src.utils.table import COLUMNS

    masquees = [COLUMNS[1], COLUMNS[3]]
    # Ordre différent : la comparaison porte sur l'ensemble, pas sur la liste.
    store = [COLUMNS[3], COLUMNS[1]]

    resultat = _module(module).update_hidden_columns_from_checkboxes(
        _lignes_cochees(masquees), store
    )

    assert resultat is no_update


@pytest.mark.parametrize("module,page", PAGES_DU_STORE)
def test_store_vide_compare_au_defaut_de_la_page(module, page):
    from dash import no_update

    from src.utils.table import COLUMNS, get_default_hidden_columns

    defaut = get_default_hidden_columns(page)
    assert defaut and len(defaut) < len(COLUMNS), (
        "défaut trivial : rien ne serait testé"
    )
    cb = _module(module).update_hidden_columns_from_checkboxes

    # Sélection = colonnes visibles par défaut : écho, rien à écrire.
    assert cb(_lignes_cochees(defaut), None) is no_update
    # Toute autre sélection est un vrai choix de l'utilisateur.
    autre = [c for c in COLUMNS if c not in defaut][:1]
    assert cb(_lignes_cochees(autre), None) == autre


@pytest.mark.parametrize("module,page", PAGES_DU_STORE)
def test_selection_differente_ecrit_la_nouvelle_liste(module, page):
    from src.utils.table import COLUMNS

    cb = _module(module).update_hidden_columns_from_checkboxes

    assert cb(_lignes_cochees([COLUMNS[0]]), [COLUMNS[1]]) == [COLUMNS[0]]
    # Tout décocher est un choix explicite : toutes les colonnes masquées.
    assert cb([], [COLUMNS[1]]) == COLUMNS
    # Tout cocher depuis un store non vide : plus rien de masqué.
    assert cb(_lignes_cochees([]), [COLUMNS[1]]) == []


def test_apercu_observatoire_sans_preference_masque_le_defaut():
    """Store à None (première visite) : l'aperçu doit masquer les mêmes colonnes
    que celles que la modale décoche, soit le défaut « tableau ». Sinon il
    affiche tout, et le premier décochage le fait sauter à « défaut moins une »."""
    from src.utils.table import COLUMNS, get_default_hidden_columns

    store_hidden_columns = _module("observatoire").store_hidden_columns
    defaut = get_default_hidden_columns("tableau")
    assert defaut, "défaut vide : rien ne serait testé"

    assert store_hidden_columns(None) == defaut
    # [] est un choix explicite : tout afficher.
    assert store_hidden_columns([]) == []
    assert store_hidden_columns([COLUMNS[2]]) == [COLUMNS[2]]
