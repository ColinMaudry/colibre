import threading
import uuid
from time import localtime

from httpx import post

from src.utils import logger
from src.utils.matomo import matomo_config, tracking_enabled

# Un seul warning par processus (et non par requête) : le logger "colibre"
# n'est relevé à DEBUG que sous DEVELOPMENT=true (src/utils/__init__.py), donc
# un logger.debug ici serait filtré en production — silence total sur une
# panne Matomo durable, exactement ce que cette branche corrige par ailleurs.
# Un logger.warning à chaque requête inonderait les journaux en cas de panne
# prolongée ; un seul suffit à donner le signal. Ne pas "corriger" ce drapeau
# pour réémettre à chaque échec : c'est voulu.
_echec_signale = False


def _envoyer(params: dict) -> None:
    """POST best-effort vers la Tracking API Matomo. Ne lève jamais.

    `data=` et non `params=` : la charge utile passe dans le corps de la requête
    plutôt que dans la query string, où elle atterrirait dans les journaux
    d'accès du serveur Matomo.

    Aucun `token_auth` : l'endpoint matomo.php est public par construction —
    c'est celui qu'appelle le matomo.js de chaque visiteur. Le token n'est
    requis que pour les paramètres privilégiés (cip, cdt au-delà de ~24 h,
    country/region/city/lat/long), qu'aucun émetteur du projet n'utilise.
    """
    if not tracking_enabled():
        return
    config = matomo_config()
    if config is None:
        return
    url, site_id = config
    try:
        # timeout court : track_search s'exécute de façon synchrone dans une
        # recherche utilisateur (src/utils/search.py), un Matomo qui pend ne
        # doit pas ajouter sa latence à la requête de l'utilisateur.
        post(url=url, data={**params, "idsite": site_id}, timeout=2.0)
    except Exception:  # noqa: BLE001
        # Ne propage jamais (invariant de ce module), mais avertit une fois
        # par processus — cf. commentaire sur _echec_signale ci-dessus.
        global _echec_signale
        if not _echec_signale:
            logger.warning("Matomo : échec d'envoi", exc_info=True)
            _echec_signale = True


def _horodatage() -> dict:
    maintenant = localtime()
    return {
        "rand": uuid.uuid4().hex,
        "apiv": "1",
        "h": maintenant.tm_hour,
        "m": maintenant.tm_min,
        "s": maintenant.tm_sec,
    }


def track_search(query, category):
    """Enregistre une recherche dans Matomo (best-effort)."""
    if len(query) < 4:
        return
    _envoyer(
        {
            "rec": "1",
            "url": "https://colibre.fr",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "search": query,
            **_horodatage(),
        }
    )


def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    """Enregistre un appel d'outil MCP dans Matomo (best-effort).

    `action_name="MCP / <tool>"`, `dimension1=<tool>`. Si l'outil porte une
    requête texte, elle est envoyée en `search`. Nécessite un Custom Dimension
    slot 1 (scope Action) configuré côté Matomo — sinon `dimension1` est ignoré.
    """
    params = {
        "rec": "1",
        "url": "https://colibre.fr/_mcp",
        "action_name": f"MCP / {tool_name}",
        "dimension1": tool_name,
        **_horodatage(),
    }
    if query:
        params["search"] = query
        params["search_cat"] = "mcp"
    _envoyer(params)


def _envoyer_async(params: dict) -> threading.Thread | None:
    """Envoie en tâche de fond et retourne le thread (pour que les tests joignent).

    Un POST synchrone retarderait de plusieurs secondes la réponse 200 au
    webhook Frisbii, qui pourrait alors considérer la livraison en échec et
    réessayer — donc émettre l'événement en double.

    `threading.Thread(...).start()` peut lever (ex. RuntimeError sous
    épuisement de ressources) : sans ce try/except, l'exception remonterait
    jusqu'à `update_from_webhook` (src/subscriptions/db.py), ferait répondre
    500 à Frisbii, et déclencherait un nouvel essai — rejouant la transaction
    et l'événement. Aucun émetteur ne doit jamais lever.
    """
    try:
        thread = threading.Thread(target=_envoyer, args=(params,), daemon=True)
        thread.start()
    except Exception:  # noqa: BLE001
        logger.debug("Matomo : échec de démarrage du thread d'envoi", exc_info=True)
        return None
    return thread


def track_subscription_goal(
    action: str, plan: str | None = None, revenue: float | None = None
) -> None:
    """Événement de conversion d'abonnement.

    N'émet en pratique que `subscription_active` : c'est l'unique valeur
    passée par son seul site d'appel en production (src/subscriptions/db.py).
    `subscription_trial` est émis séparément, côté navigateur, par
    `src/assets/goals.js`, sans passer par cette fonction. Le paramètre
    `action` reste un point d'entrée explicite plutôt qu'une valeur figée.

    Sous TOUS_ABONNES, l'accès est offert et la souscription payante est
    désactivée : aucun essai ni abonnement ne doit être comptabilisé. L'import
    est fait dans le corps de la fonction, comme dans src/subscriptions/db.py:347 —
    la constante est figée à l'import de src.utils, donc seul l'import différé
    rend effectif le monkeypatch.setattr("src.utils.TOUS_ABONNES", …) des tests.
    """
    from src.utils import TOUS_ABONNES

    if TOUS_ABONNES:
        return
    params = {
        "rec": "1",
        "url": "https://colibre.fr/compte/abonnement",
        "e_c": "Abonnement",
        "e_a": action,
        **_horodatage(),
    }
    if plan:
        params["e_n"] = plan
    if revenue is not None:
        params["e_v"] = revenue
    _envoyer_async(params)
