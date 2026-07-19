"""Runtime configuration, entirely driven by environment variables (12-factor)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration keys, overridable via environment variables of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    container_data_url: str = Field(
        description=(
            "Full URL of the Semantic Container data endpoint returning JSON, "
            "e.g. http://dc-base:3000/api/data"
        )
    )
    rml_mapping_path: Path = Field(
        default=Path("config/mapping.ttl"),
        description="Path to the RML/R2RML mapping file (Turtle)",
    )
    store_path: str = Field(
        default="",
        description="On-disk path for the Oxigraph store; empty string means in-memory",
    )
    sync_on_startup: bool = Field(
        default=True, description="Perform an initial sync before serving queries"
    )
    sync_interval_seconds: int = Field(
        default=0, description="Auto re-sync interval in seconds; 0 disables timer-based sync"
    )
    container_auth_header: str = Field(
        default="",
        description="Static Authorization header value sent to the container (e.g. 'Bearer ...')",
    )
    container_client_id: str = Field(
        default="", description="OAuth2 client id for the container (client-credentials flow)"
    )
    container_client_secret: str = Field(
        default="", description="OAuth2 client secret for the container"
    )
    container_token_url: str = Field(
        default="",
        description=(
            "OAuth2 token endpoint; defaults to '<origin of CONTAINER_DATA_URL>/oauth/token'"
        ),
    )
    container_pagination: bool = Field(
        default=False,
        description=(
            "Fetch the container data page by page (?page=1,2,...) and merge the JSON arrays"
        ),
    )
    http_timeout_seconds: float = Field(
        default=30.0, description="Timeout for HTTP requests to the container"
    )
    max_query_bytes: int = Field(
        default=50_000, description="Maximum accepted SPARQL query size in bytes"
    )
    query_timeout_seconds: float = Field(
        default=30.0, description="Maximum SPARQL query evaluation time in seconds"
    )
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ...)")
    host: str = Field(default="0.0.0.0", description="Bind address")
    port: int = Field(default=8000, description="Bind port")
