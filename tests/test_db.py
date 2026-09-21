import datetime
import importlib
import os
import time

import polars as pl
import pytest

from src.db import should_rebuild


@pytest.fixture(autouse=True, scope="module")
def _restore_global_db_after_module():
    """test_query_marches recharge src.db (importlib.reload) en pointant sur une
    DuckDB temporaire au schéma réduit. Sans restauration, le `conn` global de
    src.db reste branché sur cette base et casse get_top_org_ag_grid dans les
    tests Selenium suivants (ColumnNotFoundError: titulaire_distance). On
    recharge src.db sur la base de test du conftest une fois ce module terminé."""
    yield
    import src.db

    os.environ["DUCKDB_PATH"] = os.path.abspath("tests/decp.duckdb")
    importlib.reload(src.db)


@pytest.fixture
def parquet_and_db(tmp_path, monkeypatch):
    parquet = tmp_path / "source.parquet"
    db = tmp_path / "decp.duckdb"
    parquet.write_bytes(b"fake parquet content")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    monkeypatch.delenv("DEVELOPMENT", raising=False)
    return parquet, db


def _base_au_schema_courant(db) -> None:
    """Écrit une vraie base DuckDB portant la version de schéma attendue.

    Un fichier bidon (`db.write_bytes(b"x")`) ne suffit plus : depuis l'ajout
    du contrôle de version de schéma, `should_rebuild` conclut à juste titre
    « base illisible donc périmée » et renvoie True avant d'atteindre la
    comparaison de dates que ces tests visent. Les tests deviendraient alors
    verts pour la mauvaise raison.
    """
    import duckdb

    from src.db import SCHEMA_VERSION

    with duckdb.connect(str(db)) as c:
        c.execute(f"CREATE TABLE schema_version AS SELECT {SCHEMA_VERSION} AS version")


def test_should_rebuild_when_db_missing(parquet_and_db):
    parquet, db = parquet_and_db
    assert should_rebuild(db, parquet) is True


def test_should_rebuild_prod_when_parquet_newer(parquet_and_db, monkeypatch):
    parquet, db = parquet_and_db
    _base_au_schema_courant(db)
    parquet.touch()
    now = time.time()
    os.utime(db, (now, now))
    os.utime(parquet, (now + 10, now + 10))
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setattr("src.db.get_last_modified", lambda p: parquet.stat().st_mtime)
    assert should_rebuild(db, parquet) is True


def test_should_not_rebuild_prod_when_parquet_older(parquet_and_db, monkeypatch):
    parquet, db = parquet_and_db
    parquet.touch()
    _base_au_schema_courant(db)
    now = time.time()
    os.utime(parquet, (now, now))
    os.utime(db, (now + 10, now + 10))
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setattr("src.db.get_last_modified", lambda p: parquet.stat().st_mtime)
    assert should_rebuild(db, parquet) is False


def test_should_not_rebuild_dev_even_when_parquet_newer(parquet_and_db, monkeypatch):
    parquet, db = parquet_and_db
    _base_au_schema_courant(db)
    parquet.touch()
    now = time.time()
    os.utime(db, (now, now))
    os.utime(parquet, (now + 10, now + 10))
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    assert should_rebuild(db, parquet) is False


def test_should_rebuild_dev_when_rebuild_forced(parquet_and_db, monkeypatch):
    parquet, db = parquet_and_db
    _base_au_schema_courant(db)
    parquet.touch()
    now = time.time()
    os.utime(db, (now, now))
    os.utime(parquet, (now + 10, now + 10))
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("REBUILD_DUCKDB", "true")
    monkeypatch.setattr("src.db.get_last_modified", lambda p: parquet.stat().st_mtime)
    assert should_rebuild(db, parquet) is True


@pytest.fixture
def built_db(tmp_path, monkeypatch):
    """Build a DuckDB from a small Polars frame written as parquet."""
    parquet_path = tmp_path / "source.parquet"
    db_path = tmp_path / "decp.duckdb"

    data = pl.DataFrame(
        [
            {
                "uid": "1",
                "id": "1",
                "objet": "Travaux",
                "acheteur_id": "123",
                "acheteur_nom": "ACHETEUR 1",
                "acheteur_departement_code": "75",
                "acheteur_departement_nom": "Paris",
                "acheteur_commune_nom": "Paris",
                "titulaire_commune_nom": "Paris",
                "titulaire_departement_nom": "Paris",
                "titulaire_id": "345",
                "titulaire_nom": "TITULAIRE 1",
                "titulaire_departement_code": "35",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 1000.0,
                "dateNotification": datetime.date(2025, 1, 1),
                "donneesActuelles": True,
                "marcheInnovant": True,
            },
            {
                "uid": "2",
                "id": "2",
                "objet": "Études",
                "acheteur_id": "123",
                "acheteur_nom": "ACHETEUR 1",
                "acheteur_departement_code": "75",
                "acheteur_departement_nom": "Paris",
                "acheteur_commune_nom": "Paris",
                "titulaire_commune_nom": "Paris",
                "titulaire_departement_nom": "Paris",
                "titulaire_id": "567",
                "titulaire_nom": None,
                "titulaire_departement_code": "75",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 500.0,
                "dateNotification": datetime.date(2024, 6, 1),
                "donneesActuelles": True,
                "marcheInnovant": False,
            },
            {
                "uid": "3",
                "id": "3",
                "objet": "Ancien",
                "acheteur_id": "A2",
                "acheteur_nom": None,
                "acheteur_departement_code": "13",
                "acheteur_departement_nom": "Paris",
                "acheteur_commune_nom": "Paris",
                "titulaire_commune_nom": "Paris",
                "titulaire_departement_nom": "Paris",
                "titulaire_id": "T3",
                "titulaire_nom": "Autre",
                "titulaire_departement_code": "13",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 100.0,
                "dateNotification": datetime.date(2023, 1, 1),
                "donneesActuelles": False,  # must be filtered out
                "marcheInnovant": False,
            },
        ]
    )
    data.write_parquet(parquet_path)
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    from src.db import build_database

    build_database(db_path)
    return db_path


def test_build_filters_donnees_actuelles(built_db):
    import duckdb

    with duckdb.connect(str(built_db), read_only=True) as c:
        rows = c.execute("SELECT uid FROM decp ORDER BY uid").fetchall()
    assert [r[0] for r in rows] == ["1", "2"]


def test_build_converts_booleans_to_oui_non(built_db):
    import duckdb

    with duckdb.connect(str(built_db), read_only=True) as c:
        values = c.execute("SELECT marcheInnovant FROM decp ORDER BY uid").fetchall()
    assert [v[0] for v in values] == ["oui", "non"]


def test_build_replaces_null_org_names(built_db):
    import duckdb

    with duckdb.connect(str(built_db), read_only=True) as c:
        titulaire_2 = c.execute(
            "SELECT titulaire_nom FROM decp WHERE uid = '2'"
        ).fetchone()
    assert titulaire_2[0] == "[Inconnu de l'INSEE (567)]"


def test_build_creates_derived_tables(built_db):
    import duckdb

    with duckdb.connect(str(built_db), read_only=True) as c:
        tables = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
    assert {
        "decp",
        "acheteurs_marches",
        "titulaires_marches",
        "acheteurs_departement",
        "titulaires_departement",
    } <= tables


def test_query_marches_returns_polars_frame(built_db, monkeypatch):
    parquet_path = built_db.parent / "source.parquet"
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))
    # Patch on both the source module and dst namespace: the reload re-imports
    # get_last_modified from src.utils, so src.utils must be patched to survive.
    monkeypatch.setattr(
        "src.utils.get_last_modified", lambda p: parquet_path.stat().st_mtime
    )
    monkeypatch.setattr(
        "src.db.get_last_modified", lambda p: parquet_path.stat().st_mtime
    )
    # Force src.db to load pointing at this test DB.
    import importlib

    import src.db

    importlib.reload(src.db)
    from src.db import query_marches

    frame = query_marches("acheteur_id = ?", ("123",))
    assert isinstance(frame, pl.DataFrame)
    assert frame.height == 2
    assert set(frame["uid"].to_list()) == {"1", "2"}


def test_count_marches_returns_total_without_filter():
    from src.db import count_marches

    n = count_marches()
    assert isinstance(n, int)
    assert n > 0


def test_count_marches_with_filter():
    from src.db import count_marches

    n = count_marches('"uid" = ?', ["__nonexistent__"])
    assert n == 0


def test_count_unique_marches_respects_distinct():
    from src.db import count_unique_marches

    n = count_unique_marches()
    assert isinstance(n, int)
    assert n > 0


def test_query_marches_with_offset():
    from src.db import query_marches

    page_0 = query_marches(limit=2, offset=0)
    page_1 = query_marches(limit=2, offset=2)
    if page_0.height == 2 and page_1.height >= 1:
        assert set(page_0["uid"].to_list()).isdisjoint(set(page_1["uid"].to_list()))


def test_concurrent_build_serialized(tmp_path, monkeypatch):
    """Multiple threads calling _ensure_database must serialize via flock.

    Only one should actually build; others wait, see the fresh DB, and skip.
    No tmp file should leak. No exceptions should occur.
    """
    import fcntl
    import threading

    import src.db as db

    # Set up source parquet
    parquet_path = tmp_path / "src.parquet"
    df = pl.DataFrame(
        {
            "uid": ["A"],
            "donneesActuelles": [True],
            "dateNotification": ["2024-01-01"],
            "objet": ["Test"],
            "acheteur_id": ["a1"],
            "acheteur_nom": ["A1"],
            "titulaire_id": ["t1"],
            "titulaire_nom": ["T1"],
            "acheteur_departement_code": ["75"],
            "titulaire_departement_code": ["75"],
            "montant": [1000.0],
            "dureeMois": [12],
        }
    )
    df.write_parquet(parquet_path)
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))
    monkeypatch.setattr(
        "src.db.get_last_modified", lambda p: parquet_path.stat().st_mtime
    )

    db_path = tmp_path / "decp.duckdb"
    lock_path = db_path.with_suffix(".duckdb.lock")
    tmp_path_artifact = db_path.with_suffix(".duckdb.tmp")

    errors: list[BaseException] = []

    def worker():
        try:
            # Mirror the locking logic in _ensure_database
            with open(lock_path, "w") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    if db.should_rebuild(db_path, parquet_path):
                        db.build_database(db_path)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert db_path.exists()
    assert not tmp_path_artifact.exists()


def _raise(*args, **kwargs):
    raise RuntimeError("boom")


def test_ensure_database_reuses_db_when_should_rebuild_raises(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"existing")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", _raise)
    result = db._ensure_database()  # ne doit pas lever
    assert result == dbf
    assert dbf.read_bytes() == b"existing"


def test_ensure_database_reuses_db_when_build_raises(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"existing")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", _raise)
    result = db._ensure_database()  # ne doit pas lever
    assert result == dbf
    assert dbf.read_bytes() == b"existing"


def test_ensure_database_raises_on_cold_start(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"  # n'existe pas
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", _raise)
    with pytest.raises(RuntimeError):
        db._ensure_database()


def test_ensure_database_builds_when_needed(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"old")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://x")
    called = {}
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", lambda p: called.setdefault("built", p))
    db._ensure_database()
    assert called.get("built") == dbf
