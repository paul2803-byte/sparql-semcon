import pytest
from pydantic import ValidationError

from sc_sparql.config import Settings


def test_missing_container_data_url_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CONTAINER_DATA_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(container_data_url="http://x/api/data", _env_file=None)
    assert settings.sync_on_startup is True
    assert settings.sync_interval_seconds == 0
    assert settings.max_query_bytes == 50_000
    assert settings.store_path == ""


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTAINER_DATA_URL", "http://container:3000/api/data")
    monkeypatch.setenv("SYNC_INTERVAL_SECONDS", "600")
    settings = Settings(_env_file=None)
    assert settings.container_data_url == "http://container:3000/api/data"
    assert settings.sync_interval_seconds == 600
