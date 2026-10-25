import re
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Address(BaseModel):
    street: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""

class Contact(BaseModel):
    organization: str = ""
    role: str = ""
    website: str = ""
    address: Address | None = None


# TODO: refactorizar esta clase después
class SpatialInfo(BaseModel):
    wkt: str | None = None
    geojson: dict[str, Any] | None = None
    # Bounding box lista para Dataverse
    west_longitude: str | None = None
    east_longitude: str | None = None
    north_latitude: str | None = None
    south_latitude: str | None = None

    @model_validator(mode="after")
    def _compute_bounding_box(self) -> "SpatialInfo":
        """Calcula la bounding box a partir de wkt o geojson si no fue seteada."""
        if self.west_longitude is not None:
            return self

        coords = self._extract_coords()
        if not coords:
            return self

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]

        self.west_longitude = str(min(lons))
        self.east_longitude = str(max(lons))
        self.north_latitude = str(max(lats))
        self.south_latitude = str(min(lats))
        return self

    def _extract_coords(self) -> list[tuple]:
        """Extrae pares (lon, lat) del WKT o GeoJSON disponible."""
        if self.geojson and isinstance(self.geojson, dict):
            return self._coords_from_geojson(self.geojson)
        if self.wkt:
            return self._coords_from_wkt(self.wkt)
        return []

    @staticmethod
    def _coords_from_geojson(geojson: dict[str, Any]) -> list[tuple]:
        """Extrae coordenadas de un GeoJSON (Polygon, MultiPolygon, Point, etc.)."""
        coords = geojson.get("coordinates", [])
        geo_type = geojson.get("type", "")

        flat: list[tuple] = []

        if geo_type == "Point":
            flat.append(tuple(coords[:2]))
        elif geo_type in ("LineString", "MultiPoint"):
            flat.extend(tuple(c[:2]) for c in coords)
        elif geo_type in ("Polygon", "MultiLineString"):
            for ring in coords:
                flat.extend(tuple(c[:2]) for c in ring)
        elif geo_type == "MultiPolygon":
            for polygon in coords:
                for ring in polygon:
                    flat.extend(tuple(c[:2]) for c in ring)

        return flat

    @staticmethod
    def _coords_from_wkt(wkt: str) -> list[tuple]:
        """Extrae coordenadas de un WKT (POLYGON, MULTIPOLYGON, POINT, etc.)."""
        # Extraer todos los bloques numéricos dentro de paréntesis
        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", wkt)

        if len(numbers) < 2:
            return []

        # WKT usa pares "lon lat" separados por comas
        pairs = []
        for i in range(0, len(numbers) - 1, 2):
            pairs.append((float(numbers[i]), float(numbers[i + 1])))
        return pairs


class Link(BaseModel):
    url: str
    title: str = ""
    description: str = ""


class SpecificationConformance(BaseModel):
    title: str = ""
    date: str = ""
    explanation: str = ""
    passed: bool | None = None


class MetadataRecord(BaseModel):
    # Identificación (viene del parser)
    id: str
    # Perfil IDE: Fecha de última actualización
    modified: str = ""
    # Perfil IDE: Idioma de los datos
    language: str = ""
    other_languages: list[str] = Field(default_factory=list)
    character_set: str = ""
    resource_type: str = ""

    # Estándar de metadatos
    metadata_standard_name: str = ""
    metadata_standard_version: str = ""

    # Contenido descriptivo
    # Perfil IDE: título del recurso
    title: str
    resource_alt_title: str = ""
    # Perfil IDE: resumen del recurso
    description: str = ""
    # Perfil IDE: propósito
    purpose: str = ""
    # Perfil IDE: palabras clave
    keywords: list[str] = Field(default_factory=list)
    # Perfil IDE: estado del recurso
    status: str = ""
    # Perfil IDE: temas del recurso
    topic_category: str = ""
    resource_language: str = ""
    resource_edition: str = ""
    overview_url: str = ""
    # Perfil IDE: información adicional
    supplemental_information: str = ""

    # Fechas del recurso
    # Perfil IDE: fecha de creación del recurso
    resource_creation_date: str = ""
    # Perfil IDE: fecha de publicación del recurso
    resource_publication_date: str = ""
    resource_revision_date: str = ""

    # Identificación del recurso
    # Perfil IDE: ID Metadato
    resource_identifier: str = ""

    # Información espacial
    crs: list[str] = Field(default_factory=list)
    # Perfil IDE: extensión geográfica
    spatial: SpatialInfo | None = None
    # Perfil IDE: fecha de inicio de la extensión temporal
    temporal_extent_begin: str = ""
    # Perfil IDE: fecha de fin de la extensión temporal
    temporal_extent_end: str = ""
    # Perfil IDE: escala
    resolution_scale_denominator: str = ""
    resolution_distance: str = ""

    # Mantenimiento
    # Perfil IDE: frecuencia de mantenimiento
    maintenance_frequency: str = ""

    # Distribución
    distribution_format_name: str = ""
    distribution_format_version: str = ""

    # Restricciones y licencia
    license: str = ""
    use_limitation: str = ""
    access_constraints: str = ""

    # Calidad
    # Perfil IDE: Linaje
    lineage: str = ""
    specification_conformance: list[SpecificationConformance] = Field(default_factory=list)
    process_steps: list[str] = Field(default_factory=list)

    # Contacto y enlaces
    # Perfil IDE: punto de contacto
    contact: Contact | None = None
    author_name: str = ""
    links: list[Link] = Field(default_factory=list)

    # Campos operativos para el puente GeoNetwork ↔ Dataverse
    parent_geonetwork_uuid: str | None = None
    is_parent: bool = False
    geoserver_layer_name: str | None = None
    checksum_md5: str | None = None
    doi: str | None = None
