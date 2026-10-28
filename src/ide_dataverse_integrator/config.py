from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Dataverse
    dataverse_base_url: HttpUrl = "https://demo.dataverse.org"
    dataverse_api_token: SecretStr
    dataverse_parent_alias: str = "root"
    # Fallbacks para campos obligatorios de Dataverse
    dataverse_default_contact_name: str = ""
    dataverse_default_contact_email: str = "example@example.com"
    dataverse_default_subject: list[str] = ["Other"]

    # GeoNetwork
    geonetwork_base_url: HttpUrl = "http://localhost:8080/geonetwork"
    geonetwork_user: str = "admin"
    geonetwork_password: SecretStr
    geonetwork_verify_certs: bool = True
    geonetwork_timeout: int = 30

    # GeoServer
    geoserver_base_url: HttpUrl = "http://localhost:8080/geoserver"
    geoserver_user: str = "admin"
    geoserver_password: SecretStr
    geoserver_verify_certs: bool = True
    geoserver_timeout: int = 60
    # Formato de descarga para capas raster (WCS). Default GeoTIFF.
    geoserver_wcs_format: str = "image/tiff"
    geoserver_wcs_extension: str = ".tif"
    # Formato de descarga para capas vectoriales (WFS). Default GeoJSON.
    geoserver_wfs_format: str = "application/json"
    geoserver_wfs_extension: str = ".geojson"
    # Literales que devuelve la REST API de GeoServer para el tipo de capa.
    geoserver_layer_type_raster: str = "RASTER"
    geoserver_layer_type_vector: str = "VECTOR"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
