from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ide_dataverse_integrator.config import Settings
from ide_dataverse_integrator.models.metadata_diff import MetadataDiff
from ide_dataverse_integrator.models.metadata_record import (
    Contact,
    MetadataRecord,
    SpatialInfo,
)
from ide_dataverse_integrator.services.updater import (
    apply_diff_to_dataset,
    diff_layer_checksum,
    diff_records,
)


@pytest.fixture
def cfg() -> Settings:
    return Settings(
        dataverse_default_contact_name="Área de Sensores Remotos",
        dataverse_default_contact_email="ide@unr.edu.ar",
        dataverse_default_subject=["Earth and Environmental Sciences"],
    )


def _record(**kwargs) -> MetadataRecord:
    base = {"id": "u", "title": "Capa"}
    base.update(kwargs)
    return MetadataRecord(**base)


class TestDiffRecords:
    def test_no_changes_returns_empty_diff(self):
        a = _record(title="X", description="Y", keywords=["k"])
        b = _record(title="X", description="Y", keywords=["k"])

        diff = diff_records(a, b)

        assert not diff.has_changes
        assert diff.changed_fields == {}

    def test_single_field_change(self):
        gn = _record(title="Nuevo")
        dv = _record(title="Viejo")

        diff = diff_records(gn, dv)

        assert diff.has_changes
        assert "title" in diff.changed_fields
        current, new = diff.changed_fields["title"]
        assert current == "Viejo"
        assert new == "Nuevo"

    def test_multiple_field_changes(self):
        gn = _record(
            title="T2",
            description="D2",
            keywords=["a", "b"],
            resource_creation_date="2024-01-01",
        )
        dv = _record(
            title="T1",
            description="D1",
            keywords=["a"],
            resource_creation_date="2023-01-01",
        )

        diff = diff_records(gn, dv)

        assert set(diff.changed_fields.keys()) == {
            "title",
            "description",
            "keywords",
            "resource_creation_date",
        }

    def test_temporal_extent_is_grouped(self):
        gn = _record(temporal_extent_begin="2020-01-01", temporal_extent_end="2020-12-31")
        dv = _record(temporal_extent_begin="2020-01-01", temporal_extent_end="2021-01-01")

        diff = diff_records(gn, dv)

        assert set(diff.changed_fields.keys()) == {"temporal_extent"}
        current, new = diff.changed_fields["temporal_extent"]
        assert current == ("2020-01-01", "2021-01-01")
        assert new == ("2020-01-01", "2020-12-31")

    def test_spatial_compares_bbox_only(self):
        # Mismo bbox, distinto WKT original — deben compararse iguales.
        gn = _record(
            spatial=SpatialInfo(
                wkt="POLYGON((-60.79 -32.86,-60.61 -33.03))",
                west_longitude="-60.79",
                east_longitude="-60.61",
                north_latitude="-32.86",
                south_latitude="-33.03",
            )
        )
        dv = _record(
            spatial=SpatialInfo(
                west_longitude="-60.79",
                east_longitude="-60.61",
                north_latitude="-32.86",
                south_latitude="-33.03",
            )
        )

        diff = diff_records(gn, dv)

        assert "spatial" not in diff.changed_fields

    def test_contact_compares_organization_only(self):
        gn = _record(contact=Contact(organization="UNR", role="pointOfContact"))
        dv = _record(contact=Contact(organization="UNR"))

        diff = diff_records(gn, dv)

        assert "contact" not in diff.changed_fields

    def test_contact_change_detected(self):
        gn = _record(contact=Contact(organization="UNR"))
        dv = _record(contact=Contact(organization="CONICET"))

        diff = diff_records(gn, dv)

        assert "contact" in diff.changed_fields

    def test_author_divergence_detected(self):
        """Si el usuario edita author.name en DV, el diff debe detectarlo
        aunque dataset_contact.name siga igual al de GN."""
        gn = _record(
            contact=Contact(organization="UNR"),
            author_name="UNR",
        )
        dv = _record(
            contact=Contact(organization="UNR"),
            author_name="UNR con typo",
        )

        diff = diff_records(gn, dv)

        assert "contact" not in diff.changed_fields
        assert "author" in diff.changed_fields
        assert diff.changed_fields["author"] == ("UNR con typo", "UNR")

    def test_bridge_fields_normalize_none_to_empty(self):
        """parent_geonetwork_uuid=None en ambos no debe reportar cambio."""
        gn = _record(parent_geonetwork_uuid=None)
        dv = _record(parent_geonetwork_uuid=None)

        diff = diff_records(gn, dv)

        assert "parent_geonetwork_uuid" not in diff.changed_fields

    def test_bridge_field_change_detected(self):
        gn = _record(geoserver_layer_name="ws:nueva")
        dv = _record(geoserver_layer_name="ws:vieja")

        diff = diff_records(gn, dv)

        assert "geoserver_layer_name" in diff.changed_fields

    def test_symmetric_direction(self):
        """La API es direccionalmente simétrica (M8 invierte source/target)."""
        a = _record(title="A")
        b = _record(title="B")

        forward = diff_records(a, b)
        reverse = diff_records(b, a)

        assert forward.has_changes and reverse.has_changes
        assert forward.changed_fields["title"] == ("B", "A")
        assert reverse.changed_fields["title"] == ("A", "B")


class TestDiffLayerChecksum:
    def test_none_when_source_has_no_checksum(self):
        source = _record()
        target = _record(checksum_md5="abc")

        assert diff_layer_checksum(source, target) is None

    def test_none_when_equal(self):
        source = _record(checksum_md5="abc")
        target = _record(checksum_md5="abc")

        assert diff_layer_checksum(source, target) is None

    def test_returns_dv_and_gn_values_when_changed(self):
        source = _record(checksum_md5="new")
        target = _record(checksum_md5="old")

        assert diff_layer_checksum(source, target) == ("old", "new")

    def test_detects_first_time_checksum(self):
        source = _record(checksum_md5="new")
        target = _record()  # dataset sin checksum guardado

        assert diff_layer_checksum(source, target) == ("", "new")


# TODO: esto esta horrible
def _wire_adder(block, attr: str) -> None:
    """Hace que ``block.add_<attr>(**kwargs)`` appendee un SimpleNamespace a
    ``block.<attr>`` con esos kwargs como atributos.

    Replica la semántica real de easyDataverse. Nuestros ``_apply_*`` dependen
    de que, tras ``add_*``, el sub-objeto esté en la lista para forzar el
    change-tracking vía setattr. Un ``MagicMock`` plano no hace nada; sin esto
    los appliers que usan ``_touch`` revientan con ``IndexError``.
    """
    setattr(block, attr, [])

    def _appender(**kwargs):
        getattr(block, attr).append(SimpleNamespace(**kwargs))

    getattr(block, f"add_{attr}").side_effect = _appender


class TestApplyDiffToDataset:
    def _dataset(self):
        dataset = MagicMock()
        for attr in (
            "ds_description",
            "keyword",
            "dataset_contact",
            "author",
            "time_period_covered",
            "topic_classification",
            "other_id",
        ):
            _wire_adder(dataset.citation, attr)
        _wire_adder(dataset.geospatial, "bounding_box")
        dataset.ideBridge = SimpleNamespace(
            geonetwork_uuid="",
            parent_geonetwork_uuid="",
            geoserver_layer_name="",
            checksum_md5="",
            modified="",
            status="",
            purpose="",
            resolution_scale_denominator="",
            maintenance_frequency="",
            lineage="",
        )
        return dataset

    def test_only_changed_fields_applied(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(changed_fields={"title": ("viejo", "nuevo")})

        apply_diff_to_dataset(diff, dataset, cfg)

        assert dataset.citation.title == "nuevo"
        dataset.citation.add_keyword.assert_not_called()

    def test_keywords_replaces_whole_list(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(
            changed_fields={"keywords": (["a"], ["x", "y", "z"])}
        )

        apply_diff_to_dataset(diff, dataset, cfg)

        assert [k.value for k in dataset.citation.keyword] == ["x", "y", "z"]
        assert dataset.citation.add_keyword.call_count == 3

    def test_temporal_extent_resets_and_adds(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(
            changed_fields={
                "temporal_extent": (("2020-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31"))
            }
        )

        apply_diff_to_dataset(diff, dataset, cfg)

        assert len(dataset.citation.time_period_covered) == 1
        period = dataset.citation.time_period_covered[0]
        assert period.start == "2021-01-01"
        assert period.end == "2021-12-31"

    def test_spatial_applies_bbox(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(
            changed_fields={
                "spatial": (
                    ("-60", "-59", "-32", "-33"),
                    ("-61", "-60", "-33", "-34"),
                )
            }
        )

        apply_diff_to_dataset(diff, dataset, cfg)

        assert len(dataset.geospatial.bounding_box) == 1
        bbox = dataset.geospatial.bounding_box[0]
        assert bbox.west_longitude == "-61"
        assert bbox.east_longitude == "-60"
        assert bbox.north_latitude == "-33"
        assert bbox.south_latitude == "-34"

    def test_contact_only_rewrites_dataset_contact(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(changed_fields={"contact": ("UNR", "CONICET")})

        apply_diff_to_dataset(diff, dataset, cfg)

        assert len(dataset.citation.dataset_contact) == 1
        contact = dataset.citation.dataset_contact[0]
        assert contact.name == "CONICET"
        assert contact.email == "ide@unr.edu.ar"
        # El author tiene su propio sync group — no se toca aquí.
        dataset.citation.add_author.assert_not_called()

    def test_bridge_fields_assigned_directly(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(
            changed_fields={
                "parent_geonetwork_uuid": ("", "parent-new"),
                "geoserver_layer_name": ("", "ws:capa"),
            }
        )

        apply_diff_to_dataset(diff, dataset, cfg)

        assert dataset.ideBridge.parent_geonetwork_uuid == "parent-new"
        assert dataset.ideBridge.geoserver_layer_name == "ws:capa"

    def test_profile_bridge_fields_assigned_directly(self, cfg):
        dataset = self._dataset()
        diff = MetadataDiff(
            changed_fields={
                "modified": ("", "2013-06-01"),
                "status": ("", "completed"),
                "purpose": ("", "Monitoreo urbano"),
                "resolution_scale_denominator": ("", "50000"),
                "maintenance_frequency": ("", "asNeeded"),
                "lineage": ("", "Derivado de COSMO-SkyMed"),
            }
        )

        apply_diff_to_dataset(diff, dataset, cfg)

        assert dataset.ideBridge.modified == "2013-06-01"
        assert dataset.ideBridge.status == "completed"
        assert dataset.ideBridge.purpose == "Monitoreo urbano"
        assert dataset.ideBridge.resolution_scale_denominator == "50000"
        assert dataset.ideBridge.maintenance_frequency == "asNeeded"
        assert dataset.ideBridge.lineage == "Derivado de COSMO-SkyMed"
