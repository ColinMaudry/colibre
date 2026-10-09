import datetime
import os
import shutil
from pathlib import Path

import polars as pl
import pytest
from selenium.webdriver.chrome.options import Options

_TEST_DATA = [
    {
        "uid": "1",
        "id": "1",
        "acheteur_nom": "ACHETEUR 1",
        "acheteur_id": "123",
        "titulaire_nom": "TITULAIRE 1",
        "titulaire_id": "345",
        "montant": 10,
        # Montant retenu par les cards de l'observatoire et par le filtre
        # montant du tableau de bord (cf. OBSERVATOIRE_CARDS_COLUMNS) : les
        # cards le projettent sans garde, la colonne est donc obligatoire.
        "montant_rationalise": 10,
        "dateNotification": datetime.date(2025, 1, 1),
        "codeCPV": "71600000",
        "donneesActuelles": True,
        "acheteur_departement_code": "75",
        "acheteur_departement_nom": "Paris",
        "acheteur_commune_nom": "Paris",
        "titulaire_departement_code": "35",
        "titulaire_departement_nom": "Ille-et-Vilaine",
        "titulaire_commune_nom": "Rennes",
        "titulaire_distance": 10,
        "titulaire_typeIdentifiant": "SIRET",
        "objet": "Objet test",
        "dureeRestanteMois": 12,
        "lieuExecution_code": "75001",
        "sourceFile": "test.xml",
        "sourceDataset": "test_dataset",
        "datePublicationDonnees": datetime.date(2025, 1, 1),
        "considerationsSociales": "",
        "considerationsEnvironnementales": "",
        "type": "Marché",
        "acheteur_categorie": "Collectivité",
        "titulaire_categorie": "PME",
    }
]
_PARQUET_PATH = Path(os.path.abspath("tests/test.parquet"))

# Base DuckDB de test ISOLÉE : src.db lit le chemin via DUCKDB_PATH (défaut
# ./colibre.duckdb). On la place dans tests/ pour ne JAMAIS toucher au colibre.duckdb
# de dev/prod — plus besoin de sauvegarder/restaurer. Le nom colibre.duckdb
# est couvert par le motif **/colibre.duckdb ajouté au .gitignore.
_DB_PATH = Path(os.path.abspath("tests/colibre.duckdb"))
os.environ["DUCKDB_PATH"] = str(_DB_PATH)

# Schéma déterministe et hors-ligne : on COPIE le fixture committé vers un cache
# de test jetable (nom schema.cache.json déjà gitignoré) et on pointe
# DATA_SCHEMA_CACHE dessus. Ainsi, toute écriture du cache par le code testé ne
# mute pas tests/schema.fixture.json (versionné). DATA_SCHEMA_PATH est retiré
# pour désactiver toute récupération distante.
_SCHEMA_FIXTURE = Path(os.path.abspath("tests/schema.fixture.json"))
_SCHEMA_CACHE = Path(os.path.abspath("tests/schema.cache.json"))
shutil.copyfile(_SCHEMA_FIXTURE, _SCHEMA_CACHE)
os.environ["DATA_SCHEMA_CACHE"] = str(_SCHEMA_CACHE)
os.environ.pop("DATA_SCHEMA_PATH", None)

# Base users partagée par les tests qui démarrent l'app complète (Selenium) :
# on COPIE le fixture committé vers une base jetable (users.runtime.sqlite,
# gitignorée) et on pointe USERS_DB_PATH dessus. Ainsi, toute écriture faite
# pendant les tests (comptes créés, vues sauvegardées, etc.) ne mute pas
# tests/users.test.sqlite (versionné, partagé pour toute la suite).
_USERS_DB_FIXTURE = Path(os.path.abspath("tests/users.test.sqlite"))
_USERS_DB_RUNTIME = Path(os.path.abspath("tests/users.runtime.sqlite"))
shutil.copyfile(_USERS_DB_FIXTURE, _USERS_DB_RUNTIME)
os.environ["USERS_DB_PATH"] = str(_USERS_DB_RUNTIME)


def _cleanup_db_artifacts() -> None:
    for artifact in (
        _DB_PATH,
        _DB_PATH.with_suffix(".duckdb.tmp"),
        _DB_PATH.with_suffix(".duckdb.lock"),
    ):
        if artifact.exists():
            artifact.unlink()


# Runs at conftest import, before test modules import src.db (which builds the
# DuckDB at import time depuis DUCKDB_PATH). Garantit un parquet de test frais et
# une base de test vierge (reconstruite à partir des données de test).
pl.DataFrame(_TEST_DATA).write_parquet(_PARQUET_PATH)
_cleanup_db_artifacts()


@pytest.fixture(scope="session", autouse=True)
def test_data():
    yield str(_PARQUET_PATH)
    # Teardown : on nettoie la base de test isolée (jamais le decp.duckdb de dev).
    _cleanup_db_artifacts()


@pytest.fixture(autouse=True)
def _suivi_hors_callback(request, monkeypatch):
    """Les callbacks appelés directement (hors contexte Dash) émettent un
    événement de suivi via `set_props`, qui exige un contexte de callback.
    On le neutralise ; un test qui veut capturer les événements remplace à
    nouveau `src.utils.suivi.set_props`. Les tests navigateur gardent le vrai
    `set_props`, le serveur Dash tournant dans le même processus."""
    if "dash_duo" not in request.fixturenames:
        monkeypatch.setattr("src.utils.suivi.set_props", lambda *a, **kw: None)


def pytest_collection_modifyitems(items):
    """Marque `selenium` tout test qui demande un navigateur.

    Le marqueur se déduit de la présence de la fixture `dash_duo` plutôt que
    d'être annoté à la main : un nouveau test navigateur est donc désélectionné
    de la suite courte sans que personne ait à y penser, et il n'y a pas de
    liste à tenir à jour. Voir `markers` et `addopts` dans pyproject.toml.
    """
    for item in items:
        if "dash_duo" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.selenium)


def pytest_setup_options():
    """Options Chrome pour les tests d'intégration Selenium.

    dash.testing n'utilise PAS une fixture `chrome_options` (contrairement à
    pytest-selenium) : il appelle ce hook `pytest_setup_options`. C'est donc le
    seul point d'entrée qui a réellement un effet. On force `--headless=new`
    pour qu'aucune fenêtre Chrome ne s'ouvre pendant les tests. Le dossier de
    téléchargement, `--no-sandbox`, `--disable-gpu` et `--disable-dev-shm-usage`
    sont déjà gérés par dash.testing.browser.
    """
    options = Options()
    options.add_argument("--headless=new")
    # 1600px de large : le marches_table est large (défilement horizontal) ; un
    # viewport étroit laisse les colonnes de droite hors champ → éléments non
    # interactifs pour Selenium.
    options.add_argument("--window-size=1600,1200")
    return options


@pytest.fixture
def compte_abonne(monkeypatch):
    """Un compte vérifié, abonné via `TOUS_ABONNES` (comme en production pendant
    la période d'accès gratuit), sans passer par la base d'abonnements."""
    from werkzeug.security import generate_password_hash

    from src.auth import db as auth_db
    from tests._selenium_compte import EMAIL, MOT_DE_PASSE

    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)

    row = auth_db.get_user_by_email(EMAIL)
    if row is None:
        user_id = auth_db.create_user(EMAIL, generate_password_hash(MOT_DE_PASSE))
    else:
        user_id = row["id"]
        auth_db.update_password_hash(user_id, generate_password_hash(MOT_DE_PASSE))
    auth_db.set_email_verified(user_id)
    return user_id


@pytest.fixture
def compte_sans_abonnement(monkeypatch, compte_abonne):
    """Le même compte vérifié et connecté, mais sans accès d'abonné : c'est
    bien TOUS_ABONNES (ou un abonnement) qui ouvre les fonctionnalités, pas le
    simple fait d'avoir un compte."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr("src.subscriptions.db.has_access", lambda _uid: False)
    return compte_abonne


# Cinq graphies de « Maîtrise d'œuvre » (#147), dont une avec l'apostrophe
# typographique, qui est celle de la quasi-totalité des données de production.
OBJETS_MAITRISE = [
    "Maîtrise d'œuvre",
    "maitrise d'œuvre",
    "maîtrise d'oeuvre",
    "MAÎTRISE D'ŒUVRE",
    "Maîtrise d’œuvre",
]


@pytest.fixture
def objets_maitrise():
    """Les cinq graphies, triées comme le renvoient les tests de filtre."""
    return sorted(OBJETS_MAITRISE)


@pytest.fixture
def con_objets():
    """DuckDB en mémoire avec la table `decp` des tests de filtre sur `objet` :
    les cinq graphies, deux objets sans rapport, un NULL et une chaîne vide.
    `objet_normalise` est calculée comme au build (`normalize_text_sql`)."""
    import duckdb

    from src.utils.text_normalization import normalize_text_sql

    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE decp (objet VARCHAR, objet_normalise VARCHAR, "
        'acheteur_nom VARCHAR, titulaire_nom VARCHAR, "dateNotification" DATE)'
    )
    objets = [*OBJETS_MAITRISE, "Travaux de voirie", "Éclairage public", None, ""]
    con.executemany(
        'INSERT INTO decp (objet, acheteur_nom, titulaire_nom, "dateNotification") '
        "VALUES (?, 'NIMES METROPOLE', 'FREJUS SARL', DATE '2025-06-01')",
        [(objet,) for objet in objets],
    )
    con.execute(f"UPDATE decp SET objet_normalise = {normalize_text_sql('objet')}")
    return con


_LIGNES_BOOLEENS = [
    ("Travaux de béton", "Clause sociale, Critère social", "2024-03-01"),
    ("Béton et ciment", None, "2023-06-01"),
    ("Béton ou ciment au choix", None, "2023-06-01"),
    ("Fourniture de ciment", None, "2023-06-01"),
    ("Brique et béton", None, "2023-06-01"),
    ("Ciment et brique", None, "2023-06-01"),
    ("Entretien des espaces verts", None, "2023-06-01"),
    ("Travaux de construction", None, "2023-06-01"),
    ("Travaux de voirie", "Critère social", "2023-06-01"),
    ("Conseil en étude de marché", None, "2023-06-01"),
    ("Conseil juridique", "Clause sociale", "2025-01-01"),
    ("Maintenance sur site", None, "2023-06-01"),
    ("Site de maintenance", None, "2023-06-01"),
    ("Maîtrise d’œuvre", None, "2023-06-01"),
    ("Réseau OUEST", None, "2023-06-01"),
    ("Prix 3+4", None, "2023-06-01"),
    ("x' OR 1=1 --", None, "2023-06-01"),
    (None, None, "2023-06-01"),
    ("", None, "2023-06-01"),
]


@pytest.fixture
def con_booleens():
    """DuckDB en mémoire avec la table `decp` des tests de filtres booléens
    (#97) : 17 objets non vides, un NULL et une chaîne vide. `objet_normalise`
    est calculée comme au build (`normalize_text_sql`)."""
    import duckdb

    from src.utils.text_normalization import normalize_text_sql

    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE decp (objet VARCHAR, objet_normalise VARCHAR, "
        '"considerationsSociales" VARCHAR, "dateNotification" DATE)'
    )
    con.executemany(
        'INSERT INTO decp (objet, "considerationsSociales", "dateNotification") '
        "VALUES (?, ?, CAST(? AS DATE))",
        _LIGNES_BOOLEENS,
    )
    con.execute(f"UPDATE decp SET objet_normalise = {normalize_text_sql('objet')}")
    return con
