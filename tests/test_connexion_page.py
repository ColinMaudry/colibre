def test_connexion_cta_points_to_abonnement():
    from src.app import app  # noqa: F401  # initializes Dash app
    from src.pages import connexion

    text = str(connexion.layout())
    assert "/projet/abonnement" in text
    assert "Voir les abonnements" in text
    assert "Pas encore de compte" in text


def test_connexion_layout_two_columns():
    """La page de connexion sépare l'invitation à s'abonner (gauche) du
    formulaire de connexion (droite), avec un trait de séparation."""
    from src.app import app  # noqa: F401  # initializes Dash app
    from src.pages import connexion

    text = str(connexion.layout())
    assert "borderRight" in text
    assert "Connexion" in text
    assert "Mot de passe oublié" in text
