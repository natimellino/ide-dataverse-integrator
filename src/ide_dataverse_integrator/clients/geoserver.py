import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from ide_dataverse_integrator.config import Settings, settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayerInfo:
    """Datos mínimos de una capa de GeoServer para decidir cómo descargarla."""

    qualified_name: str
    workspace: str
    bare_name: str
    type: str


class GeoServerClient:
    """
    Cliente de GeoServer para resolver y descargar capas vía servicios OGC.

    Usa la REST API para averiguar el tipo de la capa (RASTER o VECTOR) y
    luego descarga el archivo con el servicio OGC correspondiente:
    WCS para raster, WFS para vectorial.
    """

    def __init__(self, config: Settings | None = None):
        cfg = config or settings
        self.server_url = str(cfg.geoserver_base_url).rstrip("/")
        self.auth = (cfg.geoserver_user, cfg.geoserver_password.get_secret_value())
        self.verify_certs = cfg.geoserver_verify_certs
        self.timeout = cfg.geoserver_timeout
        self.wcs_format = cfg.geoserver_wcs_format
        self.wcs_extension = cfg.geoserver_wcs_extension
        self.wfs_format = cfg.geoserver_wfs_format
        self.wfs_extension = cfg.geoserver_wfs_extension
        self.layer_type_raster = cfg.geoserver_layer_type_raster
        self.layer_type_vector = cfg.geoserver_layer_type_vector

    def get_layer_info(self, qualified_name: str) -> LayerInfo:
        """Consulta la REST API para resolver tipo + workspace de la capa."""
        workspace, bare_name = _split_qualified_name(qualified_name)
        url = f"{self.server_url}/rest/layers/{qualified_name}.json"
        response = requests.get(
            url, auth=self.auth, verify=self.verify_certs, timeout=self.timeout
        )
        response.raise_for_status()
        layer_type = response.json()["layer"]["type"]
        return LayerInfo(
            qualified_name=qualified_name,
            workspace=workspace,
            bare_name=bare_name,
            type=layer_type,
        )

    def download_layer(self, qualified_name: str, dest_dir: Path) -> Path:
        """Descarga la capa al disco en el formato OGC que corresponda a su tipo."""
        info = self.get_layer_info(qualified_name)
        logger.info("Descargando %s (%s) desde GeoServer", qualified_name, info.type)
        if info.type == self.layer_type_raster:
            return self._download_coverage(info, dest_dir)
        if info.type == self.layer_type_vector:
            return self._download_features(info, dest_dir)
        raise ValueError(f"Tipo de capa no soportado: {info.type}")

    def _download_coverage(self, info: LayerInfo, dest_dir: Path) -> Path:
        url = f"{self.server_url}/{info.workspace}/wcs"
        params = {
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "coverageId": info.qualified_name,
            "format": self.wcs_format,
        }
        dest = dest_dir / f"{info.bare_name}{self.wcs_extension}"
        return self._stream_to_file(url, params, dest)

    def _download_features(self, info: LayerInfo, dest_dir: Path) -> Path:
        url = f"{self.server_url}/{info.workspace}/wfs"
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": info.qualified_name,
            "outputFormat": self.wfs_format,
        }
        dest = dest_dir / f"{info.bare_name}{self.wfs_extension}"
        return self._stream_to_file(url, params, dest)

    def _stream_to_file(self, url: str, params: dict, dest_path: Path) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(
            url,
            params=params,
            auth=self.auth,
            verify=self.verify_certs,
            timeout=self.timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return dest_path


def _split_qualified_name(qualified_name: str) -> tuple[str, str]:
    if ":" not in qualified_name:
        raise ValueError(
            f"El nombre de capa no tiene el formato 'workspace:layer'; "
            f"se recibió: {qualified_name!r}"
        )
    workspace, bare = qualified_name.split(":", 1)
    if not workspace or not bare:
        raise ValueError(
            f"workspace y nombre de capa no pueden estar vacíos; se recibió: "
            f"{qualified_name!r}"
        )
    return workspace, bare
