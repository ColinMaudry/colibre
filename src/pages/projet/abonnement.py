import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

from src.pages._projet_shell import projet_shell
from src.subscriptions import db as sub_db
from src.subscriptions import plans
from src.utils import TOUS_ABONNES
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/projet/abonnement",
    title="Abonnement | Le projet | colibre",
    description="Conditions d'abonnement à colibre : tarifs, facturation, rétractation et résiliation.",
    image_url=META_CONTENT["image_url"],
)

abonnement_features = dcc.Markdown("""
    - sauvegardez et partagez des **vues** (ensemble de filtres, de tris et de colonnes) dans la page Tableau
    - interrogez les données depuis un agent IA via le **connecteur MCP** (ChatGPT, Claude, Mistral...)
    - personnalisez l'ordre d'affichage des tuiles de l'**Observatoire**
    - projetez les données filtrées de la page Tableau dans les visualisations de l'Observatoire
    - votez pour les fonctionnalités à développer en priorité dans la **roadmap**
    - participez à la pérennité du projet
      """)


def _plan_card(meta: dict):
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"], className="mb-1"),
                html.P(
                    f"{meta['prix_ht']} € HT / mois "
                    f"({round(meta['prix_ht'] * 1.2, 2):g} € TTC)",
                    className="text-muted mb-3",
                ),
                html.P(meta["description"], className="mb-3"),
            ],
            className="p-4",
        ),
        className="h-100",
    )


def _plan_cards():
    # L'essai n'est plus adossé à une formule : il est ouvert à la création du
    # compte, quelle que soit la formule choisie ensuite. D'où une mention
    # unique au-dessus des cartes plutôt qu'un badge par carte.
    cards = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta))
    return html.Div(
        [
            html.P(
                "3 jours d'essai gratuit à la création de votre compte, sans "
                "carte bancaire.",
                className="text-muted mb-3",
            ),
            dbc.Row([dbc.Col(c, md=6) for c in cards], className="g-4 mb-4"),
        ]
    )


def _explainer():
    col_left = dbc.Col(
        [html.H4("Fonctionnalités réservées aux abonné·es :"), abonnement_features],
        md=6,
        style={
            "borderRight": "1px solid var(--bs-border-color)",
            "paddingRight": "2rem",
        },
    )
    col_right = dbc.Col(
        [
            html.H4("Ce que les abonnements permettent"),
            html.Ul(
                [
                    html.Li(
                        "passer plus de temps à développer colibre et moins de temps "
                        "à chercher des missions"
                    ),
                    html.Li(
                        "rédaction d'études à partir des données, par exemple sur les "
                        "acheteurs dont les données sont introuvables et les raisons "
                        "de cette non-publication."
                    ),
                    html.Li(
                        "militer aux côtés des bonnes volontés pour une "
                        "législation plus ambitieuse sur la transparence de la "
                        "commande publique."
                    ),
                ]
            ),
        ],
        md=6,
        style={"paddingLeft": "2rem"},
    )
    return dbc.Row([col_left, col_right], className="align-items-start pt-2 mb-4")


def _subscribe_button(
    authenticated: bool, has_active_subscription: bool, tous_abonnes: bool
):
    if tous_abonnes:
        href = "/compte/abonnement" if authenticated else "/inscription"
        return html.Div(
            [
                dbc.Alert(
                    "Les fonctionnalités normalement accessibles contre un abonnement sont temporairement accessibles gratuitement.",
                    color="info",
                ),
                html.A(
                    "Je crée mon compte",
                    href=href,
                    className="btn btn-secondary",
                ),
            ],
            className="text-center my-4",
        )
    if authenticated and has_active_subscription:
        label, href = "Gérer mon abonnement", "/compte/abonnement"
    elif authenticated:
        label, href = "Je m'abonne", "/compte/abonnement/mes-infos"
    else:
        label, href = (
            "Je crée mon compte et démarre mon essai de 3 jours",
            "/inscription",
        )
    return html.Div(
        html.A(label, href=href, className="btn btn-secondary"),
        className="text-center my-4 btn-lg",
        style={"width": "fit-content", "margin": "auto"},
    )


subscription_terms = html.Div(
    [
        html.H2("Conditions d'abonnement"),
        dcc.Markdown(
            """
L'accès aux fonctionnalités de base de colibre est gratuit et sans inscription. Il est possible de souscrire à un abonnement mensuel qui donne accès à des fonctionnalités supplémentaires.
L'abonnement est souscrit auprès de la société Colmo dont le SIRET est 98939335000016 ([annuaire des entreprises](https://annuaire-entreprises.data.gouv.fr/etablissement/98939335000016)).

Les présentes conditions régissent l'abonnement. L'utilisation du site est par ailleurs régie par les [conditions d'utilisation](/projet/mentions-legales#conditions-utilisation).
"""
        ),
        html.H4("Tarifs"),
        dcc.Markdown(
            """
Deux formules sont proposées :

- **Abonnement** : 20 € HT / mois (soit 24 € TTC)
- **Abonnement de soutien ✊** : 50 € HT / mois (soit 60 € TTC) — mêmes fonctionnalités, contribution renforcée au projet

La TVA applicable en France est de 20 %.
"""
        ),
        html.H4("Début et durée de l'abonnement"),
        dcc.Markdown(
            """
La souscription à un abonnement ouvre immédiatement l'accès aux fonctionnalités réservées aux abonné·es.

**L'abonnement payant démarre à la souscription à un abonnement** : le premier prélèvement a lieu à ce moment-là, toujours via une action manuelle de votre part. L'abonnement est
conclu pour une durée d'un mois à compter de son démarrage, et se renouvelle automatiquement de mois en mois jusqu'à résiliation par l'abonné·e.
"""
        ),
        html.H4("Modes de paiement"),
        dcc.Markdown(
            """
Les cartes bancaires des réseaux Visa et Mastercard sont acceptées, ainsi que Google Pay et Apple Pay de manière expérimentale.

Il est également possible de payer par virement bancaire à condition de payer un an d'abonnement. [Envoyez un message](/projet/contact) avec votre SIRET ou vos coordonnées si vous êtes intéressé·e.
"""
        ),
        html.H4("Période d'essai"),
        dcc.Markdown(
            """
Un essai gratuit de 3 jours est automatiquement ouvert à la création de votre compte, sans carte bancaire et sans engagement. Aucun prélèvement n'a lieu pendant cette période.

À son terme, l'accès aux fonctionnalités réservées est suspendu jusqu'à ce que vous souscriviez à un abonnement.

L'essai est accordé une seule fois par compte.
"""
        ),
        html.H4("Facturation et paiement"),
        dcc.Markdown(
            """
La première facture est émise au démarrage de l'abonnement, c'est-à-dire à la souscription d'un abonnement. Les suivantes le sont automatiquement chaque mois à cette date anniversaire.

Chaque échéance donne lieu à l'émission d'une facture, envoyée par email à l'abonné·e.
Le paiement est traité par [Frisbii](https://www.frisbii.com), prestataire européen de paiement en ligne.
Les coordonnées bancaires sont conservées exclusivement par Frisbii et ne sont pas transmises à colibre.

Le paiement est exigible à la date de facturation et se fait automatiquement si une méthode de paiement a été renseignée. En cas de retard de paiement, des pénalités sont dues au taux de trois fois le taux d'intérêt légal, ainsi qu'une indemnité forfaitaire de 40 € pour frais de recouvrement (art. L441-10 du code de commerce). En cas d'échec du prélèvement, l'accès aux fonctionnalités payantes est suspendu.
"""
        ),
        html.H4("Droit de rétractation"),
        dcc.Markdown(
            """
Vous disposez d'un délai de rétractation de 14 jours à compter de la souscription à un abonnement.

L'accès aux fonctionnalités réservées aux abonné·es étant ouvert dès la souscription à un abonnement, il vous est demandé d'y renoncer expressément à ce moment-là ; à défaut, votre abonnement ne peut pas être finalisé.
"""
        ),
        html.H4("Résiliation"),
        dcc.Markdown(
            """
L'abonnement peut être résilié à tout moment depuis l'espace [Mon compte](/compte/abonnement).
La résiliation prend effet à la fin de la période mensuelle en cours : l'accès aux fonctionnalités payantes est maintenu jusqu'à cette date, sans remboursement au prorata.
"""
        ),
        html.H4("Données recueillies"),
        dcc.Markdown(
            """
La gestion de l'abonnement implique le traitement de données par Frisbii, prestataire de paiement. Conformément au RGPD, seules les données strictement nécessaires à la facturation sont recueillies.

**Données stockées par Frisbii :**

- Informations de facturation : prénom et nom (et nom et SIRET de l'organisme si applicable), adresse postale, code postal, ville, pays
- Informations de paiement : coordonnées bancaires
- Historique des factures

Ces données sont utilisées uniquement pour la gestion de votre abonnement et ne sont pas transmises à des tiers à des fins commerciales.
Vous pouvez demander l'accès, la rectification ou la suppression de vos données en [me contactant](/projet/contact).

Les données recueillies par colibre en dehors de l'abonnement (compte, conversations, suivi d'audience) sont décrites dans les [conditions d'utilisation](/projet/mentions-legales#cu-donnees-personnelles).
"""
        ),
        html.H4("Loi applicable"),
        dcc.Markdown(
            """
Les présentes conditions d'abonnement sont soumises au droit français.

En cas de litige, les parties s'efforceront de trouver une solution amiable avant toute action contentieuse.
"""
        ),
        html.H4("Contact"),
        dcc.Markdown(
            "Pour toute question relative à votre abonnement : [page de contact](/projet/contact)."
        ),
    ]
)


def layout(**_):
    authenticated = current_user.is_authenticated
    has_active = authenticated and sub_db.has_active_subscription(current_user.id)
    body = html.Div(
        [
            _plan_cards(),
            _subscribe_button(authenticated, has_active, TOUS_ABONNES),
            _explainer(),
            subscription_terms,
        ]
    )
    return projet_shell("abonnement", body)
