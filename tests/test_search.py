"""#150 : la recherche d'organismes (accueil `/recherche`, MCP) est insensible
à la casse et aux accents, sur des noms en casse normale accentuée — le format
désormais en production.

`build_org_frame` est exécutée pour de vrai contre une table `decp`
synthétique : c'est elle qui précalcule la colonne de recherche.
"""

import pytest

import src.utils.data as data
from src.utils.search import search_org
from src.utils.text_normalization import champs_recherches


@pytest.fixture
def con_decp():
    """Table `decp` synthétique : deux organismes de Nîmes, une autre
    métropole, un nom avec trait d'union.

    La table porte toutes les colonnes `acheteur_*` du schéma réel, car
    `build_org_frame` groupe sur `schema.names()` ; seules celles que cherche
    `search_org` sont renseignées."""
    import duckdb

    colonnes = [c for c in data.schema.names() if c.startswith("acheteur_")]
    renseignees = champs_recherches("acheteur")
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE decp (" + ", ".join(f'"{c}" VARCHAR' for c in colonnes) + ")"
    )
    con.executemany(
        f"INSERT INTO decp ({', '.join(renseignees)}) VALUES (?, ?, ?, ?, ?)",
        [
            ("210540000001", "Mairie de Nîmes", "Gard", "30", "Nîmes"),
            ("210540000002", "Nîmes Métropole", "Gard", "30", "Nîmes"),
            ("330000000001", "Bordeaux Métropole", "Gironde", "33", "Bordeaux"),
            (
                "421000000001",
                "Commune de Saint-Étienne",
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


@pytest.mark.parametrize("saisie", ["-", "--", " - ", "", "   "])
def test_saisie_sans_jeton_ne_retourne_rien(frame_acheteurs, saisie):
    """Sans jeton à chercher (vide, ou seulement traits d'union et espaces),
    aucun résultat, avec les colonnes d'un résultat normal."""
    resultats = search_org(frame_acheteurs, saisie, "acheteur")

    assert resultats.height == 0
    assert resultats.columns == search_org(frame_acheteurs, "nimes", "acheteur").columns


def test_colonne_de_recherche_absente_du_resultat(frame_acheteurs):
    from src.utils.text_normalization import COLONNE_RECHERCHE

    resultats = search_org(frame_acheteurs, "nimes", "acheteur")

    assert COLONNE_RECHERCHE not in resultats.columns
