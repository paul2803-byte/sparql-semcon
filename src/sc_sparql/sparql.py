"""SPARQL query request handling (POST with query in the body)."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs

import structlog
from fastapi import Request, Response

from .config import Settings
from .errors import (
    QueryError,
    QueryTimeoutError,
    QueryTooLargeError,
    StoreNotReadyError,
    UnsupportedMediaTypeError,
)
from .store import TripleStore

log = structlog.get_logger("sc_sparql.query")

_UPDATE_REJECTION = "SPARQL Update is not supported: this endpoint is read-only"


async def _extract_query(request: Request) -> str:
    """Extract the SPARQL query from the POST body.

    Accepts either a raw ``application/sparql-query`` body or a
    ``application/x-www-form-urlencoded`` body with a ``query`` field.
    """
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    body = await request.body()
    if content_type == "application/sparql-update":
        raise QueryError(_UPDATE_REJECTION)
    if content_type == "application/sparql-query":
        return body.decode("utf-8")
    if content_type == "application/x-www-form-urlencoded":
        form = parse_qs(body.decode("utf-8"))
        if "update" in form:
            raise QueryError(_UPDATE_REJECTION)
        values = form.get("query")
        if not values:
            raise QueryError("missing 'query' form field")
        return values[0]
    raise UnsupportedMediaTypeError(
        f"unsupported content type: {content_type or '(none)'}; "
        "use application/sparql-query or application/x-www-form-urlencoded"
    )


async def handle_sparql_request(
    request: Request, store: TripleStore, settings: Settings
) -> Response:
    query = await _extract_query(request)
    if len(query.encode("utf-8")) > settings.max_query_bytes:
        raise QueryTooLargeError(
            f"query exceeds the maximum size of {settings.max_query_bytes} bytes"
        )
    if not store.ready:
        raise StoreNotReadyError(
            "the store holds no data yet (initial synchronization has not completed)"
        )

    accept = request.headers.get("accept")
    started = time.perf_counter()
    try:
        # Note: on timeout the worker thread finishes in the background; the engine
        # itself has no cancellation hook, but the client gets a prompt 504.
        outcome = await asyncio.wait_for(
            asyncio.to_thread(store.query, query, accept),
            timeout=settings.query_timeout_seconds,
        )
    except TimeoutError as exc:
        raise QueryTimeoutError(
            f"query exceeded the time limit of {settings.query_timeout_seconds}s"
        ) from exc
    log.info(
        "query served",
        method=request.method,
        query_bytes=len(query),
        content_type=outcome.content_type,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return Response(content=outcome.body, media_type=outcome.content_type)
