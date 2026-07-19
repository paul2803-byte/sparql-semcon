"""Triplestore abstraction and the embedded Oxigraph implementation."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pyoxigraph import (
    QueryBoolean,
    QueryResultsFormat,
    QuerySolutions,
    RdfFormat,
    Store,
)

from .errors import NotAcceptableError, QueryError

DEFAULT_SOLUTION_TYPE = "application/sparql-results+json"
DEFAULT_GRAPH_TYPE = "text/turtle"

SOLUTION_MEDIA_TYPES: dict[str, QueryResultsFormat] = {
    "application/sparql-results+json": QueryResultsFormat.JSON,
    "application/json": QueryResultsFormat.JSON,
    "application/sparql-results+xml": QueryResultsFormat.XML,
    "text/csv": QueryResultsFormat.CSV,
    "text/tab-separated-values": QueryResultsFormat.TSV,
}

GRAPH_MEDIA_TYPES: dict[str, RdfFormat] = {
    "text/turtle": RdfFormat.TURTLE,
    "application/n-triples": RdfFormat.N_TRIPLES,
    "application/rdf+xml": RdfFormat.RDF_XML,
}


@dataclass(frozen=True)
class QueryOutcome:
    """A serialized query result together with its media type."""

    body: bytes
    content_type: str


def _accepted_types(accept: str | None) -> list[str]:
    """Parse an Accept header into an ordered list of media types (q-weights ignored)."""
    if not accept:
        return []
    types: list[str] = []
    for part in accept.split(","):
        media_type = part.split(";")[0].strip().lower()
        if media_type:
            types.append(media_type)
    return types


def negotiate[T](accept: str | None, supported: Mapping[str, T], default: str) -> tuple[str, T]:
    """Pick the first supported media type from the Accept header, or the default."""
    wanted = _accepted_types(accept)
    if not wanted:
        return default, supported[default]
    for media_type in wanted:
        if media_type == "*/*":
            return default, supported[default]
        if media_type in supported:
            return media_type, supported[media_type]
    raise NotAcceptableError(
        f"none of the requested media types is supported; supported: {', '.join(supported)}"
    )


class TripleStore(Protocol):
    """Minimal engine-agnostic interface so the SPARQL engine stays swappable."""

    def replace(self, rdf_nquads: bytes) -> int:
        """Replace the entire store content with the given N-Quads; returns the triple count."""
        ...

    def query(self, sparql: str, accept: str | None) -> QueryOutcome:
        """Evaluate a read-only SPARQL query and serialize per content negotiation."""
        ...

    @property
    def triple_count(self) -> int: ...

    @property
    def ready(self) -> bool: ...


class OxigraphStore:
    """Embedded Oxigraph store (in-memory by default, on-disk when a path is given)."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._store = Store(path) if path else Store()
        self._swap_lock = threading.Lock()
        # A persistent store may already contain data from a previous run.
        self._ready = len(self._store) > 0

    def replace(self, rdf_nquads: bytes) -> int:
        if self._path:
            # On-disk stores cannot be swapped wholesale; clear + reload under a lock.
            with self._swap_lock:
                self._store.clear()
                self._store.bulk_load(rdf_nquads, RdfFormat.N_QUADS)
                count = len(self._store)
        else:
            # Atomic swap: load into a fresh store, then flip the reference so queries
            # never observe a half-loaded graph.
            fresh = Store()
            fresh.bulk_load(rdf_nquads, RdfFormat.N_QUADS)
            count = len(fresh)
            with self._swap_lock:
                self._store = fresh
        self._ready = True
        return count

    def query(self, sparql: str, accept: str | None) -> QueryOutcome:
        store = self._store  # snapshot the reference; swaps do not affect a running query
        try:
            results = store.query(sparql)
        except (SyntaxError, ValueError, OSError) as exc:
            raise QueryError(str(exc)) from exc
        if isinstance(results, QuerySolutions | QueryBoolean):
            content_type, results_format = negotiate(
                accept, SOLUTION_MEDIA_TYPES, DEFAULT_SOLUTION_TYPE
            )
            body = results.serialize(format=results_format)
        else:
            content_type, rdf_format = negotiate(accept, GRAPH_MEDIA_TYPES, DEFAULT_GRAPH_TYPE)
            body = results.serialize(format=rdf_format)
        assert body is not None
        return QueryOutcome(body=body, content_type=content_type)

    @property
    def triple_count(self) -> int:
        return len(self._store)

    @property
    def ready(self) -> bool:
        return self._ready
