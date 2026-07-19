from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from sc_sparql.config import Settings
from sc_sparql.main import create_app

DATA_URL = "http://container.test/api/data"

SAMPLE_RECORDS = [
    {"id": "1", "value": "42.5"},
    {"id": "2", "value": "17.0"},
]
# Each record yields 2 triples (rdf:type + ex:value).
SAMPLE_TRIPLES = 4

MAPPING = """\
@prefix rr:  <http://www.w3.org/ns/r2rml#> .
@prefix rml: <http://semweb.mmlab.be/ns/rml#> .
@prefix ql:  <http://semweb.mmlab.be/ns/ql#> .
@prefix ex:  <http://example.org/ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<#RecordMapping>
  rml:logicalSource [
    rml:source "data.json" ;
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
"""


@pytest.fixture()
def mapping_file(tmp_path: Path) -> Path:
    path = tmp_path / "mapping.ttl"
    path.write_text(MAPPING, encoding="utf-8")
    return path


@pytest.fixture()
def settings(mapping_file: Path) -> Settings:
    return Settings(
        container_data_url=DATA_URL,
        rml_mapping_path=mapping_file,
        sync_on_startup=True,
        query_timeout_seconds=15,
        _env_file=None,
    )


@pytest.fixture()
def container_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(DATA_URL).mock(return_value=Response(200, json=SAMPLE_RECORDS))
        yield mock


@pytest.fixture()
def client(settings: Settings, container_mock: respx.MockRouter) -> Iterator[TestClient]:
    """App with a mocked container; the startup sync loads SAMPLE_RECORDS."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def cold_client(mapping_file: Path, container_mock: respx.MockRouter) -> Iterator[TestClient]:
    """App that has not synced yet (store empty)."""
    cold_settings = Settings(
        container_data_url=DATA_URL,
        rml_mapping_path=mapping_file,
        sync_on_startup=False,
        _env_file=None,
    )
    with TestClient(create_app(cold_settings)) as test_client:
        yield test_client
