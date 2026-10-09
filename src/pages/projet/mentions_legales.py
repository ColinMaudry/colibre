from dash import dcc, html, register_page

from src.pages._projet_shell import projet_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/projet/mentions-legales",
    title="Conditions d'utilisation et mentions légales | Le projet | colibre",
    description=(
        "Conditions d'utilisation de colibre et mentions légales : éditeur, "
        "hébergement, responsabilité, données personnelles, suivi d'audience."
    ),
    image_url=META_CONTENT["image_url"],
)


def _conditions_utilisation():
    return html.Div(
        [
            html.H3("Conditions d'utilisation", id="conditions-utilisation"),
            html.H4("Objet et acceptation", id="cu-objet"),
            dcc.Markdown(
                """
colibre est un service d'exploration des données de la commande publique française, édité par SAS Colmo (voir [Publication](#publication)).

L'utilisation du site vaut acceptation des présentes conditions d'utilisation.

Les fonctionnalités de base sont accessibles gratuitement et sans inscription. Certaines fonctionnalités nécessitent un compte et un abonnement : elles sont régies par les [conditions d'abonnement](/projet/abonnement), distinctes des présentes conditions.
"""
            ),
            html.H4("Compte utilisateur", id="cu-compte"),
            dcc.Markdown(
                """
La création d'un compte requiert une adresse e-mail valide. Vous êtes responsable de la confidentialité de vos identifiants et des actions effectuées depuis votre compte.

Vous pouvez demander la suppression de votre compte à tout moment depuis la [page de contact](/projet/contact).
"""
            ),
            html.H4("Usage du service", id="cu-usage"),
            dcc.Markdown(
                """
colibre est mis à disposition pour une consultation normale. Sont notamment proscrits :

- l'extraction massive automatisée des pages du site ;
- le partage d'un compte entre plusieurs personnes ;
- toute action portant atteinte à la disponibilité ou à la sécurité du service.

Les données sont par ailleurs disponibles en [téléchargement libre](/projet/donnees#donnees-brutes) : merci de les récupérer par ce biais plutôt que par moissonnage du site.

En cas de manquement, l'accès au service peut être suspendu.
"""
            ),
            html.H4("Données affichées", id="cu-donnees"),
            dcc.Markdown(
                """
Les données présentées proviennent des Données Essentielles de la Commande Publique (DECP) publiées par les acheteurs publics, mises à disposition sous [Licence Ouverte](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) et retraitées par colibre.

Elles sont fournies en l'état. colibre s'engage sur une obligation de moyens quant à leur qualité et leur fraîcheur, sans garantie d'exhaustivité ni d'exactitude : celles-ci dépendent de la publication par les acheteurs publics eux-mêmes.

Toute erreur constatée peut être signalée depuis la [page de contact](/projet/contact).
"""
            ),
            html.H4("Disponibilité du service", id="cu-disponibilite"),
            dcc.Markdown(
                """
colibre est accessible en continu, sous réserve des opérations de maintenance et des cas d'indisponibilité indépendants de notre volonté.

Les fonctionnalités du site peuvent évoluer, être ajoutées ou retirées.
"""
            ),
            html.H4("Responsabilité", id="cu-responsabilite"),
            dcc.Markdown(
                """
La responsabilité de Colmo est limitée aux dommages directs résultant d'une faute prouvée.

Sont exclus les dommages indirects (perte d'exploitation, perte de chance, préjudice commercial), les conséquences de l'inexactitude ou de l'absence de mise à jour des données publiées par des tiers, ainsi que les cas de force majeure et les indisponibilités imputables à un tiers (hébergeur, opérateur réseau).
"""
            ),
            html.H4("Données personnelles", id="cu-donnees-personnelles"),
            dcc.Markdown(
                """
Conformément au RGPD, colibre ne recueille que les données strictement nécessaires au bon fonctionnement du site.

**Données stockées par Colmo pour l'administration de colibre :**

- Adresse e-mail (identification du compte)
- Le mot de passe est [haché](https://fr.wikipedia.org/wiki/Fonction_de_hachage_cryptographique#V%C3%A9rification_de_mot_de_passe), donc connu seulement de l'abonné•e
- Numéro SIRET (optionnel, si renseigné, conservé pour pré-remplir les futures souscriptions)

**Conversations en direct depuis le site Web 💬**

Le contenu des conversations est transmis au prestataire Chatwoot et au logiciel Slack. Si vous êtes connecté·e, votre adresse e-mail y est jointe pour vous identifier.

Ces données ne sont pas transmises à des tiers à des fins commerciales. Vous pouvez demander l'accès, la rectification ou la suppression de vos données en [me contactant](/projet/contact).

Les données de facturation et de paiement des abonné·es sont traitées séparément par le prestataire de paiement : voir les [conditions d'abonnement](/projet/abonnement).
"""
            ),
            html.H4("Loi applicable", id="cu-loi"),
            dcc.Markdown(
                """
Les présentes conditions d'utilisation sont soumises au droit français.

En cas de litige, les parties s'efforceront de trouver une solution amiable avant toute action contentieuse.
"""
            ),
        ]
    )


def _mentions_legales():
    return html.Div(
        [
            html.H3("Mentions légales", id="mentions-legales"),
            html.H4("Publication", id="publication"),
            dcc.Markdown(
                """
Site Web développé et administré par [SAS Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350), 989 393 350 RCS Rennes au capital de 3 000 euros, société présidée par Colin Maudry.

Siège social : 1 carrefour Jouaust, 35000 Rennes

Hébergement : serveur situé en France et administré par Scaleway, 8 rue de la Ville l'Evêque, 75008 Paris
"""
            ),
            html.H4("Suivi d'audience", id="audience"),
            dcc.Markdown(
                """
Ce site dépose un petit fichier texte (un « cookie ») sur votre ordinateur lorsque vous le consultez ([Wikipédia](https://fr.wikipedia.org/wiki/Cookie_(informatique))). Cela me permet de mesurer le nombre de visites, de distinguer les nouveaux visiteurs des utilisateurs réguliers et ainsi de communiquer sur l'impact de colibre.

**Ce site n'affiche pas de bannière de consentement aux cookies, pourquoi ?**

C'est vrai, vous n'avez pas eu à cliquer sur un bloc qui recouvre la moitié de la page pour dire que vous êtes d'accord avec le dépôt de cookies.

Rien d'exceptionnel, ce site respecte simplement la loi, qui dit que certains outils de suivi d'audience, correctement configurés pour respecter la vie privée, sont exemptés d'autorisation préalable.

L'outil utilisé pour le suivi d'audience est [Matomo](https://matomo.org/), un [logiciel libre](https://matomo.org/free-software/), paramétré pour être en conformité avec [la recommandation « Cookies »](https://www.cnil.fr/fr/solutions-pour-les-cookies-de-mesure-daudience) de la CNIL. Cela signifie que votre adresse IP, par exemple, est anonymisée avant d'être enregistrée. Il m'est donc impossible d'associer vos visites sur ce site à votre personne.

Les données suivantes sont également enregistrées, de manière anonyme, afin de mieux comprendre comment vous utilisez le site et l'améliorer :

- recherches sur la page d'accueil et nombre de résultats
- combinaisons de filtres appliquées aux données
- téléchargements de données (format et nombre de lignes)
- changements de thème (clair ou sombre) et de mode d'affichage du tableau (lignes ou observatoire)
- réinitialisations des filtres et ouvertures du mode d'emploi
- réorganisation des tuiles de l'observatoire
"""
            ),
            html.H4("Attributions", id="attributions"),
            dcc.Markdown(
                """
Les polices de caractères sont distribuées par [Bunny fonts](https://fonts.bunny.net), une alternative européenne et qualitative à Google Fonts.

- la police de caractère [Inter](https://fonts.bunny.net/family/inter), principale police de ce site, a été créée par The Inter Project Authors ([source](https://github.com/rsms/inter))
- la police de caractère [Fira Code](https://fonts.bunny.net/family/fira-code), la police à largeure fixe, a été créée par The Fira Code Project Authors (https://github.com/tonsky/FiraCode)
"""
            ),
            html.H4("Marchés par département", id="liste_marches"),
            dcc.Markdown("- [Marchés par département](/departements)"),
        ]
    )


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Conditions d'utilisation et mentions légales"),
            _conditions_utilisation(),
            _mentions_legales(),
        ]
    )
    return projet_shell("mentions-legales", contenu)
