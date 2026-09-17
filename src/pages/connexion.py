import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

NAME = "Connexion"

register_page(
    __name__,
    path="/connexion",
    title="Connexion | colibre",
    name=NAME,
    description="Se connecter à colibre.",
)

ERROR_MESSAGES = {
    "invalid_credentials": "Identifiants invalides.",
    "email_not_verified": "Vérifiez d'abord votre adresse email (consultez votre boîte de réception).",
    "oauth_cancelled": "Connexion LinkedIn annulée.",
    "oauth_failed": "Échec de la connexion via LinkedIn. Réessayez.",
}

INFO_MESSAGES = {
    "pending_verification": (
        "Compte créé. Un email de vérification a été envoyé. "
        "Cliquez sur le lien reçu avant de vous connecter."
    ),
    "verified": "Adresse email vérifiée. Vous pouvez maintenant vous connecter.",
    "password_changed": "Mot de passe mis à jour. Connectez-vous avec le nouveau.",
}


def linkedin_button(next_url: str | None = None):
    href = "/auth/linkedin"
    if next_url:
        href += f"?next={next_url}"
    return html.A(
        "Connexion avec LinkedIn",
        href=href,
        className="btn w-100 mb-2",
        style={"backgroundColor": "rgb(10, 102, 194)", "color": "white"},
    )


def layout(error: str | None = None, email: str | None = None, **kwargs):
    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    for flag, msg in INFO_MESSAGES.items():
        if kwargs.get(flag) == "1":
            alerts.append(dbc.Alert(msg, color="info"))

    next_url = kwargs.get("next", "")

    left_col = dbc.Col(
        md=5,
        children=[
            html.H4("Pas encore de compte ?"),
            html.P(
                "Découvrez les abonnements disponibles et leurs avantages.",
                className="text-muted",
            ),
            html.A(
                "Voir les abonnements disponibles et leurs avantages",
                href="/projet/abonnement",
                className="btn btn-secondary",
            ),
        ],
        style={
            "borderRight": "1px solid var(--bs-border-color)",
            "paddingRight": "2rem",
        },
    )

    right_col = dbc.Col(
        md=7,
        children=[
            html.H2("Connexion"),
            *alerts,
            html.Form(
                method="POST",
                action="/auth/login",
                children=[
                    dcc.Input(
                        type="hidden",
                        id={"type": "csrf-input", "index": "login"},
                        name="csrf_token",
                    ),
                    dcc.Input(type="hidden", name="next", value=next_url),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Label("Mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Button("Se connecter", type="submit", color="secondary"),
                ],
            ),
            dcc.Link(
                "Mot de passe oublié ?",
                href="/mot-de-passe-oublie",
                className="small d-block mt-2",
            ),
            html.Div("ou", className="text-center text-muted my-2"),
            linkedin_button(next_url),
        ],
        style={"paddingLeft": "2rem"},
    )

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "800px"},
        children=[
            dbc.Row([left_col, right_col], className="align-items-start g-4"),
        ],
    )
