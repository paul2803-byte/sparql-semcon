from fastapi.testclient import TestClient
from httpx import Response

from tests.conftest import SAMPLE_TRIPLES

SELECT_ALL = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"


def _post_query(
    client: TestClient, query: str, *, accept: str | None = None
) -> Response:
    headers = {"Content-Type": "application/sparql-query"}
    if accept is not None:
        headers["Accept"] = accept
    return client.post("/sparql", content=query, headers=headers)


def test_post_direct_sparql_query(client: TestClient) -> None:
    response = _post_query(client, SELECT_ALL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/sparql-results+json")
    assert len(response.json()["results"]["bindings"]) == SAMPLE_TRIPLES


def test_post_form_urlencoded(client: TestClient) -> None:
    response = client.post("/sparql", data={"query": SELECT_ALL})
    assert response.status_code == 200
    assert len(response.json()["results"]["bindings"]) == SAMPLE_TRIPLES


def test_get_is_method_not_allowed(client: TestClient) -> None:
    response = client.get("/sparql", params={"query": SELECT_ALL})
    assert response.status_code == 405


def test_ask_query(client: TestClient) -> None:
    response = _post_query(client, "ASK { ?s ?p ?o }")
    assert response.status_code == 200
    assert response.json()["boolean"] is True


def test_construct_defaults_to_turtle(client: TestClient) -> None:
    response = _post_query(client, "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/turtle")


def test_accept_csv(client: TestClient) -> None:
    response = _post_query(client, SELECT_ALL, accept="text/csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_accept_xml(client: TestClient) -> None:
    response = _post_query(client, SELECT_ALL, accept="application/sparql-results+xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/sparql-results+xml")


def test_unsupported_accept_is_406(client: TestClient) -> None:
    response = _post_query(client, SELECT_ALL, accept="text/html")
    assert response.status_code == 406


def test_malformed_query_is_400(client: TestClient) -> None:
    response = _post_query(client, "SELECT WHERE {")
    assert response.status_code == 400


def test_missing_query_is_400(client: TestClient) -> None:
    response = client.post(
        "/sparql",
        content="",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400


def test_update_via_form_field_is_400(client: TestClient) -> None:
    response = client.post("/sparql", data={"update": "DELETE WHERE { ?s ?p ?o }"})
    assert response.status_code == 400


def test_update_query_is_400(client: TestClient) -> None:
    response = _post_query(
        client, "INSERT DATA { <http://x/s> <http://x/p> <http://x/o> }"
    )
    assert response.status_code == 400


def test_sparql_update_content_type_is_400(client: TestClient) -> None:
    response = client.post(
        "/sparql",
        content="DELETE WHERE { ?s ?p ?o }",
        headers={"Content-Type": "application/sparql-update"},
    )
    assert response.status_code == 400


def test_unknown_content_type_is_415(client: TestClient) -> None:
    response = client.post("/sparql", content="{}", headers={"Content-Type": "application/json"})
    assert response.status_code == 415


def test_oversized_query_is_413(client: TestClient) -> None:
    padded_query = SELECT_ALL + " #" + "x" * 60_000
    response = _post_query(client, padded_query)
    assert response.status_code == 413
