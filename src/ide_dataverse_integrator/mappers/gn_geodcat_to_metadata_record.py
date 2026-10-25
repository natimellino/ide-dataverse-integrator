"""
Mapper de GeoDCAT-AP RDF a MetadataRecord.

Parsea la respuesta GeoDCAT-AP de GeoNetwork y construye un MetadataRecord
con los campos principales del dataset.
"""
import json

from rdflib import RDF, Graph, Literal, Namespace, URIRef

from ide_dataverse_integrator.models.metadata_record import MetadataRecord
from ide_dataverse_integrator.utils import clean_url, extract_uri_slug

DCAT = Namespace("http://www.w3.org/ns/dcat#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
LOCN = Namespace("http://www.w3.org/ns/locn#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
GEODCATAP = Namespace("http://data.europa.eu/930/")
GSP = Namespace("http://www.opengis.net/ont/geosparql#")
PROV = Namespace("http://www.w3.org/ns/prov#")


def _classify_geometry(geometry_literal: Literal) -> tuple[str | None, ...]:
    """
    Clasifica un Literal de geometría en WKT o GeoJSON.

    Returns:
        Tupla (wkt, geojson) donde uno de los dos será el valor y el otro None.
    """
    geometry_text = str(geometry_literal).strip()

    is_wkt = (
        geometry_literal.datatype == GSP.wktLiteral
        or geometry_text.startswith("POLYGON")
    )
    if is_wkt:
        return geometry_text, None

    if "coordinates" not in geometry_text:
        return None, None

    try:
        return None, json.loads(geometry_text)
    except json.JSONDecodeError:
        return None, geometry_text


def extract_spatial(graph: Graph, dataset_node: URIRef) -> dict:
    """
    Extrae información espacial de un dataset. Puede devolver un WKT o GeoJSON.

    Args:
        graph: Grafo RDF.
        dataset_node: Nodo del dataset.

    Returns:
        Diccionario con claves "wkt" y "geojson".
    """
    spatial_node = graph.value(dataset_node, DCTERMS.spatial)
    if not spatial_node:
        return {"wkt": None, "geojson": None}

    wkt_geometry = None
    geojson_geometry = None

    for geometry in graph.objects(spatial_node, LOCN.geometry):
        if not isinstance(geometry, Literal):
            continue

        wkt_candidate, geojson_candidate = _classify_geometry(geometry)
        if wkt_candidate:
            wkt_geometry = wkt_candidate
        if geojson_candidate:
            geojson_geometry = geojson_candidate

    return {"wkt": wkt_geometry, "geojson": geojson_geometry}


def _extract_contact_role(graph: Graph, dataset_node: URIRef) -> str:
    """Extrae el rol del punto de contacto desde prov:qualifiedAttribution."""
    for attribution in graph.objects(dataset_node, PROV.qualifiedAttribution):
        role_node = (
            graph.value(attribution, DCAT.hadRole)
            or graph.value(attribution, DCTERMS.type)
        )
        if role_node:
            return extract_uri_slug(role_node)
    return ""


def _extract_address_fields(graph: Graph, address_node) -> dict:
    """Extrae campos de dirección de un nodo vcard:Address."""
    if not address_node:
        return {
            "street": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "country": "",
        }

    return {
        "street": str(graph.value(address_node, VCARD["street-address"]) or ""),
        "city": str(graph.value(address_node, VCARD.locality) or ""),
        "state": str(graph.value(address_node, VCARD.region) or ""),
        "postal_code": str(graph.value(address_node, VCARD["postal-code"]) or ""),
        "country": str(graph.value(address_node, VCARD["country-name"]) or ""),
    }


def extract_contact(graph: Graph, dataset_node: URIRef) -> dict:
    """
    Extrae información de contacto de un dataset.

    Args:
        graph: Grafo RDF.
        dataset_node: Nodo del dataset.

    Returns:
        Diccionario con información de contacto (organization, role, website, address).
    """
    contact_node = graph.value(dataset_node, DCAT.contactPoint)
    if not contact_node:
        return {}

    address_node = graph.value(contact_node, VCARD.hasAddress)

    return {
        "organization": str(graph.value(contact_node, VCARD.fn) or ""),
        "role": _extract_contact_role(graph, dataset_node),
        "website": clean_url(graph.value(contact_node, VCARD.hasURL)),
        "address": _extract_address_fields(graph, address_node),
    }


def extract_links(graph: Graph, dataset_node: URIRef) -> list:
    """
    Extrae información de enlaces (landing pages) de un dataset.

    Args:
        graph: Grafo RDF.
        dataset_node: Nodo del dataset.

    Returns:
        Lista de diccionarios con url, title y description.
    """
    return [
        {
            "url": str(document),
            "title": str(graph.value(document, DCTERMS.title) or ""),
            "description": str(graph.value(document, DCTERMS.description) or ""),
        }
        for document in graph.objects(dataset_node, DCAT.landingPage)
    ]


def _as_str(value, graph) -> str:
    return str(value)


def _as_stripped_str(value, graph) -> str:
    return str(value).strip()


def _as_uri_slug(value, graph) -> str:
    return extract_uri_slug(value)


def _crs_title(node, graph):
    """Extrae el título de un nodo de sistema de referencia."""
    return str(graph.value(node, DCTERMS.title) or "")


SIMPLE_FIELD_SPECS = [
    ("id", "catalog_record", DCTERMS.identifier, "single", _as_str),
    ("modified", "catalog_record", DCTERMS.modified, "single", _as_str),
    ("language", "catalog_record", DCTERMS.language, "single", _as_uri_slug),
    ("resource_type", "dataset", GEODCATAP.resourceType, "single", _as_uri_slug),
    ("title", "dataset", DCTERMS.title, "single", _as_stripped_str),
    ("description", "dataset", DCTERMS.description, "single", _as_stripped_str),
    ("keywords", "dataset", DCAT.keyword, "list", _as_str),
    ("crs", "dataset", GEODCATAP.referenceSystem, "list", _crs_title),
]

COMPLEX_HANDLERS = {
    "spatial": extract_spatial,
    "contact": extract_contact,
    "links": extract_links,
}


def _extract_single_field(graph, source_node, predicate, transform_fn):
    """Extrae un campo de cardinalidad 'single' del grafo."""
    raw_value = graph.value(source_node, predicate)
    if raw_value is None:
        return ""
    return transform_fn(raw_value, graph)


def _extract_list_field(graph, source_node, predicate, transform_fn):
    """Extrae un campo de cardinalidad 'list' del grafo (deduplicado y ordenado)."""
    items = [
        transformed
        for obj in graph.objects(source_node, predicate)
        if (transformed := transform_fn(obj, graph))
    ]
    return sorted(set(items))


def _process_simple_fields(graph, entity_sources) -> dict:
    """Procesa todas las especificaciones de campos simples y devuelve un dict."""
    result = {}

    for field_name, source_key, predicate, cardinality, transform_fn in SIMPLE_FIELD_SPECS:
        source_node = entity_sources.get(source_key)

        if not source_node:
            result[field_name] = [] if cardinality == "list" else ""
            continue

        if cardinality == "list":
            result[field_name] = _extract_list_field(
                graph, source_node, predicate, transform_fn,
            )
        else:
            result[field_name] = _extract_single_field(
                graph, source_node, predicate, transform_fn,
            )

    return result


def parse_geodcat_to_model(rdf_text: str) -> MetadataRecord:
    """
    Parsea un texto GeoDCAT-AP y devuelve un MetadataRecord validado.

    Args:
        rdf_text: Texto en formato GeoDCAT-AP (RDF/XML).

    Returns:
        MetadataRecord con la información del dataset.
    """
    graph = Graph()
    graph.parse(data=rdf_text, format="xml")

    dataset_node = graph.value(predicate=RDF.type, object=DCAT.Dataset)
    if not dataset_node:
        raise ValueError("No se encontró dcat:Dataset en el archivo RDF.")

    catalog_record_node = graph.value(subject=dataset_node, predicate=FOAF.isPrimaryTopicOf)

    entity_sources = {
        "dataset": dataset_node,
        "catalog_record": catalog_record_node,
    }

    # Campos simples (declarativos)
    result = _process_simple_fields(graph, entity_sources)

    # Estructuras complejas
    for key, handler in COMPLEX_HANDLERS.items():
        result[key] = handler(graph, dataset_node)

    return MetadataRecord(**result)
