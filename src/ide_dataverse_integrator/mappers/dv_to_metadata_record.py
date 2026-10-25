"""
Mapper inverso Dataverse → MetadataRecord.

Sólo recupera el subconjunto de campos que ``fill_dataset_metadata``
escribe. Los demás se dejan con el default del modelo.
"""

from easyDataverse import Dataset

from ide_dataverse_integrator.models.metadata_record import (
    Contact,
    MetadataRecord,
    SpatialInfo,
)


def _first(items):
    if not items:
        return None
    return items[0]


def _ds_description(citation) -> str:
    first = _first(getattr(citation, "ds_description", None))
    return getattr(first, "value", "") or "" if first else ""


def _keywords(citation) -> list[str]:
    keywords = getattr(citation, "keyword", None) or []
    return [k.value for k in keywords if getattr(k, "value", None)]


def _temporal_extent(citation) -> tuple[str, str]:
    first = _first(getattr(citation, "time_period_covered", None))
    if not first:
        return "", ""
    return (getattr(first, "start", "") or "", getattr(first, "end", "") or "")


def _spatial(geospatial) -> SpatialInfo | None:
    first = _first(getattr(geospatial, "bounding_box", None))
    if not first:
        return None
    return SpatialInfo(
        west_longitude=getattr(first, "west_longitude", None),
        east_longitude=getattr(first, "east_longitude", None),
        north_latitude=getattr(first, "north_latitude", None),
        south_latitude=getattr(first, "south_latitude", None),
    )


def _contact(citation) -> Contact | None:
    first = _first(getattr(citation, "dataset_contact", None))
    if not first:
        return None
    organization = getattr(first, "name", "") or ""
    if not organization:
        return None
    return Contact(organization=organization)


def _author_name(citation) -> str:
    """Nombre del primer autor del dataset (si existe)."""
    first = _first(getattr(citation, "author", None))
    return getattr(first, "name", "") or "" if first else ""


def _topic_category(citation) -> str:
    first = _first(getattr(citation, "topic_classification", None))
    return getattr(first, "value", "") or "" if first else ""


def _resource_identifier(citation) -> str:
    first = _first(getattr(citation, "other_id", None))
    return getattr(first, "value", "") or "" if first else ""


def dv_to_metadata_record(dataset: Dataset) -> MetadataRecord:
    """Reconstruye un ``MetadataRecord`` a partir de un dataset de Dataverse.

    Sólo rellena los campos que el pipeline sincroniza; el resto queda con el
    default del modelo. Los nulos operativos del bloque ``ideBridge`` (que en
    Dataverse se guardan como ``""``) se traducen a ``None`` para que la
    comparación contra un ``MetadataRecord`` de GN sea consistente.
    """
    citation = dataset.citation
    geospatial = dataset.geospatial
    bridge = dataset.ideBridge

    begin, end = _temporal_extent(citation)

    return MetadataRecord(
        id=bridge.geonetwork_uuid or "",
        title=citation.title or "",
        description=_ds_description(citation),
        keywords=_keywords(citation),
        supplemental_information=getattr(citation, "notes_text", "") or "",
        resource_creation_date=getattr(citation, "production_date", "") or "",
        resource_publication_date=getattr(citation, "date_of_deposit", "") or "",
        temporal_extent_begin=begin,
        temporal_extent_end=end,
        spatial=_spatial(geospatial),
        contact=_contact(citation),
        author_name=_author_name(citation),
        topic_category=_topic_category(citation),
        resource_identifier=_resource_identifier(citation),
        modified=getattr(bridge, "modified", "") or "",
        status=getattr(bridge, "status", "") or "",
        purpose=getattr(bridge, "purpose", "") or "",
        resolution_scale_denominator=getattr(
            bridge, "resolution_scale_denominator", ""
        ) or "",
        maintenance_frequency=getattr(bridge, "maintenance_frequency", "") or "",
        lineage=getattr(bridge, "lineage", "") or "",
        parent_geonetwork_uuid=bridge.parent_geonetwork_uuid or None,
        geoserver_layer_name=bridge.geoserver_layer_name or None,
        checksum_md5=bridge.checksum_md5 or None,
    )
