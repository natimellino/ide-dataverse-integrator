# clients/dataverse.py

import logging

import httpx
from dvuploader import DVUploader, File
from easyDataverse import Dataset, Dataverse

from ide_dataverse_integrator.config import Settings, settings

logger = logging.getLogger(__name__)


class DataverseClient:
    """
    Cliente de Dataverse basado en easyDataverse.

    Encapsula la conexión y operaciones comunes contra una instalación
    de Dataverse, delegando el trabajo HTTP a la librería easyDataverse.
    """

    def __init__(self, config: Settings | None = None):
        cfg = config or settings
        self.server_url = str(cfg.dataverse_base_url).rstrip("/")
        self.api_token = cfg.dataverse_api_token.get_secret_value()
        self.parent_alias = cfg.dataverse_parent_alias

        # Instancia principal de easyDataverse
        self.dataverse = Dataverse(
            server_url=self.server_url,
            api_token=self.api_token,
        )

    def create_dataset(self) -> Dataset:
        """
        Crea un objeto Dataset vacío que respeta los metadataBlocks
        de la instalación Dataverse configurada.

        Returns:
            Dataset de easyDataverse listo para poblar metadatos.
        """
        return self.dataverse.create_dataset()

    def upload_dataset(self, dataset, collection_alias: str | None = None):
        """
        Sube un dataset (con sus metadatos y archivos) a la colección indicada.

        Args:
            dataset: Objeto Dataset de easyDataverse ya poblado.
            collection_alias: Alias de la colección destino.
                              Si no se indica, usa el parent_alias de la config.
        """
        alias = collection_alias or self.parent_alias

        # No usamos dataset.upload() porque internamente valida el JSON con
        # pyDataverse.models.Dataset, que tiene mal definido geographicBoundingBox
        # (espera northLongitude/southLongitude en lugar de northLatitude/southLatitude)
        # y rechaza JSON válido. Creamos el dataset directo con la API nativa:
        # el propio servidor Dataverse valida los metadatos.
        dataset._validate_required_fields()

        response = self.dataverse.native_api.create_dataset(
            alias, dataset.dataverse_json()
        )
        response.raise_for_status()
        dataset.p_id = response.json()["data"]["persistentId"]

        if dataset.files:
            DVUploader(files=dataset.files).upload(
                persistent_id=dataset.p_id,
                dataverse_url=self.server_url,
                api_token=self.api_token,
            )

        return dataset.p_id

    def load_dataset(self, pid: str, version: str = "latest", filedir: str | None = None):
        """
        Descarga un dataset existente desde Dataverse.

        Args:
            pid: Persistent identifier del dataset (e.g. "doi:10.70122/FK2/ABCDEF").
            version: Versión a descargar. Por default ``"latest"``
            filedir: Directorio local donde descargar los archivos. Si es None,
                     se cargan sólo los metadatos y se omite la descarga de files.

        Returns:
            Dataset de easyDataverse con metadatos (y archivos si filedir != None).
        """
        return self.dataverse.load_dataset(
            pid=pid,
            version=version,
            filedir=filedir if filedir is not None else ".",
            download_files=filedir is not None,
        )

    def update_dataset(self, dataset):
        """
        Sincroniza los cambios locales de un dataset con la instancia remota.

        Args:
            dataset: Objeto Dataset de easyDataverse previamente cargado/creado.
        """
        dataset.update()

    def add_file_to_dataset(self, dataset, file_path: str, dv_dir: str = ""):
        """
        Agrega un archivo local a un objeto Dataset.

        Args:
            dataset: Objeto Dataset de easyDataverse.
            file_path: Ruta al archivo local.
            dv_dir: Directorio destino dentro del dataset en Dataverse.
        """
        dataset.add_file(local_path=file_path, dv_dir=dv_dir)

    def replace_file(self, pid: str, file_path: str, dv_dir: str = "") -> None:
        """Reemplaza en Dataverse el archivo de igual nombre por el de ``file_path``.

        Args:
            pid: Persistent identifier del dataset destino.
            file_path: Ruta al archivo local con el contenido nuevo.
            dv_dir: Directorio del archivo dentro del dataset (debe coincidir con
                    el usado al subirlo).
        """
        new_file = File(filepath=file_path, directoryLabel=dv_dir)
        DVUploader(files=[new_file]).upload(
            persistent_id=pid,
            dataverse_url=self.server_url,
            api_token=self.api_token,
            replace_existing=True,
        )

    def find_by_geonetwork_uuid(self, uuid: str) -> str | None:
        """Busca un dataset por geonetworkUuid en el bloque ideBridge.

        Usa la Search API de Dataverse. Devuelve el persistentId si
        existe, None si no se encontró.
        """
        response = httpx.get(
            f"{self.server_url}/api/search",
            params={
                "q": f'geonetworkUuid:"{uuid}"',
                "type": "dataset",
            },
            headers={"X-Dataverse-key": self.api_token},
        )
        response.raise_for_status()
        items = response.json().get("data", {}).get("items", [])
        if not items:
            return None
        pid = items[0]["global_id"]
        if len(items) > 1:
            logger.warning(
                "Múltiples datasets con geonetworkUuid=%s, usando %s", uuid, pid
            )
        return pid
