"""
Unit tests para mappers/gn_geodcat_to_metadata_record.py
"""

import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef

from ide_dataverse_integrator.mappers.gn_geodcat_to_metadata_record import (
    DCAT,
    DCTERMS,
    GSP,
    _as_str,
    _classify_geometry,
    _crs_title,
    _extract_address_fields,
    _extract_contact_role,
    _extract_list_field,
    _extract_single_field,
    extract_contact,
    extract_links,
    extract_spatial,
    parse_geodcat_to_model,
)

RESOURCES_DIR = Path(__file__).parent / "resources"


def _make_graph(triples_ttl: str) -> Graph:
    """Helper: crea un grafo RDF desde Turtle."""
    prefixes = """
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix dcat: <http://www.w3.org/ns/dcat#> .
    @prefix dct: <http://purl.org/dc/terms/> .
    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
    @prefix vcard: <http://www.w3.org/2006/vcard/ns#> .
    @prefix locn: <http://www.w3.org/ns/locn#> .
    @prefix prov: <http://www.w3.org/ns/prov#> .
    @prefix gsp: <http://www.opengis.net/ont/geosparql#> .
    @prefix geodcatap: <http://data.europa.eu/930/> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    """
    graph = Graph()
    graph.parse(data=prefixes + triples_ttl, format="turtle")
    return graph


def test_parses_real_rdf():
    rdf = (RESOURCES_DIR / "gn-ide-geodcatresponse.rdf").read_text(encoding="utf-8")
    expected = (RESOURCES_DIR / "expected_geodcat_record.json").read_text(encoding="utf-8")
    assert parse_geodcat_to_model(rdf).model_dump() == json.loads(expected)


class TestClassifyGeometry:
    """Tests para _classify_geometry."""

    def test_wkt_literal_by_datatype(self):
        literal = Literal(
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            datatype=GSP.wktLiteral,
        )
        wkt, geojson = _classify_geometry(literal)
        assert wkt == "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        assert geojson is None

    def test_wkt_literal_by_prefix(self):
        literal = Literal("POLYGON((0 0, 1 0, 1 1, 0 0))")
        wkt, geojson = _classify_geometry(literal)
        assert wkt is not None
        assert "POLYGON" in wkt
        assert geojson is None

    def test_geojson_valid(self):
        geojson_str = '{"type": "Point", "coordinates": [0, 0]}'
        literal = Literal(geojson_str)
        wkt, geojson = _classify_geometry(literal)
        assert wkt is None
        assert geojson == {"type": "Point", "coordinates": [0, 0]}

    def test_geojson_invalid_json(self):
        literal = Literal('{"coordinates": [broken}')
        wkt, geojson = _classify_geometry(literal)
        assert wkt is None
        assert geojson == '{"coordinates": [broken}'

    def test_unrecognized_geometry(self):
        literal = Literal("some random string")
        wkt, geojson = _classify_geometry(literal)
        assert wkt is None
        assert geojson is None


class TestExtractSpatial:
    """Tests para extract_spatial."""

    def test_returns_empty_when_no_spatial(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_spatial(graph, dataset)
        assert result == {"wkt": None, "geojson": None}

    def test_extracts_wkt(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                dct:spatial <http://example.org/loc> .
            <http://example.org/loc> a dct:Location ;
                locn:geometry "POLYGON((0 0, 1 0, 1 1, 0 0))"^^gsp:wktLiteral .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_spatial(graph, dataset)
        assert "POLYGON" in result["wkt"]
        assert result["geojson"] is None

    def test_ignores_non_literal_geometry(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                dct:spatial <http://example.org/loc> .
            <http://example.org/loc> locn:geometry <http://example.org/geom> .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_spatial(graph, dataset)
        assert result == {"wkt": None, "geojson": None}


class TestExtractContactRole:
    """Tests para _extract_contact_role."""

    def test_extracts_role_from_had_role(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                prov:qualifiedAttribution <http://example.org/attr> .
            <http://example.org/attr>
                dcat:hadRole <http://example.org/role/author> .
        """)
        dataset = URIRef("http://example.org/ds")
        assert _extract_contact_role(graph, dataset) == "author"

    def test_extracts_role_from_dct_type_fallback(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                prov:qualifiedAttribution <http://example.org/attr> .
            <http://example.org/attr>
                dct:type <http://example.org/role/publisher> .
        """)
        dataset = URIRef("http://example.org/ds")
        assert _extract_contact_role(graph, dataset) == "publisher"

    def test_returns_empty_when_no_attribution(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        dataset = URIRef("http://example.org/ds")
        assert _extract_contact_role(graph, dataset) == ""


class TestExtractAddressFields:
    """Tests para _extract_address_fields."""

    def test_returns_empty_when_no_address(self):
        graph = _make_graph("")
        result = _extract_address_fields(graph, None)
        assert result == {
            "street": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "country": "",
        }

    def test_extracts_all_fields(self):
        graph = _make_graph("""
            <http://example.org/addr>
                vcard:street-address "Av. Siempre Viva 742" ;
                vcard:locality "Springfield" ;
                vcard:region "Oregon" ;
                vcard:postal-code "97403" ;
                vcard:country-name "USA" .
        """)
        address_node = URIRef("http://example.org/addr")
        result = _extract_address_fields(graph, address_node)
        assert result["street"] == "Av. Siempre Viva 742"
        assert result["city"] == "Springfield"
        assert result["state"] == "Oregon"
        assert result["postal_code"] == "97403"
        assert result["country"] == "USA"


class TestExtractContact:
    """Tests para extract_contact."""

    def test_returns_empty_dict_when_no_contact(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        dataset = URIRef("http://example.org/ds")
        assert extract_contact(graph, dataset) == {}

    def test_extracts_organization(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                dcat:contactPoint <http://example.org/cp> .
            <http://example.org/cp> vcard:fn "ACME Corp" .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_contact(graph, dataset)
        assert result["organization"] == "ACME Corp"


class TestExtractLinks:
    """Tests para extract_links."""

    def test_returns_empty_when_no_landing_pages(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        dataset = URIRef("http://example.org/ds")
        assert extract_links(graph, dataset) == []

    def test_extracts_links(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                dcat:landingPage <http://example.org/page1> .
            <http://example.org/page1>
                dct:title "Page 1" ;
                dct:description "Description 1" .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_links(graph, dataset)
        assert len(result) == 1
        assert result[0]["url"] == "http://example.org/page1"
        assert result[0]["title"] == "Page 1"
        assert result[0]["description"] == "Description 1"

    def test_link_without_title_or_description(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset ;
                dcat:landingPage <http://example.org/page2> .
        """)
        dataset = URIRef("http://example.org/ds")
        result = extract_links(graph, dataset)
        assert len(result) == 1
        assert result[0]["title"] == ""
        assert result[0]["description"] == ""


class TestCrsTitle:
    """Tests para _crs_title."""

    def test_extracts_title(self):
        graph = _make_graph("""
            <http://example.org/crs> dct:title "EPSG:4326" .
        """)
        node = URIRef("http://example.org/crs")
        assert _crs_title(node, graph) == "EPSG:4326"

    def test_returns_empty_when_no_title(self):
        graph = _make_graph("""
            <http://example.org/crs> a dct:Standard .
        """)
        node = URIRef("http://example.org/crs")
        assert _crs_title(node, graph) == ""


class TestExtractSingleField:
    """Tests para _extract_single_field."""

    def test_extracts_value(self):
        graph = _make_graph("""
            <http://example.org/ds> dct:title "My Dataset" .
        """)
        node = URIRef("http://example.org/ds")
        result = _extract_single_field(graph, node, DCTERMS.title, _as_str)
        assert result == "My Dataset"

    def test_returns_empty_when_missing(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        node = URIRef("http://example.org/ds")
        result = _extract_single_field(graph, node, DCTERMS.title, _as_str)
        assert result == ""


class TestExtractListField:
    """Tests para _extract_list_field."""

    def test_extracts_sorted_and_deduped(self):
        graph = _make_graph("""
            <http://example.org/ds>
                dcat:keyword "beta" ;
                dcat:keyword "alpha" ;
                dcat:keyword "beta" .
        """)
        node = URIRef("http://example.org/ds")
        result = _extract_list_field(graph, node, DCAT.keyword, _as_str)
        assert result == ["alpha", "beta"]

    def test_returns_empty_list_when_missing(self):
        graph = _make_graph("""
            <http://example.org/ds> a dcat:Dataset .
        """)
        node = URIRef("http://example.org/ds")
        result = _extract_list_field(graph, node, DCAT.keyword, _as_str)
        assert result == []

    def test_filters_empty_values(self):
        graph = _make_graph("""
            <http://example.org/ds>
                dcat:keyword "" ;
                dcat:keyword "valid" .
        """)
        node = URIRef("http://example.org/ds")
        result = _extract_list_field(graph, node, DCAT.keyword, _as_str)
        assert result == ["valid"]


class TestParseGeodcatSynthetic:
    """Tests para parse_geodcat_to_model con casos edge."""

    def test_raises_on_no_dataset(self):
        rdf_text = """<?xml version="1.0" encoding="utf-8"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:dcat="http://www.w3.org/ns/dcat#">
            <rdf:Description>
                <rdf:type rdf:resource="http://www.w3.org/ns/dcat#Catalog"/>
            </rdf:Description>
        </rdf:RDF>
        """
        with pytest.raises(ValueError, match="No se encontró dcat:Dataset"):
            parse_geodcat_to_model(rdf_text)

    def test_minimal_dataset(self):
        rdf_text = """<?xml version="1.0" encoding="utf-8"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:dcat="http://www.w3.org/ns/dcat#"
                 xmlns:dct="http://purl.org/dc/terms/"
                 xmlns:foaf="http://xmlns.com/foaf/0.1/">
            <rdf:Description>
                <rdf:type rdf:resource="http://www.w3.org/ns/dcat#Dataset"/>
                <dct:title xml:lang="en">Test</dct:title>
                <foaf:isPrimaryTopicOf>
                    <rdf:Description>
                        <rdf:type rdf:resource="http://www.w3.org/ns/dcat#CatalogRecord"/>
                        <dct:identifier>test-id-123</dct:identifier>
                    </rdf:Description>
                </foaf:isPrimaryTopicOf>
            </rdf:Description>
        </rdf:RDF>
        """
        record = parse_geodcat_to_model(rdf_text)
        assert record.id == "test-id-123"
        assert record.title == "Test"
        assert record.keywords == []
        assert record.links == []

    def test_no_catalog_record(self):
        """Si no hay CatalogRecord, los campos de catalog_record quedan vacíos."""
        rdf_text = """<?xml version="1.0" encoding="utf-8"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:dcat="http://www.w3.org/ns/dcat#"
                 xmlns:dct="http://purl.org/dc/terms/">
            <rdf:Description>
                <rdf:type rdf:resource="http://www.w3.org/ns/dcat#Dataset"/>
                <dct:title xml:lang="en">Orphan Dataset</dct:title>
            </rdf:Description>
        </rdf:RDF>
        """
        record = parse_geodcat_to_model(rdf_text)
        assert record.id == ""
        assert record.modified == ""
        assert record.language == ""
        assert record.title == "Orphan Dataset"
