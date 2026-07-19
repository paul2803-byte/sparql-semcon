from fastapi.testclient import TestClient


def test_health_before_first_sync(cold_client: TestClient) -> None:
    body = cold_client.get("/health").json()
    assert body["store_ready"] is False
    assert body["triples"] == 0
    assert body["last_sync"] is None


def test_sparql_before_first_sync_is_503(cold_client: TestClient) -> None:
    response = cold_client.get("/sparql", params={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert response.status_code == 503


def test_health_after_sync(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["store_ready"] is True
    assert body["triples"] > 0
    assert body["last_sync"] is not None


def test_root_metadata(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["name"] == "sc-sparql"
    assert body["endpoints"]["sparql"] == "/sparql"
