from src.mcp import tools


def test_all_four_tools_are_callable():
    for name in (
        "rechercher_organisations",
        "stats_acheteur",
        "stats_titulaire",
        "rechercher_marches",
    ):
        assert callable(getattr(tools, name))


def test_rechercher_organisations_returns_list():
    result = tools.rechercher_organisations("ACHETEUR", "acheteur")
    assert isinstance(result, list)
    assert any(r["id"] == "123" for r in result)


def test_rechercher_marches_returns_meta():
    result = tools.rechercher_marches(acheteur_id="123")
    assert result["meta"]["total"] >= 1


def test_stats_acheteur_returns_stats():
    result = tools.stats_acheteur("123")
    assert result["nb_marches"] >= 1
    assert result["identite"]["id"] == "123"


def test_stats_titulaire_returns_stats():
    result = tools.stats_titulaire("345")
    assert result["nb_marches"] >= 1


def test_rechercher_marches_colonnes_param_is_enum():
    import typing

    from pydantic import TypeAdapter

    hints = typing.get_type_hints(tools.rechercher_marches)
    schema = TypeAdapter(hints["colonnes"]).json_schema()
    # list[ColonneMarche] | None -> anyOf[array(items.enum), null]
    array_schema = next(s for s in schema["anyOf"] if s.get("type") == "array")
    enum = array_schema["items"]["enum"]
    assert "objet" in enum
    assert "montant" in enum
    assert "uid" in enum


def test_rechercher_marches_colonnes_passthrough(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = tools.rechercher_marches(acheteur_id="123", colonnes=["objet"])
    m = result["marches"][0]
    assert set(m.keys()) == {"uid", "objet", "lien"}
    assert m["lien"] == f"https://colibre.fr/marches/{m['uid']}"


def test_rechercher_marches_page_size_passthrough():
    result = tools.rechercher_marches(acheteur_id="123", page_size=10)
    assert result["meta"]["page_size"] == 10


def test_rechercher_marches_page_size_out_of_bounds_returns_error():
    result = tools.rechercher_marches(acheteur_id="123", page_size=201)
    assert "error" in result
    assert result["champ"] == "page_size"
