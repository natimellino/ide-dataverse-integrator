import logging

from ide_dataverse_integrator.clients.dataverse import DataverseClient
from ide_dataverse_integrator.models.reconciliation import ReconciliationPlan

logger = logging.getLogger(__name__)


def reconcile(
    discovered_uuids: list[str],
    dv: DataverseClient,
) -> ReconciliationPlan:
    """Concilia UUIDs descubiertos en GeoNetwork contra Dataverse.

    Para cada UUID descubierto, busca si ya existe un dataset en Dataverse
    con ese geonetwork_uuid. Los clasifica en to_create o existing.

    La detección de huérfanos requiere tener parent records implementados
    en Geonetwork, hasta entonces se devuelve vacía.
    """
    to_create: list[str] = []
    existing: dict[str, str] = {}

    for uuid in discovered_uuids:
        pid = dv.find_by_geonetwork_uuid(uuid)
        if pid:
            logger.info("UUID %s ya existe en Dataverse: %s", uuid, pid)
            existing[uuid] = pid
        else:
            logger.info("UUID %s es nuevo, se creará en Dataverse", uuid)
            to_create.append(uuid)

    return ReconciliationPlan(
        to_create=to_create,
        existing=existing,
        orphans={},
    )
