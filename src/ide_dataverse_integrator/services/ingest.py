import logging
import tempfile
from pathlib import Path

import click
import httpx

from ide_dataverse_integrator.clients.dataverse import DataverseClient
from ide_dataverse_integrator.clients.geonetwork import GeonetworkClient
from ide_dataverse_integrator.clients.geoserver import GeoServerClient
from ide_dataverse_integrator.mappers.dv_to_metadata_record import dv_to_metadata_record
from ide_dataverse_integrator.mappers.gn_geodcat_to_metadata_record import (
    parse_geodcat_to_model,
)
from ide_dataverse_integrator.mappers.gn_xml_to_metadata_record import (
    merge_iso19139_extras,
    parse_iso19139_extras,
)
from ide_dataverse_integrator.mappers.metadata_record_to_dv import (
    fill_dataset_metadata,
    normalize_for_dataverse,
)
from ide_dataverse_integrator.models.metadata_diff import MetadataDiff
from ide_dataverse_integrator.models.metadata_record import MetadataRecord
from ide_dataverse_integrator.services.reconciler import reconcile
from ide_dataverse_integrator.services.updater import (
    apply_diff_to_dataset,
    diff_layer_checksum,
    diff_records,
)
from ide_dataverse_integrator.utils import compute_md5

logger = logging.getLogger(__name__)


def fetch_metadata_record(gn: GeonetworkClient, uuid: str) -> MetadataRecord:
    """
    Obtiene un record de GeoNetwork y lo convierte a MetadataRecord.
    """
    record = parse_geodcat_to_model(gn.get_record(uuid))
    # Priorizamos extraer de GeoDCAT-AP porque es más simple pero
    # completamos con XML todos los metadatos que falten.
    extras = parse_iso19139_extras(gn.get_record(uuid, format="xml"))
    return merge_iso19139_extras(record, extras)


def prepare_layer_file(
    geoserver_client: GeoServerClient,
    layer_name: str,
    record: MetadataRecord,
    dest_dir: Path,
) -> Path:
    """Descarga la capa, calcula el md5 y actualiza el record con el checksum."""
    layer_file = geoserver_client.download_layer(layer_name, dest_dir)
    record.checksum_md5 = compute_md5(layer_file)
    return layer_file


def publish_to_dataverse(
    dv: DataverseClient,
    record: MetadataRecord,
    layer_file: Path | None = None,
):
    """Crea un dataset en Dataverse a partir del record y devuelve su persistentId.

    Si se pasa `layer_file`, se adjunta al dataset antes de subirlo.
    """
    dataset = dv.create_dataset()
    fill_dataset_metadata(dataset, record)
    if layer_file is not None:
        dv.add_file_to_dataset(dataset, str(layer_file))
    return dv.upload_dataset(dataset)


def _refresh_layer_checksum(
    geoserver_client: GeoServerClient | None,
    record: MetadataRecord,
) -> None:
    """Descarga la capa y recalcula el md5 del record para detectar cambios."""
    if not record.geoserver_layer_name or geoserver_client is None:
        return
    with tempfile.TemporaryDirectory(prefix="ide-dv-layer-") as tmp:
        prepare_layer_file(
            geoserver_client, record.geoserver_layer_name, record, Path(tmp)
        )


def _diff_existing(
    dv_record: MetadataRecord,
    gn_record: MetadataRecord,
) -> MetadataDiff:
    """Calcula el diff GN->DV, incluyendo el checksum de la capa."""
    source = normalize_for_dataverse(gn_record)
    diff = diff_records(source, dv_record)
    checksum_change = diff_layer_checksum(source, dv_record)
    if checksum_change is not None:
        diff.changed_fields["checksum_md5"] = checksum_change
    return diff


def _apply_metadata_update(
    dv: DataverseClient, dataset, diff: MetadataDiff
) -> None:
    """Aplica el diff al dataset y lo sincroniza si hay cambios."""
    if not diff.has_changes:
        return
    apply_diff_to_dataset(diff, dataset)
    dv.update_dataset(dataset)


def update_existing_dataset(
    dv: DataverseClient,
    pid: str,
    gn_record: MetadataRecord,
    geoserver_client: GeoServerClient | None = None,
) -> MetadataDiff:
    """Actualiza un dataset existente en Dataverse si hay campos que difieren."""
    dataset = dv.load_dataset(pid)
    dv_record = dv_to_metadata_record(dataset)
    layer_name = gn_record.geoserver_layer_name

    if not layer_name or geoserver_client is None:
        diff = _diff_existing(dv_record, gn_record)
        _apply_metadata_update(dv, dataset, diff)
        return diff

    # La capa se descarga a un temp que vive hasta terminar el reemplazo.
    with tempfile.TemporaryDirectory(prefix="ide-dv-layer-") as tmp:
        layer_file = prepare_layer_file(
            geoserver_client, layer_name, gn_record, Path(tmp)
        )
        diff = _diff_existing(dv_record, gn_record)
        _apply_metadata_update(dv, dataset, diff)
        if "checksum_md5" in diff.changed_fields:
            logger.info("La capa %s cambió, se reemplaza el archivo", layer_name)
            dv.replace_file(pid, str(layer_file))
    return diff


def _format_value(value, max_len: int = 80) -> str:
    """Representación compacta de un valor para el detalle del diff en dry-run."""
    if value is None or value == "":
        return "(vacío)"
    rendered = repr(value) if isinstance(value, str) else str(value)
    if len(rendered) > max_len:
        rendered = rendered[: max_len - 1] + "…"
    return rendered


def _print_existing_diff(diff: MetadataDiff) -> None:
    """Imprime el detalle del diff de un existente en dry-run con --update-existing."""
    if not diff.has_changes:
        click.echo("    sin cambios")
        return
    click.secho("    campos a actualizar:", fg="cyan")
    for key, (current, new) in diff.changed_fields.items():
        click.echo(
            f"      · {key}: {_format_value(current)} → {_format_value(new)}"
        )


def _print_plan(
    plan,
    records: dict[str, MetadataRecord],
    diffs: dict[str, MetadataDiff] | None = None,
):
    """Imprime el plan de conciliación en dry-run.

    Si `diffs` está presente, también muestra qué campos se actualizarían.
    """
    click.secho("=== Plan de conciliación ===", bold=True)

    if plan.to_create:
        click.secho(f"\nNuevos ({len(plan.to_create)}):", fg="green")
        for uuid in plan.to_create:
            record = records.get(uuid)
            title = record.title if record else uuid
            layer = record.geoserver_layer_name if record else None
            layer_suffix = f" [capa: {layer}]" if layer else ""
            click.echo(f"  + {uuid} — {title}{layer_suffix}")

    if plan.existing:
        click.secho(f"\nExistentes ({len(plan.existing)}):", fg="yellow")
        for uuid, pid in plan.existing.items():
            title = records[uuid].title if uuid in records else uuid
            click.echo(f"  = {uuid} → {pid} — {title}")
            diff = diffs.get(uuid) if diffs else None
            if diff is not None:
                _print_existing_diff(diff)

    if plan.orphans:
        click.secho(f"\nHuérfanos ({len(plan.orphans)}):", fg="red")
        for uuid, pid in plan.orphans.items():
            click.echo(f"  - {uuid} → {pid}")

    has_updates = bool(diffs) and any(d.has_changes for d in diffs.values())
    if not plan.has_work and not has_updates:
        click.secho("\nNada que hacer, todo está sincronizado.", fg="green")


def _compute_update_diffs(
    dv: DataverseClient,
    existing: dict[str, str],
    discovered_records: dict[str, MetadataRecord],
    gn: GeonetworkClient,
    geoserver_client: GeoServerClient | None = None,
) -> dict[str, MetadataDiff]:
    """Calcula los diffs de los existentes sin aplicarlos (para dry-run)."""
    diffs: dict[str, MetadataDiff] = {}
    for uuid, pid in existing.items():
        gn_record = discovered_records.get(uuid) or fetch_metadata_record(gn, uuid)
        _refresh_layer_checksum(geoserver_client, gn_record)
        dataset = dv.load_dataset(pid)
        dv_record = dv_to_metadata_record(dataset)
        diffs[uuid] = _diff_existing(dv_record, gn_record)
    return diffs


def sync(
    uuid: str,
    sync_deletions: bool,
    dry_run: bool,
    update_existing: bool = False,
):
    if sync_deletions:
        raise click.ClickException("--sync-deletions no está implementado")

    gn = GeonetworkClient()
    dv = DataverseClient()

    record = fetch_metadata_record(gn, uuid)

    # Por ahora cada UUID se trata como capa única (no tenemos parent records
    # implementados en Geonetwork)
    discovered_uuids = [uuid]
    plan = reconcile(discovered_uuids, dv)

    if dry_run:
        diffs: dict[str, MetadataDiff] | None = None
        if update_existing and plan.existing:
            dry_geoserver = GeoServerClient() if record.geoserver_layer_name else None
            diffs = _compute_update_diffs(
                dv, plan.existing, {uuid: record}, gn, dry_geoserver
            )
        _print_plan(plan, {uuid: record}, diffs)
        return

    # El cliente de GeoServer sólo se instancia si algún record
    # tiene una capa.
    geoserver_client: GeoServerClient | None = None

    for new_uuid in plan.to_create:
        rec = record if new_uuid == uuid else fetch_metadata_record(gn, new_uuid)
        if rec.geoserver_layer_name and geoserver_client is None:
            geoserver_client = GeoServerClient()
        try:
            pid = _publish_with_optional_layer(dv, geoserver_client, rec)
        except httpx.HTTPStatusError as e:
            raise click.ClickException(
                f"Dataverse respondió {e.response.status_code}: {e.response.text}"
            ) from e
        click.secho(f"Dataset creado en Dataverse: {pid}", fg="green")

    for existing_uuid, pid in plan.existing.items():
        if not update_existing:
            logger.info("UUID %s ya existe (%s), se omite", existing_uuid, pid)
            continue
        rec = (
            record if existing_uuid == uuid else fetch_metadata_record(gn, existing_uuid)
        )
        if rec.geoserver_layer_name and geoserver_client is None:
            geoserver_client = GeoServerClient()
        try:
            diff = update_existing_dataset(dv, pid, rec, geoserver_client)
        except httpx.HTTPStatusError as e:
            raise click.ClickException(
                f"Dataverse respondió {e.response.status_code}: {e.response.text}"
            ) from e
        if not diff.has_changes:
            logger.info("UUID %s sin cambios, se omite update", existing_uuid)
            click.secho(f"= {pid}: sin cambios", fg="yellow")
            continue
        changed = ", ".join(diff.changed_fields.keys())
        logger.info("UUID %s actualizado, campos: %s", existing_uuid, changed)
        click.secho(f"≈ {pid}: actualizado ({changed})", fg="green")

    if plan.orphans:
        click.secho(
            f"Advertencia: {len(plan.orphans)} dataset(s) huérfano(s) en Dataverse",
            fg="yellow",
        )
        for orphan_uuid, pid in plan.orphans.items():
            logger.warning("Huérfano: %s → %s", orphan_uuid, pid)


def _publish_with_optional_layer(
    dv: DataverseClient,
    geoserver_client: GeoServerClient | None,
    record: MetadataRecord,
) -> str:
    """Descarga la capa (si corresponde) y publica el dataset con el archivo adjunto."""
    layer_name = record.geoserver_layer_name
    if not layer_name:
        return publish_to_dataverse(dv, record)

    assert geoserver_client is not None, (
        "GeoServerClient requerido para capas con geoserver_layer_name"
    )
    with tempfile.TemporaryDirectory(prefix="ide-dv-layer-") as tmp:
        layer_file = prepare_layer_file(geoserver_client, layer_name, record, Path(tmp))
        return publish_to_dataverse(dv, record, layer_file)
