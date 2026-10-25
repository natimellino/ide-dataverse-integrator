from unittest.mock import patch

import pytest
import requests
import responses
from responses import matchers

from ide_dataverse_integrator.clients.geonetwork import GeonetworkClient
from ide_dataverse_integrator.config import Settings

RECORD_URL = "http://gn.test/geonetwork/srv/api/records/uuid-1/formatters"


@pytest.fixture
def client() -> GeonetworkClient:
    return GeonetworkClient(
        Settings(
            geonetwork_base_url="http://gn.test/geonetwork/",
            geonetwork_user="user",
            geonetwork_password="secret",
            geonetwork_verify_certs=False,
            geonetwork_timeout=5,
        )
    )


@responses.activate
def test_get_record_uses_geodcat_by_default(client):
    responses.get(
        f"{RECORD_URL}/eu-geodcat-ap-semiceu",
        body="<rdf/>",
        match=[matchers.header_matcher({"Authorization": "Basic dXNlcjpzZWNyZXQ="})],
    )
    assert client.get_record("uuid-1") == "<rdf/>"


@responses.activate
def test_get_record_with_format(client):
    responses.get(f"{RECORD_URL}/xml", body="<xml/>")
    assert client.get_record("uuid-1", format="xml") == "<xml/>"


@responses.activate
def test_get_record_raises_on_http_error(client):
    responses.get(f"{RECORD_URL}/xml", status=404)
    with pytest.raises(requests.HTTPError):
        client.get_record("uuid-1", format="xml")


def test_passes_verify_and_timeout(client):
    with patch("ide_dataverse_integrator.clients.geonetwork.requests.get") as get:
        client.get_record("uuid-1")
    _, kwargs = get.call_args
    assert kwargs["verify"] is False
    assert kwargs["timeout"] == 5
