from dash import html

from src.app import app  # noqa: F401  (instancie Dash avant les pages)
from src.pages import observatoire  # noqa: E402
from src.pages.observatoire import afficher_aide_objet, aide_objet  # noqa: E402


def _a_banniere(enfants) -> bool:
    return any(
        isinstance(e, html.Span) and "filter-pills-banniere" in (e.className or "")
        for e in enfants or []
    )


def test_aide_correction():
    assert aide_objet("(béton OU", True) == [
        "Filtre appliqué : béton (parenthèse manquante, OU orphelin)"
    ]


def test_aide_expression_vide_apres_reparation():
    assert aide_objet("ET", True) == ["Filtre appliqué : n'est pas vide (ET orphelin)"]


def test_aide_rien_si_propre():
    assert aide_objet("béton OU ciment", True) is None
    assert aide_objet(None, True) is None
    assert aide_objet("", False) is None


def test_aide_non_abonne():
    assert _a_banniere(aide_objet("béton OU ciment", False))
    assert aide_objet('"béton OU ciment"', False) is None


def test_callback_lit_l_abonnement(monkeypatch):
    monkeypatch.setattr(observatoire, "current_user_has_subscription", lambda: False)
    assert _a_banniere(afficher_aide_objet("béton OU ciment"))
