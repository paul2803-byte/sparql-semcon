"""JSON-to-RDF conversion via morph-kgc using a user-supplied RML/R2RML mapping."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .errors import MappingError

# `file_path` overrides the rml:source declared in the mapping, so the same mapping
# file works no matter where the fetched snapshot is written.
_MORPH_CONFIG_TEMPLATE = """\
[CONFIGURATION]
logging_level=WARNING

[ContainerData]
mappings={mappings}
file_path={file_path}
"""


def map_json_to_rdf(json_payload: bytes, mapping_path: Path) -> bytes:
    """Materialize the container's JSON payload into RDF (N-Triples bytes).

    Runs synchronously and can take a while for large payloads; call it from a
    worker thread (``asyncio.to_thread``) in async code.
    """
    try:
        json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise MappingError(f"container returned invalid JSON: {exc}") from exc
    if not mapping_path.is_file():
        raise MappingError(f"RML mapping file not found: {mapping_path}")

    import morph_kgc  # deferred: heavy import (pandas et al.)

    with tempfile.TemporaryDirectory(prefix="sc-sparql-") as tmp_dir:
        data_file = Path(tmp_dir) / "data.json"
        data_file.write_bytes(json_payload)
        config = _MORPH_CONFIG_TEMPLATE.format(mappings=mapping_path.resolve(), file_path=data_file)
        try:
            graph = morph_kgc.materialize(config)
        except Exception as exc:  # morph-kgc raises assorted exception types
            raise MappingError(f"RML mapping failed: {exc}") from exc

    ntriples: str = graph.serialize(format="nt")
    return ntriples.encode("utf-8")
