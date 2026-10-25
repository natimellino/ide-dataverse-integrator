from types import SimpleNamespace

from ide_dataverse_integrator.mappers.dv_to_metadata_record import dv_to_metadata_record
from ide_dataverse_integrator.models.metadata_record import (
    Contact,
)


def _bridge(**kwargs) -> SimpleNamespace:
    """Namespace con los defaults vacíos del bloque ideBridge."""
    defaults = {
        "geonetwork_uuid": "",
        "parent_geonetwork_uuid": "",
        "geoserver_layer_name": "",
        "checksum_md5": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_dataset(citation=None, geospatial=None, bridge=None) -> SimpleNamespace:
    """Fabrica un stub minimalista con la forma que usa el mapper inverso."""
    return SimpleNamespace(
        citation=citation or SimpleNamespace(),
        geospatial=geospatial or SimpleNamespace(bounding_box=[]),
        ideBridge=bridge or _bridge(),
    )


class TestDvToMetadataRecord:
    def test_extracts_simple_citation_fields(self):
        citation = SimpleNamespace(
            title="Capa X",
            ds_description=[SimpleNamespace(value="Una descripción")],
            keyword=[SimpleNamespace(value="GeoTIFF"), SimpleNamespace(value="WCS")],
            notes_text="Notas útiles",
            production_date="2013-06-01",
            date_of_deposit="2013-07-01",
            time_period_covered=[],
            dataset_contact=[],
        )
        dataset = _make_dataset(citation=citation, bridge=_bridge(geonetwork_uuid="abc"))

        record = dv_to_metadata_record(dataset)

        assert record.id == "abc"
        assert record.title == "Capa X"
        assert record.description == "Una descripción"
        assert record.keywords == ["GeoTIFF", "WCS"]
        assert record.supplemental_information == "Notas útiles"
        assert record.resource_creation_date == "2013-06-01"
        assert record.resource_publication_date == "2013-07-01"

    def test_extracts_temporal_extent(self):
        citation = SimpleNamespace(
            title="t",
            ds_description=[],
            keyword=[],
            notes_text="",
            production_date="",
            date_of_deposit="",
            time_period_covered=[SimpleNamespace(start="2020-01-01", end="2020-12-31")],
            dataset_contact=[],
        )
        dataset = _make_dataset(citation=citation)

        record = dv_to_metadata_record(dataset)

        assert record.temporal_extent_begin == "2020-01-01"
        assert record.temporal_extent_end == "2020-12-31"

    def test_extracts_bounding_box_as_spatial(self):
        geospatial = SimpleNamespace(
            bounding_box=[
                SimpleNamespace(
                    west_longitude="-60.79",
                    east_longitude="-60.61",
                    north_latitude="-32.86",
                    south_latitude="-33.03",
                )
            ]
        )
        citation = SimpleNamespace(
            title="t",
            ds_description=[],
            keyword=[],
            notes_text="",
            production_date="",
            date_of_deposit="",
            time_period_covered=[],
            dataset_contact=[],
        )
        dataset = _make_dataset(citation=citation, geospatial=geospatial)

        record = dv_to_metadata_record(dataset)

        assert record.spatial is not None
        assert record.spatial.west_longitude == "-60.79"
        assert record.spatial.east_longitude == "-60.61"
        assert record.spatial.north_latitude == "-32.86"
        assert record.spatial.south_latitude == "-33.03"

    def test_extracts_contact_organization(self):
        citation = SimpleNamespace(
            title="t",
            ds_description=[],
            keyword=[],
            notes_text="",
            production_date="",
            date_of_deposit="",
            time_period_covered=[],
            dataset_contact=[SimpleNamespace(name="UNR", email="ide@unr.edu.ar")],
        )
        dataset = _make_dataset(citation=citation)

        record = dv_to_metadata_record(dataset)

        assert record.contact == Contact(organization="UNR")

    def test_extracts_bridge_fields(self):
        bridge = _bridge(
            geonetwork_uuid="uuid-123",
            parent_geonetwork_uuid="parent-456",
            geoserver_layer_name="ws:capa",
            checksum_md5="deadbeef",
        )
        citation = SimpleNamespace(
            title="t",
            ds_description=[],
            keyword=[],
            notes_text="",
            production_date="",
            date_of_deposit="",
            time_period_covered=[],
            dataset_contact=[],
        )
        dataset = _make_dataset(citation=citation, bridge=bridge)

        record = dv_to_metadata_record(dataset)

        assert record.id == "uuid-123"
        assert record.parent_geonetwork_uuid == "parent-456"
        assert record.geoserver_layer_name == "ws:capa"
        assert record.checksum_md5 == "deadbeef"

    def test_empty_bridge_strings_become_none(self):
        """Dataverse guarda strings vacíos para los opcionales; el record los
        debe ver como None para comparar bien contra uno de GN."""
        citation = SimpleNamespace(
            title="t",
            ds_description=[],
            keyword=[],
            notes_text="",
            production_date="",
            date_of_deposit="",
            time_period_covered=[],
            dataset_contact=[],
        )
        dataset = _make_dataset(citation=citation, bridge=_bridge(geonetwork_uuid="x"))

        record = dv_to_metadata_record(dataset)

        assert record.parent_geonetwork_uuid is None
        assert record.geoserver_layer_name is None
        assert record.checksum_md5 is None
