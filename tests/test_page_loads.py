import os


def test_update_timestamp_falls_back_to_db_mtime(tmp_path, monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    fb = tmp_path / "decp.duckdb"
    fb.write_bytes(b"x")
    assert get_data_update_timestamp("http://x", str(fb)) == os.path.getmtime(str(fb))


def test_update_timestamp_none_when_all_fail(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    assert get_data_update_timestamp("http://x", None) is None


def test_update_timestamp_nominal(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    monkeypatch.setattr(u, "get_last_modified", lambda p: 123.0)
    assert get_data_update_timestamp("http://x", None) == 123.0


def test_sources_tables_none_path():
    from src.figures import get_sources_tables

    div = get_sources_tables(None)
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_missing_file():
    from src.figures import get_sources_tables

    div = get_sources_tables("/does/not/exist.csv")
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_valid_csv(tmp_path):
    import dash_ag_grid as dag

    from src.figures import get_sources_tables

    csv = tmp_path / "s.csv"
    csv.write_text(
        "nom,organisation,nb_marchés,nb_acheteurs,code,url,unique\n"
        "Source A,Org A,5,2,XA,http://a,1\n"
        "Source B,Org B,20,7,XB,http://b,1\n"
    )
    div = get_sources_tables(str(csv))
    grid = div.children

    assert isinstance(grid, dag.AgGrid)
    assert grid.id == "source_table"

    # Triées par nb_marchés décroissant.
    assert [row["nb_marchés"] for row in grid.rowData] == [20, 5]

    # La cellule "nom" contient bien le lien.
    assert [row["nom"] for row in grid.rowData] == [
        '<a href = "http://b">Source B</a>',
        '<a href = "http://a">Source A</a>',
    ]

    col_by_field = {c["field"]: c for c in grid.columnDefs}

    # Colonnes nom / organisation en markdown, avec retour à la ligne auto.
    for field in ("nom", "organisation"):
        assert col_by_field[field]["cellRenderer"] == "markdown"
        assert col_by_field[field]["wrapText"] is True
        assert col_by_field[field]["autoHeight"] is True

    # Colonnes de nombres alignées à droite.
    for field in ("nb_marchés", "nb_acheteurs"):
        assert col_by_field[field]["type"] == "rightAligned"


def test_sources_tables_numeric_columns_keep_numbers_for_sort(tmp_path):
    """nb_marchés/nb_acheteurs restent numériques dans rowData (sinon le tri
    AG Grid serait alphabétique) ; le formatage français se fait via un
    valueFormatter côté colonne, pas en amont dans les données."""
    from src.figures import get_sources_tables

    csv = tmp_path / "s.csv"
    csv.write_text(
        "nom,organisation,nb_marchés,nb_acheteurs,code,url,unique\n"
        "Source A,Org A,5,2,XA,http://a,1\n"
        "Source B,Org B,20,7,XB,http://b,1\n"
    )
    div = get_sources_tables(str(csv))
    grid = div.children

    for row in grid.rowData:
        assert isinstance(row["nb_marchés"], int)
        assert isinstance(row["nb_acheteurs"], int)

    col_by_field = {c["field"]: c for c in grid.columnDefs}
    for field in ("nb_marchés", "nb_acheteurs"):
        assert "valueFormatter" in col_by_field[field]
        assert "function" in col_by_field[field]["valueFormatter"]
