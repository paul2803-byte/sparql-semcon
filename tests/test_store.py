import pytest

from sc_sparql.errors import NotAcceptableError, QueryError
from sc_sparql.store import OxigraphStore

NTRIPLES = (
    b'<http://example.org/id/1> <http://example.org/ns#value> "42.5" .\n'
    b'<http://example.org/id/2> <http://example.org/ns#value> "17.0" .\n'
)


def test_replace_and_count() -> None:
    store = OxigraphStore()
    assert store.ready is False
    assert store.replace(NTRIPLES) == 2
    assert store.triple_count == 2
    assert store.ready is True


def test_replace_swaps_content() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    store.replace(b'<http://example.org/id/3> <http://example.org/ns#value> "1.0" .\n')
    assert store.triple_count == 1


def test_select_query_json() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    outcome = store.query("SELECT ?s WHERE { ?s ?p ?o }", accept=None)
    assert outcome.content_type == "application/sparql-results+json"
    assert b"bindings" in outcome.body


def test_construct_query_turtle() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    outcome = store.query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", accept="text/turtle")
    assert outcome.content_type == "text/turtle"


def test_invalid_query_raises_query_error() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    with pytest.raises(QueryError):
        store.query("NOT A SPARQL QUERY", accept=None)


def test_update_raises_query_error() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    with pytest.raises(QueryError):
        store.query("DELETE WHERE { ?s ?p ?o }", accept=None)


def test_unsupported_accept_raises() -> None:
    store = OxigraphStore()
    store.replace(NTRIPLES)
    with pytest.raises(NotAcceptableError):
        store.query("SELECT ?s WHERE { ?s ?p ?o }", accept="text/html")


def test_persistent_store(tmp_path: str) -> None:
    store = OxigraphStore(str(tmp_path) + "/oxigraph")
    store.replace(NTRIPLES)
    assert store.triple_count == 2
