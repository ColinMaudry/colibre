"""Suivi Matomo des actions des visiteurs, émis par le navigateur.

Les callbacks écrivent un événement dans le store `STORE_ID` ; un callback
client le transmet à `window._paq` s'il existe. Aucun identifiant Colibre
n'est envoyé.
"""

import uuid

from dash import set_props

STORE_ID = "suivi-matomo"
LONGUEUR_MAX_FILTRES = 500


def emettre(
    categorie: str,
    action: str,
    nom: str | None = None,
    valeur: int | float | None = None,
) -> None:
    """Écrit un événement Matomo dans le store (nonce : deux envois identiques restent distincts)."""
    set_props(
        STORE_ID,
        {
            "data": {
                "type": "evenement",
                "categorie": categorie,
                "action": action,
                "nom": nom,
                "valeur": valeur,
                "nonce": uuid.uuid4().hex,
            }
        },
    )


def emettre_recherche(mot_cle: str, categorie: str, nb_resultats: int) -> None:
    """Écrit une recherche (Site search Matomo) dans le store."""
    set_props(
        STORE_ID,
        {
            "data": {
                "type": "recherche",
                "mot_cle": mot_cle,
                "categorie": categorie,
                "nb_resultats": nb_resultats,
                "nonce": uuid.uuid4().hex,
            }
        },
    )


def _est_vide(valeur: object) -> bool:
    return valeur is None or valeur == "" or valeur == []


def _formater(cle: str, valeur: object) -> str:
    if isinstance(valeur, list):
        return f"{cle} [{', '.join(sorted(str(v) for v in valeur))}]"
    if isinstance(valeur, str):
        return f'{cle} = "{valeur}"'
    if isinstance(valeur, bool):
        return f"{cle} = {'true' if valeur else 'false'}"
    return f"{cle} = {valeur}"


def serialiser_filtres_observatoire(filtres: dict[str, object]) -> tuple[str, int]:
    """Chaîne stable (clés triées, tronquée à 500 caractères) et nombre de filtres non vides."""
    parties = [
        _formater(cle, valeur)
        for cle, valeur in sorted(filtres.items())
        if not _est_vide(valeur)
    ]
    chaine = " | ".join(parties)
    if len(chaine) > LONGUEUR_MAX_FILTRES:
        chaine = chaine[: LONGUEUR_MAX_FILTRES - 1] + "…"
    return chaine, len(parties)
