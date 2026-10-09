from dash.mcp import mcp_enabled

from src.mcp import queries
from src.mcp.queries import ColonneMarche
from src.utils.tracking import track_mcp_tool


@mcp_enabled(name="rechercher_organisations", expose_docstring=True)
def rechercher_organisations(
    query: str,
    type: str = "acheteur",
    limite: int = 20,  # noqa: A002
) -> list[dict]:
    """Recherche des acheteurs ou titulaires publics par nom.

    Utiliser en premier pour résoudre un nom d'organisation vers son
    identifiant, à passer ensuite à stats_acheteur / stats_titulaire.

    query: texte libre (nom d'organisation).
    type: "acheteur" ou "titulaire".
    Retourne une liste de {id, nom, departement}.
    """
    track_mcp_tool("rechercher_organisations", query=query)
    return queries.search_organisations(query, type, limite)


@mcp_enabled(name="stats_acheteur", expose_docstring=True)
def stats_acheteur(acheteur_id: str) -> dict:
    """Statistiques agrégées d'un acheteur public (par identifiant).

    Retourne nombre de marchés, montant total, répartition annuelle,
    principaux titulaires et principaux codes CPV.
    """
    track_mcp_tool("stats_acheteur")
    return queries.compute_org_stats("acheteur", acheteur_id)


@mcp_enabled(name="stats_titulaire", expose_docstring=True)
def stats_titulaire(titulaire_id: str) -> dict:
    """Statistiques agrégées d'un titulaire (entreprise) par identifiant.

    Retourne nombre de marchés remportés, montant total, répartition
    annuelle, principaux acheteurs et principaux codes CPV.
    """
    track_mcp_tool("stats_titulaire")
    return queries.compute_org_stats("titulaire", titulaire_id)


@mcp_enabled(name="schema_donnees", expose_docstring=True)
def schema_donnees() -> dict:
    """Schéma des données marchés (DECP) pour construire des filtres.

    À consulter avant d'utiliser `filtres_avances` de rechercher_marches.
    - colonnes_filtrables : {colonne: {type, titre, description}}, utilisables
      comme "colonne__operateur" (la description inclut les valeurs possibles).
    - colonnes_retournees : colonnes présentes dans chaque marché renvoyé.
    - operateurs : opérateurs de filtre valides (exact, contains, greater, less,
      in, isnull, sort…). L'agrégation n'est pas supportée ici (API REST /data).
    - filtres_nommes : correspondance paramètre nommé -> "colonne__operateur".
    """
    track_mcp_tool("schema_donnees")
    return queries.describe_schema()


@mcp_enabled(name="rechercher_marches", expose_docstring=True)
def rechercher_marches(
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    page_size: int = 50,
    filtres_avances: dict | None = None,
    colonnes: list[ColonneMarche] | None = None,
) -> dict:
    """Recherche paginée de marchés publics (DECP).

    Filtres nommés : acheteur_id, titulaire_id, cpv (code CPV, filtre par
    préfixe — ex. « 72 » = informatique, « 7220 » = logiciels),
    objet_contient (texte de l'objet), montant_min, montant_max,
    date_min / date_max (format YYYY-MM-DD, sur dateNotification),
    departement (code département de l'acheteur).
    filtres_avances : dict optionnel {"colonne__operateur": valeur} pour les
    besoins pointus. Colonnes et opérateurs disponibles via l'outil
    schema_donnees().
    colonnes : liste optionnelle de colonnes à renvoyer. Par défaut, un jeu
    standard (uid, objet, montant, dateNotification, codeCPV, acheteur_id,
    acheteur_nom, acheteur_departement_code, titulaire_id, titulaire_nom). Si
    fournie, REMPLACE le jeu par défaut (le champ uid reste toujours présent).
    Colonnes disponibles via schema_donnees().colonnes_disponibles.
    Chaque marché renvoyé contient en plus un champ `lien` (URL de la fiche
    marché sur colibre).
    page : numéro de page.
    page_size : nombre de résultats par page (défaut 50, max 1000 ;
    erreur si hors [1, 1000]).
    Retourne {meta: {page, page_size, total}, marches: [...]}.
    """
    track_mcp_tool("rechercher_marches", query=objet_contient)
    return queries.search_marches(
        acheteur_id=acheteur_id,
        titulaire_id=titulaire_id,
        cpv=cpv,
        objet_contient=objet_contient,
        montant_min=montant_min,
        montant_max=montant_max,
        date_min=date_min,
        date_max=date_max,
        departement=departement,
        page=page,
        page_size=page_size,
        filtres_avances=filtres_avances,
        colonnes=colonnes,
    )
