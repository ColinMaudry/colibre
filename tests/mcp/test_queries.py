import pytest

from src.mcp.queries import (
    build_where_args,
    compute_org_stats,
    search_marches,
    search_organisations,
)


def test_search_organisations_finds_known_acheteur():
    result = search_organisations("ACHETEUR", "acheteur")
    assert any(r["id"] == "123" for r in result)
    first = next(r for r in result if r["id"] == "123")
    assert set(first.keys()) == {"id", "nom", "departement"}
    # Vérifier que le nom a été extrait en texte plain (HTML strippé)
    assert first["nom"] == "ACHETEUR 1"
    assert "<" not in first["nom"]  # Défense : aucun markup HTML ne s'échappe


def test_search_organisations_finds_known_titulaire():
    result = search_organisations("TITULAIRE", "titulaire")
    assert any(r["id"] == "345" for r in result)
    first = next(r for r in result if r["id"] == "345")
    assert set(first.keys()) == {"id", "nom", "departement"}
    # Vérifier que le nom a été extrait en texte plain (HTML strippé),
    # même chemin SIRET/non-SIRET différent de celui du test acheteur.
    assert first["id"] == "345"
    assert first["nom"] == "TITULAIRE 1"
    assert "<" not in first["id"]
    assert "<" not in first["nom"]


def test_search_organisations_invalid_type_raises():
    with pytest.raises(ValueError):
        search_organisations("x", "autre")


def test_search_organisations_respects_limite():
    result = search_organisations("ACHETEUR", "acheteur", limite=1)
    assert len(result) <= 1


def test_build_where_args_named_params():
    args = build_where_args(
        {"acheteur_id": "123", "montant_min": 5, "objet_contient": "test"}, None
    )
    assert ("acheteur_id__exact", "123") in args
    assert ("montant__greater", "5") in args
    assert ("objet__contains", "test") in args


def test_build_where_args_merges_filtres_avances():
    args = build_where_args(
        {"acheteur_id": "123"}, {"titulaire_departement_code__exact": "35"}
    )
    assert ("acheteur_id__exact", "123") in args
    assert ("titulaire_departement_code__exact", "35") in args


def test_search_marches_returns_meta_and_rows():
    result = search_marches(acheteur_id="123")
    assert result["meta"]["total"] >= 1
    assert result["meta"]["page"] == 1
    assert result["meta"]["page_size"] == 50
    assert any(m["acheteur_id"] == "123" for m in result["marches"])
    # dates sérialisées en ISO
    assert result["marches"][0]["dateNotification"] == "2025-01-01"


def test_search_marches_no_match_is_empty():
    result = search_marches(acheteur_id="inconnu-xyz")
    assert result["meta"]["total"] == 0
    assert result["marches"] == []


def test_search_marches_bad_filter_returns_error():
    result = search_marches(filtres_avances={"colonne_bidon__exact": "x"})
    assert "error" in result


def test_search_marches_montant_min_filters_correctly():
    assert search_marches(montant_min=100)["meta"]["total"] == 0
    assert search_marches(montant_min=1)["meta"]["total"] >= 1


def test_search_marches_date_min_max_filters_correctly():
    assert search_marches(date_min="2025-01-01")["meta"]["total"] >= 1
    assert search_marches(date_min="2025-01-02")["meta"]["total"] == 0
    assert search_marches(date_max="2025-01-01")["meta"]["total"] >= 1
    assert search_marches(date_max="2024-12-31")["meta"]["total"] == 0


def test_search_marches_cpv_filters_correctly():
    assert search_marches(cpv="716")["meta"]["total"] >= 1
    assert search_marches(cpv="999")["meta"]["total"] == 0


def test_build_where_args_cpv_is_prefix():
    # le filtre nommé cpv est un « commence par » (code CPV hiérarchique)
    args = build_where_args({"cpv": "72"}, None)
    assert ("codeCPV__startswith", "72") in args


def test_search_marches_cpv_is_prefix_not_contains():
    # "1600" est contenu dans le codeCPV de test (71600000) mais n'en est pas
    # le préfixe : en sémantique « commence par », aucun résultat.
    assert search_marches(cpv="1600")["meta"]["total"] == 0
    assert search_marches(cpv="716")["meta"]["total"] >= 1


def test_search_marches_objet_contient_ignore_accents():
    sans = search_marches(objet_contient="objet")["meta"]["total"]
    avec = search_marches(objet_contient="ôbjét")["meta"]["total"]
    assert sans >= 1
    assert avec == sans


def test_search_marches_page_2_is_empty_with_correct_meta():
    result = search_marches(acheteur_id="123", page=2)
    assert result["meta"]["page"] == 2
    assert result["marches"] == []


def test_search_marches_page_zero_is_clamped_to_one():
    result = search_marches(acheteur_id="123", page=0)
    assert result["meta"]["page"] == 1


def test_compute_org_stats_acheteur_known():
    stats = compute_org_stats("acheteur", "123")
    assert stats["nb_marches"] >= 1
    assert stats["montant_total"] == 10
    assert stats["identite"]["id"] == "123"
    assert stats["identite"]["nom"] == "ACHETEUR 1"
    assert "top_titulaires" in stats
    assert "top_cpv" in stats
    # répartition annuelle dérivée de dateNotification (2025)
    annees = [row["annee"] for row in stats["repartition_annuelle"]]
    assert 2025 in annees


def test_compute_org_stats_titulaire_known():
    stats = compute_org_stats("titulaire", "345")
    assert stats["nb_marches"] >= 1
    assert "top_acheteurs" in stats


def test_compute_org_stats_unknown_is_empty():
    stats = compute_org_stats("acheteur", "inconnu-xyz")
    assert stats["nb_marches"] == 0
    assert stats["montant_total"] == 0
    assert stats["repartition_annuelle"] == []
    assert stats["top_titulaires"] == []
    assert stats["top_cpv"] == []


def test_search_marches_default_columns_and_lien(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    from src.mcp.queries import MARCHES_COLUMNS

    result = search_marches(acheteur_id="123")
    m = result["marches"][0]
    # Toutes les colonnes du défaut + le lien
    assert set(MARCHES_COLUMNS).issubset(m.keys())
    assert m["lien"] == f"https://colibre.fr/marches/{m['uid']}"


def test_search_marches_custom_columns_replace(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = search_marches(acheteur_id="123", colonnes=["objet", "montant"])
    m = result["marches"][0]
    # « remplace » : exactement les colonnes demandées + uid (clé) + lien
    assert set(m.keys()) == {"uid", "objet", "montant", "lien"}


def test_search_marches_custom_columns_include_uid_only_once(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = search_marches(acheteur_id="123", colonnes=["uid", "objet"])
    m = result["marches"][0]
    assert set(m.keys()) == {"uid", "objet", "lien"}


def test_search_marches_duplicate_columns_deduped(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    # Un client peut répéter une colonne malgré l'enum : pas de doublon au SELECT.
    result = search_marches(acheteur_id="123", colonnes=["objet", "objet"])
    m = result["marches"][0]
    assert set(m.keys()) == {"uid", "objet", "lien"}


def test_search_marches_invalid_column_rejected():
    result = search_marches(acheteur_id="123", colonnes=["nexiste_pas"])
    assert result["error"] == "colonne inconnue: nexiste_pas"
    assert result["champ"] == "nexiste_pas"
    assert "marches" not in result


def test_search_marches_lien_relative_when_base_unset(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    result = search_marches(acheteur_id="123", colonnes=["objet"])
    m = result["marches"][0]
    assert m["lien"] == f"/marches/{m['uid']}"


def test_search_marches_page_size_reflected_in_meta():
    result = search_marches(acheteur_id="123", page_size=10)
    assert result["meta"]["page_size"] == 10


def test_search_marches_page_size_controls_limit_and_offset(monkeypatch):
    import polars as pl

    from src.mcp import queries as queries_mod

    captured = {}

    def fake_query_marches(where_sql, params, columns, order_by, limit, offset):
        captured["limit"] = limit
        captured["offset"] = offset
        return pl.DataFrame()

    monkeypatch.setattr(queries_mod, "query_marches", fake_query_marches)
    search_marches(page=3, page_size=25)
    assert captured["limit"] == 25
    assert captured["offset"] == 2 * 25


def test_search_marches_page_size_out_of_bounds_returns_error():
    for bad in (0, -1, 1001):
        result = search_marches(acheteur_id="123", page_size=bad)
        assert "error" in result
        assert result["champ"] == "page_size"


def test_describe_schema_exposes_colonnes_disponibles():
    from src.mcp.queries import describe_schema

    schema = describe_schema()
    dispo = schema["colonnes_disponibles"]
    assert isinstance(dispo, list) and dispo
    # surensemble des colonnes filtrables (inclut le défaut)
    assert set(schema["colonnes_filtrables"]).issubset(set(dispo))
    assert "lien" in schema["colonnes_retournees"]
