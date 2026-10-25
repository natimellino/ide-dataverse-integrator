"""
Servicio de actualización selectiva en Dataverse (M5).

Compara dos ``MetadataRecord`` (uno de GeoNetwork y otro de Dataverse) y
produce un ``MetadataDiff`` con los campos que difieren. Después,
``apply_diff_to_dataset`` aplica únicamente esos campos sobre un ``Dataset``.

Las piezas están diseñadas para ser reusables en el camino inverso (DV→GN):
``diff_records`` es simétrico (basta invertir ``source`` y ``target``). Las
funciones ``_apply_*`` son específicas del flujo GN→DV; para el flujo inverso
se escribirían sus equivalentes contra el patch de GeoNetwork.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from easyDataverse import Dataset

from ide_dataverse_integrator.config import Settings, settings
from ide_dataverse_integrator.models.metadata_diff import MetadataDiff
from ide_dataverse_integrator.models.metadata_record import MetadataRecord

logger = logging.getLogger(__name__)


# Extractores de info

def _extract_spatial_bbox(record: MetadataRecord) -> tuple | None:
    if not record.spatial:
        return None
    return (
        record.spatial.west_longitude,
        record.spatial.east_longitude,
        record.spatial.north_latitude,
        record.spatial.south_latitude,
    )


def _extract_contact_org(record: MetadataRecord) -> str:
    return record.contact.organization if record.contact else ""


def _extract_temporal(record: MetadataRecord) -> tuple[str, str]:
    return (record.temporal_extent_begin, record.temporal_extent_end)


# Appliers: escriben los valores actualizados en el Dataset de Dataverse


def _touch(compound, **fields) -> None:
    """Fuerza el change-tracking de easyDataverse en un sub-compound recién creado."""
    for name, value in fields.items():
        setattr(compound, name, value)


def _apply_title(dataset: Dataset, new_value: str) -> None:
    dataset.citation.title = new_value


def _apply_description(dataset: Dataset, new_value: str) -> None:
    dataset.citation.ds_description = []
    dataset.citation.add_ds_description(value=new_value)
    _touch(dataset.citation.ds_description[-1], value=new_value)


def _apply_keywords(dataset: Dataset, new_value: list[str]) -> None:
    dataset.citation.keyword = []
    for keyword in new_value:
        dataset.citation.add_keyword(value=keyword)
        _touch(dataset.citation.keyword[-1], value=keyword)


def _apply_notes_text(dataset: Dataset, new_value: str) -> None:
    dataset.citation.notes_text = new_value


def _apply_production_date(dataset: Dataset, new_value: str) -> None:
    dataset.citation.production_date = new_value


def _apply_date_of_deposit(dataset: Dataset, new_value: str) -> None:
    dataset.citation.date_of_deposit = new_value


def _apply_temporal_extent(dataset: Dataset, new_value: tuple[str, str]) -> None:
    begin, end = new_value
    dataset.citation.time_period_covered = []
    if begin or end:
        dataset.citation.add_time_period_covered(start=begin, end=end)
        _touch(dataset.citation.time_period_covered[-1], start=begin, end=end)


def _apply_spatial(dataset: Dataset, new_value: tuple | None) -> None:
    dataset.geospatial.bounding_box = []
    if new_value is None:
        return
    west, east, north, south = new_value
    dataset.geospatial.add_bounding_box(
        west_longitude=west,
        east_longitude=east,
        north_latitude=north,
        south_latitude=south,
    )
    _touch(
        dataset.geospatial.bounding_box[-1],
        west_longitude=west,
        east_longitude=east,
        north_latitude=north,
        south_latitude=south,
    )


def _apply_contact(dataset: Dataset, new_value: str, cfg: Settings) -> None:
    """Reemplaza ``dataset_contact`` con la organización del record.

    El email sale del fallback de configuración (GN no exporta mail de contacto).
    """
    dataset.citation.dataset_contact = []
    dataset.citation.add_dataset_contact(
        name=new_value, email=cfg.dataverse_default_contact_email
    )
    _touch(
        dataset.citation.dataset_contact[-1],
        name=new_value,
        email=cfg.dataverse_default_contact_email,
    )


def _apply_author(dataset: Dataset, new_value: str) -> None:
    """Reemplaza ``author`` en la citation."""
    dataset.citation.author = []
    dataset.citation.add_author(name=new_value, affiliation=new_value)
    _touch(dataset.citation.author[-1], name=new_value, affiliation=new_value)


def _apply_topic_classification(dataset: Dataset, new_value: str) -> None:
    dataset.citation.topic_classification = []
    if new_value:
        dataset.citation.add_topic_classification(value=new_value)
        _touch(dataset.citation.topic_classification[-1], value=new_value)


def _apply_other_id(dataset: Dataset, new_value: str) -> None:
    dataset.citation.other_id = []
    if new_value:
        dataset.citation.add_other_id(value=new_value)
        _touch(dataset.citation.other_id[-1], value=new_value)


def _apply_parent_uuid(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.parent_geonetwork_uuid = new_value


def _apply_geoserver_layer(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.geoserver_layer_name = new_value


def _apply_modified(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.modified = new_value


def _apply_status(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.status = new_value


def _apply_purpose(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.purpose = new_value


def _apply_resolution_scale_denominator(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.resolution_scale_denominator = new_value


def _apply_maintenance_frequency(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.maintenance_frequency = new_value


def _apply_lineage(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.lineage = new_value


def _apply_checksum_md5(dataset: Dataset, new_value: str) -> None:
    dataset.ideBridge.checksum_md5 = new_value


# --- Sync groups: tabla única que acopla extract + apply ----------------------


@dataclass(frozen=True)
class _SyncGroup:
    """Describe un campo lógico que se sincroniza GN↔DV.

    ``extract`` normaliza el valor del record para que la comparación sea
    semántica; ``apply`` lo escribe en el Dataset. Un sync group puede
    agrupar varios campos del record (ej. ``temporal_extent`` cubre begin+end).
    """

    key: str
    extract: Callable[[MetadataRecord], Any]
    apply: Callable[[Dataset, Any, Settings], None]


def _wrap(apply_fn: Callable[[Dataset, Any], None]):
    """Adapta un applier simple (sin cfg) a la firma uniforme ``(ds, val, cfg)``."""

    def wrapped(dataset: Dataset, value: Any, _cfg: Settings) -> None:
        apply_fn(dataset, value)

    return wrapped


_SYNC_GROUPS: list[_SyncGroup] = [
    _SyncGroup("title", lambda r: r.title, _wrap(_apply_title)),
    _SyncGroup("description", lambda r: r.description, _wrap(_apply_description)),
    _SyncGroup("keywords", lambda r: list(r.keywords), _wrap(_apply_keywords)),
    _SyncGroup("topic_category", lambda r: r.topic_category, _wrap(_apply_topic_classification)),
    _SyncGroup(
        "resource_identifier",
        lambda r: r.resource_identifier,
        _wrap(_apply_other_id),
    ),
    _SyncGroup("modified", lambda r: r.modified, _wrap(_apply_modified)),
    _SyncGroup("status", lambda r: r.status, _wrap(_apply_status)),
    _SyncGroup("purpose", lambda r: r.purpose, _wrap(_apply_purpose)),
    _SyncGroup(
        "resolution_scale_denominator",
        lambda r: r.resolution_scale_denominator,
        _wrap(_apply_resolution_scale_denominator),
    ),
    _SyncGroup(
        "maintenance_frequency",
        lambda r: r.maintenance_frequency,
        _wrap(_apply_maintenance_frequency),
    ),
    _SyncGroup("lineage", lambda r: r.lineage, _wrap(_apply_lineage)),
    _SyncGroup(
        "supplemental_information",
        lambda r: r.supplemental_information,
        _wrap(_apply_notes_text),
    ),
    _SyncGroup(
        "resource_creation_date",
        lambda r: r.resource_creation_date,
        _wrap(_apply_production_date),
    ),
    _SyncGroup(
        "resource_publication_date",
        lambda r: r.resource_publication_date,
        _wrap(_apply_date_of_deposit),
    ),
    _SyncGroup("temporal_extent", _extract_temporal, _wrap(_apply_temporal_extent)),
    _SyncGroup("spatial", _extract_spatial_bbox, _wrap(_apply_spatial)),
    _SyncGroup("contact", _extract_contact_org, _apply_contact),
    _SyncGroup("author", lambda r: r.author_name, _wrap(_apply_author)),
    _SyncGroup(
        "parent_geonetwork_uuid",
        lambda r: r.parent_geonetwork_uuid or "",
        _wrap(_apply_parent_uuid),
    ),
    _SyncGroup(
        "geoserver_layer_name",
        lambda r: r.geoserver_layer_name or "",
        _wrap(_apply_geoserver_layer),
    ),
    # checksum_md5 se compara aparte (ver diff_layer_checksum): sólo entra al
    # diff cuando la capa se volvió a descargar y recalcular, para no pisar el
    # valor guardado en las corridas que no tocan la capa.
]


# El checksum de la capa se recalcula descargando la capa.
# Queda fuera de _SYNC_GROUPS pero necesita su applier.
_CHECKSUM_GROUP = _SyncGroup(
    "checksum_md5", lambda r: r.checksum_md5 or "", _wrap(_apply_checksum_md5)
)


# --- Interface publica


def diff_records(source: MetadataRecord, target: MetadataRecord) -> MetadataDiff:
    """Compara dos records y devuelve los sync groups cuyo valor difiere.

    Es direccionalmente simétrico; la convención en el flujo GN→DV es
    ``source=gn_record`` y ``target=dv_record``, lo que deja
    ``changed_fields[n] = (dv_value, gn_value)``. Para el flujo DV→GN se invierten
    los argumentos.
    """
    changed: dict[str, tuple[Any, Any]] = {}
    for group in _SYNC_GROUPS:
        source_value = group.extract(source)
        target_value = group.extract(target)
        if source_value != target_value:
            changed[group.key] = (target_value, source_value)
    return MetadataDiff(changed_fields=changed)


def diff_layer_checksum(
    source: MetadataRecord, target: MetadataRecord
) -> tuple[str, str] | None:
    """Compara el md5 recalculado de la capa contra el guardado en Dataverse.

    Devuelve ``(dv_value, gn_value)`` si el checksum cambió, o ``None``
    en cualquier otro caso.
    """
    if source.checksum_md5 is None:
        return None
    current = target.checksum_md5 or ""
    new = source.checksum_md5
    return (current, new) if current != new else None


def apply_diff_to_dataset(
    diff: MetadataDiff,
    dataset: Dataset,
    config: Settings | None = None,
) -> None:
    """Aplica al dataset los campos del diff."""
    cfg = config or settings
    groups_by_key = {g.key: g for g in (*_SYNC_GROUPS, _CHECKSUM_GROUP)}
    for key, (_current, new_value) in diff.changed_fields.items():
        group = groups_by_key.get(key)
        if group is None:
            logger.warning("Sync group desconocido en diff: %s (se ignora)", key)
            continue
        group.apply(dataset, new_value, cfg)
