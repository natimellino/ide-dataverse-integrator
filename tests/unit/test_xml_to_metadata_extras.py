"""
Unit tests para mappers/gn_xml_to_metadata_record.py
"""

import json
from pathlib import Path

import pytest
from lxml import etree

from ide_dataverse_integrator.mappers.gn_xml_to_metadata_record import (
    _code_list_value,
    _extract_constraints,
    _extract_geoserver_layer_name,
    _extract_process_steps,
    _extract_resource_dates,
    _extract_specification_conformance,
    _extract_temporal_extent,
    _text,
    merge_iso19139_extras,
    parse_iso19139_extras,
)
from ide_dataverse_integrator.models.metadata_record import MetadataRecord

RESOURCES_DIR = Path(__file__).parent / "resources"


def _root(xml_str: str):
    """Helper: parsea un fragmento XML y devuelve el root element."""
    return etree.fromstring(xml_str.encode("utf-8"))


def test_parses_real_xml():
    xml = (RESOURCES_DIR / "gnidexmlresponse.xml").read_text(encoding="utf-8")
    expected = (RESOURCES_DIR / "expected_iso19139_extras.json").read_text(encoding="utf-8")
    assert parse_iso19139_extras(xml) == json.loads(expected)


class TestText:
    """Tests para la función _text."""

    def test_strips_whitespace(self):
        xml = '<root xmlns:gco="http://www.isotc211.org/2005/gco"><gco:CharacterString>  spaced  </gco:CharacterString></root>'
        root = _root(xml)
        assert _text(root, "gco:CharacterString") == "spaced"

    def test_returns_empty_for_none_text(self):
        """Elemento existe pero .text es None (e.g. tiene solo hijos)."""
        xml = '<root xmlns:gco="http://www.isotc211.org/2005/gco"><gco:CharacterString><child/></gco:CharacterString></root>'
        root = _root(xml)
        assert _text(root, "gco:CharacterString") == ""


class TestCodeListValue:
    """Tests para la función _code_list_value."""

    def test_returns_empty_when_attr_missing(self):
        xml = (
            '<root xmlns:gmd="http://www.isotc211.org/2005/gmd">'
            '<gmd:MD_ProgressCode codeList="something"/>'
            "</root>"
        )
        root = _root(xml)
        assert _code_list_value(root, "gmd:MD_ProgressCode") == ""


class TestExtractResourceDates:
    """Tests para _extract_resource_dates con XML sintéticos."""

    def _make_xml(self, dates_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:citation><gmd:CI_Citation>"
            f"{dates_xml}"
            "</gmd:CI_Citation></gmd:citation>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_creation_date(self):
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2020-01-15</gco:Date></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="creation"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_creation_date"] == "2020-01-15"
        assert result["resource_publication_date"] == ""
        assert result["resource_revision_date"] == ""

    def test_extracts_publication_date(self):
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:DateTime>2021-06-01T10:00:00</gco:DateTime></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="publication"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_publication_date"] == "2021-06-01T10:00:00"

    def test_extracts_multiple_dates(self):
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2020-01-01</gco:Date></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="creation"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2021-03-15</gco:Date></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="publication"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:DateTime>2022-12-25T08:30:00</gco:DateTime></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="revision"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_creation_date"] == "2020-01-01"
        assert result["resource_publication_date"] == "2021-03-15"
        assert result["resource_revision_date"] == "2022-12-25T08:30:00"

    def test_ignores_unknown_date_type(self):
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2020-01-01</gco:Date></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="adopted"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_creation_date"] == ""
        assert result["resource_publication_date"] == ""
        assert result["resource_revision_date"] == ""

    def test_ignores_date_without_value(self):
        """Si no hay gco:Date ni gco:DateTime, no se asigna nada."""
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date></gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="creation"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_creation_date"] == ""

    def test_no_dates_returns_all_empty(self):
        root = _root(self._make_xml(""))
        result = _extract_resource_dates(root)
        assert result == {
            "resource_creation_date": "",
            "resource_publication_date": "",
            "resource_revision_date": "",
        }

    def test_prefers_datetime_over_date(self):
        """Cuando hay tanto gco:DateTime como gco:Date, se toma el primero (DateTime)."""
        dates_xml = (
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date>"
            "<gco:DateTime>2020-01-01T12:00:00</gco:DateTime>"
            "<gco:Date>2020-01-01</gco:Date>"
            "</gmd:date>"
            '<gmd:dateType><gmd:CI_DateTypeCode codeListValue="creation"/></gmd:dateType>'
            "</gmd:CI_Date></gmd:date>"
        )
        root = _root(self._make_xml(dates_xml))
        result = _extract_resource_dates(root)
        assert result["resource_creation_date"] == "2020-01-01T12:00:00"


class TestExtractTemporalExtent:
    """Tests para _extract_temporal_extent con XML sintéticos."""

    def _make_xml(self, temporal_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco"'
            ' xmlns:gml="http://www.opengis.net/gml/3.2">'
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:extent><gmd:EX_Extent>"
            f"{temporal_xml}"
            "</gmd:EX_Extent></gmd:extent>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_begin_and_end_gml32(self):
        temporal_xml = (
            "<gmd:temporalElement><gmd:EX_TemporalExtent><gmd:extent>"
            '<gml:TimePeriod gml:id="tp1">'
            "<gml:beginPosition>2010-01-01</gml:beginPosition>"
            "<gml:endPosition>2020-12-31</gml:endPosition>"
            "</gml:TimePeriod>"
            "</gmd:extent></gmd:EX_TemporalExtent></gmd:temporalElement>"
        )
        root = _root(self._make_xml(temporal_xml))
        result = _extract_temporal_extent(root)
        assert result["temporal_extent_begin"] == "2010-01-01"
        assert result["temporal_extent_end"] == "2020-12-31"

    def test_extracts_with_gml320_namespace(self):
        """Prueba con el namespace GML legacy (gml320)."""
        xml = (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco"'
            ' xmlns:gml="http://www.opengis.net/gml">'
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:extent><gmd:EX_Extent>"
            "<gmd:temporalElement><gmd:EX_TemporalExtent><gmd:extent>"
            '<gml:TimePeriod gml:id="tp1">'
            "<gml:beginPosition>2015-06-01</gml:beginPosition>"
            "<gml:endPosition>2016-05-31</gml:endPosition>"
            "</gml:TimePeriod>"
            "</gmd:extent></gmd:EX_TemporalExtent></gmd:temporalElement>"
            "</gmd:EX_Extent></gmd:extent>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
            "</gmd:MD_Metadata>"
        )
        root = _root(xml)
        result = _extract_temporal_extent(root)
        assert result["temporal_extent_begin"] == "2015-06-01"
        assert result["temporal_extent_end"] == "2016-05-31"

    def test_returns_empty_when_no_temporal(self):
        root = _root(self._make_xml(""))
        result = _extract_temporal_extent(root)
        assert result == {"temporal_extent_begin": "", "temporal_extent_end": ""}

    def test_partial_begin_only(self):
        temporal_xml = (
            "<gmd:temporalElement><gmd:EX_TemporalExtent><gmd:extent>"
            '<gml:TimePeriod gml:id="tp1">'
            "<gml:beginPosition>2010-01-01</gml:beginPosition>"
            "<gml:endPosition/>"
            "</gml:TimePeriod>"
            "</gmd:extent></gmd:EX_TemporalExtent></gmd:temporalElement>"
        )
        root = _root(self._make_xml(temporal_xml))
        result = _extract_temporal_extent(root)
        assert result["temporal_extent_begin"] == "2010-01-01"
        assert result["temporal_extent_end"] == ""


class TestExtractConstraints:
    """Tests para _extract_constraints con XML sintéticos."""

    def _make_xml(self, constraints_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            f"{constraints_xml}"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_use_limitation_from_md_constraints(self):
        xml = self._make_xml(
            "<gmd:resourceConstraints><gmd:MD_Constraints>"
            "<gmd:useLimitation><gco:CharacterString>Solo uso académico</gco:CharacterString></gmd:useLimitation>"
            "</gmd:MD_Constraints></gmd:resourceConstraints>"
        )
        root = _root(xml)
        result = _extract_constraints(root)
        assert result["use_limitation"] == "Solo uso académico"

    def test_extracts_use_limitation_from_legal_constraints(self):
        xml = self._make_xml(
            "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
            "<gmd:useLimitation><gco:CharacterString>Uso restringido</gco:CharacterString></gmd:useLimitation>"
            "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        )
        root = _root(xml)
        result = _extract_constraints(root)
        assert result["use_limitation"] == "Uso restringido"

    def test_extracts_license(self):
        xml = self._make_xml(
            "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
            "<gmd:otherConstraints><gco:CharacterString>CC-BY 4.0</gco:CharacterString></gmd:otherConstraints>"
            "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        )
        root = _root(xml)
        result = _extract_constraints(root)
        assert result["license"] == "CC-BY 4.0"

    def test_extracts_access_constraints(self):
        xml = self._make_xml(
            "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
            '<gmd:accessConstraints><gmd:MD_RestrictionCode codeListValue="otherRestrictions"/></gmd:accessConstraints>'
            "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        )
        root = _root(xml)
        result = _extract_constraints(root)
        assert result["access_constraints"] == "otherRestrictions"

    def test_all_empty_when_no_constraints(self):
        root = _root(self._make_xml(""))
        result = _extract_constraints(root)
        assert result == {"license": "", "use_limitation": "", "access_constraints": ""}

    def test_extracts_all_constraint_fields(self):
        xml = self._make_xml(
            "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
            "<gmd:useLimitation><gco:CharacterString>No comercial</gco:CharacterString></gmd:useLimitation>"
            "<gmd:otherConstraints><gco:CharacterString>GPL-3.0</gco:CharacterString></gmd:otherConstraints>"
            '<gmd:accessConstraints><gmd:MD_RestrictionCode codeListValue="license"/></gmd:accessConstraints>'
            "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        )
        root = _root(xml)
        result = _extract_constraints(root)
        assert result["use_limitation"] == "No comercial"
        assert result["license"] == "GPL-3.0"
        assert result["access_constraints"] == "license"


class TestExtractSpecificationConformance:
    """Tests para _extract_specification_conformance con XML sintéticos."""

    def _make_xml(self, reports_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            "<gmd:dataQualityInfo><gmd:DQ_DataQuality>"
            f"{reports_xml}"
            "</gmd:DQ_DataQuality></gmd:dataQualityInfo>"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_conformance_result(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>INSPIRE</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2010-12-08</gco:Date></gmd:date>"
            "</gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString>Conforme</gco:CharacterString></gmd:explanation>"
            "<gmd:pass><gco:Boolean>true</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert len(result) == 1
        assert result[0]["title"] == "INSPIRE"
        assert result[0]["date"] == "2010-12-08"
        assert result[0]["explanation"] == "Conforme"
        assert result[0]["passed"] is True

    def test_passed_false(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>Spec X</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2023-01-01</gco:Date></gmd:date>"
            "</gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString>No conforme</gco:CharacterString></gmd:explanation>"
            "<gmd:pass><gco:Boolean>false</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert result[0]["passed"] is False

    def test_passed_none_when_missing(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>Spec Y</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:Date>2023-06-15</gco:Date></gmd:date>"
            "</gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString/></gmd:explanation>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert result[0]["passed"] is None

    def test_skips_conformance_without_title(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString/></gmd:title>"
            "</gmd:CI_Citation></gmd:specification>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert result == []

    def test_empty_when_no_reports(self):
        root = _root(self._make_xml(""))
        result = _extract_specification_conformance(root)
        assert result == []

    def test_multiple_conformance_results(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>Spec A</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date><gmd:date><gco:Date>2020-01-01</gco:Date></gmd:date></gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString>OK</gco:CharacterString></gmd:explanation>"
            "<gmd:pass><gco:Boolean>true</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>Spec B</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date><gmd:date><gco:Date>2021-06-01</gco:Date></gmd:date></gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString>Fail</gco:CharacterString></gmd:explanation>"
            "<gmd:pass><gco:Boolean>false</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert len(result) == 2
        assert result[0]["title"] == "Spec A"
        assert result[1]["title"] == "Spec B"

    def test_uses_datetime_for_specification_date(self):
        reports_xml = (
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>Spec DT</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date>"
            "<gmd:date><gco:DateTime>2022-07-15T10:30:00</gco:DateTime></gmd:date>"
            "</gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString/></gmd:explanation>"
            "<gmd:pass><gco:Boolean>true</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
        )
        root = _root(self._make_xml(reports_xml))
        result = _extract_specification_conformance(root)
        assert result[0]["date"] == "2022-07-15T10:30:00"


class TestExtractProcessSteps:
    """Tests para _extract_process_steps con XML sintéticos."""

    def _make_xml(self, steps_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            "<gmd:dataQualityInfo><gmd:DQ_DataQuality>"
            "<gmd:lineage><gmd:LI_Lineage>"
            f"{steps_xml}"
            "</gmd:LI_Lineage></gmd:lineage>"
            "</gmd:DQ_DataQuality></gmd:dataQualityInfo>"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_single_step(self):
        steps_xml = (
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString>Reproyección a EPSG:4326</gco:CharacterString></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
        )
        root = _root(self._make_xml(steps_xml))
        result = _extract_process_steps(root)
        assert result == ["Reproyección a EPSG:4326"]

    def test_extracts_multiple_steps(self):
        steps_xml = (
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString>Paso 1</gco:CharacterString></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString>Paso 2</gco:CharacterString></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
        )
        root = _root(self._make_xml(steps_xml))
        result = _extract_process_steps(root)
        assert result == ["Paso 1", "Paso 2"]

    def test_skips_empty_descriptions(self):
        steps_xml = (
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString/></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString>Paso válido</gco:CharacterString></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
        )
        root = _root(self._make_xml(steps_xml))
        result = _extract_process_steps(root)
        assert result == ["Paso válido"]

    def test_returns_empty_when_no_steps(self):
        root = _root(self._make_xml(""))
        result = _extract_process_steps(root)
        assert result == []


class TestExtractGeoserverLayerName:
    """Tests para _extract_geoserver_layer_name con XML sintéticos."""

    def _make_xml(self, online_resources_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            "<gmd:distributionInfo><gmd:MD_Distribution>"
            "<gmd:transferOptions><gmd:MD_DigitalTransferOptions>"
            f"{online_resources_xml}"
            "</gmd:MD_DigitalTransferOptions></gmd:transferOptions>"
            "</gmd:MD_Distribution></gmd:distributionInfo>"
            "</gmd:MD_Metadata>"
        )

    def _online_resource(self, url: str, protocol: str, name: str) -> str:
        return (
            "<gmd:onLine><gmd:CI_OnlineResource>"
            f"<gmd:linkage><gmd:URL>{url}</gmd:URL></gmd:linkage>"
            f"<gmd:protocol><gco:CharacterString>{protocol}</gco:CharacterString></gmd:protocol>"
            f"<gmd:name><gco:CharacterString>{name}</gco:CharacterString></gmd:name>"
            "</gmd:CI_OnlineResource></gmd:onLine>"
        )

    def test_extracts_from_ogc_wms(self):
        xml = self._make_xml(
            self._online_resource(
                "https://host/geoserver/ASR/ows?SERVICE=WMS&amp;",
                "OGC:WMS-1.3.0-http-get-map",
                "HU_CSK_sample",
            )
        )
        assert _extract_geoserver_layer_name(_root(xml)) == "ASR:HU_CSK_sample"

    def test_extracts_from_ogc_wfs(self):
        xml = self._make_xml(
            self._online_resource(
                "https://host/geoserver/VectorWS/wfs?service=WFS",
                "OGC:WFS-2.0.0-http-get-feature",
                "parcelas",
            )
        )
        assert _extract_geoserver_layer_name(_root(xml)) == "VectorWS:parcelas"

    def test_skips_non_ogc_protocols(self):
        xml = self._make_xml(
            self._online_resource(
                "http://host/doc.pdf",
                "text/plain",
                "metadato_pdf",
            )
            + self._online_resource(
                "https://host/geoserver/ASR/ows?SERVICE=WMS",
                "OGC:WMS-1.3.0-http-get-map",
                "capa_ok",
            )
        )
        assert _extract_geoserver_layer_name(_root(xml)) == "ASR:capa_ok"

    def test_returns_none_when_no_online_resources(self):
        xml = self._make_xml("")
        assert _extract_geoserver_layer_name(_root(xml)) is None

    def test_returns_none_when_url_is_not_geoserver(self):
        xml = self._make_xml(
            self._online_resource(
                "https://other-host/wms?SERVICE=WMS",
                "OGC:WMS-1.3.0-http-get-map",
                "capa",
            )
        )
        assert _extract_geoserver_layer_name(_root(xml)) is None

    def test_returns_none_when_name_is_empty(self):
        xml = self._make_xml(
            "<gmd:onLine><gmd:CI_OnlineResource>"
            "<gmd:linkage><gmd:URL>https://host/geoserver/ASR/ows</gmd:URL></gmd:linkage>"
            "<gmd:protocol><gco:CharacterString>OGC:WMS-1.3.0-http-get-map</gco:CharacterString></gmd:protocol>"
            "<gmd:name><gco:CharacterString/></gmd:name>"
            "</gmd:CI_OnlineResource></gmd:onLine>"
        )
        assert _extract_geoserver_layer_name(_root(xml)) is None

    def test_takes_first_ogc_match(self):
        xml = self._make_xml(
            self._online_resource(
                "https://host/geoserver/WsA/wms",
                "OGC:WMS-1.3.0-http-get-map",
                "primero",
            )
            + self._online_resource(
                "https://host/geoserver/WsB/wfs",
                "OGC:WFS-2.0.0-http-get-feature",
                "segundo",
            )
        )
        assert _extract_geoserver_layer_name(_root(xml)) == "WsA:primero"


class TestParentGeonetworkUuid:
    """Tests para la extracción de parent_geonetwork_uuid."""

    def _make_xml(self, parent_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            f"{parent_xml}"
            "</gmd:MD_Metadata>"
        )

    def test_extracts_parent_uuid(self):
        xml = self._make_xml(
            "<gmd:parentIdentifier>"
            "<gco:CharacterString>abc-123-parent</gco:CharacterString>"
            "</gmd:parentIdentifier>"
        )
        result = parse_iso19139_extras(xml)
        assert result["parent_geonetwork_uuid"] == "abc-123-parent"

    def test_returns_none_when_absent(self):
        xml = self._make_xml("")
        result = parse_iso19139_extras(xml)
        assert result["parent_geonetwork_uuid"] is None

    def test_returns_none_when_empty(self):
        xml = self._make_xml(
            "<gmd:parentIdentifier>"
            "<gco:CharacterString></gco:CharacterString>"
            "</gmd:parentIdentifier>"
        )
        result = parse_iso19139_extras(xml)
        assert result["parent_geonetwork_uuid"] is None


class TestParseIso19139ExtrasSyntheticXml:
    """Tests que cubren ramas de parse_iso19139_extras no ejercitadas por el XML real."""

    def _make_full_xml(self, inner_xml: str) -> str:
        return (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco"'
            ' xmlns:gml="http://www.opengis.net/gml/3.2">'
            f"{inner_xml}"
            "</gmd:MD_Metadata>"
        )

    def test_resource_alt_title(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:citation><gmd:CI_Citation>"
            "<gmd:alternateTitle><gco:CharacterString>Alt Title</gco:CharacterString></gmd:alternateTitle>"
            "</gmd:CI_Citation></gmd:citation>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resource_alt_title"] == "Alt Title"

    def test_resource_identifier(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:citation><gmd:CI_Citation>"
            "<gmd:identifier><gmd:MD_Identifier>"
            "<gmd:code><gco:CharacterString>doi:10.1234/test</gco:CharacterString></gmd:code>"
            "</gmd:MD_Identifier></gmd:identifier>"
            "</gmd:CI_Citation></gmd:citation>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resource_identifier"] == "doi:10.1234/test"

    def test_topic_category(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:topicCategory>"
            "<gmd:MD_TopicCategoryCode>imageryBaseMapsEarthCover</gmd:MD_TopicCategoryCode>"
            "</gmd:topicCategory>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["topic_category"] == "imageryBaseMapsEarthCover"

    def test_overview_url(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:graphicOverview><gmd:MD_BrowseGraphic>"
            "<gmd:fileName><gco:CharacterString>https://example.com/thumb.png</gco:CharacterString></gmd:fileName>"
            "</gmd:MD_BrowseGraphic></gmd:graphicOverview>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["overview_url"] == "https://example.com/thumb.png"

    def test_distribution_format_with_values(self):
        xml = self._make_full_xml(
            "<gmd:distributionInfo><gmd:MD_Distribution>"
            "<gmd:distributionFormat><gmd:MD_Format>"
            "<gmd:name><gco:CharacterString>GeoTIFF</gco:CharacterString></gmd:name>"
            "<gmd:version><gco:CharacterString>1.0</gco:CharacterString></gmd:version>"
            "</gmd:MD_Format></gmd:distributionFormat>"
            "</gmd:MD_Distribution></gmd:distributionInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["distribution_format_name"] == "GeoTIFF"
        assert result["distribution_format_version"] == "1.0"

    def test_distribution_format_absent(self):
        """Sin elemento MD_Format, los campos deben ser cadena vacía."""
        xml = self._make_full_xml(
            "<gmd:distributionInfo><gmd:MD_Distribution>"
            "</gmd:MD_Distribution></gmd:distributionInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["distribution_format_name"] == ""
        assert result["distribution_format_version"] == ""

    def test_lineage_with_content(self):
        xml = self._make_full_xml(
            "<gmd:dataQualityInfo><gmd:DQ_DataQuality>"
            "<gmd:lineage><gmd:LI_Lineage>"
            "<gmd:statement><gco:CharacterString>Datos derivados de imágenes SAR</gco:CharacterString></gmd:statement>"
            "</gmd:LI_Lineage></gmd:lineage>"
            "</gmd:DQ_DataQuality></gmd:dataQualityInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["lineage"] == "Datos derivados de imágenes SAR"

    def test_single_crs(self):
        xml = self._make_full_xml(
            "<gmd:referenceSystemInfo><gmd:MD_ReferenceSystem>"
            "<gmd:referenceSystemIdentifier><gmd:RS_Identifier>"
            "<gmd:code><gco:CharacterString>EPSG:4326</gco:CharacterString></gmd:code>"
            "</gmd:RS_Identifier></gmd:referenceSystemIdentifier>"
            "</gmd:MD_ReferenceSystem></gmd:referenceSystemInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["crs"] == ["EPSG:4326"]

    def test_no_crs(self):
        xml = self._make_full_xml("")
        result = parse_iso19139_extras(xml)
        assert result["crs"] == []

    def test_other_languages(self):
        xml = self._make_full_xml(
            '<gmd:locale><gmd:PT_Locale><gmd:languageCode>'
            '<gmd:LanguageCode codeListValue="spa"/>'
            "</gmd:languageCode></gmd:PT_Locale></gmd:locale>"
            '<gmd:locale><gmd:PT_Locale><gmd:languageCode>'
            '<gmd:LanguageCode codeListValue="por"/>'
            "</gmd:languageCode></gmd:PT_Locale></gmd:locale>"
        )
        result = parse_iso19139_extras(xml)
        assert result["other_languages"] == ["spa", "por"]

    def test_resource_language_codelist(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            '<gmd:language><gmd:LanguageCode codeListValue="spa"/></gmd:language>'
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resource_language"] == "spa"

    def test_resource_language_fallback_char_string(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:language><gco:CharacterString>español</gco:CharacterString></gmd:language>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resource_language"] == "español"

    def test_resource_edition(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:citation><gmd:CI_Citation>"
            "<gmd:edition><gco:CharacterString>2da edición</gco:CharacterString></gmd:edition>"
            "</gmd:CI_Citation></gmd:citation>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resource_edition"] == "2da edición"

    def test_purpose(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:purpose><gco:CharacterString>Monitoreo ambiental</gco:CharacterString></gmd:purpose>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["purpose"] == "Monitoreo ambiental"

    def test_supplemental_information(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:supplementalInformation>"
            "<gco:CharacterString>Contactar para acceso</gco:CharacterString>"
            "</gmd:supplementalInformation>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["supplemental_information"] == "Contactar para acceso"

    def test_resolution_scale_denominator(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:spatialResolution><gmd:MD_Resolution>"
            "<gmd:equivalentScale><gmd:MD_RepresentativeFraction>"
            "<gmd:denominator><gco:Integer>50000</gco:Integer></gmd:denominator>"
            "</gmd:MD_RepresentativeFraction></gmd:equivalentScale>"
            "</gmd:MD_Resolution></gmd:spatialResolution>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resolution_scale_denominator"] == "50000"

    def test_resolution_distance_with_uom(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:spatialResolution><gmd:MD_Resolution>"
            '<gmd:distance><gco:Distance uom="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/uom/ML_gmxUom.xml#m">30</gco:Distance></gmd:distance>'
            "</gmd:MD_Resolution></gmd:spatialResolution>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resolution_distance"] == "30 m"

    def test_resolution_distance_with_simple_uom(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:spatialResolution><gmd:MD_Resolution>"
            '<gmd:distance><gco:Distance uom="km">5</gco:Distance></gmd:distance>'
            "</gmd:MD_Resolution></gmd:spatialResolution>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resolution_distance"] == "5 km"

    def test_resolution_distance_without_uom(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:spatialResolution><gmd:MD_Resolution>"
            "<gmd:distance><gco:Distance>100</gco:Distance></gmd:distance>"
            "</gmd:MD_Resolution></gmd:spatialResolution>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["resolution_distance"] == "100"

    def test_maintenance_frequency(self):
        xml = self._make_full_xml(
            "<gmd:identificationInfo><gmd:MD_DataIdentification>"
            "<gmd:resourceMaintenance><gmd:MD_MaintenanceInformation>"
            "<gmd:maintenanceAndUpdateFrequency>"
            '<gmd:MD_MaintenanceFrequencyCode codeListValue="annually"/>'
            "</gmd:maintenanceAndUpdateFrequency>"
            "</gmd:MD_MaintenanceInformation></gmd:resourceMaintenance>"
            "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert result["maintenance_frequency"] == "annually"

    def test_specification_conformance_included_when_present(self):
        xml = self._make_full_xml(
            "<gmd:dataQualityInfo><gmd:DQ_DataQuality>"
            "<gmd:report><gmd:DQ_DomainConsistency>"
            "<gmd:result><gmd:DQ_ConformanceResult>"
            "<gmd:specification><gmd:CI_Citation>"
            "<gmd:title><gco:CharacterString>INSPIRE</gco:CharacterString></gmd:title>"
            "<gmd:date><gmd:CI_Date><gmd:date><gco:Date>2010-12-08</gco:Date></gmd:date>"
            "</gmd:CI_Date></gmd:date>"
            "</gmd:CI_Citation></gmd:specification>"
            "<gmd:explanation><gco:CharacterString>OK</gco:CharacterString></gmd:explanation>"
            "<gmd:pass><gco:Boolean>true</gco:Boolean></gmd:pass>"
            "</gmd:DQ_ConformanceResult></gmd:result>"
            "</gmd:DQ_DomainConsistency></gmd:report>"
            "</gmd:DQ_DataQuality></gmd:dataQualityInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert "specification_conformance" in result
        assert len(result["specification_conformance"]) == 1
        assert result["specification_conformance"][0]["title"] == "INSPIRE"

    def test_process_steps_included_when_present(self):
        xml = self._make_full_xml(
            "<gmd:dataQualityInfo><gmd:DQ_DataQuality>"
            "<gmd:lineage><gmd:LI_Lineage>"
            "<gmd:processStep><gmd:LI_ProcessStep>"
            "<gmd:description><gco:CharacterString>Recorte</gco:CharacterString></gmd:description>"
            "</gmd:LI_ProcessStep></gmd:processStep>"
            "</gmd:LI_Lineage></gmd:lineage>"
            "</gmd:DQ_DataQuality></gmd:dataQualityInfo>"
        )
        result = parse_iso19139_extras(xml)
        assert "process_steps" in result
        assert result["process_steps"] == ["Recorte"]


class TestMergeIso19139Extras:
    @pytest.fixture
    def record(self) -> MetadataRecord:
        return MetadataRecord(
            id="abc-123",
            title="Título GeoDCAT",
            status="onGoing",
            crs=["http://www.opengis.net/def/crs/EPSG/0/4326"],
        )

    def test_fills_empty_fields(self, record):
        merged = merge_iso19139_extras(record, {"character_set": "utf8"})
        assert merged.character_set == "utf8"

    def test_does_not_override_fields_with_value(self, record):
        merged = merge_iso19139_extras(record, {"status": "completed", "title": "Otro"})
        assert merged.status == "onGoing"
        assert merged.title == "Título GeoDCAT"

    def test_crs_always_prefers_xml(self, record):
        merged = merge_iso19139_extras(record, {"crs": ["CRS:84"]})
        assert merged.crs == ["CRS:84"]

    def test_empty_xml_crs_does_not_override(self, record):
        merged = merge_iso19139_extras(record, {"crs": []})
        assert merged.crs == ["http://www.opengis.net/def/crs/EPSG/0/4326"]
