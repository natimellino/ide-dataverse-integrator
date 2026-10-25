import logging
from unittest.mock import MagicMock, call

import pytest

from ide_dataverse_integrator.config import Settings
from ide_dataverse_integrator.mappers.metadata_record_to_dv import (
    fill_bridge_metadata,
    fill_dataset_metadata,
    normalize_for_dataverse,
)
from ide_dataverse_integrator.models.metadata_record import (
    Contact,
    MetadataRecord,
    SpatialInfo,
)


@pytest.fixture
def cfg() -> Settings:
    return Settings(
        dataverse_default_contact_name="Área de Sensores Remotos",
        dataverse_default_contact_email="ide@unr.edu.ar",
        dataverse_default_subject=["Earth and Environmental Sciences"],
    )


@pytest.fixture
def record() -> MetadataRecord:
    return MetadataRecord(
        id="8a608e18",
        title="HUELLA URBANA CSK 2013",
        description="Una descripción",
        keywords=["GeoTIFF", "WCS"],
        supplemental_information="Notas",
        resource_creation_date="2013-06-01",
        resource_publication_date="2013-07-01",
        spatial=SpatialInfo(wkt="POLYGON((-60.79 -32.86,-60.61 -33.03))"),
        contact=Contact(organization="Universidad Nacional de Rosario"),
    )


@pytest.fixture
def dataset() -> MagicMock:
    return MagicMock()


def test_maps_citation_fields(dataset, record, cfg):
    fill_dataset_metadata(dataset, record, cfg)

    citation = dataset.citation
    assert citation.title == record.title
    assert citation.notes_text == "Notas"
    assert citation.production_date == "2013-06-01"
    assert citation.date_of_deposit == "2013-07-01"
    assert citation.subject == ["Earth and Environmental Sciences"]
    citation.add_ds_description.assert_called_once_with(value="Una descripción")
    citation.add_author.assert_called_once_with(
        name="Universidad Nacional de Rosario",
        affiliation="Universidad Nacional de Rosario",
    )
    citation.add_keyword.assert_has_calls([call(value="GeoTIFF"), call(value="WCS")])


def test_contact_uses_default_email(dataset, record, cfg):
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_dataset_contact.assert_called_once_with(
        name="Universidad Nacional de Rosario", email="ide@unr.edu.ar"
    )


def test_without_contact_uses_default_contact_name(dataset, record, cfg):
    record.contact = None
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_dataset_contact.assert_called_once_with(
        name="Área de Sensores Remotos", email="ide@unr.edu.ar"
    )


def test_empty_description_falls_back_to_title_and_warns(dataset, record, cfg, caplog):
    record.description = ""
    with caplog.at_level(logging.WARNING):
        fill_dataset_metadata(dataset, record, cfg)

    dataset.citation.add_ds_description.assert_called_once_with(
        value="HUELLA URBANA CSK 2013"
    )
    assert "sin descripción" in caplog.text


def test_maps_topic_and_identifier_to_citation(dataset, record, cfg):
    record.topic_category = "imageryBaseMapsEarthCover"
    record.resource_identifier = "urn:ide:csk-2013"
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_topic_classification.assert_called_once_with(
        value="imageryBaseMapsEarthCover"
    )
    dataset.citation.add_other_id.assert_called_once_with(value="urn:ide:csk-2013")


def test_language_mapped_to_controlled_vocabulary(dataset, record, cfg):
    record.language = "spa"
    record.other_languages = ["eng"]
    fill_dataset_metadata(dataset, record, cfg)
    assert dataset.citation.language == ["Spanish; Castilian", "English"]


def test_unmapped_language_is_skipped(dataset, record, cfg):
    record.language = "xyz"
    fill_dataset_metadata(dataset, record, cfg)
    assert not isinstance(dataset.citation.language, list)


def test_bridge_gets_profile_fields(dataset, record, cfg):
    record.modified = "2013-06-01"
    record.status = "completed"
    record.purpose = "Monitoreo urbano"
    record.resolution_scale_denominator = "50000"
    record.maintenance_frequency = "asNeeded"
    record.lineage = "Derivado de COSMO-SkyMed"
    fill_dataset_metadata(dataset, record, cfg)

    bridge = dataset.ideBridge
    assert bridge.modified == "2013-06-01"
    assert bridge.status == "completed"
    assert bridge.purpose == "Monitoreo urbano"
    assert bridge.resolution_scale_denominator == "50000"
    assert bridge.maintenance_frequency == "asNeeded"
    assert bridge.lineage == "Derivado de COSMO-SkyMed"


def test_no_keywords_means_no_calls(dataset, record, cfg):
    record.keywords = []
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_keyword.assert_not_called()


def test_time_period_covered(dataset, record, cfg):
    record.temporal_extent_begin = "2013-06-19"
    record.temporal_extent_end = "2013-06-27"
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_time_period_covered.assert_called_once_with(
        start="2013-06-19", end="2013-06-27"
    )


def test_no_temporal_extent_skips_time_period(dataset, record, cfg):
    fill_dataset_metadata(dataset, record, cfg)
    dataset.citation.add_time_period_covered.assert_not_called()


def test_bounding_box_from_spatial(dataset, record, cfg):
    fill_dataset_metadata(dataset, record, cfg)
    dataset.geospatial.add_bounding_box.assert_called_once_with(
        west_longitude="-60.79",
        east_longitude="-60.61",
        north_latitude="-32.86",
        south_latitude="-33.03",
    )


def test_no_spatial_skips_bounding_box(dataset, record, cfg):
    record.spatial = None
    fill_dataset_metadata(dataset, record, cfg)
    dataset.geospatial.add_bounding_box.assert_not_called()


class TestFillBridgeMetadata:
    """Tests para fill_bridge_metadata (bloque ideBridge)."""

    def test_sets_all_bridge_fields(self, dataset):
        record = MetadataRecord(
            id="uuid-abc-123",
            title="Capa test",
            parent_geonetwork_uuid="parent-uuid-456",
            geoserver_layer_name="ws:layer_name",
            checksum_md5="d41d8cd98f00b204e9800998ecf8427e",
        )
        fill_bridge_metadata(dataset, record)

        bridge = dataset.ideBridge
        assert bridge.geonetwork_uuid == "uuid-abc-123"
        assert bridge.parent_geonetwork_uuid == "parent-uuid-456"
        assert bridge.geoserver_layer_name == "ws:layer_name"
        assert bridge.checksum_md5 == "d41d8cd98f00b204e9800998ecf8427e"

    def test_empty_optional_fields_become_empty_string(self, dataset):
        record = MetadataRecord(id="uuid-solo", title="Solo metadata")
        fill_bridge_metadata(dataset, record)

        bridge = dataset.ideBridge
        assert bridge.geonetwork_uuid == "uuid-solo"
        assert bridge.parent_geonetwork_uuid == ""
        assert bridge.geoserver_layer_name == ""
        assert bridge.checksum_md5 == ""

    def test_fill_dataset_metadata_calls_bridge(self, dataset, cfg):
        record = MetadataRecord(
            id="uuid-full",
            title="Full record",
            contact=Contact(organization="UNR"),
        )
        fill_dataset_metadata(dataset, record, cfg)

        bridge = dataset.ideBridge
        assert bridge.geonetwork_uuid == "uuid-full"


class TestNormalizeForDataverse:
    """normalize_for_dataverse debe aplicar los mismos fallbacks que fill_dataset_metadata
    para que el diff contra un dataset ya cargado no reporte falsos positivos."""

    def test_empty_description_falls_back_to_title(self, cfg):
        record = MetadataRecord(id="u", title="t", description="")

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.description == "t"

    def test_empty_contact_gets_default_contact_name(self, cfg):
        record = MetadataRecord(id="u", title="t")

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.contact.organization == "Área de Sensores Remotos"

    def test_existing_contact_organization_is_preserved(self, cfg):
        record = MetadataRecord(
            id="u", title="t", contact=Contact(organization="UNR")
        )

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.contact.organization == "UNR"

    def test_non_empty_description_is_preserved(self, cfg):
        record = MetadataRecord(id="u", title="t", description="Real desc")

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.description == "Real desc"

    def test_returns_copy_not_mutation(self, cfg):
        record = MetadataRecord(id="u", title="t", description="")

        normalized = normalize_for_dataverse(record, cfg)

        assert record.description == ""
        assert normalized is not record

    def test_author_name_defaults_to_contact_organization(self, cfg):
        """fill_dataset_metadata escribe author.name = contact.organization,
        así que para el diff el gn record tiene que tener ese valor también."""
        record = MetadataRecord(
            id="u", title="t", contact=Contact(organization="UNR")
        )

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.author_name == "UNR"

    def test_author_name_is_preserved_if_set(self, cfg):
        record = MetadataRecord(
            id="u",
            title="t",
            contact=Contact(organization="UNR"),
            author_name="Autor específico",
        )

        normalized = normalize_for_dataverse(record, cfg)

        assert normalized.author_name == "Autor específico"
