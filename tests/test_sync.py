import respx
from fastapi.testclient import TestClient
from httpx import Response
from tests.conftest import DATA_URL, SAMPLE_TRIPLES


def test_refresh_reports_triple_count(client: TestClient) -> None:
    response = client.post("/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["triples"] == SAMPLE_TRIPLES
    assert body["synced_at"]


def test_refresh_picks_up_new_data(client: TestClient, container_mock: respx.MockRouter) -> None:
    new_records = [{"id": str(i), "value": f"{i}.0"} for i in range(3)]
    container_mock.get(DATA_URL).mock(return_value=Response(200, json=new_records))

    response = client.post("/refresh")
    assert response.status_code == 200
    assert response.json()["triples"] == 6  # 3 records x (type + value)

    count_query = "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"
    result = client.get("/sparql", params={"query": count_query}).json()
    assert result["results"]["bindings"][0]["n"]["value"] == "6"


def test_refresh_with_unreachable_container_is_502(
    cold_client: TestClient, container_mock: respx.MockRouter
) -> None:
    container_mock.get(DATA_URL).mock(return_value=Response(500))
    response = cold_client.post("/refresh")
    assert response.status_code == 502
    assert "error" in response.json()


def test_old_data_stays_queryable_after_failed_refresh(
    client: TestClient, container_mock: respx.MockRouter
) -> None:
    container_mock.get(DATA_URL).mock(return_value=Response(503))
    assert client.post("/refresh").status_code == 502

    response = client.get("/sparql", params={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert response.status_code == 200
    assert len(response.json()["results"]["bindings"]) == SAMPLE_TRIPLES
