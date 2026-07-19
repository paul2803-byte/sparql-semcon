"""FastAPI application factory and HTTP routes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .errors import (
    ContainerFetchError,
    MappingError,
    NotAcceptableError,
    QueryError,
    QueryTimeoutError,
    QueryTooLargeError,
    ScSparqlError,
    StoreNotReadyError,
    UnsupportedMediaTypeError,
)
from .sparql import handle_sparql_request
from .store import OxigraphStore
from .sync import SyncService

_ERROR_STATUS: dict[type[ScSparqlError], int] = {
    QueryError: 400,
    NotAcceptableError: 406,
    QueryTooLargeError: 413,
    UnsupportedMediaTypeError: 415,
    MappingError: 500,
    ContainerFetchError: 502,
    StoreNotReadyError: 503,
    QueryTimeoutError: 504,
}


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
    )


log = structlog.get_logger("sc_sparql")


async def _sync_timer(syncer: SyncService, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await syncer.sync()
        except ScSparqlError as exc:
            log.error("scheduled sync failed", error=str(exc))


def create_app(settings: Settings | None = None) -> FastAPI:
    # Required fields (CONTAINER_DATA_URL) come from the environment at runtime.
    settings = settings or Settings()  # type: ignore[call-arg]
    _configure_logging(settings.log_level)

    store = OxigraphStore(settings.store_path or None)
    syncer = SyncService(settings, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.sync_on_startup:
            try:
                await syncer.sync()
            except ScSparqlError as exc:
                # Serve anyway: /health reports store_ready=false and /sparql answers 503
                # until a later sync (timer or POST /refresh) succeeds.
                log.error("initial sync failed", error=str(exc))
        timer: asyncio.Task[None] | None = None
        if settings.sync_interval_seconds > 0:
            timer = asyncio.create_task(_sync_timer(syncer, settings.sync_interval_seconds))
        yield
        if timer:
            timer.cancel()

    app = FastAPI(
        title="sc-sparql",
        version=__version__,
        description="Read-only SPARQL 1.1 query layer for OwnYourData Semantic Containers",
        lifespan=lifespan,
    )

    @app.exception_handler(ScSparqlError)
    async def _handle_app_error(request: Request, exc: ScSparqlError) -> JSONResponse:
        for exc_type in type(exc).__mro__:
            if exc_type in _ERROR_STATUS:
                status = _ERROR_STATUS[exc_type]
                break
        else:
            status = 500
        return JSONResponse({"error": str(exc)}, status_code=status)

    @app.api_route("/sparql", methods=["GET", "POST"])
    async def sparql(request: Request) -> Response:
        """SPARQL 1.1 Protocol query endpoint (read-only)."""
        return await handle_sparql_request(request, store, settings)

    @app.post("/refresh")
    async def refresh() -> JSONResponse:
        """Re-fetch the container data, re-run the mapping, and reload the store."""
        result = await syncer.sync()
        return JSONResponse({"triples": result.triples, "synced_at": result.synced_at.isoformat()})

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "store_ready": store.ready,
                "triples": store.triple_count,
                "last_sync": syncer.last_sync.isoformat() if syncer.last_sync else None,
            }
        )

    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "sc-sparql",
                "version": __version__,
                "description": (
                    "Read-only SPARQL 1.1 query layer for OwnYourData Semantic Containers"
                ),
                "endpoints": {
                    "sparql": "/sparql",
                    "refresh": "/refresh",
                    "health": "/health",
                    "openapi": "/docs",
                },
                "last_sync": syncer.last_sync.isoformat() if syncer.last_sync else None,
            }
        )

    return app
