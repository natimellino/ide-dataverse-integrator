from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from ide_dataverse_integrator.clients.dataverse import DataverseClient
from ide_dataverse_integrator.config import Settings

PID = "doi:10.5072/FK2/TEST"


@pytest.fixture
def dataverse():
    with patch("ide_dataverse_integrator.clients.dataverse.Dataverse") as dataverse_cls:
        yield dataverse_cls.return_value


@pytest.fixture
def client(dataverse) -> DataverseClient:
    return DataverseClient(
        Settings(
            dataverse_base_url="http://dv.test/",
            dataverse_api_token="token",
            dataverse_parent_alias="ide",
        )
    )


@pytest.fixture
def dataset() -> MagicMock:
    dataset = MagicMock(files=[])
    dataset.dataverse_json.return_value = '{"datasetVersion": {}}'
    return dataset


def _mock_create_response(dataverse, status_code=201):
    request = httpx.Request("POST", "http://dv.test/api/dataverses/ide/datasets")
    dataverse.native_api.create_dataset.return_value = httpx.Response(
        status_code, json={"data": {"persistentId": PID}}, request=request
    )


def test_upload_creates_dataset_in_parent_collection(client, dataverse, dataset):
    _mock_create_response(dataverse)

    assert client.upload_dataset(dataset) == PID
    dataset._validate_required_fields.assert_called_once()
    dataverse.native_api.create_dataset.assert_called_once_with(
        "ide", '{"datasetVersion": {}}'
    )
    assert dataset.p_id == PID


def test_upload_to_explicit_collection(client, dataverse, dataset):
    _mock_create_response(dataverse)
    client.upload_dataset(dataset, collection_alias="otra")
    assert dataverse.native_api.create_dataset.call_args.args[0] == "otra"


def test_upload_raises_on_http_error(client, dataverse, dataset):
    _mock_create_response(dataverse, status_code=400)
    with pytest.raises(httpx.HTTPStatusError):
        client.upload_dataset(dataset)


def test_upload_skips_files_when_none(client, dataverse, dataset):
    _mock_create_response(dataverse)
    with patch("ide_dataverse_integrator.clients.dataverse.DVUploader") as uploader_cls:
        client.upload_dataset(dataset)
    uploader_cls.assert_not_called()


def test_upload_sends_files(client, dataverse, dataset):
    _mock_create_response(dataverse)
    dataset.files = ["capa.tiff"]
    with patch("ide_dataverse_integrator.clients.dataverse.DVUploader") as uploader_cls:
        client.upload_dataset(dataset)

    uploader_cls.assert_called_once_with(files=["capa.tiff"])
    uploader_cls.return_value.upload.assert_called_once_with(
        persistent_id=PID, dataverse_url="http://dv.test", api_token="token"
    )


def test_replace_file_uploads_with_replace_existing(client):
    with (
        patch("ide_dataverse_integrator.clients.dataverse.DVUploader") as uploader_cls,
        patch("ide_dataverse_integrator.clients.dataverse.File") as file_cls,
    ):
        client.replace_file(PID, "/tmp/capa.tiff")

    file_cls.assert_called_once_with(filepath="/tmp/capa.tiff", directoryLabel="")
    uploader_cls.assert_called_once_with(files=[file_cls.return_value])
    uploader_cls.return_value.upload.assert_called_once_with(
        persistent_id=PID,
        dataverse_url="http://dv.test",
        api_token="token",
        replace_existing=True,
    )


class TestFindByGeonetworkUuid:
    SEARCH_URL = "http://dv.test/api/search"

    @respx.mock
    def test_returns_pid_when_found(self, client):
        respx.get(self.SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "items": [{"global_id": PID, "type": "dataset"}],
                        "total_count": 1,
                    }
                },
            )
        )

        assert client.find_by_geonetwork_uuid("uuid-abc") == PID

    @respx.mock
    def test_returns_none_when_not_found(self, client):
        respx.get(self.SEARCH_URL).mock(
            return_value=httpx.Response(
                200, json={"data": {"items": [], "total_count": 0}}
            )
        )

        assert client.find_by_geonetwork_uuid("uuid-missing") is None

    @respx.mock
    def test_sends_api_token_and_query(self, client):
        route = respx.get(self.SEARCH_URL).mock(
            return_value=httpx.Response(
                200, json={"data": {"items": [], "total_count": 0}}
            )
        )

        client.find_by_geonetwork_uuid("uuid-abc")

        request = route.calls.last.request
        assert request.headers["X-Dataverse-key"] == "token"
        from urllib.parse import unquote
        url_decoded = unquote(str(request.url))
        assert 'geonetworkUuid:"uuid-abc"' in url_decoded
        assert "type=dataset" in url_decoded

    @respx.mock
    def test_raises_on_http_error(self, client):
        respx.get(self.SEARCH_URL).mock(
            return_value=httpx.Response(500, json={"status": "ERROR"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            client.find_by_geonetwork_uuid("uuid-abc")

    @respx.mock
    def test_warns_on_multiple_results(self, client, caplog):
        respx.get(self.SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {"global_id": PID, "type": "dataset"},
                            {"global_id": "doi:10.5072/FK2/OTHER", "type": "dataset"},
                        ],
                        "total_count": 2,
                    }
                },
            )
        )

        with caplog.at_level("WARNING"):
            result = client.find_by_geonetwork_uuid("uuid-dup")

        assert result == PID
        assert "Múltiples datasets" in caplog.text
