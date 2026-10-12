def test_section_connecteur_mcp_present():
    from src.pages._compte_shell import SECTIONS

    keys = {s["key"]: s for s in SECTIONS}
    assert "ia" in keys
    assert keys["ia"]["label"] == "Connecteur IA"
    assert keys["ia"]["href"] == "/compte/ia"
    assert keys["ia"]["require_subscription"] is True


def test_page_module_registers_and_builds_client_instructions():
    # importe l'app pour la découverte use_pages en contexte propre
    from src.app import app  # noqa: F401
    from src.pages.compte import ia as ia_page

    # helper pur : construit les 4 blocs d'instructions clients
    blocks = ia_page.client_instructions("https://colibre.fr/_mcp", "colibre_TESTTOKEN")
    text = str(blocks)
    assert "colibre_TESTTOKEN" in text
    assert "https://colibre.fr/_mcp" in text
    for client_name in ("Claude", "Gemini", "Mistral", "ChatGPT"):
        assert client_name in text


def test_client_instructions_include_oauth_apps():
    from src.app import app  # noqa: F401
    from src.pages.compte.ia import client_instructions

    comp = client_instructions("https://colibre.fr/_mcp", "<VOTRE_JETON>")
    titles = _collect_titles(comp)
    assert any("Claude.ai" in t for t in titles)
    assert any("ChatGPT" in t for t in titles)


def test_prompt_tips_mentions_columns_and_examples():
    from src.app import app  # noqa: F401
    from src.pages.compte.ia import prompt_tips

    text = str(prompt_tips())
    assert "Morbihan" in text  # un exemple de prompt concret
    assert "colonnes" in text  # l'astuce sur le choix des colonnes
    assert "lien" in text  # mention du lien vers la fiche marché


def test_token_row_has_copy_button_when_token_available():
    from src.app import app  # noqa: F401
    from src.pages.compte.ia import _token_row

    text = str(
        _token_row(
            {
                "id": 42,
                "label": "l",
                "created_at": "c",
                "last_used_at": None,
                "revoked_at": None,
                "token_plain": "colibre_abc123",
            }
        )
    )
    assert "Copier le jeton" in text
    assert "colibre_abc123" in text  # contenu du presse-papier (dcc.Clipboard)


def test_token_row_no_copy_button_when_token_unavailable():
    from src.app import app  # noqa: F401
    from src.pages.compte.ia import _token_row

    text = str(
        _token_row(
            {
                "id": 42,
                "label": "l",
                "created_at": "c",
                "last_used_at": None,
                "revoked_at": None,
                "token_plain": None,  # ancien jeton haché, non récupérable
            }
        )
    )
    assert "Copier le jeton" not in text


def _collect_titles(component):
    # Parcourt récursivement les AccordionItem pour collecter leurs `title`.
    found = []

    def walk(node):
        title = getattr(node, "title", None)
        if isinstance(title, str):
            found.append(title)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                walk(c)
        elif children is not None:
            walk(children)

    walk(component)
    return found
