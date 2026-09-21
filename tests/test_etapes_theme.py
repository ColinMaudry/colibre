"""La frise des étapes (/etapes) ne doit plus figer ses couleurs en clair
(#118) : elles doivent suivre le thème via des variables CSS.
"""

import re

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def test_le_graphique_desktop_ne_contient_plus_de_couleur_hexadecimale():
    from src.pages.etapes import build_chart

    assert HEX_COLOR.findall(str(build_chart())) == []


def test_la_vue_mobile_ne_contient_plus_de_couleur_hexadecimale():
    from src.pages.etapes import build_mobile

    assert HEX_COLOR.findall(str(build_mobile())) == []


def test_le_graphique_desktop_utilise_les_variables_etape():
    from src.pages.etapes import build_chart

    rendu = str(build_chart())
    for variable in (
        "var(--etape-approch)",
        "var(--etape-jal)",
        "var(--etape-boamp)",
        "var(--etape-joue)",
        "var(--etape-decp)",
    ):
        assert variable in rendu, f"{variable} absente du graphique desktop"


def test_la_vue_mobile_utilise_les_variables_etape():
    from src.pages.etapes import build_mobile

    rendu = str(build_mobile())
    for variable in (
        "var(--etape-approch)",
        "var(--etape-jal)",
        "var(--etape-boamp)",
        "var(--etape-joue)",
        "var(--etape-decp)",
    ):
        assert variable in rendu, f"{variable} absente de la vue mobile"
