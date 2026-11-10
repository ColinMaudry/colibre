"""#150 : la recherche d'organismes (accueil `/recherche`, MCP) est insensible
à la casse et aux accents, sur des noms en casse normale accentuée — le format
désormais en production.

`build_org_frame` est exécutée pour de vrai contre une table `decp`
synthétique : c'est elle qui précalcule la colonne de recherche.
"""

import pytest

import src.utils.data as data
from src.utils.search import search_org


@pytest.fixture
def con_decp():
    """Table `decp` synthétique : deux organismes de Nîmes, une autre
    métropole, un nom avec trait d'union."""
    import duckdb

    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE decp ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, acheteur_categorie VARCHAR, "
        "acheteur_departement_nom VARCHAR, acheteur_departement_code VARCHAR, "
        "acheteur_commune_nom VARCHAR)"
    )
    con.executemany(
        "INSERT INTO decp VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("210540000001", "Mairie de Nîmes", "Collectivité", "Gard", "30", "Nîmes"),
            ("210540000002", "Nîmes Métropole", "EPCI", "Gard", "30", "Nîmes"),
            ("330000000001", "Bordeaux Métropole", "EPCI", "Gironde", "33", "Bordeaux"),
            (
                "421000000001",
                "Commune de Saint-Étienne",
                "Collectivité",
                "Loire",
                "42",
                "Saint-Étienne",
            ),
        ],
    )
    return con


@pytest.fixture
def frame_acheteurs(con_decp, monkeypatch):
    monkeypatch.setattr(data, "get_cursor", lambda: con_decp.cursor())
    return data.build_org_frame("acheteur")


@pytest.mark.parametrize(
    ("saisie", "ids_attendus"),
    [
        ("nimes", ["210540000001", "210540000002"]),
        ("Nîmes", ["210540000001", "210540000002"]),
        ("NIMES", ["210540000001", "210540000002"]),
        ("mairie de nîmes", ["210540000001"]),
        ("nîmes métropole", ["210540000002"]),
    ],
)
def test_retrouve_les_organismes_de_nimes(frame_acheteurs, saisie, ids_attendus):
    resultats = search_org(frame_acheteurs, saisie, "acheteur")

    # `add_links` enveloppe les colonnes de HTML : on teste les identifiants
    # par sous-chaînes.
    ids = " ".join(resultats["acheteur_id"])
    assert resultats.height == len(ids_attendus)
    assert all(id_attendu in ids for id_attendu in ids_attendus)


def test_nom_et_departement_doivent_tous_matcher(frame_acheteurs):
    assert search_org(frame_acheteurs, "nimes gard", "acheteur").height == 2
    # Bordeaux est en Gironde : le département ne matche pas.
    assert search_org(frame_acheteurs, "nimes gironde", "acheteur").height == 0


def test_trait_d_union_equivalent_aux_espaces(frame_acheteurs):
    assert search_org(frame_acheteurs, "saint-etienne", "acheteur").height == 1
    assert search_org(frame_acheteurs, "saint etienne", "acheteur").height == 1


def test_saisie_avec_metacaractere_regex_ne_leve_pas(frame_acheteurs):
    """La correspondance est littérale : une saisie contenant `(`, `*`…
    n'est pas une expression régulière."""
    assert search_org(frame_acheteurs, "a(b", "acheteur").height == 0


def test_aucun_resultat(frame_acheteurs):
    assert search_org(frame_acheteurs, "absent", "acheteur").height == 0


def test_colonne_de_recherche_absente_du_resultat(frame_acheteurs):
    from src.utils.text_normalization import COLONNE_RECHERCHE

    resultats = search_org(frame_acheteurs, "nimes", "acheteur")

    assert COLONNE_RECHERCHE not in resultats.columns


def test_frames_reelles_portent_la_colonne_de_recherche():
    from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
    from src.utils.text_normalization import COLONNE_RECHERCHE

    assert COLONNE_RECHERCHE in DF_ACHETEURS.columns
    assert COLONNE_RECHERCHE in DF_TITULAIRES.columns
