import click

from ide_dataverse_integrator.services.ingest import sync
from ide_dataverse_integrator.utils import configure_logging


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Activa el logging de debug.")
def cli(verbose):
    configure_logging(verbose)


@cli.command("sync")
@click.argument("uuid")
@click.option(
    "--sync-deletions",
    is_flag=True,
    help="Elimina o da de baja en Dataverse capas borradas de GeoNetwork.",
)
@click.option(
    "--update-existing",
    is_flag=True,
    help="Actualiza los datasets ya existentes con los campos que cambiaron en GeoNetwork.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Muestra el record mapeado sin publicar en Dataverse.",
)
def sync_command(uuid, sync_deletions, update_existing, dry_run):
    """Publica en Dataverse el record de GeoNetwork indicado.

    El nombre de la capa en GeoServer se autodescubre del XML del record.
    """
    sync(uuid, sync_deletions, dry_run, update_existing=update_existing)


@cli.command("update-doi")
@click.argument("geonetwork_uuid", type=click.UUID)
@click.argument("new_doi", type=str)
def update_doi(geonetwork_uuid, new_doi):
    """Actualiza el metadato en GeoNetwork asociándole el DOI definitivo de Dataverse."""
    raise click.ClickException("No implementado")


if __name__ == "__main__":
    cli()
