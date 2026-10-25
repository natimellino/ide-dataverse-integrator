"""
Parser complementario para ISO 19139 XML.

Extrae campos que no están disponibles en el formato GeoDCAT-AP RDF
pero sí en la respuesta XML nativa de GeoNetwork.
"""
import re

from lxml import etree

from ide_dataverse_integrator.models.metadata_record import MetadataRecord

# Namespaces ISO 19139
NS = {
    "gmd": "http://www.isotc211.org/2005/gmd",
    "gco": "http://www.isotc211.org/2005/gco",
    "gml": "http://www.opengis.net/gml/3.2",
    "gml320": "http://www.opengis.net/gml",
}

# Xpath base para identificationInfo
_ID_BASE = ".//gmd:identificationInfo/gmd:MD_DataIdentification"
_CITATION = f"{_ID_BASE}/gmd:citation/gmd:CI_Citation"

# Prefijo de protocolo que marca una URL como servicio OGC (WMS/WFS/WCS/WPS).
_OGC_PROTOCOL_PREFIX = "OGC:"

# Captura el workspace de un endpoint de GeoServer: /geoserver/<workspace>/<servicio>
_GEOSERVER_WORKSPACE_RE = re.compile(
    r"/geoserver/([^/]+)/(?:ows|wms|wfs|wcs|wps)",
    re.IGNORECASE,
)


def _text(element, xpath: str) -> str:
    """Extrae el texto de un elemento XML dado un xpath, o devuelve cadena vacía."""
    node = element.find(xpath, NS)
    if node is not None and node.text:
        return node.text.strip()
    return ""


def _code_list_value(element, xpath: str) -> str:
    """Extrae el atributo codeListValue de un elemento con codelist."""
    node = element.find(xpath, NS)
    if node is not None:
        return node.get("codeListValue", "")
    return ""


def _extract_resource_dates(root) -> dict:
    """Extrae las fechas del recurso (creation, publication, revision)."""
    dates = {
        "resource_creation_date": "",
        "resource_publication_date": "",
        "resource_revision_date": "",
    }

    for ci_date in root.findall(f"{_CITATION}/gmd:date/gmd:CI_Date", NS):
        date_type = _code_list_value(
            ci_date,
            "gmd:dateType/gmd:CI_DateTypeCode",
        )
        date_val = (
            _text(ci_date, "gmd:date/gco:DateTime")
            or _text(ci_date, "gmd:date/gco:Date")
        )

        key = f"resource_{date_type}_date"
        if date_type and date_val and key in dates:
            dates[key] = date_val

    return dates


def _extract_temporal_extent(root) -> dict:
    """Extrae la extensión temporal del recurso."""
    result = {
        "temporal_extent_begin": "",
        "temporal_extent_end": "",
    }

    # Buscar TimePeriod en ambos namespaces GML (3.2 y 3.2.0/legacy)
    for prefix in ("gml", "gml320"):
        time_period = root.find(
            f"{_ID_BASE}/gmd:extent/gmd:EX_Extent"
            f"/gmd:temporalElement/gmd:EX_TemporalExtent"
            f"/gmd:extent/{prefix}:TimePeriod",
            NS,
        )

        if time_period is None:
            continue

        begin = time_period.find(f"{prefix}:beginPosition", NS)
        end = time_period.find(f"{prefix}:endPosition", NS)

        if begin is not None and begin.text:
            result["temporal_extent_begin"] = begin.text.strip()

        if end is not None and end.text:
            result["temporal_extent_end"] = end.text.strip()

        break

    return result


def _extract_constraints(root) -> dict:
    """Extrae restricciones legales, limitaciones de uso y restricciones de acceso."""
    result = {"license": "", "use_limitation": "", "access_constraints": ""}

    constraints_base = f"{_ID_BASE}/gmd:resourceConstraints"

    # useLimitation (puede estar en cualquier tipo de constraints)
    result["use_limitation"] = _text(
        root,
        f"{constraints_base}/gmd:MD_Constraints"
        "/gmd:useLimitation/gco:CharacterString",
    ) or _text(
        root,
        f"{constraints_base}/gmd:MD_LegalConstraints"
        "/gmd:useLimitation/gco:CharacterString",
    )

    # license (otherConstraints de MD_LegalConstraints)
    result["license"] = _text(
        root,
        f"{constraints_base}/gmd:MD_LegalConstraints"
        "/gmd:otherConstraints/gco:CharacterString",
    )

    # accessConstraints (codelist value)
    result["access_constraints"] = _code_list_value(
        root,
        f"{constraints_base}/gmd:MD_LegalConstraints"
        "/gmd:accessConstraints/gmd:MD_RestrictionCode",
    )

    return result


def _extract_specification_conformance(root) -> list:
    """Extrae conformidad con especificaciones del dataQualityInfo."""
    specifications = []
    data_quality_path = (
        ".//gmd:dataQualityInfo/gmd:DQ_DataQuality"
        "/gmd:report"
    )

    for report in root.findall(data_quality_path, NS):
        conformance_results = report.findall(
            ".//gmd:result/gmd:DQ_ConformanceResult",
            NS,
        )

        for result_node in conformance_results:
            title = _text(
                result_node,
                "gmd:specification/gmd:CI_Citation"
                "/gmd:title/gco:CharacterString",
            )

            if not title:
                continue

            specification_date = (
                _text(
                    result_node,
                    "gmd:specification/gmd:CI_Citation"
                    "/gmd:date/gmd:CI_Date/gmd:date/gco:Date",
                )
                or _text(
                    result_node,
                    "gmd:specification/gmd:CI_Citation"
                    "/gmd:date/gmd:CI_Date/gmd:date/gco:DateTime",
                )
            )

            explanation = _text(
                result_node,
                "gmd:explanation/gco:CharacterString",
            )

            pass_value = result_node.findtext(
                "gmd:pass/gco:Boolean",
                default="",
                namespaces=NS,
            )
            passed = pass_value.strip().lower() == "true" if pass_value else None

            specifications.append({
                "title": title,
                "date": specification_date,
                "explanation": explanation,
                "passed": passed,
            })

    return specifications


def _extract_geoserver_layer_name(root) -> str | None:
    """Resuelve el nombre calificado (workspace:layer) desde los onLine OGC del XML.

    Recorre los `gmd:CI_OnlineResource` de `distributionInfo` y toma el primero
    cuyo `gmd:protocol` indique un servicio OGC. El nombre bare sale de
    `gmd:name` y el workspace del path de la URL de GeoServer.
    """
    online_resources = root.findall(
        ".//gmd:distributionInfo/gmd:MD_Distribution"
        "/gmd:transferOptions/gmd:MD_DigitalTransferOptions"
        "/gmd:onLine/gmd:CI_OnlineResource",
        NS,
    )
    for resource in online_resources:
        protocol = _text(resource, "gmd:protocol/gco:CharacterString")
        if not protocol.startswith(_OGC_PROTOCOL_PREFIX):
            continue
        bare_name = _text(resource, "gmd:name/gco:CharacterString")
        if not bare_name:
            continue
        url = _text(resource, "gmd:linkage/gmd:URL")
        workspace_match = _GEOSERVER_WORKSPACE_RE.search(url)
        if not workspace_match:
            continue
        return f"{workspace_match.group(1)}:{bare_name}"
    return None


def _extract_process_steps(root) -> list:
    """Extrae descripciones de los pasos de procesamiento del lineage."""
    steps = []
    for ps in root.findall(
        ".//gmd:dataQualityInfo/gmd:DQ_DataQuality"
        "/gmd:lineage/gmd:LI_Lineage"
        "/gmd:processStep/gmd:LI_ProcessStep",
        NS,
    ):
        description = _text(ps, "gmd:description/gco:CharacterString")
        if description:
            steps.append(description)
    return steps


def parse_iso19139_extras(xml_text: str) -> dict:
    """
    Parsea un XML ISO 19139 y extrae los campos complementarios
    que no están presentes en la respuesta GeoDCAT-AP.

    Args:
        xml_text (str): XML ISO 19139 como string.

    Returns:
        dict: Diccionario con los campos extra.
    """
    root = etree.fromstring(xml_text.encode("utf-8"))

    result = {}

    # parentIdentifier (UUID del registro padre en GeoNetwork)
    # TODO: validar que esto esté asi en el XML, sino tenemos que cambiar la implementación
    result["parent_geonetwork_uuid"] = _text(
        root, ".//gmd:parentIdentifier/gco:CharacterString"
    ) or None

    # geoserver_layer_name (workspace:layer) autodescubierto desde los onLine OGC.
    result["geoserver_layer_name"] = _extract_geoserver_layer_name(root)

    # characterSet (ej: "utf8")
    result["character_set"] = _code_list_value(
        root, ".//gmd:characterSet/gmd:MD_CharacterSetCode"
    )

    # metadataStandardName (ej: "ISO 19115:2003/19139")
    result["metadata_standard_name"] = _text(
        root, ".//gmd:metadataStandardName/gco:CharacterString"
    )

    # metadataStandardVersion (ej: "1.0")
    result["metadata_standard_version"] = _text(
        root, ".//gmd:metadataStandardVersion/gco:CharacterString"
    )

    # resourceAltTitle
    result["resource_alt_title"] = _text(
        root, f"{_CITATION}/gmd:alternateTitle/gco:CharacterString"
    )

    # resourceIdentifier (code del identifier de la citation)
    result["resource_identifier"] = _text(
        root,
        f"{_CITATION}/gmd:identifier/gmd:MD_Identifier"
        "/gmd:code/gco:CharacterString",
    )

    # status (ej: "completed")
    result["status"] = _code_list_value(
        root, f"{_ID_BASE}/gmd:status/gmd:MD_ProgressCode"
    )

    # topicCategory (ej: "imageryBaseMapsEarthCover")
    result["topic_category"] = _text(
        root, f"{_ID_BASE}/gmd:topicCategory/gmd:MD_TopicCategoryCode"
    )

    # overview / thumbnail URL
    result["overview_url"] = _text(
        root,
        f"{_ID_BASE}/gmd:graphicOverview/gmd:MD_BrowseGraphic"
        "/gmd:fileName/gco:CharacterString",
    )

    # Fechas del recurso (creation, publication, revision)
    result.update(_extract_resource_dates(root))

    # Extensión temporal
    result.update(_extract_temporal_extent(root))

    # Restricciones y licencia
    result.update(_extract_constraints(root))

    # distributionFormat (name + version)
    dist_format = root.find(
        ".//gmd:distributionInfo/gmd:MD_Distribution"
        "/gmd:distributionFormat/gmd:MD_Format",
        NS,
    )
    if dist_format is not None:
        result["distribution_format_name"] = _text(
            dist_format, "gmd:name/gco:CharacterString"
        )
        result["distribution_format_version"] = _text(
            dist_format, "gmd:version/gco:CharacterString"
        )
    else:
        result["distribution_format_name"] = ""
        result["distribution_format_version"] = ""

    # lineage
    result["lineage"] = _text(
        root,
        ".//gmd:dataQualityInfo/gmd:DQ_DataQuality"
        "/gmd:lineage/gmd:LI_Lineage/gmd:statement/gco:CharacterString",
    )

    # CRS del XML original (ej: ["EPSG:22185", "CRS:84"])
    crs_list = []
    for ref_sys in root.findall(".//gmd:referenceSystemInfo", NS):
        code = _text(
            ref_sys,
            "gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier"
            "/gmd:RS_Identifier/gmd:code/gco:CharacterString",
        )
        if code:
            crs_list.append(code)
    result["crs"] = sorted(crs_list)

    # otherLanguages (idiomas adicionales del metadata)
    other_langs = []
    for locale in root.findall(".//gmd:locale/gmd:PT_Locale", NS):
        lang_code = _code_list_value(
            locale, "gmd:languageCode/gmd:LanguageCode"
        )
        if lang_code:
            other_langs.append(lang_code)
    result["other_languages"] = other_langs

    # resourceLanguage (idioma del recurso)
    result["resource_language"] = _code_list_value(
        root, f"{_ID_BASE}/gmd:language/gmd:LanguageCode"
    ) or _text(root, f"{_ID_BASE}/gmd:language/gco:CharacterString")

    # resourceEdition
    result["resource_edition"] = _text(
        root, f"{_CITATION}/gmd:edition/gco:CharacterString"
    )

    # purpose
    result["purpose"] = _text(
        root, f"{_ID_BASE}/gmd:purpose/gco:CharacterString"
    )

    # supplementalInformation
    result["supplemental_information"] = _text(
        root, f"{_ID_BASE}/gmd:supplementalInformation/gco:CharacterString"
    )

    # spatialResolution — scale denominator
    result["resolution_scale_denominator"] = _text(
        root,
        f"{_ID_BASE}/gmd:spatialResolution/gmd:MD_Resolution"
        "/gmd:equivalentScale/gmd:MD_RepresentativeFraction"
        "/gmd:denominator/gco:Integer",
    )

    # spatialResolution — distance
    distance_node = root.find(
        f"{_ID_BASE}/gmd:spatialResolution/gmd:MD_Resolution"
        "/gmd:distance/gco:Distance",
        NS,
    )
    result["resolution_distance"] = ""
    if distance_node is not None and distance_node.text:
        unit_of_measure = distance_node.get("uom", "")
        if "#" in unit_of_measure:
            unit_of_measure = unit_of_measure.split("#")[-1]
        distance_value = distance_node.text.strip()
        result["resolution_distance"] = (
            f"{distance_value} {unit_of_measure}".strip()
            if unit_of_measure
            else distance_value
        )

    # maintenanceFrequency
    result["maintenance_frequency"] = _code_list_value(
        root,
        f"{_ID_BASE}/gmd:resourceMaintenance"
        "/gmd:MD_MaintenanceInformation"
        "/gmd:maintenanceAndUpdateFrequency"
        "/gmd:MD_MaintenanceFrequencyCode",
    )

    # specificationConformance
    specs = _extract_specification_conformance(root)
    if specs:
        result["specification_conformance"] = specs

    # processSteps
    steps = _extract_process_steps(root)
    if steps:
        result["process_steps"] = steps

    return result


def merge_iso19139_extras(record: MetadataRecord, extras: dict) -> MetadataRecord:
    """
    Completa un MetadataRecord con los campos extraídos del XML ISO 19139.

    Los campos de `xml_preferred_fields` siempre se toman del XML si tienen valor;
    el resto solo se completa si el campo del record está vacío.

    Args:
        record: MetadataRecord obtenido del formatter GeoDCAT-AP.
        extras: Diccionario devuelto por `parse_iso19139_extras`.

    Returns:
        MetadataRecord: nuevo record con los campos combinados.
    """
    xml_preferred_fields = {"crs"}
    merged = record.model_dump()
    for key, value in extras.items():
        if not value:
            continue
        if key in xml_preferred_fields or not merged.get(key):
            merged[key] = value
    return MetadataRecord.model_validate(merged)
