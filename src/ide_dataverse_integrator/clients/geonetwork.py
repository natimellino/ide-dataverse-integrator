import requests

from ide_dataverse_integrator.config import Settings, settings


class GeonetworkClient:

    def __init__(self, config: Settings | None = None):
        cfg = config or settings
        self.server_url = str(cfg.geonetwork_base_url).rstrip("/")
        self.auth = (cfg.geonetwork_user, cfg.geonetwork_password.get_secret_value())
        self.verify_certs = cfg.geonetwork_verify_certs
        self.timeout = cfg.geonetwork_timeout

    def get_record(self, uuid: str, format: str = "eu-geodcat-ap-semiceu") -> str:
        """Devuelve los metadatos de un registro en el formato indicado."""
        url = f"{self.server_url}/srv/api/records/{uuid}/formatters/{format}"
        response = requests.get(
            url, auth=self.auth, verify=self.verify_certs, timeout=self.timeout
        )
        response.raise_for_status()
        return response.text
