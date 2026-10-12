import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
from flask_login import current_user

# Définition centralisée des sections de l'espace compte.
# Ajouter une section future = ajouter une ligne ici (+ créer sa page).
SECTIONS = [
    {
        "key": "vues",
        "label": "Mes vues",
        "href": "/compte/vues",
        "require_subscription": True,
    },
    {
        "key": "roadmap",
        "label": "Roadmap",
        "href": "/compte/roadmap",
        "require_subscription": True,
    },
    {
        "key": "ia",
        "label": "Connecteur IA",
        "href": "/compte/ia",
        "require_subscription": True,
    },
    {
        "key": "abonnement",
        "label": "Abonnement",
        "href": "/compte/abonnement",
        "require_subscription": False,
    },
    {
        "key": "admin",
        "label": "Compte",
        "href": "/compte/admin",
        "require_subscription": False,
    },
]


def current_user_has_subscription() -> bool:
    from src.subscriptions import db
    from src.utils import TOUS_ABONNES

    if not current_user.is_authenticated:
        return False
    if TOUS_ABONNES:
        return True
    # has_access, pas has_active_subscription : la période d'essai ouvre les
    # mêmes fonctionnalités qu'un abonnement.
    return db.has_access(current_user.id)


def visible_sections(has_subscription: bool) -> list[dict]:
    return [s for s in SECTIONS if has_subscription or not s["require_subscription"]]


def guard_redirect(
    is_authenticated: bool,
    has_subscription: bool,
    require_subscription: bool,
    path: str,
) -> str | None:
    if not is_authenticated:
        return f"/connexion?next={path}"
    if require_subscription and not has_subscription:
        return "/compte/abonnement"
    return None


def account_guard(path: str, require_subscription: bool):
    href = guard_redirect(
        current_user.is_authenticated,
        current_user_has_subscription(),
        require_subscription,
        path,
    )
    return dcc.Location(href=href, id="compte-guard-redirect") if href else None


def logout_form(csrf_index: str, item_class: str = "nav-link"):
    """Formulaire de déconnexion, partagé par la barre latérale et la navbar.

    `csrf_index` doit être unique par formulaire effectivement rendu : le jeton
    est rempli par motif (`{"type": "csrf-input", "index": ALL}` dans
    src/app.py), donc deux champs partageant un index se marcheraient dessus.

    `item_class` porte l'habillage du contexte d'accueil — `nav-link` dans la
    barre latérale, `dropdown-item` dans le menu de la navbar.
    """
    return html.Form(
        method="POST",
        action="/auth/logout",
        children=[
            dcc.Input(
                type="hidden",
                id={"type": "csrf-input", "index": csrf_index},
                name="csrf_token",
            ),
            html.Button(
                "Déconnexion",
                type="submit",
                className=item_class,
                style={
                    "background": "none",
                    "border": "none",
                    "width": "100%",
                    "textAlign": "left",
                },
            ),
        ],
    )


def _logout_item():
    return dbc.NavItem(logout_form("sidebar-logout"))


def _nav(active: str):
    links = [
        dbc.NavLink(s["label"], href=s["href"], active=(s["key"] == active))
        for s in visible_sections(current_user_has_subscription())
    ]
    return dbc.Nav(links + [_logout_item()], vertical=True, class_name="account-nav")


def account_shell(active: str, contenu):
    sidebar = dbc.Col(
        # La classe collante est sur le bloc intérieur, pas sur la colonne :
        # dbc.Row étire ses colonnes sur toute la hauteur (flex), ce qui ne
        # laisse à un `position: sticky` posé sur la Col aucune marge de
        # défilement — il ne collerait jamais.
        html.Div(
            [html.H5("Mon compte", className="mb-3"), _nav(active)],
            className="shell-nav-sticky",
        ),
        md=3,
        className="d-none d-md-block",
    )
    mobile = html.Div(
        [
            dbc.Button(
                "☰ Sections",
                id="compte-offcanvas-open",
                color="secondary",
                outline=True,
                className="mb-3",
            ),
            dbc.Offcanvas(
                _nav(active),
                id="compte-offcanvas",
                title="Mon compte",
                is_open=False,
            ),
        ],
        className="d-md-none",
    )
    content = dbc.Col([mobile, contenu], md=9)
    return dbc.Container(dbc.Row([sidebar, content]), className="py-4", fluid=True)


@callback(
    Output("compte-offcanvas", "is_open"),
    Input("compte-offcanvas-open", "n_clicks"),
    State("compte-offcanvas", "is_open"),
    prevent_initial_call=True,
)
def _toggle_offcanvas(_n, is_open):
    return not is_open
