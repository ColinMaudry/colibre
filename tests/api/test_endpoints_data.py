import pytest


def test_data_without_token_returns_401(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/data")
    assert resp.status_code == 401


def test_data_default_pagination(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) >= {"data", "meta", "links"}
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 50  # default page_size
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 50
    assert "total" in body["meta"]


def test_data_count_results_false_omits_total(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?count_results=false", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" not in body["meta"]


def test_data_page_size_max_enforced(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page_size=5000", headers=valid_token_header)
    assert resp.status_code == 400


def test_data_page_size_below_min_rejected(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page_size=0", headers=valid_token_header)
    assert resp.status_code == 400


def test_data_pagination_links(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page=1&page_size=1", headers=valid_token_header)
    body = resp.get_json()
    assert body["links"]["prev"] is None
    if body["meta"]["total"] > 1:
        assert body["links"]["next"] is not None
        assert "page=2" in body["links"]["next"]


def test_data_filter_exact_string(api_client, valid_token_header):
    client, _ = api_client
    # On choisit une valeur qui existe dans test.parquet : récupère via la 1re ligne
    base = client.get("/api/v1/data?page_size=1", headers=valid_token_header).get_json()
    assert base["data"], "test.parquet vide ?"
    uid = base["data"][0]["uid"]

    resp = client.get(f"/api/v1/data?uid__exact={uid}", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(row["uid"] == uid for row in body["data"])


def test_data_unknown_column_filter_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?colonne_inexistante__exact=x",
        headers=valid_token_header,
    )
    assert resp.status_code == 400


def test_data_columns_selection(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?columns=uid,objet&page_size=3",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    for row in body["data"]:
        assert set(row.keys()) == {"uid", "objet"}


def test_data_columns_unknown_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?columns=uid,foobar",
        headers=valid_token_header,
    )
    assert resp.status_code == 400


def test_data_objet_contains_ignore_accents(api_client, valid_token_header):
    client, _ = api_client
    sans = client.get("/api/v1/data?objet__contains=objet", headers=valid_token_header)
    avec = client.get("/api/v1/data?objet__contains=ôbjét", headers=valid_token_header)
    assert avec.status_code == 200
    assert sans.get_json()["meta"]["total"] >= 1
    assert avec.get_json()["meta"]["total"] == sans.get_json()["meta"]["total"]


def test_data_sans_columns_n_expose_pas_objet_normalise(api_client, valid_token_header):
    client, _ = api_client
    body = client.get("/api/v1/data?page_size=1", headers=valid_token_header).get_json()
    assert body["data"], "test.parquet vide ?"
    assert "objet_normalise" not in body["data"][0]


@pytest.mark.parametrize(
    "query", ["objet_normalise__contains=x", "columns=objet_normalise"]
)
def test_data_objet_normalise_inconnu_retourne_400(
    api_client, valid_token_header, query
):
    client, _ = api_client
    resp = client.get(f"/api/v1/data?{query}", headers=valid_token_header)
    assert resp.status_code == 400


def test_data_sort_desc(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?dateNotification__sort=desc&page_size=5",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    dates = [
        row["dateNotification"] for row in body["data"] if row.get("dateNotification")
    ]
    assert dates == sorted(dates, reverse=True)


def test_data_differs_excludes_value(api_client, valid_token_header):
    client, _ = api_client
    base = client.get("/api/v1/data?page_size=1", headers=valid_token_header).get_json()
    uid = base["data"][0]["uid"]
    resp = client.get(f"/api/v1/data?uid__differs={uid}", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(row["uid"] != uid for row in body["data"])


def test_data_aggregation_groupby_count(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?acheteur_departement_code__groupby&uid__count",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"], "agrégation vide ?"
    for row in body["data"]:
        assert set(row.keys()) == {"acheteur_departement_code", "uid__count"}
    assert "total" not in body["meta"]


def test_data_aggregation_global_count(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?uid__count", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["data"]) == 1
    assert "uid__count" in body["data"][0]


def test_data_aggregation_with_filter(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?acheteur_departement_code__groupby&uid__count&montant__greater=0",
        headers=valid_token_header,
    )
    assert resp.status_code == 200


def test_data_aggregation_flags_accept_empty_value(api_client, valid_token_header):
    """Swagger UI sérialise les drapeaux sans valeur en `col__groupby=`.

    Le champ « filtres » est un objet free-form : une valeur vide produit
    `key=` et non `key` nu, il faut donc que les deux formes passent.
    """
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?acheteur_departement_code__groupby=&uid__count=",
        headers=valid_token_header,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    for row in resp.get_json()["data"]:
        assert set(row.keys()) == {"acheteur_departement_code", "uid__count"}


def test_data_aggregation_with_columns_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?uid__count&columns=uid",
        headers=valid_token_header,
    )
    assert resp.status_code == 400
