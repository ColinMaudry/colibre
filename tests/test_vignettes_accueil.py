"""Vignettes de l'accueil déclinées en mode sombre (#118).

Les deux versions sont dans la page ; le CSS n'en affiche qu'une selon
`data-bs-theme`. On vérifie ici les deux moitiés du mécanisme : le rendu
(les deux images, avec leurs classes) et les règles CSS qui les basculent.
"""

from pathlib import Path

import pytest

CSS = Path("src/assets/css/style.css")


@pytest.fixture
def vignettes():
    import src.app  # noqa: F401  — register_page() exige une app instanciée
    from src.pages.recherche import _vignette

    return {
        "table": _vignette("table", "le tableau de données"),
        "dashboard": _vignette("dashboard", "l'observatoire"),
    }


@pytest.mark.parametrize("nom", ["table", "dashboard"])
def test_les_deux_versions_sont_rendues(vignettes, nom):
    claire, sombre = vignettes[nom].children

    assert claire.src == f"/assets/{nom}-thumbnail.png"
    assert claire.className == "vignette-claire"
    assert sombre.src == f"/assets/{nom}-thumbnail-dark.png"
    assert sombre.className == "vignette-sombre"
    assert claire.alt and claire.alt == sombre.alt


@pytest.mark.parametrize("nom", ["table", "dashboard"])
def test_les_fichiers_existent(nom):
    for fichier in (
        f"src/assets/{nom}-thumbnail.png",
        f"src/assets/{nom}-thumbnail-dark.png",
    ):
        assert Path(fichier).is_file(), f"{fichier} manquant"


def test_le_css_bascule_les_vignettes():
    css = CSS.read_text()

    # Positif : la version claire est bien celle affichée par défaut.
    assert ".vignette-sombre {\n  display: none;\n}" in css
    assert '[data-bs-theme="dark"] .vignette-claire {\n  display: none;\n}' in css
    assert '[data-bs-theme="dark"] .vignette-sombre {\n  display: inline;\n}' in css
