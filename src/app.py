# ruff: noqa: E402  -- sys.path manipulation must precede third-party imports
import os
import sys
from pathlib import Path
from shutil import rmtree

# Sur les serveurs où le package est installé en mode éditable, pip peut ajouter
# src/ à sys.path via un fichier .pth. Combiné à la racine du projet (déjà dans
# sys.path via gunicorn), Dash's use_pages enregistre alors chaque page deux fois :
# une fois comme pages.X et une fois comme src.pages.X → erreur "duplicate paths".
_src_dir = str(Path(__file__).parent.resolve())
while _src_dir in sys.path:
    sys.path.remove(_src_dir)

import dash_bootstrap_components as dbc
import pandas  # noqa: F401  # eager import: avoid plotly's lazy-import race across Dash callback threads
import tomllib
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    page_container,
    page_registry,
)
from dotenv import load_dotenv
from flask import Flask, Response, redirect, send_from_directory
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from src.admin.guard import is_admin
from src.auth.setup import init_auth
from src.utils import DEVELOPMENT
from src.utils.cache import (
    cache,
    cache_dir_par_defaut,
    cache_threshold_par_defaut,
)
from src.utils.chatwoot import (
    build_identity_script,
    build_reset_script,
    build_widget_script,
    subscription_attributes,
)
from src.utils.matomo import avertir_si_config_incomplete, build_tracker_script

load_dotenv()

# Appelé ici, après load_dotenv() et non à l'import de src.utils.matomo : la
# garde y lit os.environ, qui ne contient pas encore les variables du .env au
# moment où ce module est importé (ligne 45, avant le load_dotenv() ci-dessus).
# Un appel au chargement du module verrait donc toujours une configuration
# absente et ne s'alerterait jamais — c'est précisément le bug que cette
# fonction existe pour rendre bruyant. Ne pas la redéplacer dans matomo.py.
avertir_si_config_incomplete()

# if os.getenv("PYTEST_CURRENT_TEST"):
#     os.environ["DATA_FILE_PARQUET_PATH"]

META_TAGS = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {
        "name": "keywords",
        "content": "commande publique, decp, marchés publics, données essentielles, colibre",
    },
    # og:title/description/image/twitter:* sont générées par page (register_page),
    # celles-ci sont statiques et communes à toutes les pages.
    {"property": "og:site_name", "content": "colibre"},
    {"property": "og:locale", "content": "fr_FR"},
    {"property": "og:image:width", "content": "1200"},
    {"property": "og:image:height", "content": "630"},
]

if DEVELOPMENT:
    META_TAGS.append({"name": "robots", "content": "noindex"})

# Le cache doit être initialisé AVANT la construction de Dash : `use_pages=True`
# importe les modules de pages pendant l'instanciation, et certains appellent des
# fonctions memoizées (@cache.memoize) dès l'import (ex. tableau.py).
server = Flask(__name__)

# nginx transmet X-Forwarded-Proto (voir deploy/nginx-colibre.conf) ; sans ce
# middleware Flask croit servir en http et le canonical pointerait vers une URL
# qui redirige. x_host=0 : nginx ne transmet PAS X-Forwarded-Host (voir le même
# fichier), donc le faire lire par ProxyFix reviendrait à faire confiance à
# l'en-tête Host envoyé par le client — un client malveillant pourrait alors
# faire servir un canonical pointant vers un domaine tiers.
server.wsgi_app = ProxyFix(server.wsgi_app, x_proto=1, x_host=0)

cache_dir = cache_dir_par_defaut()

# En production la purge est faite une seule fois par le master gunicorn (hook
# `on_starting`, cf. gunicorn.conf.py) : la rejouer ici la ferait exécuter par
# CHAQUE worker à son import, donc à chaque recyclage `max_requests`, et le
# cache partagé ne survivrait jamais plus que la vie d'un worker.
#
# Reste le développement (`uv run run.py`), sans master gunicorn, où repartir
# d'un cache propre à chaque lancement évite de traîner des valeurs produites
# par du code qu'on vient de modifier. La variable est relue ici plutôt que via
# la constante DEVELOPMENT de src.utils : celle-ci est figée à l'import du
# module, en amont du load_dotenv() ci-dessus, donc aveugle au .env.
if os.getenv("DEVELOPMENT", "False").lower() == "true":
    rmtree(cache_dir, ignore_errors=True)

cache.init_app(
    server,
    config={
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": cache_dir,
        "CACHE_DEFAULT_TIMEOUT": int(
            os.getenv("CACHE_DEFAULT_TIMEOUT", 3600 * 24)
        ),  # 24h par défaut
        # Voir cache_threshold_par_defaut() : seuil relevé (300 000 par défaut,
        # pilotable via CACHE_THRESHOLD) pour ne pas évincer la mémoïsation des
        # 242 005 SIRET de l'Annuaire des entreprises pendant le crawl SEO.
        "CACHE_THRESHOLD": cache_threshold_par_defaut(),
    },
)

_mcp_enabled = os.getenv("DASH_MCP_ENABLED", "").lower() == "true"

app: Dash = Dash(
    server=server,
    # name="src" (et non "src.app") pour que use_pages enregistre les pages sous
    # le namespace `src.pages.*`, identique aux imports inter-pages (ex.
    # inscription.py: `from src.pages.connexion import linkedin_button`). Sinon
    # Dash découvre `pages.connexion` tandis que l'import explicite crée
    # `src.pages.connexion` : deux identités, même URL → "duplicate paths" →
    # check_for_duplicate_pathnames lève à chaque requête → 500 sur toute l'app.
    name="src",
    title="Colibre",
    use_pages=True,
    suppress_callback_exceptions=True,
    compress=True,
    enable_mcp=_mcp_enabled,
    meta_tags=META_TAGS,
)

init_auth(app.server)

# Exempter les routes internes de Dash de la protection CSRF.
# Dash enregistre ses routes directement sur le serveur Flask (pas via blueprint),
# donc on itère la url_map après init_auth pour cibler les bons endpoints.
from src.auth.setup import _csrf as _auth_csrf  # noqa: E402

if _auth_csrf is not None:
    for _rule in app.server.url_map.iter_rules():
        if _rule.rule.startswith("/_dash") or _rule.rule.startswith("/_reload"):
            _vf = app.server.view_functions.get(_rule.endpoint)
            if _vf is not None:
                _auth_csrf.exempt(_vf)

from src.api import init_api  # noqa: E402  # inline: src.db.conn must be ready first

init_api(app.server)

# Serveur MCP (issue #111, scope A) : n'expose QUE les fonctions @mcp_enabled,
# jamais les callbacks/layout/pages d'UI. Activé via DASH_MCP_ENABLED=true.
if _mcp_enabled:
    from dash.mcp import configure_mcp_server  # noqa: E402

    configure_mcp_server(
        include_layout=False,
        include_callbacks=False,
        include_pages=False,
        include_clientside_callbacks=False,
    )
    import src.mcp.tools  # noqa: E402,F401  # l'import enregistre les @mcp_enabled

    # Les routes /_mcp existent maintenant : exempter du CSRF (POST JSON-RPC
    # externe sans jeton) puis brancher le garde d'abonnement.
    from src.mcp.auth import init_mcp_auth  # noqa: E402

    if _auth_csrf is not None:
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule.startswith("/_mcp"):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)

    init_mcp_auth(app.server)

    # Serveur d'autorisation OAuth 2.1 (scope B2, #114) : découverte, DCR,
    # authorize/token, révocation. Réutilise la session flask_login.
    from src.mcp import usage  # noqa: E402
    from src.mcp.oauth import routes as oauth_routes  # noqa: E402
    from src.mcp.oauth import store as oauth_store  # noqa: E402

    _users_db = os.environ["USERS_DB_PATH"]
    oauth_store.init_schema(_users_db)
    usage.init_schema(_users_db)
    usage.purge_older_than(_users_db)

    oauth_routes.init_oauth(app.server)

    # Exempter du CSRF les endpoints OAuth machine-à-machine (POST externes sans
    # cookie) et les documents de découverte (GET). /oauth/authorize N'EST PAS
    # exempté : endpoint de consentement authentifié par cookie de session, donc
    # protégé par CSRF via un jeton dans le formulaire de consentement.
    if _auth_csrf is not None:
        _csrf_exempt_oauth = ("/oauth/token", "/oauth/register", "/oauth/revoke")
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule in _csrf_exempt_oauth or _rule.rule.startswith(
                "/.well-known/"
            ):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)

from src.subscriptions.setup import init_subscriptions  # noqa: E402

init_subscriptions(app.server)

from src.saved_views import db as saved_views_db  # noqa: E402

saved_views_db.init_schema()

from src.roadmap import db as roadmap_db  # noqa: E402

roadmap_db.init_schema()

from src.mcp.account import mcp_account_bp  # noqa: E402

app.server.register_blueprint(mcp_account_bp)

# Pages SEO rendues côté serveur (voir src/seo/routes.py). Enregistrées avant
# init_not_found pour être de vraies règles Flask, donc hors du catch-all Dash.
from src.seo.routes import seo_bp  # noqa: E402

app.server.register_blueprint(seo_bp)


# Ancienne section « À propos », renommée en « Le projet » : redirige les URLs
# /a-propos/* déjà indexées ou partagées vers leur équivalent /projet/*.
@app.server.route("/a-propos")
def _redirect_a_propos_racine():
    return redirect("/projet", code=301)


@app.server.route("/a-propos/<path:sous_chemin>")
def _redirect_a_propos(sous_chemin: str):
    return redirect(f"/projet/{sous_chemin}", code=301)


# 404 sur les chemins qui ne correspondent à aucune page (#125). À déclarer
# après les autres routes : le garde ne s'applique qu'au catch-all de Dash, donc
# toute route enregistrée ici ou plus haut lui échappe par construction.
from src.not_found import init_not_found  # noqa: E402

init_not_found(app.server)


# robots.txt
def _build_robots_txt(development: bool) -> str:
    """Contenu du robots.txt, selon l'environnement.

    Les instances non-prod (test.colibre.fr, dev) sont interdites d'indexation
    dans leur intégralité, pour ne pas concurrencer colibre.fr dans les résultats
    de recherche avec du contenu dupliqué. Complète la meta `robots: noindex`
    ajoutée aux META_TAGS : le Disallow empêche l'exploration, la meta empêche
    l'indexation des URLs découvertes par ailleurs (liens entrants).
    """
    if development:
        return """
User-agent: *
Disallow: /
"""
    return """
User-agent: meta-externalagent
User-agent: dotbot
User-agent: Bytespider
User-agent: Baiduspider
User-agent: ClaudeBot
Disallow: /

User-agent: *
Allow: /
Sitemap: https://colibre.fr/sitemap.xml
"""


@app.server.route("/robots.txt")
def robots():
    return Response(_build_robots_txt(DEVELOPMENT), mimetype="text/plain")


# Index de sitemaps + sous-sitemaps paginés (voir src.utils.sitemap).
from src.utils import sitemap as _sitemap  # noqa: E402  # src.db doit être prêt


@app.server.route("/sitemap.xml")
def sitemap():
    return Response(_sitemap.build_index(), mimetype="application/xml")


@app.server.route("/sitemap-pages.xml")
def sitemap_pages():
    return Response(_sitemap.build_pages(), mimetype="application/xml")


@app.server.route("/sitemap-arbre.xml")
def sitemap_arbre():
    return Response(_sitemap.build_arbre(), mimetype="application/xml")


@app.server.route("/sitemap-<segment>-<int:page>.xml")
def sitemap_org(segment: str, page: int):
    xml = _sitemap.build_org_page(segment, page)
    if xml is None:
        return Response("Not found", status=404)
    return Response(xml, mimetype="application/xml")


@app.server.route("/llms.txt")
def llms():
    return redirect("/assets/llms.md")


_WELL_KNOWN_DIR = Path(__file__).parent / "assets" / ".well-known"


@app.server.route("/.well-known/<path:filename>")
def well_known(filename: str):
    return send_from_directory(_WELL_KNOWN_DIR, filename)


# Fichier .ics d'une rencontre (voir src.rencontres). La route appelle
# openagenda.fetch_rencontres() via le module pour rester monkeypatchable.
from src.rencontres import openagenda as _openagenda  # noqa: E402
from src.rencontres.calendrier import ics_evenement as _ics_evenement  # noqa: E402


@app.server.route("/rencontres/<uid>.ics")
def rencontre_ics(uid: str):
    for ev in _openagenda.fetch_rencontres():
        if ev.uid == uid:
            return Response(
                _ics_evenement(ev),
                mimetype="text/calendar",
                headers={
                    "Content-Disposition": f'attachment; filename="rencontre-{uid}.ics"'
                },
            )
    return Response("Not found", status=404)


with open("./pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)
    version = "v" + pyproject["project"]["version"]

# Widget de chat Chatwoot (essai, issue #120) : chaîne vide si la variable
# d'env n'est pas définie, ce qui désactive le widget (utilisé notamment
# pour ne jamais le charger pendant les tests/CI).
chatwoot_script = build_widget_script(os.getenv("CHATWOOT_WEBSITE_TOKEN"))

# Traqueur Matomo (src/utils/matomo.py) : chaîne vide si MATOMO_TRACKING_ENABLED
# n'est pas "true" (mis à "false" pendant les tests, pyproject.toml). Le même
# fragment est servi par les pages SEO SSR (src/templates/seo_liste.html, via
# le context_processor de src/seo/routes.py) : une seule source, pas de
# duplication du bloc <script>.
matomo_script = build_tracker_script()

app.index_string = """
<!DOCTYPE html>
<html lang="fr">
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="shortcut icon" href="/assets/icons/favicon.ico">
        <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
        <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32x32.png">
        <link rel="icon" type="image/png" sizes="16x16" href="/assets/icons/favicon-16x16.png">
        <link rel="manifest" href="/assets/icons/site.webmanifest">
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        __MATOMO_SCRIPT__
        __CHATWOOT_SCRIPT__
    </body>
</html>
""".replace("__MATOMO_SCRIPT__", matomo_script).replace(
    "__CHATWOOT_SCRIPT__", chatwoot_script
)

# Dash génère automatiquement twitter:url par page (via register_page), mais pas
# og:url : on l'injecte ici à partir de l'URL de la requête en cours. Ce point
# d'interpolation, appelé par requête, sert aussi à poser le <title> (Dash le
# résout déjà par page pour ses balises sociales, cf. src/utils/page_meta.py,
# mais passe app.title à {%title%}) et le canonical (auparavant posé côté
# client par un script, désormais servi directement dans le HTML).
_default_interpolate_index = app.interpolate_index


def _org_jsonld_tag(path: str) -> str:
    """Balise JSON-LD servie pour les fiches acheteur et titulaire.

    Chaîne vide pour tout autre chemin : le JSON-LD Organization n'a de sens
    que sur une fiche d'organisme. Filtre uniquement sur des DataFrames Polars
    déjà chargés en mémoire (DF_ACHETEURS/DF_TITULAIRES) : aucune requête base
    ni appel réseau, cette fonction tourne à chaque requête HTTP.
    """
    import json

    import polars as pl

    from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
    from src.utils.seo import make_org_jsonld_minimal

    segments = path.strip("/").split("/")
    if len(segments) != 2:
        return ""
    segment, org_id = segments
    org_type = {"acheteurs": "acheteur", "titulaires": "titulaire"}.get(segment)
    if not org_type:
        return ""

    df = DF_ACHETEURS if org_type == "acheteur" else DF_TITULAIRES
    row = df.filter(pl.col(f"{org_type}_id") == org_id)
    if row.height == 0:
        return ""
    nom = row.select(f"{org_type}_nom").item(0, 0)

    # NE PAS échapper en HTML : markupsafe.escape transformerait les guillemets
    # du JSON en &quot; et rendrait le bloc illisible pour un parseur. Le seul
    # risque réel dans un <script> est une séquence `</script>` dans une valeur ;
    # neutraliser `<` en < suffit, et reste du JSON valide.
    payload = json.dumps(
        make_org_jsonld_minimal(org_id, org_type, nom), ensure_ascii=False
    ).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


def _interpolate_index_per_request(**kwargs):
    from flask import request as _request
    from markupsafe import escape as _escape

    og_url_tag = f'<meta property="og:url" content="{_escape(_request.url)}"/>'
    kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {og_url_tag}"

    from src.utils.page_meta import resolve_title

    titre = resolve_title(_request.path)
    if titre:
        kwargs["title"] = str(_escape(titre))

    canonical_tag = f'<link rel="canonical" href="{_escape(_request.base_url)}"/>'
    kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {canonical_tag}"

    jsonld_tag = _org_jsonld_tag(_request.path)
    if jsonld_tag:
        kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {jsonld_tag}"

    # Identité Chatwoot : le chargement du widget est figé dans index_string
    # (même token pour tout le monde), mais setUser dépend de la session, donc
    # il se pose ici, par requête. La connexion et la déconnexion passent par
    # des routes Flask avec redirection — donc par un vrai rechargement de page
    # —, ce qui suffit à resynchroniser l'identité malgré la navigation SPA.
    if chatwoot_script:
        if current_user.is_authenticated:
            identity = build_identity_script(
                current_user.id,
                current_user.email,
                os.getenv("CHATWOOT_HMAC_TOKEN"),
                custom_attributes=subscription_attributes(current_user.id),
            )
        elif _request.args.get("deconnexion") or _request.args.get("account_deleted"):
            identity = build_reset_script()
        else:
            identity = ""
        if identity:
            kwargs["scripts"] = f"{kwargs.get('scripts', '')}\n        {identity}"

    return _default_interpolate_index(**kwargs)


app.interpolate_index = _interpolate_index_per_request

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            dbc.NavItem(
                children=[
                    html.Div(
                        [
                            dcc.Link(html.H1("colibre"), href="/", className="logo"),
                            html.P(
                                [
                                    html.A(
                                        version,
                                        href="/projet/roadmap#versions",
                                    )
                                ],
                                className="version",
                            ),
                        ],
                        className="logo-wrapper",
                    )
                ],
                style={"minWidth": "230px"},
            ),
            dbc.Nav(
                children=[
                    dcc.Markdown(
                        os.getenv("ANNOUNCEMENTS"),
                        id="announcements",
                        dangerously_allow_html=True,
                    ),
                ],
                style={
                    "maxWidth": "1200px",
                    "display": "inline-block",
                },
                navbar=True,
                id="announcements-nav",
            ),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavItem(
                            dbc.NavLink(
                                page["name"].replace(" ", " "),
                                href=page["relative_path"] + "/presentation"
                                if page["name"] == "Le projet"
                                else page["relative_path"],
                                active="exact",
                            )
                        )
                        for page in page_registry.values()
                        if page["name"]
                        in ["Recherche", "Le projet", "Tableau", "Observatoire"]
                    ]
                    + [
                        html.Div(id="auth-nav-slot"),
                        # Créneau distinct plutôt qu'un second élément dans
                        # `auth-nav-slot` : les NavItem rendent des <li>, et
                        # deux <li> dans un même <div> s'empileraient
                        # verticalement. `navbar-nav` étant en flex, deux <div>
                        # frères sont deux éléments côte à côte.
                        html.Div(id="admin-nav-slot"),
                    ],
                    className="ms-auto",
                    navbar=True,
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
    ),
    color="light",
    dark=False,
    className="mb-4",
    expand="lg",
)

app.layout = html.Div(
    [
        dcc.Store(id="csrf-token"),
        navbar,
        dbc.Container(
            page_container,
            fluid=True,
            id="page-content-container",
            className="mb-4",
        ),
    ]
)


@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


_AUTH_PAGES = (
    "/connexion",
    "/inscription",
    "/mot-de-passe-oublie",
    "/verification-email",
)


@callback(
    Output("auth-nav-slot", "children"),
    Input("auth-nav-slot", "id"),
    Input("_pages_location", "pathname"),
)
def _auth_nav(_, pathname=None):
    """« Mon compte » ouvre la liste des sections plutôt que de naviguer (#133).

    Les entrées viennent de `visible_sections`, la même source que la barre
    latérale de l'espace compte : les deux navigations ne peuvent pas diverger,
    et une section réservée est masquée plutôt que grisée.

    Import local : `src.pages._compte_shell` fait partie des pages, découvertes
    par `use_pages` après l'exécution de ce module.
    """
    if not current_user.is_authenticated:
        href = "/connexion"
        if pathname and pathname not in _AUTH_PAGES:
            href += f"?next={pathname}"
        return dbc.NavItem(
            dbc.NavLink(
                [html.Span("Espace"), html.Br(), html.Span("abonné")],
                href=href,
                style={
                    "color": "var(--primary-color-text)",
                    "textAlign": "center",
                    "display": "flex",
                    "flexDirection": "column",
                    "justifyContent": "center",
                    "lineHeight": "1.2",
                    "height": "100%",
                    "paddingTop": "10px",
                    "paddingBottom": "10px",
                    "paddingLeft": "12px",
                },
            )
        )

    from src.pages._compte_shell import (
        current_user_has_subscription,
        logout_form,
        visible_sections,
    )

    sections = [
        dbc.DropdownMenuItem(section["label"], href=section["href"])
        for section in visible_sections(current_user_has_subscription())
    ]
    return dbc.DropdownMenu(
        label="Mon compte",
        nav=True,
        in_navbar=True,
        # Le menu est en bout de navbar (`ms-auto`) : aligné à gauche, il
        # déborderait de la fenêtre.
        align_end=True,
        toggle_style={"color": "var(--primary-color-text)"},
        children=sections
        + [
            dbc.DropdownMenuItem(divider=True),
            logout_form("navbar-logout", "dropdown-item"),
        ],
    )


@callback(
    Output("admin-nav-slot", "children"),
    Input("admin-nav-slot", "id"),
)
def _admin_nav(_):
    """Raccourci vers le panneau admin, réservé à ADMIN_EMAIL.

    Simple ergonomie : `/admin` revérifie `is_admin()` dans son layout ET dans
    ses callbacks (issue #110), donc masquer ce lien ne protège rien — c'est la
    page qui protège.

    Même déclencheur que `_auth_nav` (`Input(<slot>, "id")`) : il se joue au
    chargement de page, ce qui suffit puisque connexion et déconnexion passent
    par des routes Flask avec redirection, donc par un vrai rechargement.
    """
    if not is_admin():
        return None
    return dbc.NavItem(dbc.NavLink("Administration", href="/admin"))


@callback(
    Output("csrf-token", "data"),
    Input("_pages_location", "pathname"),
    Input("auth-nav-slot", "children"),
)
def _generate_csrf_token(*_):
    from flask_wtf.csrf import generate_csrf

    return generate_csrf()


@callback(
    Output({"type": "csrf-input", "index": ALL}, "value"),
    Input("csrf-token", "data"),
)
def _fill_csrf_inputs(token):
    return [token] * len(ctx.outputs_list)


# Préchauffage du registre de ressources, à l'import donc AVANT que gunicorn ne
# serve la moindre requête.
#
# Dash ne remplit `app.registered_paths` (la liste blanche de /_dash-component-
# suites) que dans _generate_scripts_html, appelé par le before_request
# `_setup_server`. Or _setup_server pose son drapeau `_got_first_request` AVANT
# de faire le travail, et sans verrou : sur un worker gthread neuf, un 2e thread
# qui arrive pendant ce laps de temps saute l'initialisation et lit un registre
# à moitié construit. Le renderer demandant plotly.js à une URL codée en dur et
# sans empreinte (`_dash-component-suites/plotly/package_data/plotly.min.js`,
# cf. dash_renderer.min.js), la course se manifeste par des 500 « "plotly" is
# not a registered library » quelques secondes après chaque recyclage de worker
# (max_requests), comme observé sur test.colibre.fr du 23 au 29/07/2026.
#
# Ces deux méthodes sont idempotentes (rejouées à chaque rendu de page), donc
# les appeler ici ne fait qu'avancer le remplissage du registre.
app._generate_scripts_html()
app._generate_css_dist_html()
