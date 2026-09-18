def test_titulaire_page_has_observatoire_button():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import titulaire

    html_str = str(titulaire.layout(titulaire_id="54202182900123"))
    assert "📊 Visualiser dans l'observatoire" in html_str
    assert "/observatoire?titulaire_id=54202182900123" in html_str


def test_acheteur_page_has_observatoire_button():
    # Import app first to initialize Dash
    from src.app import app  # noqa: F401
    from src.pages import acheteur

    html_str = str(acheteur.layout(acheteur_id="21590350100017"))
    assert "📊 Visualiser dans l'observatoire" in html_str
    assert "/observatoire?acheteur_id=21590350100017" in html_str
