"""Typed application errors; each maps to a specific HTTP status code (see main.py)."""


class ScSparqlError(Exception):
    """Base class for all application errors."""


class ContainerFetchError(ScSparqlError):
    """Fetching data from the Semantic Container failed (HTTP 502)."""


class MappingError(ScSparqlError):
    """RML mapping of the container data to RDF failed (HTTP 500)."""


class QueryError(ScSparqlError):
    """The SPARQL query is malformed, missing, or an update operation (HTTP 400)."""


class QueryTooLargeError(ScSparqlError):
    """The SPARQL query exceeds the configured size limit (HTTP 413)."""


class QueryTimeoutError(ScSparqlError):
    """The SPARQL query exceeded the configured time limit (HTTP 504)."""


class UnsupportedMediaTypeError(ScSparqlError):
    """The request body has an unsupported content type (HTTP 415)."""


class NotAcceptableError(ScSparqlError):
    """None of the requested response media types is supported (HTTP 406)."""


class StoreNotReadyError(ScSparqlError):
    """The triplestore has no data yet; the initial sync has not completed (HTTP 503)."""
