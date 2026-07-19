# sc-sparql

**A read-only SPARQL 1.1 query layer for [OwnYourData Semantic Containers](https://ownyourdata.github.io/semcon/).**

`sc-sparql` is a small sidecar service that runs *next to* an existing Semantic
Container (e.g. an [`oydeu/dc-base`](https://hub.docker.com/r/oydeu/dc-base)
instance) and adds exactly one capability: running **SPARQL queries** over the
container's data. The Semantic Container itself is never modified — `sc-sparql`
only reads from its public HTTP data API.

It is the modern successor of the legacy
[`sem-con/sc-sparql`](https://github.com/sem-con/sc-sparql) image
(Ruby + Java 8 + Fuseki): a single Python process with an embedded
[Oxigraph](https://github.com/oxigraph/oxigraph) triplestore and the
[morph-kgc](https://github.com/morph-kgc/morph-kgc) RML engine.

## How it works

```
                 ┌──────────────────────────────────────────────┐
   SPARQL        │              sc-sparql (this app)             │
   client  ───▶  │                                              │
  GET/POST       │  FastAPI ──▶ query handler ──▶ Oxigraph store │
  /sparql        │                                    ▲          │
                 │  sync: fetch ─▶ RML mapping ───────┘          │
                 └───────┬──────────────────────────────────────┘
                         │ HTTP GET (JSON)
                         ▼
             ┌───────────────────────────┐
             │  Semantic Container        │
             │  (oydeu/dc-base,           │
             │   GET /api/data)           │   ← unmodified
             └───────────────────────────┘
```

1. **Sync** — the service fetches the container's data (JSON) from
   `CONTAINER_DATA_URL`, converts it to RDF using your **RML mapping**, and
   loads the result into the embedded triplestore. The new snapshot replaces
   the old one **atomically**, so queries never see a half-loaded graph.
   Syncs run at startup, optionally on a timer, and on demand via
   `POST /refresh`.
2. **Query** — clients send standard SPARQL 1.1 queries to `/sparql` and get
   results in the format requested via the `Accept` header. The endpoint is
   strictly **read-only**: SPARQL Update operations are rejected.

## Quickstart

### With Docker Compose (service + demo container)

```bash
docker compose up --build
```

This starts an unmodified `oydeu/dc-base` Semantic Container on port 3000 and
`sc-sparql` on port 8000. Once the container holds data and the initial sync
has run, query away:

```bash
curl -G http://localhost:8000/sparql \
  --data-urlencode 'query=SELECT * WHERE { ?s ?p ?o } LIMIT 10' \
  -H 'Accept: application/sparql-results+json'
```

### Standalone against an existing container

```bash
docker build -t sc-sparql .
docker run --rm -p 8000:8000 \
  -e CONTAINER_DATA_URL=https://my-container.example.com/api/data \
  -v $(pwd)/config:/app/config:ro \
  sc-sparql
```

### Local development (no Docker)

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
cp .env.example .env          # then edit CONTAINER_DATA_URL etc.
uv run uvicorn sc_sparql.main:create_app --factory --host 0.0.0.0 --port 8000
```

Interactive OpenAPI documentation is served at <http://localhost:8000/docs>.

## Using the SPARQL endpoint

`/sparql` implements the query operation of the
[SPARQL 1.1 Protocol](https://www.w3.org/TR/sparql11-protocol/), so any
standard SPARQL client, library, or federation engine can talk to it.

**GET** (query in the URL):

```bash
curl -G http://localhost:8000/sparql \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }'
```

**POST, form-encoded:**

```bash
curl http://localhost:8000/sparql \
  --data-urlencode 'query=ASK { ?s a <http://example.org/ns#Record> }'
```

**POST, raw query body:**

```bash
curl http://localhost:8000/sparql \
  -H 'Content-Type: application/sparql-query' \
  -H 'Accept: text/csv' \
  --data 'SELECT ?s ?value WHERE { ?s <http://example.org/ns#value> ?value }'
```

**Result formats** (choose via the `Accept` header):

| Query type | Formats (first = default) |
|---|---|
| `SELECT` / `ASK` | `application/sparql-results+json`, `application/sparql-results+xml`, `text/csv`, `text/tab-separated-values` |
| `CONSTRUCT` / `DESCRIBE` | `text/turtle`, `application/n-triples`, `application/rdf+xml` |

**Status codes**: `200` success · `400` malformed query or attempted update ·
`406` unsupported `Accept` type · `413` query too large · `415` unsupported
request content type · `503` store not synced yet · `504` query timeout.

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `POST /refresh` | Re-fetch container data and reload the store; returns `{"triples": n, "synced_at": "..."}` |
| `GET /health` | Liveness/readiness: `{"status": "ok", "store_ready": true, "triples": 1234, "last_sync": "..."}` |
| `GET /` | Service metadata |
| `GET /docs` | Interactive OpenAPI/Swagger UI |

## Configuration

Everything is configured through environment variables (or a local `.env`
file; see [.env.example](.env.example)):

| Variable | Meaning | Default |
|---|---|---|
| `CONTAINER_DATA_URL` | Data endpoint of the Semantic Container, e.g. `http://dc-base:3000/api/data` | **required** |
| `RML_MAPPING_PATH` | RML/R2RML mapping file (Turtle) | `config/mapping.ttl` |
| `STORE_PATH` | Directory for a persistent Oxigraph store; empty = in-memory | `""` |
| `SYNC_ON_STARTUP` | Sync before serving | `true` |
| `SYNC_INTERVAL_SECONDS` | Timer-based re-sync; `0` = off | `0` |
| `CONTAINER_PAGINATION` | Fetch `?page=1,2,...` and merge the JSON arrays | `false` |
| `CONTAINER_AUTH_HEADER` | Static `Authorization` header sent to the container | unset |
| `CONTAINER_CLIENT_ID` / `CONTAINER_CLIENT_SECRET` | OAuth2 client-credentials towards the container (dc-base/Doorkeeper) | unset |
| `CONTAINER_TOKEN_URL` | Token endpoint override | `<origin>/oauth/token` |
| `HTTP_TIMEOUT_SECONDS` | Timeout for container requests | `30` |
| `MAX_QUERY_BYTES` | Maximum SPARQL query size | `50000` |
| `QUERY_TIMEOUT_SECONDS` | Maximum query evaluation time | `30` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, ... | `INFO` |
| `HOST` / `PORT` | Bind address | `0.0.0.0` / `8000` |

## Supplying an RML mapping

The mapping tells `sc-sparql` how the container's JSON records become RDF.
Any valid [RML](https://rml.io/specs/rml/) or R2RML mapping works — point
`RML_MAPPING_PATH` at it. The shipped example
([config/mapping.ttl](config/mapping.ttl)) maps a JSON array of
`{"id": ..., "value": ...}` records:

```turtle
<#RecordMapping>
  rml:logicalSource [
    rml:source "data.json" ;                  # placeholder, see note below
    rml:referenceFormulation ql:JSONPath ;
    rml:iterator "$[*]"
  ] ;
  rr:subjectMap [
    rr:template "http://example.org/id/{id}" ;
    rr:class ex:Record
  ] ;
  rr:predicateObjectMap [
    rr:predicate ex:value ;
    rr:objectMap [ rml:reference "value" ; rr:datatype xsd:decimal ]
  ] .
```

Note: the `rml:source` file name in the mapping is a placeholder. At sync
time, `sc-sparql` writes the JSON fetched from the container to a temporary
file and points the mapping engine at it, overriding the declared source. You
only need to get the **iterator and references** right for your container's
data shape.

**Migrating legacy mappings**: RML files written for the old
`sem-con/sc-sparql` (e.g. iterators like `$.provision.content[*]`) are
generally reusable as-is — adjust the iterator if your container API wraps
records differently, and keep the rest.

## Security notes

- The service is **read-only**; SPARQL Update, and any data-writing API, do
  not exist here. The only outbound credential is the one used to *read* from
  the container.
- There is deliberately **no built-in authentication**. If the endpoint must
  be protected, put it behind a reverse proxy or API gateway.
- Query size (`MAX_QUERY_BYTES`) and evaluation time
  (`QUERY_TIMEOUT_SECONDS`) are limited to keep the endpoint responsive.
- The Docker image runs as a non-root user.

## Development

```bash
uv sync                    # install runtime + dev dependencies
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src            # type check (strict)
uv run pytest              # test suite (mocks the container; no network needed)
```

Layout:

```
src/sc_sparql/
├── main.py      # FastAPI app factory + routes
├── config.py    # environment-driven settings
├── sync.py      # fetch → map → atomic reload pipeline
├── mapping.py   # morph-kgc (RML) wrapper
├── store.py     # TripleStore protocol + embedded Oxigraph implementation
├── sparql.py    # SPARQL protocol parsing + content negotiation
└── errors.py    # typed errors mapped to HTTP status codes
```

## License

[MIT](LICENSE) — like its predecessor.
