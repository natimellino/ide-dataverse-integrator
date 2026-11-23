import re
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

ONTOLOGY_PROPERTY_KEY = "ontology_property"


def ontology_field(ontology_property: str, **field_kwargs: Any) -> Any:
    """Declara un campo anotado con la propiedad de la ontología que representa."""
    return Field(json_schema_extra={ONTOLOGY_PROPERTY_KEY: ontology_property}, **field_kwargs)


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
    """Capa de la IDE (`unr:CapaIDE`).

    Cada campo de dominio declara la propiedad de la ontología que representa.
    """

    ontology_class: ClassVar[str] = "unr:CapaIDE"

    # Identificación (viene del parser)
    id: str
    modified: str = ontology_field("dct:modified", default="")
    language: str = ontology_field("dct:language", default="")
    other_languages: list[str] = Field(default_factory=list)
    resource_type: str = ontology_field("dct:type", default="")

    # Estándar de metadatos
    metadata_standard_name: str = ""
    metadata_standard_version: str = ""

    title: str = ontology_field("dct:title")
    resource_alt_title: str = ""
    description: str = ontology_field("dct:description", default="")
    purpose: str = ontology_field("unr:ideProposito", default="")
    keywords: list[str] = ontology_field("dcat:keyword", default_factory=list)
    status: str = ontology_field("unr:ideEstadoRecurso", default="")
    topic_category: str = ontology_field("dcat:theme", default="")
    resource_language: str = ""
    resource_edition: str = ontology_field("dcat:version", default="")
    overview_url: str = ""
    supplemental_information: str = ontology_field("foaf:page", default="")

    resource_creation_date: str = ontology_field("dct:created", default="")
    resource_publication_date: str = ontology_field("dct:issued", default="")
    resource_revision_date: str = ""

    resource_identifier: str = ontology_field("dct:identifier", default="")

    # Información espacial
    crs: list[str] = ontology_field("dct:conformsTo", default_factory=list)
    spatial: SpatialInfo | None = ontology_field("dct:spatial", default=None)
    temporal_extent_begin: str = ontology_field("dct:temporal", default="")
    temporal_extent_end: str = ontology_field("dct:temporal", default="")
    resolution_scale_denominator: str = ontology_field("unr:ideEscala", default="")

    maintenance_frequency: str = ontology_field("dct:accrualPeriodicity", default="")

    # Distribución
    distribution_format_name: str = ontology_field("unr:ideFormatoRecurso", default="")
    distribution_format_version: str = ""

    # Restricciones y licencia
    license: str = ""
    use_limitation: str = ""
    access_constraints: str = ontology_field("dct:accessRights", default="")

    lineage: str = ontology_field("dct:provenance", default="")
    specification_conformance: list[SpecificationConformance] = Field(default_factory=list)
    process_steps: list[str] = Field(default_factory=list)

    contact: Contact | None = ontology_field("dcat:contactPoint", default=None)
    author_name: str = ""
    links: list[Link] = Field(default_factory=list)

    # Campos operativos para el puente GeoNetwork <-> Dataverse
    parent_geonetwork_uuid: str | None = None
    is_parent: bool = False
    geoserver_layer_name: str | None = None
    geonetwork_record_url: str | None = None
    checksum_md5: str | None = None
    doi: str | None = None


class RasterRecord(MetadataRecord):
    """Capa ráster de la IDE (`unr:CapaRaster`)."""

    ontology_class: ClassVar[str] = "unr:CapaRaster"

    resolution_distance: str = ontology_field(
        "dcat:spatialResolutionInMeters", default=""
    )


class VectorRecord(MetadataRecord):
    """Capa vectorial de la IDE (`unr:CapaVectorial`)."""

    ontology_class: ClassVar[str] = "unr:CapaVectorial"

    character_set: str = ontology_field("unr:ideConjuntoCaracteres", default="")


def ontology_properties(model: type[BaseModel]) -> dict[str, str]:
    """Devuelve, por cada campo anotado, la propiedad de la ontología que representa."""
    properties = {}
    for field_name, field_info in model.model_fields.items():
        extra = field_info.json_schema_extra
        if isinstance(extra, dict) and ONTOLOGY_PROPERTY_KEY in extra:
            properties[field_name] = extra[ONTOLOGY_PROPERTY_KEY]
    return properties
