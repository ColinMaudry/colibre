"""Mise en page des grilles « Top acheteurs / Top titulaires » (#142).

Ces grilles sont en modèle `infinite` : `domLayout: "autoHeight"` n'existe pas
dans ce modèle, donc leur hauteur est FIXE et connue avant même le premier
rendu. Elles arrivent pourtant par callback, après la page.

Si le conteneur qui les accueille réserve moins que cette hauteur, leur arrivée
pousse vers le bas tout ce qui suit — ici les boutons « Colonnes »,
« Téléchargement » et « Réinitialiser ». Un clic déjà engagé rate alors sa
cible (« element click intercepted » côté Selenium, bouton qui se dérobe sous
le doigt côté utilisateur). C'est exactement ce qui cassait
tests/test_selecteurs_colonnes_navigateur.py.

On vérifie donc l'invariant qui l'interdit : la hauteur réservée par le
conteneur couvre la hauteur réellement occupée par la grille.
"""

import time

import pytest
from dash.testing.composite import DashComposite

from src.utils.top_org_grid import (
    CARD_MIN_HEIGHT,
    GRID_HEIGHT_PX,
    HOST_MIN_HEIGHT,
)

# (url, id du conteneur du top, id du bouton situé sous le top)
FICHES = [
    ("/acheteurs/123", "top10_titulaires", "acheteur_columns_open"),
    ("/titulaires/345", "top10_acheteurs", "titulaire_columns_open"),
]

#: Mesures du conteneur du top et du bouton qui le suit.
MESURES = """
const hote = document.getElementById(arguments[0]);
const bouton = document.getElementById(arguments[1]);
const contenu = hote.firstElementChild;
const rh = hote.getBoundingClientRect();
const rc = contenu.getBoundingClientRect();
const rb = bouton.getBoundingClientRect();
const dessus = document.elementFromPoint(
  rb.left + rb.width / 2, rb.top + rb.height / 2
);
return {
  reserve: parseFloat(getComputedStyle(hote).minHeight) || 0,
  hoteBas: rh.bottom,
  contenuHauteur: rc.height,
  contenuBas: rc.bottom,
  dessusId: dessus ? (dessus.id || dessus.tagName) : "null",
};
"""


def _mesurer(dash_duo: DashComposite, chemin, hote, bouton):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}{chemin}")
    # La barre de pagination n'existe qu'une fois la grille montée : c'est le
    # signal que la hauteur définitive est posée.
    dash_duo.wait_for_element(f"#{hote} .ag-paging-panel", timeout=20)
    dash_duo.wait_for_element(f"#{bouton}", timeout=10)
    time.sleep(1)  # laisse AG Grid finir son dimensionnement
    # `elementFromPoint` ne répond que sur des coordonnées dans la fenêtre : on
    # amène le bouton à l'écran avant de mesurer.
    dash_duo.driver.execute_script(
        "document.getElementById(arguments[0]).scrollIntoView({block: 'center'});",
        bouton,
    )
    time.sleep(0.5)
    return dash_duo.driver.execute_script(MESURES, hote, bouton)


@pytest.mark.parametrize("chemin,hote,bouton", FICHES)
def test_le_conteneur_reserve_la_hauteur_de_la_grille(
    dash_duo: DashComposite, chemin, hote, bouton
):
    """Sans cette réserve, l'arrivée du top décale la page sous le curseur."""
    m = _mesurer(dash_duo, chemin, hote, bouton)

    assert m["reserve"] >= m["contenuHauteur"] - 1, (
        f"{hote} ne réserve que {m['reserve']:.0f} px pour un top qui en occupe "
        f"{m['contenuHauteur']:.0f} : son arrivée décale tout ce qui suit"
    )


@pytest.mark.parametrize("chemin,hote,bouton", FICHES)
def test_la_grille_ne_deborde_pas_de_son_conteneur(
    dash_duo: DashComposite, chemin, hote, bouton
):
    """Et elle tient dans son conteneur, sans recouvrir ce qui suit."""
    m = _mesurer(dash_duo, chemin, hote, bouton)

    assert m["contenuBas"] <= m["hoteBas"] + 1, (
        f"le top déborde de {hote} de {m['contenuBas'] - m['hoteBas']:.0f} px"
    )
    assert m["dessusId"] == bouton, (
        f"le bouton {bouton} n'est pas l'élément au point de son propre centre "
        f"({m['dessusId']}) : il est recouvert, donc non cliquable"
    )


#: Mesure chaque card de l'observatoire qui héberge une grille top.
CARTES = """
const out = [];
for (const colonne of document.querySelectorAll('.observatoire-card')) {
  const grille = colonne.querySelector('.ag-root-wrapper');
  if (!grille) continue;
  const carte = colonne.querySelector('.card');
  out.push({
    classe: colonne.getAttribute('class'),
    debordement: grille.getBoundingClientRect().bottom
                 - carte.getBoundingClientRect().bottom,
  });
}
return out;
"""


def test_observatoire_les_cards_accueillent_la_grille(dash_duo: DashComposite):
    """3e contexte : les cards de l'observatoire hébergent le top sans rognage.

    Le 4e (mode observatoire de /tableau) construit ses cards par le même
    chemin — `get_dashboard_cards` + `make_card`, seul `context` change — donc
    cette mesure vaut pour les deux.
    """
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element(
        ".observatoire-card--top-titulaires .ag-paging-panel", timeout=30
    )
    time.sleep(1)
    cartes = dash_duo.driver.execute_script(CARTES)

    assert len(cartes) == 2, f"deux tops attendus, {len(cartes)} trouvé(s)"
    for carte in cartes:
        assert carte["debordement"] <= 1, (
            f"la grille déborde de sa card ({carte['classe']}) de "
            f"{carte['debordement']:.0f} px"
        )


def test_les_hauteurs_reservees_derivent_de_la_grille():
    """Les réserves se dérivent de `GRID_HEIGHT_PX`, jamais recopiées en dur.

    Test sans navigateur : il garde les quatre contextes cohérents si la taille
    de page ou la hauteur de ligne change.
    """
    assert HOST_MIN_HEIGHT == f"{GRID_HEIGHT_PX}px"
    assert int(CARD_MIN_HEIGHT.removesuffix("px")) > GRID_HEIGHT_PX


def test_les_fiches_reservent_au_moins_la_hauteur_de_la_grille():
    """Les deux fiches réservent bien la hauteur voulue dans leur layout."""
    from src.app import app  # noqa: F401  (instancie Dash avant les pages)
    from src.pages import acheteur, titulaire

    def reserve(layout, cible):
        trouve = []

        def descendre(noeud):
            if isinstance(noeud, (list, tuple)):
                for enfant in noeud:
                    descendre(enfant)
                return
            if getattr(noeud, "id", None) == cible:
                trouve.append(getattr(noeud, "style", None) or {})
            enfants = getattr(noeud, "children", None)
            if enfants is not None:
                descendre(enfants)

        descendre(layout)
        assert trouve, f"conteneur {cible} introuvable dans le layout"
        return trouve[0].get("minHeight")

    assert reserve(acheteur.layout("123"), "top10_titulaires") == CARD_MIN_HEIGHT
    assert reserve(titulaire.layout("345"), "top10_acheteurs") == HOST_MIN_HEIGHT
