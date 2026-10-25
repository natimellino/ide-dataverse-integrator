import json
from pathlib import Path

import pytest
import requests
import responses
from responses import matchers

from ide_dataverse_integrator.clients.geoserver import (
    GeoServerClient,
    LayerInfo,
)
from ide_dataverse_integrator.config import Settings

BASE_URL = "https://gs.test/geoserver"
WORKSPACE = "ASR"
BARE_NAME = "HU_CSK_sample"
QUALIFIED = f"{WORKSPACE}:{BARE_NAME}"


@pytest.fixture
def client() -> GeoServerClient:
    return GeoServerClient(
        Settings(
            dataverse_api_token="dummy",
            geonetwork_password="dummy",
            geoserver_base_url=BASE_URL,
            geoserver_user="user",
            geoserver_password="secret",
            geoserver_verify_certs=False,
            geoserver_timeout=5,
        )
    )


def _layer_info_body(layer_type: str) -> str:
    return json.dumps({
        "layer": {
            "name": BARE_NAME,
            "type": layer_type,
            "resource": {"name": QUALIFIED},
        }
    })


@responses.activate
def test_get_layer_info_returns_type_and_workspace(client):
    responses.get(
        f"{BASE_URL}/rest/layers/{QUALIFIED}.json",
        body=_layer_info_body(client.layer_type_raster),
        content_type="application/json",
        match=[matchers.header_matcher({"Authorization": "Basic dXNlcjpzZWNyZXQ="})],
    )

    info = client.get_layer_info(QUALIFIED)

    assert info == LayerInfo(
        qualified_name=QUALIFIED,
        workspace=WORKSPACE,
        bare_name=BARE_NAME,
        type=client.layer_type_raster,
    )


@responses.activate
def test_get_layer_info_raises_on_http_error(client):
    responses.get(f"{BASE_URL}/rest/layers/{QUALIFIED}.json", status=404)
    with pytest.raises(requests.HTTPError):
        client.get_layer_info(QUALIFIED)


@pytest.mark.parametrize(
    ("qualified_name"),
    ["sin_dos_puntos", ":sin_workspace", "sin_capa:", ""],
)
def test_get_layer_info_rejects_unqualified_names(client, qualified_name):
    with pytest.raises(ValueError, match="workspace"):
        client.get_layer_info(qualified_name)


@responses.activate
def test_download_layer_raster_uses_wcs(client, tmp_path: Path):
    responses.get(
        f"{BASE_URL}/rest/layers/{QUALIFIED}.json",
        body=_layer_info_body(client.layer_type_raster),
        content_type="application/json",
    )
    responses.get(
        f"{BASE_URL}/{WORKSPACE}/wcs",
        body=b"\x00FAKE-TIF\x00",
        content_type="image/tiff",
        match=[
            matchers.query_param_matcher({
                "service": "WCS",
                "version": "2.0.1",
                "request": "GetCoverage",
                "coverageId": QUALIFIED,
                "format": client.wcs_format,
            })
        ],
    )

    path = client.download_layer(QUALIFIED, tmp_path)

    assert path == tmp_path / f"{BARE_NAME}{client.wcs_extension}"
    assert path.read_bytes() == b"\x00FAKE-TIF\x00"


@responses.activate
def test_download_layer_vector_uses_wfs_geojson(client, tmp_path: Path):
    responses.get(
        f"{BASE_URL}/rest/layers/{QUALIFIED}.json",
        body=_layer_info_body(client.layer_type_vector),
        content_type="application/json",
    )
    responses.get(
        f"{BASE_URL}/{WORKSPACE}/wfs",
        body=b'{"type":"FeatureCollection","features":[]}',
        content_type="application/json",
        match=[
            matchers.query_param_matcher({
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": QUALIFIED,
                "outputFormat": client.wfs_format,
            })
        ],
    )

    path = client.download_layer(QUALIFIED, tmp_path)

    assert path == tmp_path / f"{BARE_NAME}{client.wfs_extension}"
    assert b"FeatureCollection" in path.read_bytes()


@responses.activate
def test_download_layer_rejects_unknown_type(client, tmp_path: Path):
    responses.get(
        f"{BASE_URL}/rest/layers/{QUALIFIED}.json",
        body=_layer_info_body("STYLE"),
        content_type="application/json",
    )

    with pytest.raises(ValueError, match="no soportado"):
        client.download_layer(QUALIFIED, tmp_path)
