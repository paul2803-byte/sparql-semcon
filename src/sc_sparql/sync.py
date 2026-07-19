"""Synchronization pipeline: fetch container JSON -> RML mapping -> atomic store reload."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import structlog

from .config import Settings
from .errors import ContainerFetchError
from .mapping import map_json_to_rdf
from .store import TripleStore

log = structlog.get_logger("sc_sparql.sync")


@dataclass(frozen=True)
class SyncResult:
    triples: int
    synced_at: datetime


class SyncService:
    """Runs at most one sync at a time; concurrent requests coalesce onto the same run."""

    def __init__(self, settings: Settings, store: TripleStore) -> None:
        self._settings = settings
        self._store = store
        self._lock = asyncio.Lock()
        self._last_result: SyncResult | None = None

    @property
    def last_sync(self) -> datetime | None:
        return self._last_result.synced_at if self._last_result else None

    async def sync(self) -> SyncResult:
        requested_at = datetime.now(UTC)
        async with self._lock:
            # Coalesce: if another sync completed while we waited for the lock,
            # return its result instead of hitting the container again.
            if self._last_result and self._last_result.synced_at >= requested_at:
                return self._last_result

            started = time.perf_counter()
            payload = await self._fetch()
            rdf = await asyncio.to_thread(map_json_to_rdf, payload, self._settings.rml_mapping_path)
            triples = await asyncio.to_thread(self._store.replace, rdf)
            result = SyncResult(triples=triples, synced_at=datetime.now(UTC))
            self._last_result = result
            log.info(
                "sync completed",
                triples=triples,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                source=self._settings.container_data_url,
            )
            return result

    async def _fetch(self) -> bytes:
        settings = self._settings
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                headers = {"Accept": "application/json"}
                headers.update(await self._auth_headers(client))
                if settings.container_pagination:
                    return await self._fetch_paginated(client, headers)
                response = await client.get(settings.container_data_url, headers=headers)
                self._raise_for_status(response)
                return response.content
        except httpx.HTTPError as exc:
            raise ContainerFetchError(
                f"failed to fetch {settings.container_data_url}: {exc}"
            ) from exc

    async def _fetch_paginated(self, client: httpx.AsyncClient, headers: dict[str, str]) -> bytes:
        """Fetch ?page=1,2,... and merge the JSON arrays until an empty page is returned."""
        items: list[object] = []
        page = 1
        while True:
            response = await client.get(
                self._settings.container_data_url, params={"page": page}, headers=headers
            )
            self._raise_for_status(response)
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            page += 1
        return json.dumps(items).encode("utf-8")

    async def _auth_headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        settings = self._settings
        if settings.container_auth_header:
            return {"Authorization": settings.container_auth_header}
        if settings.container_client_id and settings.container_client_secret:
            token_url = settings.container_token_url or self._default_token_url()
            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.container_client_id,
                    "client_secret": settings.container_client_secret,
                },
            )
            self._raise_for_status(response)
            token = response.json().get("access_token")
            if not token:
                raise ContainerFetchError(f"no access_token in response from {token_url}")
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _default_token_url(self) -> str:
        parts = urlsplit(self._settings.container_data_url)
        return f"{parts.scheme}://{parts.netloc}/oauth/token"

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code // 100 != 2:
            raise ContainerFetchError(
                f"container answered {response.status_code} for {response.request.url}"
            )
