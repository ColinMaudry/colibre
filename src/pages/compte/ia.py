import os

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask import session
from flask_login import current_user

from src.api import tokens_db
from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/ia",
    title="Connecteur IA | colibre",
    name="Connecteur IA",
    description="Connectez votre agent IA aux données colibre via le protocole MCP.",
)

MCP_ENABLED = os.getenv("DASH_MCP_ENABLED", "").lower() == "true"
_TOKEN_PLACEHOLDER = "<VOTRE_JETON>"


def _mcp_url() -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    return f"{base}/_mcp" if base else "/_mcp"


def _csrf(index: str):
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": index},
        name="csrf_token",
    )


def client_instructions(url: str, token: str):
    """Construit les blocs d'instructions par client (fonction pure, testable)."""
    claude = f'claude mcp add colibre --scope user --transport http {url} --header "Authorization: Bearer {token}"'
    gemini = f'gemini mcp add --scope user --transport http --header "Authorization: Bearer {token}" colibre {url}'
    return dbc.Accordion(
        start_collapsed=True,
        always_open=False,
        children=[
            dbc.AccordionItem(
                title="ChatGPT",
                children=[
                    html.P(
                        "ChatGPT utilise aussi OAuth (aucun jeton à copier). Dans les "
                        "connecteurs, ajoutez un connecteur par URL :"
                    ),
                    html.Ol(
                        [
                            html.Li(f"URL du serveur MCP : {url}"),
                            html.Li(
                                "Connectez-vous avec colibre, puis autorisez l'accès."
                            ),
                        ]
                    ),
                    html.P(
                        "La disponibilité des connecteurs dépend de votre plan ChatGPT.",
                        className="text-muted",
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Claude Code",
                children=html.Pre(html.Code(claude)),
            ),
            dbc.AccordionItem(
                title="Claude.ai / Claude Desktop / mobile",
                children=[
                    html.P("Aucun jeton à copier : ces applications utilisent OAuth."),
                    html.Ol(
                        [
                            html.Li(
                                "Icône utilisateur → Paramètres → Connecteurs → Ajouter → Ajouter un connecteur personnalisé."
                            ),
                            html.Li("Nom : colibre"),
                            html.Li(f"URL du serveur MCP distant : {url}"),
                            html.Li(
                                'Laissez les champs "Client ID" et "Client secret" vides.'
                            ),
                            html.Li(
                                'Connectez-vous avec votre compte colibre, puis "Autoriser".'
                            ),
                        ]
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Gemini CLI",
                children=[
                    html.P(
                        "Commande à exécuter dans un terminal en remplaçant <VOTRE_JETON> par un jeton généré (voir plus bas) :"
                    ),
                    html.Pre(html.Code(gemini)),
                ],
            ),
            dbc.AccordionItem(
                title="Mistral Vibe",
                children=dcc.Markdown(f"""
                    1. Sur l'[interface Work](https://chat.mistral.ai/work), cliquez sur **Connectez vos applications...**
                    2. Cliquez sur **+ Ajouter un connecteur**
                    3. Cliquez sur **Connecteur personnalisé**
                    4. Titre : colibre, Description : Base de données ouverte des marchés publics français (par exemple)
                    5. Serveur : `{url}`
                    6. Méthode d'authentification : Authentification par token API
                    7. Valeur du header : Bearer <VOTRE_JETON> (à remplacer par un jeton généré ci-dessous)
                    8. Cliquez sur **Créer**
                    """),
            ),
        ],
    )


def prompt_tips():
    """Exemples de prompts pour guider l'utilisateur (fonction pure, testable)."""
    exemples = [
        "Depuis colibre, trouve le dernier marché public attribué par le "
        "département du Morbihan.",
        "Donne-moi les statistiques de l'acheteur Rennes Métropole : nombre de "
        "marchés, montant total et principaux titulaires.",
        "Quelles entreprises ont remporté le plus de marchés d'informatique "
        "(CPV 72) en Ille-et-Vilaine depuis 2023 ?",
        "Reprends ces marchés en n'affichant que l'objet, le montant et la date "
        "de notification, avec le lien vers chaque fiche.",
    ]
    return html.Div(
        [
            html.Ul([html.Li(html.Em(p)) for p in exemples]),
        ]
    )


def _copy_token_button(token: str):
    """Bouton « Copier le jeton » (même design que « Copier le lien » des vues)."""
    return dcc.Clipboard(
        content=token,
        title="Copier le jeton",
        className="btn btn-outline-secondary btn-sm d-inline-flex "
        "align-items-center me-2",
        children=[
            html.Img(
                src="/assets/copy.svg",
                alt="",
                style={
                    "height": "1em",
                    "verticalAlign": "-0.15em",
                    "marginRight": "0.35em",
                },
            ),
            "Copier le jeton",
        ],
        copied_children="✓ Copié",
    )


def _token_row(row: dict):
    statut = "Révoqué" if row["revoked_at"] else "Actif"
    actions = []
    if not row["revoked_at"]:
        token_plain = row.get("token_plain")
        if token_plain:
            actions.append(_copy_token_button(token_plain))
        else:
            actions.append(
                html.Span(
                    "Régénérez pour copier",
                    className="text-muted small me-2",
                )
            )
        actions.append(
            html.Form(
                method="POST",
                action=f"/compte/ia/revoquer/{row['id']}",
                className="d-inline",
                children=[
                    _csrf(f"revoke-{row['id']}"),
                    dbc.Button(
                        "Révoquer",
                        type="submit",
                        color="danger",
                        size="sm",
                        outline=True,
                    ),
                ],
            )
        )
    return html.Tr(
        [
            html.Td(row["label"]),
            html.Td(row["created_at"]),
            html.Td(row["last_used_at"] or "—"),
            html.Td(statut),
            html.Td(actions),
        ]
    )


def layout(**_):
    guard = account_guard("/compte/ia", require_subscription=True)
    if guard is not None:
        return guard

    if not MCP_ENABLED:
        contenu = html.Div(
            [
                html.H2("Connecteur IA"),
                dbc.Alert(
                    "Le connecteur IA sera bientôt disponible. Revenez prochainement.",
                    color="info",
                ),
            ]
        )
        return account_shell("mcp", contenu)

    # url = _mcp_url()
    new_token = session.pop("mcp_new_token", None)

    alerts = []
    if new_token:
        alerts.append(
            dbc.Alert(
                [
                    html.Strong(
                        "Votre nouveau jeton (vous pourrez le copier à tout "
                        "moment via « Copier le jeton ») :"
                    ),
                    html.Pre(html.Code(new_token)),
                ],
                color="success",
            )
        )

    db_path = os.environ["USERS_DB_PATH"]
    tokens = tokens_db.list_user_tokens(db_path, current_user.id, "mcp")
    token_rows = []
    for r in tokens:
        row = dict(r)
        row["token_plain"] = tokens_db.get_token_plaintext_for_user(
            db_path, row["id"], current_user.id
        )
        token_rows.append(_token_row(row))
    table = (
        dbc.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Nom"),
                            html.Th("Créé le"),
                            html.Th("Dernière utilisation"),
                            html.Th("Statut"),
                            html.Th(""),
                        ]
                    )
                ),
                html.Tbody(token_rows),
            ],
            striped=True,
            bordered=False,
            hover=True,
        )
        if tokens
        else html.P("Aucun jeton pour le moment.")
    )

    create_form = html.Form(
        method="POST",
        action="/compte/ia/creer",
        className="mb-4",
        children=[
            _csrf("mcp-create"),
            dbc.Label("Nom du jeton (ex. « Claude sur mon portable »)"),
            dbc.Input(
                type="text",
                name="label",
                required=True,
                className="mb-2",
                style={"width": "300px"},
            ),
            dbc.Button("Générer un jeton", type="submit", color="secondary"),
        ],
    )

    # snippet_token = new_token or _TOKEN_PLACEHOLDER
    contenu = html.Div(
        [
            html.H2("Connecteur IA"),
            html.P(
                "Un connecteur IA est une interface proposée par un outil (ici colibre) pour faciliter "
                "son interrogation par un agent IA tel que Mistral, Claude ou ChatGPT. "
                "Dans le cas de colibre, cela vous permet de poser des questions très précises aux données, "
                "et d'obtenir une réponse rapide, précise et peu coûteuse en tokens. Exemples de questions :"
            ),
            prompt_tips(),
            html.P(
                "L'utilisation de cette fonctionnalité étant liée à un abonnement colibre, vous devez d'abord vous "
                "authentifier pour donner l'accès votre agent IA. La méthode varie selon les outils, il est donc "
                "difficile de décrire la procédure pour chaque outil. "
                "Le plus simple est de donner ce prompt à votre agent, et de suivre ses instructions :"
            ),
            html.Textarea(
                "Je souhaite consulter les données mises à disposition par le site colibre.fr et "
                "accessibles via le connecteur exposé à l'URL https://colibre.fr/_mcp.\n"
                "Je dispose d'un abonnnement colibre, donc je peux soit (par ordre de préférence)\n"
                "- procéder à l'authentification dans mon navigateur\n"
                "- fournir un jeton d'authentification",
                className="mcp_prompt",
            ),
            # html.H4("Connecter un client", className="mt-4"),
            # client_instructions(url, snippet_token),
            *alerts,
            html.H4("Générer un jeton d'authentification", className="mt-3"),
            create_form,
            html.H4("Mes jetons", className="mt-4"),
            table,
        ]
    )
    return account_shell("mcp", contenu)
