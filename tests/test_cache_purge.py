"""Purge du cache disque au démarrage.

Elle vivait au niveau module de src/app.py : sans `preload_app`, chaque worker
gunicorn l'exécutait à son import et détruisait le cache partagé — donc à
chaque recyclage `max_requests`. En production le TTL de 30 jours de
get_annuaire_data n'avait ainsi jamais d'effet.
"""

import importlib.util
from pathlib import Path


def _charger_gunicorn_conf():
    """gunicorn.conf.py n'est pas importable par son nom (il entrerait en
    collision avec le package `gunicorn`)."""
    chemin = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("gunicorn_conf_colibre", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cache_dir_par_defaut_suit_la_variable_d_environnement(monkeypatch):
    from src.utils.cache import cache_dir_par_defaut

    monkeypatch.setenv("CACHE_DIR", "/ailleurs/cache")
    assert cache_dir_par_defaut() == "/ailleurs/cache"


def test_cache_dir_par_defaut_a_un_repli(monkeypatch):
    from src.utils.cache import cache_dir_par_defaut

    monkeypatch.delenv("CACHE_DIR", raising=False)
    assert cache_dir_par_defaut() == "/tmp/colibre-cache"


def test_on_starting_purge_le_repertoire_de_cache(tmp_path, monkeypatch):
    repertoire = tmp_path / "colibre-cache"
    repertoire.mkdir()
    (repertoire / "une-entree").write_text("x")
    monkeypatch.setenv("CACHE_DIR", str(repertoire))

    _charger_gunicorn_conf().on_starting(object())

    assert not repertoire.exists()


def test_on_starting_tolere_un_repertoire_absent(tmp_path, monkeypatch):
    """Premier démarrage sur une machine neuve."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "jamais-cree"))

    _charger_gunicorn_conf().on_starting(object())
