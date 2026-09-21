import polars as pl
import pytest


@pytest.fixture
def sample_lff():
    """Small LazyFrame with the columns needed by add_links / format_values."""
    return pl.LazyFrame(
        [
            {
                "uid": "u1",
                "id": "u1",
                "acheteur_id": "12345678900011",
                "acheteur_nom": "Mairie de Test",
                "titulaire_id": "98765432100022",
                "titulaire_nom": "Entreprise Test",
                "titulaire_typeIdentifiant": "SIRET",
                "objet": "Travaux divers",
                "montant": 12500.0,
                "dateNotification": "2025-03-15",
                "codeCPV": "45000000",
                "dureeRestanteMois": 6,
                "titulaire_distance": 42.0,
            }
        ]
    )


def test_table_module_imports():
    from src.utils import table

    assert hasattr(table, "prepare_table_data")


def test_filter_table_data_does_not_call_track_search(monkeypatch, sample_lff):
    from src.utils import table

    calls = []
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    result = table.filter_table_data(sample_lff, "{objet} icontains travaux").collect()

    assert calls == []
    assert result.height == 1


def test_filter_table_data_accent_insensitive():
    """Chercher sans accent doit trouver des valeurs accentuées, et vice versa."""
    from src.utils.table import filter_table_data

    lff = pl.LazyFrame(
        [
            {"uid": "1", "acheteur_nom": "Mairie de Nîmes", "objet": "Voirie"},
            {"uid": "2", "acheteur_nom": "Commune de Reims", "objet": "Éclairage"},
            {"uid": "3", "acheteur_nom": "Ville de Paris", "objet": "Travaux"},
        ]
    )

    # Sans accent → trouve la valeur accentuée
    result = filter_table_data(lff, "{acheteur_nom} icontains Nimes").collect()
    assert result.height == 1
    assert result["uid"][0] == "1"

    # Avec accent → trouve la valeur accentuée
    result = filter_table_data(lff, "{acheteur_nom} icontains Nîmes").collect()
    assert result.height == 1

    # Sans accent → trouve la valeur avec accent initial (É)
    result = filter_table_data(lff, "{objet} icontains eclairage").collect()
    assert result.height == 1
    assert result["uid"][0] == "2"


def test_normalize_sort_by_handles_empty():
    from src.utils.table import normalize_sort_by

    assert normalize_sort_by(None) == ()
    assert normalize_sort_by([]) == ()


def test_normalize_sort_by_returns_hashable_tuple():
    from src.utils.table import normalize_sort_by

    sort_by = [
        {"column_id": "montant", "direction": "desc"},
        {"column_id": "dateNotification", "direction": "asc"},
    ]
    key = normalize_sort_by(sort_by)

    assert key == (("montant", "desc"), ("dateNotification", "asc"))
    # Must be hashable so that flask-caching can build a cache key from it
    hash(key)


def test_normalize_sort_by_preserves_order():
    """Order matters for sort: [A, B] != [B, A]."""
    from src.utils.table import normalize_sort_by

    a_then_b = normalize_sort_by(
        [{"column_id": "a", "direction": "asc"}, {"column_id": "b", "direction": "asc"}]
    )
    b_then_a = normalize_sort_by(
        [{"column_id": "b", "direction": "asc"}, {"column_id": "a", "direction": "asc"}]
    )
    assert a_then_b != b_then_a


@pytest.fixture(scope="module")
def flask_app():
    """Minimal Flask app with SimpleCache so @cache.memoize() works in tests."""
    from flask import Flask

    from src.utils.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})
    return app


@pytest.fixture(autouse=True)
def reset_cache(flask_app):
    """Ensure the flask-caching backend is empty between tests so that
    cache-hit assertions are meaningful. Falls back to no-op when no
    Flask app context is active (NullCache)."""
    from src.utils.cache import cache

    with flask_app.app_context():
        try:
            cache.clear()
        except (RuntimeError, AttributeError):
            # No app context — cache is NullCache, nothing to clear
            pass
        yield


def test_prepare_table_data_returns_expected_tuple(flask_app):
    from src.utils import table

    with flask_app.app_context():
        result = table.prepare_table_data(
            data=None,
            data_timestamp=5,
            filter_query=None,
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="tableau",
        )

    # Same arity as before: 9 outputs
    assert len(result) == 9
    dicts, columns, tooltip, ts, nb_rows, dl_disabled, dl_text, dl_title, cleanup = (
        result
    )
    assert isinstance(dicts, list)
    assert ts == 6  # data_timestamp + 1 must still increment
    assert "lignes" in nb_rows


def test_prepare_table_data_calls_track_search_on_filter(monkeypatch, flask_app):
    from src.utils import table

    calls = []
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    with flask_app.app_context():
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query="{objet} icontains travaux",
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="tableau",
        )

    assert calls == [("{objet} icontains travaux", "tableau")]


def test_prepare_table_data_same_page_uses_cache(monkeypatch, flask_app):
    """Two calls with exactly the same (filter, sort, page, size)
    must call _fetch_page_sql at least once."""
    from src.utils import table

    call_count = {"n": 0}

    def counting_fetch(*args, **kwargs):
        call_count["n"] += 1
        import polars as pl

        return (
            pl.DataFrame(
                {
                    "uid": [],
                    "acheteur_id": [],
                    "titulaire_id": [],
                    "titulaire_typeIdentifiant": [],
                }
            ),
            0,
            0,
        )

    monkeypatch.setattr(table, "_fetch_page_sql", counting_fetch)

    with flask_app.app_context():
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query=None,
            page_current=0,
            page_size=10,
            sort_by=[],
            source_table="tableau",
        )
        table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query=None,
            page_current=0,
            page_size=10,
            sort_by=[],
            source_table="tableau",
        )
    assert call_count["n"] >= 1


def test_prepare_table_data_cleanup_trigger_for_non_tableau(flask_app):
    """Non-tableau pages still get a fresh uuid trigger, not no_update."""
    from dash import no_update

    from src.utils import table

    with flask_app.app_context():
        result = table.prepare_table_data(
            data=None,
            data_timestamp=0,
            filter_query="{objet} icontains travaux",
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="acheteur",
        )

    cleanup = result[8]
    assert cleanup is not no_update
    assert isinstance(cleanup, str)
    assert len(cleanup) >= 32  # uuid4 hex string


def test_prepare_table_data_with_external_data_does_not_use_cache(
    monkeypatch, flask_app, sample_lff
):
    """When a caller passes data (acheteur/titulaire/observatoire path),
    bypass the memoized helper entirely."""
    from src.utils import table

    sentinel = {"called": False}

    def should_not_be_called(*a, **kw):
        sentinel["called"] = True
        raise AssertionError("Memoized helper must not be called when data is provided")

    monkeypatch.setattr(table, "_fetch_page_sql", should_not_be_called)

    with flask_app.app_context():
        table.prepare_table_data(
            data=sample_lff,
            data_timestamp=0,
            filter_query=None,
            page_current=0,
            page_size=20,
            sort_by=[],
            source_table="acheteur",
        )

    assert sentinel["called"] is False


def test_fetch_page_sql_respects_pagination(flask_app):
    """New path: returns (page_dff, total_count, total_unique) via DuckDB."""
    from src.utils import table

    with flask_app.app_context():
        page, total, total_unique = table._fetch_page_sql(
            filter_query=None, sort_by_key=(), page_current=0, page_size=5
        )
    assert page.height <= 5
    assert total >= page.height
    assert isinstance(total_unique, int)


def test_fetch_page_sql_applies_filter(flask_app):
    from src.utils import table

    with flask_app.app_context():
        page, total, total_unique = table._fetch_page_sql(
            filter_query="{uid} icontains __ne_matche_rien__",
            sort_by_key=(),
            page_current=0,
            page_size=20,
        )
    assert total == 0
    assert page.height == 0


def test_fetch_page_sql_post_processes_links(flask_app):
    from src.utils import table

    with flask_app.app_context():
        page, _, _ = table._fetch_page_sql(
            filter_query=None, sort_by_key=(), page_current=0, page_size=1
        )
    if page.height > 0:
        assert "<a href" in page["uid"][0]


def test_postprocess_page_adds_marche_column():
    """postprocess_page doit créer une colonne 'marche' en première position,
    un lien 🔍 vers /marches/{uid}, tout en conservant la colonne uid."""
    from src.utils.table import postprocess_page

    dff = pl.DataFrame({"uid": ["abc"], "objet": ["Travaux divers"]})
    result = postprocess_page(dff)

    # 'marche' existe et est la première colonne
    assert result.columns[0] == "marche"
    # Lien loupe vers la fiche du marché
    assert "/marches/abc" in result["marche"][0]
    assert "🔍" in result["marche"][0]
    # uid est conservée et reste un lien affichant sa propre valeur
    assert "uid" in result.columns
    assert "abc" in result["uid"][0]


def test_postprocess_page_without_uid_has_no_marche():
    """Sans colonne uid, aucune colonne 'marche' n'est ajoutée."""
    from src.utils.table import postprocess_page

    dff = pl.DataFrame({"objet": ["Travaux divers"]})
    result = postprocess_page(dff)

    assert "marche" not in result.columns


# Sélecteur de colonnes en AG Grid (#141) : conversion entre les lignes cochées
# (`selectedRows`) et la liste des colonnes masquées du store.


def test_hidden_columns_from_selection_masque_les_colonnes_non_cochees():
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    cochees = [COLUMNS[2], COLUMNS[0]]  # ordre volontairement inversé
    # Lignes telles qu'AG Grid les réémet : la ligne entière, pas que l'id.
    lignes = [{"id": c, "name": f"titre {c}", "description": "…"} for c in cochees]

    masquees = hidden_columns_from_selection(lignes)

    assert masquees == [c for c in COLUMNS if c not in cochees]
    assert COLUMNS[1] in masquees
    assert COLUMNS[0] not in masquees and COLUMNS[2] not in masquees


@pytest.mark.parametrize("selection", [[], None])
def test_hidden_columns_from_selection_vide_masque_tout(selection):
    """Tout décocher est un choix explicite : toutes les colonnes masquées."""
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    assert len(COLUMNS) > 3
    assert hidden_columns_from_selection(selection) == COLUMNS


def test_selection_from_hidden_columns_coche_les_colonnes_visibles():
    from src.utils.table import COLUMNS, selection_from_hidden_columns

    masquees = [COLUMNS[3], COLUMNS[1]]

    selection = selection_from_hidden_columns(masquees)

    assert selection == {"ids": [c for c in COLUMNS if c not in masquees]}
    assert COLUMNS[0] in selection["ids"]


def test_selection_from_hidden_columns_vide_coche_tout():
    from src.utils.table import COLUMNS, selection_from_hidden_columns

    assert selection_from_hidden_columns([]) == {"ids": COLUMNS}


def test_selection_et_colonnes_masquees_aller_retour():
    from src.utils.table import (
        COLUMNS,
        hidden_columns_from_selection,
        selection_from_hidden_columns,
    )

    masquees = [COLUMNS[1], COLUMNS[4], COLUMNS[-1]]
    lignes = [{"id": i} for i in selection_from_hidden_columns(masquees)["ids"]]

    assert hidden_columns_from_selection(lignes) == masquees


def test_hidden_columns_from_selection_accepte_la_forme_ids():
    """La valeur posée par le serveur (`{"ids": [...]}`) redéclenche aussi le
    callback « cases → store » : Dash chaîne les callbacks sur la sortie écrite,
    avant qu'AG Grid ne réémette la sélection sous forme de lignes. Vu en
    navigateur : sans ce cas, le callback levait une erreur (HTTP 500)."""
    from src.utils.table import COLUMNS, hidden_columns_from_selection

    cochees = [COLUMNS[0], COLUMNS[2]]

    masquees = hidden_columns_from_selection({"ids": cochees})

    assert masquees == [c for c in COLUMNS if c not in cochees]
    assert COLUMNS[1] in masquees
