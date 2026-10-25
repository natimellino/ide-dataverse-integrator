from pathlib import Path
from unittest.mock import create_autospec, patch

import click
import httpx
import pytest
from click.testing import CliRunner

from ide_dataverse_integrator.cli import cli
from ide_dataverse_integrator.clients.dataverse import DataverseClient
from ide_dataverse_integrator.clients.geonetwork import GeonetworkClient
from ide_dataverse_integrator.clients.geoserver import GeoServerClient
from ide_dataverse_integrator.models.metadata_diff import MetadataDiff
from ide_dataverse_integrator.models.metadata_record import MetadataRecord
from ide_dataverse_integrator.services import ingest
from ide_dataverse_integrator.services.ingest import (
    fetch_metadata_record,
    prepare_layer_file,
    publish_to_dataverse,
    sync,
    update_existing_dataset,
)

RESOURCES_DIR = Path(__file__).parent / "resources"
PID = "doi:10.5072/FK2/TEST"


@pytest.fixture
def gn_client():
    def _get_record(uuid, format="eu-geodcat-ap-semiceu"):
        if format == "xml":
            return (RESOURCES_DIR / "gnidexmlresponse.xml").read_text(encoding="utf-8")
        return (RESOURCES_DIR / "gn-ide-geodcatresponse.rdf").read_text(encoding="utf-8")

    gn = create_autospec(GeonetworkClient, instance=True)
    gn.get_record.side_effect = _get_record
    return gn


@pytest.fixture
def dv_client():
    dv = create_autospec(DataverseClient, instance=True)
    dv.upload_dataset.return_value = PID
    return dv


@pytest.fixture
def record() -> MetadataRecord:
    return MetadataRecord(id="abc-123", title="Capa de prueba")


def _http_error(status_code: int, text: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://dataverse.test/api/dataverses/root/datasets")
    response = httpx.Response(status_code, text=text, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_fetch_metadata_record_merges_geodcat_and_xml(gn_client):
    record = fetch_metadata_record(gn_client, "uuid-1")

    assert record.title
    # character_set solo viene en el XML ISO 19139
    assert record.character_set == "utf8"


class TestPublishToDataverse:
    def test_fills_and_uploads_dataset(self, dv_client, record):
        with patch.object(ingest, "fill_dataset_metadata") as fill:
            pid = publish_to_dataverse(dv_client, record)

        dataset = dv_client.create_dataset.return_value
        assert pid == PID
        fill.assert_called_once_with(dataset, record)
        dv_client.upload_dataset.assert_called_once_with(dataset)
        dv_client.add_file_to_dataset.assert_not_called()

    def test_attaches_layer_file_when_provided(self, dv_client, record, tmp_path):
        layer_file = tmp_path / "capa.tif"
        layer_file.write_bytes(b"RASTER-BYTES")

        with patch.object(ingest, "fill_dataset_metadata"):
            publish_to_dataverse(dv_client, record, layer_file)

        dataset = dv_client.create_dataset.return_value
        dv_client.add_file_to_dataset.assert_called_once_with(dataset, str(layer_file))


class TestPrepareLayerFile:
    def test_downloads_and_populates_checksum(self, record, tmp_path: Path):
        geoserver_client = create_autospec(GeoServerClient, instance=True)
        downloaded = tmp_path / "capa.tif"
        downloaded.write_bytes(b"XYZ")
        geoserver_client.download_layer.return_value = downloaded

        with patch.object(ingest, "compute_md5", return_value="deadbeef") as md5:
            result = prepare_layer_file(
                geoserver_client, "ASR:capa", record, tmp_path
            )

        geoserver_client.download_layer.assert_called_once_with("ASR:capa", tmp_path)
        md5.assert_called_once_with(downloaded)
        assert result == downloaded
        assert record.checksum_md5 == "deadbeef"


class TestSync:
    @pytest.fixture(autouse=True)
    def _mock_clients(self, record):
        with (
            patch.object(ingest, "GeonetworkClient"),
            patch.object(ingest, "fetch_metadata_record", return_value=record),
            patch.object(ingest, "DataverseClient") as dv_cls,
            patch.object(ingest, "GeoServerClient") as gs_cls,
        ):
            self.dv_instance = dv_cls.return_value
            self.gs_cls = gs_cls
            self.gs_instance = gs_cls.return_value
            yield

    def test_creates_new_dataset(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = None

        with patch.object(
            ingest, "publish_to_dataverse", return_value=PID
        ) as publish:
            sync("uuid-1", sync_deletions=False, dry_run=False)

        publish.assert_called_once_with(self.dv_instance, record)
        self.gs_cls.assert_not_called()
        assert PID in capsys.readouterr().out

    def test_downloads_layer_when_record_has_layer_name(self, tmp_path, record):
        record.geoserver_layer_name = "ASR:capa"
        self.dv_instance.find_by_geonetwork_uuid.return_value = None
        downloaded = tmp_path / "capa.tif"
        downloaded.write_bytes(b"RASTER")
        self.gs_instance.download_layer.return_value = downloaded

        with (
            patch.object(ingest, "fill_dataset_metadata"),
            patch.object(ingest, "compute_md5", return_value="abc"),
        ):
            sync("uuid-1", sync_deletions=False, dry_run=False)

        self.gs_cls.assert_called_once()
        self.gs_instance.download_layer.assert_called_once()
        called_layer, called_dir = self.gs_instance.download_layer.call_args.args
        assert called_layer == "ASR:capa"
        assert isinstance(called_dir, Path)
        self.dv_instance.add_file_to_dataset.assert_called_once()
        assert record.checksum_md5 == "abc"

    def test_skips_existing_dataset(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID

        with patch.object(ingest, "publish_to_dataverse") as publish:
            sync("uuid-1", sync_deletions=False, dry_run=False)

        publish.assert_not_called()

    def test_second_run_is_idempotent(self, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID

        with patch.object(ingest, "publish_to_dataverse") as publish:
            sync("uuid-1", sync_deletions=False, dry_run=False)
            sync("uuid-1", sync_deletions=False, dry_run=False)

        publish.assert_not_called()

    def test_http_error_becomes_click_exception(self, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = None
        error = _http_error(400, '{"status":"ERROR","message":"campo inválido"}')

        with (
            patch.object(ingest, "fill_dataset_metadata"),
            pytest.raises(click.ClickException) as exc_info,
        ):
            self.dv_instance.upload_dataset.side_effect = error
            self.dv_instance.create_dataset.return_value = None
            sync("uuid-1", sync_deletions=False, dry_run=False)

        assert "400" in exc_info.value.message
        assert "campo inválido" in exc_info.value.message

    def test_sync_deletions_not_implemented(self):
        with pytest.raises(click.ClickException, match="no está implementado"):
            sync("uuid-1", sync_deletions=True, dry_run=False)


class TestSyncDryRun:
    @pytest.fixture(autouse=True)
    def _mock_clients(self, record):
        with (
            patch.object(ingest, "GeonetworkClient"),
            patch.object(ingest, "fetch_metadata_record", return_value=record),
            patch.object(ingest, "DataverseClient") as dv_cls,
            patch.object(ingest, "GeoServerClient") as gs_cls,
        ):
            self.dv_instance = dv_cls.return_value
            self.gs_cls = gs_cls
            yield

    def test_dry_run_shows_plan_for_new(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = None

        sync("uuid-1", sync_deletions=False, dry_run=True)

        output = capsys.readouterr().out
        assert "Plan de conciliación" in output
        assert "Nuevos (1)" in output
        assert "uuid-1" in output

    def test_dry_run_shows_existing(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID

        sync("uuid-1", sync_deletions=False, dry_run=True)

        output = capsys.readouterr().out
        assert "Existentes (1)" in output
        assert PID in output
        assert "Nada que hacer" in output

    def test_dry_run_does_not_publish(self, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = None

        with patch.object(ingest, "publish_to_dataverse") as publish:
            sync("uuid-1", sync_deletions=False, dry_run=True)

        publish.assert_not_called()

    def test_dry_run_shows_layer_in_plan(self, capsys, record):
        record.geoserver_layer_name = "ASR:capa"
        self.dv_instance.find_by_geonetwork_uuid.return_value = None

        sync("uuid-1", sync_deletions=False, dry_run=True)

        output = capsys.readouterr().out
        assert "ASR:capa" in output
        self.gs_cls.assert_not_called()


def test_cli_sync_dry_run_shows_plan(record):
    with (
        patch.object(ingest, "GeonetworkClient"),
        patch.object(ingest, "fetch_metadata_record", return_value=record),
        patch.object(ingest, "DataverseClient") as dv_cls,
    ):
        dv_cls.return_value.find_by_geonetwork_uuid.return_value = None
        result = CliRunner().invoke(cli, ["sync", "uuid-1", "--dry-run"])

    assert result.exit_code == 0
    assert "Plan de conciliación" in result.output


class TestUpdateExistingDataset:
    """Flujo de update selectivo de un dataset ya existente."""

    def test_no_diff_skips_update(self, dv_client, record):
        loaded = object()
        dv_client.load_dataset.return_value = loaded

        with (
            patch.object(ingest, "dv_to_metadata_record", return_value=record),
            patch.object(
                ingest, "diff_records", return_value=MetadataDiff()
            ) as diff_fn,
            patch.object(ingest, "apply_diff_to_dataset") as apply_fn,
        ):
            diff = update_existing_dataset(dv_client, PID, record)

        assert not diff.has_changes
        diff_fn.assert_called_once()
        apply_fn.assert_not_called()
        dv_client.update_dataset.assert_not_called()

    def test_applies_diff_and_updates(self, dv_client, record):
        loaded = object()
        dv_client.load_dataset.return_value = loaded
        pretend_diff = MetadataDiff(changed_fields={"title": ("x", "y")})

        with (
            patch.object(ingest, "dv_to_metadata_record", return_value=record),
            patch.object(ingest, "diff_records", return_value=pretend_diff),
            patch.object(ingest, "apply_diff_to_dataset") as apply_fn,
        ):
            diff = update_existing_dataset(dv_client, PID, record)

        assert diff.has_changes
        apply_fn.assert_called_once_with(pretend_diff, loaded)
        dv_client.update_dataset.assert_called_once_with(loaded)

    def test_detects_layer_checksum_change(self, dv_client, tmp_path):
        gn_record = MetadataRecord(
            id="abc-123", title="Capa", geoserver_layer_name="ASR:capa"
        )
        dv_record = MetadataRecord(id="abc-123", title="Capa", checksum_md5="old")
        dv_client.load_dataset.return_value = object()
        geoserver_client = create_autospec(GeoServerClient, instance=True)
        downloaded = tmp_path / "capa.tif"
        downloaded.write_bytes(b"NEW")
        geoserver_client.download_layer.return_value = downloaded

        with (
            patch.object(ingest, "dv_to_metadata_record", return_value=dv_record),
            patch.object(ingest, "diff_records", return_value=MetadataDiff()),
            patch.object(ingest, "compute_md5", return_value="new"),
            patch.object(ingest, "apply_diff_to_dataset") as apply_fn,
        ):
            diff = update_existing_dataset(dv_client, PID, gn_record, geoserver_client)

        assert diff.changed_fields["checksum_md5"] == ("old", "new")
        assert gn_record.checksum_md5 == "new"
        apply_fn.assert_called_once()
        dv_client.update_dataset.assert_called_once()
        dv_client.replace_file.assert_called_once_with(PID, str(downloaded))

    def test_layer_unchanged_leaves_checksum_out(self, dv_client, tmp_path):
        gn_record = MetadataRecord(
            id="abc-123", title="Capa", geoserver_layer_name="ASR:capa"
        )
        dv_record = MetadataRecord(id="abc-123", title="Capa", checksum_md5="same")
        dv_client.load_dataset.return_value = object()
        geoserver_client = create_autospec(GeoServerClient, instance=True)
        downloaded = tmp_path / "capa.tif"
        downloaded.write_bytes(b"SAME")
        geoserver_client.download_layer.return_value = downloaded

        with (
            patch.object(ingest, "dv_to_metadata_record", return_value=dv_record),
            patch.object(ingest, "diff_records", return_value=MetadataDiff()),
            patch.object(ingest, "compute_md5", return_value="same"),
            patch.object(ingest, "apply_diff_to_dataset") as apply_fn,
        ):
            diff = update_existing_dataset(dv_client, PID, gn_record, geoserver_client)

        assert not diff.has_changes
        assert "checksum_md5" not in diff.changed_fields
        apply_fn.assert_not_called()
        dv_client.update_dataset.assert_not_called()
        dv_client.replace_file.assert_not_called()


class TestSyncUpdateExisting:

    @pytest.fixture(autouse=True)
    def _mock_clients(self, record):
        with (
            patch.object(ingest, "GeonetworkClient"),
            patch.object(ingest, "fetch_metadata_record", return_value=record),
            patch.object(ingest, "DataverseClient") as dv_cls,
            patch.object(ingest, "GeoServerClient"),
        ):
            self.dv_instance = dv_cls.return_value
            yield

    def test_updates_existing_when_flag_set(self, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID
        pretend_diff = MetadataDiff(changed_fields={"title": ("a", "b")})

        with patch.object(
            ingest, "update_existing_dataset", return_value=pretend_diff
        ) as updater:
            sync(
                "uuid-1",
                sync_deletions=False,
                dry_run=False,
                update_existing=True,
            )

        updater.assert_called_once_with(self.dv_instance, PID, record, None)

    def test_without_flag_skips_update(self, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID

        with patch.object(ingest, "update_existing_dataset") as updater:
            sync(
                "uuid-1",
                sync_deletions=False,
                dry_run=False,
                update_existing=False,
            )

        updater.assert_not_called()

    def test_logs_no_changes_message(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID
        empty_diff = MetadataDiff()

        with patch.object(ingest, "update_existing_dataset", return_value=empty_diff):
            sync(
                "uuid-1",
                sync_deletions=False,
                dry_run=False,
                update_existing=True,
            )

        assert "sin cambios" in capsys.readouterr().out

    def test_logs_changed_fields(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID
        diff = MetadataDiff(
            changed_fields={"title": ("a", "b"), "keywords": ([], ["x"])}
        )

        with patch.object(ingest, "update_existing_dataset", return_value=diff):
            sync(
                "uuid-1",
                sync_deletions=False,
                dry_run=False,
                update_existing=True,
            )

        out = capsys.readouterr().out
        assert "title" in out and "keywords" in out

    def test_dry_run_shows_fields_to_update(self, capsys, record):
        self.dv_instance.find_by_geonetwork_uuid.return_value = PID
        diff = MetadataDiff(changed_fields={"title": ("viejo", "nuevo")})

        with patch.object(
            ingest, "_compute_update_diffs", return_value={"uuid-1": diff}
        ):
            sync(
                "uuid-1",
                sync_deletions=False,
                dry_run=True,
                update_existing=True,
            )

        out = capsys.readouterr().out
        assert "campos a actualizar" in out
