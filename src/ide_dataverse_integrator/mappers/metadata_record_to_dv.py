import logging

from easyDataverse import Dataset

from ide_dataverse_integrator.config import Settings, settings
from ide_dataverse_integrator.models.metadata_record import Contact, MetadataRecord

logger = logging.getLogger(__name__)


# Vocabulario controlado de idioma del bloque citation de Dataverse (ISO 639-2).
# Mapea los códigos/slugs que exporta GeoNetwork al valor exacto que espera
# Dataverse; un idioma sin entrada acá se omite para no romper la validación.
_DATAVERSE_LANGUAGE_BY_CODE = {
    "es": "Spanish; Castilian",
    "esp": "Spanish; Castilian",
    "spa": "Spanish; Castilian",
    "en": "English",
    "eng": "English",
    "pt": "Portuguese",
    "por": "Portuguese",
}


def _dataverse_languages(metadata: MetadataRecord) -> list[str]:
    """Traduce los idiomas del record al vocabulario controlado de Dataverse."""
    languages: list[str] = []
    for code in [metadata.language, *metadata.other_languages]:
        if not code:
            continue
        value = _DATAVERSE_LANGUAGE_BY_CODE.get(code.strip().lower())
        if value is None:
            logger.warning(
                "Idioma '%s' sin equivalente en el vocabulario de Dataverse, se omite",
                code,
            )
        elif value not in languages:
            languages.append(value)
    return languages


def _contact_name(record: MetadataRecord, config: Settings) -> str:
    """Nombre del punto de contacto: el de GeoNetwork o el default de config."""
    organization = record.contact.organization if record.contact else ""
    return organization or config.dataverse_default_contact_name


def normalize_for_dataverse(
    record: MetadataRecord, config: Settings | None = None
) -> MetadataRecord:
    """Devuelve una copia del record con los fallbacks que el mapper inyectaría."""
    cfg = config or settings
    organization = record.contact.organization if record.contact else ""
    contact_name = _contact_name(record, cfg)
    contact = (
        record.contact.model_copy(update={"organization": contact_name})
        if record.contact
        else Contact(organization=contact_name)
    )
    return record.model_copy(
        update={
            "description": record.description or record.title,
            "author_name": record.author_name or organization,
            "contact": contact,
        }
    )


def fill_dataset_metadata(
    dataset: Dataset, metadata: MetadataRecord, config: Settings | None = None
):
    cfg = config or settings
    organization = metadata.contact.organization if metadata.contact else ""

    dataset.citation.title = metadata.title

    description = metadata.description
    if not description:
        logger.warning("Record %s sin descripción, se usa el título", metadata.id)
        description = metadata.title
    dataset.citation.add_ds_description(value=description)

    dataset.citation.add_dataset_contact(
        name=_contact_name(metadata, cfg), email=cfg.dataverse_default_contact_email
    )
    # TODO: ¿el autor sale de otro campo o del contacto?
    dataset.citation.add_author(name=organization, affiliation=organization)
    dataset.citation.subject = cfg.dataverse_default_subject

    for keyword in metadata.keywords:
        dataset.citation.add_keyword(value=keyword)

    if metadata.topic_category:
        dataset.citation.add_topic_classification(value=metadata.topic_category)
    if metadata.resource_identifier:
        dataset.citation.add_other_id(value=metadata.resource_identifier)

    languages = _dataverse_languages(metadata)
    if languages:
        dataset.citation.language = languages

    dataset.citation.notes_text = metadata.supplemental_information
    dataset.citation.production_date = metadata.resource_creation_date
    dataset.citation.date_of_deposit = metadata.resource_publication_date

    # TODO: soportar varios períodos
    if metadata.temporal_extent_begin:
        dataset.citation.add_time_period_covered(
            start=metadata.temporal_extent_begin, end=metadata.temporal_extent_end
        )

    if metadata.spatial:
        dataset.geospatial.add_bounding_box(
            west_longitude=metadata.spatial.west_longitude,
            east_longitude=metadata.spatial.east_longitude,
            north_latitude=metadata.spatial.north_latitude,
            south_latitude=metadata.spatial.south_latitude,
        )

    fill_bridge_metadata(dataset, metadata)


def _get_bridge_block(dataset: Dataset):
    """Accede al bloque custom ideBridge del dataset.

    El nombre del atributo depende de la lógica de easyDataverse para
    eliminar prefijos comunes de los typeNames. Centralizamos el acceso
    acá para que si cambia el nombre real sólo se toque este lugar.
    """
    return dataset.ideBridge


def fill_bridge_metadata(dataset: Dataset, metadata: MetadataRecord):
    """Inyecta en el bloque custom la trazabilidad GeoNetwork ↔ Dataverse y los
    campos del Perfil IDE que no tienen equivalente en citation/geospatial."""
    bridge = _get_bridge_block(dataset)

    bridge.geonetwork_uuid = metadata.id
    bridge.parent_geonetwork_uuid = metadata.parent_geonetwork_uuid or ""
    bridge.geoserver_layer_name = metadata.geoserver_layer_name or ""
    bridge.checksum_md5 = metadata.checksum_md5 or ""

    bridge.modified = metadata.modified
    bridge.status = metadata.status
    bridge.purpose = metadata.purpose
    bridge.resolution_scale_denominator = metadata.resolution_scale_denominator
    bridge.maintenance_frequency = metadata.maintenance_frequency
    bridge.lineage = metadata.lineage
