#!/usr/bin/env python3
"""Import a NAACCR Volume V (HL7 v2 ORU) synoptic report into the three-schema
SDC CDM.

Ported from SdcCdmLib/SdcCdm/ImportNaaccrVolV.cs. Writes:
  - omop.person          (create-or-find by source identifier)
  - sdc.sdc_report       (one synoptic report header per message)
  - naaccr.naaccr_value  (one row per logical captured value)

CAP messages use OBX-4 to connect a coded selection with its numeric or text
companion, so components sharing a normalized item/sub-ID are combined into one
naaccr_value row: CWE supplies value_code, numeric components supply value_num
and units, and non-numeric text supplies value_text.

The bridge ETL (database/etl/sqlite/1_naaccr_sdc_to_omop.sql) later turns these
into stock omop.note / omop.measurement rows.
"""

import logging
import math
import re
import uuid
from datetime import date, datetime
from typing import Any

from python_cdm_utils.crud_sqlite import (
    find_person_by_identifier,
    create_person,
    find_first_sdc_report_by_accession,
    create_sdc_report,
    create_naaccr_value,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

VALID_REPORT_TYPE_CODES = {"60568-3", "35265-8"}

# HL7 TS/DTM precisions the importer understands, longest first.
_HL7_DATE_PRECISIONS = (
    (14, "%Y%m%d%H%M%S"),
    (12, "%Y%m%d%H%M"),
    (10, "%Y%m%d%H"),
    (8, "%Y%m%d"),
)


def _null_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_obx_sub_id(value: str | None) -> str | None:
    """Drop a leading '+' and the identifier suffix so '+31357.100004300' -> '31357'."""
    normalized = _null_if_blank(value)
    if normalized is None:
        return None
    return _null_if_blank(normalized.lstrip("+").split(".", 1)[0])


def _parse_hl7_date(value: str | None) -> date | None:
    trimmed = _null_if_blank(value)
    if trimmed is None:
        return None
    digits = re.match(r"\d*", trimmed).group(0)  # \d* always matches
    for width, date_format in _HL7_DATE_PRECISIONS:
        if len(digits) >= width:
            try:
                return datetime.strptime(digits[:width], date_format).date()
            except ValueError:
                continue
    return None


def _new_captured_value(
    item_num: int, obx_sub_id: str | None, observation_date: date | None
) -> dict[str, Any]:
    """One logical answered item: an OBX-4 group's code, number, and text components."""
    return {
        "item_num": item_num,
        "obx_sub_id": obx_sub_id,
        "value_code": None,
        "value_num": None,
        "value_text": None,
        "value_unit_source": None,
        "observation_date": observation_date,
    }


def _numeric_value(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def import_data_from_hl7(cursor, hl7_message, exit_on_error=True):
    def hl7_error(message):
        raise Exception(message)

    def get_field(fields, index):
        # MSH segments shift the index by one (the field separator is field 1).
        idx = index - 1 if fields[0] == "MSH" else index
        return fields[idx] if 0 <= idx < len(fields) else ""

    def get_first_segment(segments, segment_name):
        for segment in segments:
            seg = segment.strip()
            fields = seg.split("|")
            name = fields[0].lstrip("﻿") if fields else ""
            if name == segment_name:
                return seg
        return None

    def get_all_segments(segments, segment_name):
        found = []
        for segment in segments:
            seg = segment.strip()
            fields = seg.split("|")
            name = fields[0].lstrip("﻿") if fields else ""
            if name == segment_name:
                found.append(seg)
        return found

    # HL7 commonly uses CR line endings, sometimes CRLF.
    lines = [ln for ln in hl7_message.replace("\r", "\n").split("\n") if ln.strip()]

    # MSH segment
    msh_segment = get_first_segment(lines, "MSH")
    if msh_segment is None:
        hl7_error("No MSH segment found")
        return
    msh_fields = msh_segment.split("|")
    message_type = get_field(msh_fields, 9)
    if message_type != "ORU^R01^ORU_R01":
        hl7_error(f"Unknown message type: {message_type}")
    print(f"Message type: {message_type}")
    # Message-profile validation is intentionally disabled (matches C#).

    # PID segment -> person
    pid_segment = get_first_segment(lines, "PID")
    if pid_segment is None:
        hl7_error("No PID segment found")
        return
    pid_fields = pid_segment.split("|")

    # OBR segment -> report identity
    obr_segment = get_first_segment(lines, "OBR")
    if obr_segment is None:
        hl7_error("No OBR segment found")
        return
    obr_fields = obr_segment.split("|")
    report_type = get_field(obr_fields, 4)
    report_type_code = (report_type or "").split("^")[0]
    if report_type_code not in VALID_REPORT_TYPE_CODES:
        hl7_error(f"Unknown report type: {report_type}")

    # OBR-3 = filler order number / accession (durable report key); OBR-4 = LOINC.
    # Normalize a missing/blank accession to None so accession-less reports never share
    # an empty-string join key in the bridge.
    report_accession_raw = (get_field(obr_fields, 3) or "").split("^")[0]
    report_accession = report_accession_raw if report_accession_raw.strip() else None
    report_loinc = report_type_code
    # OBR-7 (observation date) then OBR-22 (results change date) back the per-value
    # dates when an OBX carries no OBX-14 of its own.
    report_observation_date = (
        _parse_hl7_date(get_field(obr_fields, 7))
        or _parse_hl7_date(get_field(obr_fields, 22))
        or date.today()
    )

    # Person data
    person_source_value = get_field(pid_fields, 3)
    person_name = get_field(pid_fields, 5)
    birth_date = get_field(pid_fields, 7)
    gender = get_field(pid_fields, 8)

    birth_datetime = None
    if birth_date and len(birth_date) >= 8:
        try:
            birth_datetime = datetime(
                int(birth_date[0:4]), int(birth_date[4:6]), int(birth_date[6:8])
            )
        except Exception as ex:
            print(f"Error parsing birth date: {ex}")

    person_id = find_person_by_identifier(cursor, person_source_value)
    if person_id is None:
        gender_concept_id = 8507 if gender == "M" else 8532 if gender == "F" else 0
        person_id = create_person(
            cursor=cursor,
            person_source_value=person_source_value,
            year_of_birth=birth_datetime.year if birth_datetime else 1900,
            month_of_birth=birth_datetime.month if birth_datetime else None,
            day_of_birth=birth_datetime.day if birth_datetime else None,
            birth_datetime=birth_datetime.isoformat() if birth_datetime else None,
            gender_concept_id=gender_concept_id,
        )

    # OBX segments
    obx_segments = get_all_segments(lines, "OBX")
    if len(obx_segments) < 6:
        hl7_error("Not enough OBX segments for template metadata (need at least 6)")
        return
    print(f"Found {len(obx_segments)} total OBX segments")

    def find_obx_value(predicate):
        for seg in obx_segments:
            fields = seg.split("|")
            oid = get_field(fields, 3)
            if predicate(oid):
                return get_field(fields, 5)
        return ""

    template_source = find_obx_value(
        lambda oid: "60573-3" in oid
        and ("Report Template Source" in oid or "Report template source" in oid)
    )
    template_id = find_obx_value(
        lambda oid: "60572-5" in oid
        and ("Report Template ID" in oid or "Report template ID" in oid)
    )
    template_version = find_obx_value(
        lambda oid: "60574-1" in oid
        and ("Report Template Version ID" in oid or "Report template version ID" in oid)
    )
    tumor_site = _null_if_blank(
        find_obx_value(
            lambda oid: "Tumor Site" in oid
            or "22371.100004300" in oid
            or "2118.1000043" in oid
        )
    )
    procedure_type = _null_if_blank(
        find_obx_value(
            lambda oid: "Procedure" in oid
            or "51121.100004300" in oid
            or "820603.1000043" in oid
        )
    )
    specimen_laterality = _null_if_blank(
        find_obx_value(
            lambda oid: "Tumor Focality" in oid
            or "8722.100004300" in oid
            or "Specimen Laterality" in oid
            or "52756.1000043" in oid
        )
    )
    report_narrative = _null_if_blank(
        find_obx_value(lambda oid: "2168.1000043" in oid or "Comment" in oid)
    )

    template_instance_guid = str(uuid.uuid4())

    # Re-import policy: never dedup -- always insert -- but flag collisions so
    # duplicate synoptic reports (same OBR accession) are queryable.
    first_seen_report_id = (
        find_first_sdc_report_by_accession(cursor, report_accession)
        if report_accession
        else None
    )
    is_duplicate_accession = first_seen_report_id is not None
    if is_duplicate_accession:
        print(
            f"Duplicate synoptic report accession '{report_accession}' "
            f"(first seen sdc_report_id {first_seen_report_id}); inserting and flagging."
        )

    sdc_report_id = create_sdc_report(
        cursor=cursor,
        template_name=template_id,
        template_version=template_version,
        template_instance_guid=template_instance_guid,
        person_id=person_id,
        report_text=report_narrative,
        report_template_source=_null_if_blank(template_source),
        report_template_id=_null_if_blank(template_id),
        report_template_version_id=_null_if_blank(template_version),
        tumor_site=tumor_site,
        procedure_type=procedure_type,
        specimen_laterality=specimen_laterality,
        report_accession=report_accession,
        report_loinc=report_loinc,
        is_duplicate_accession=is_duplicate_accession,
        first_seen_report_id=first_seen_report_id,
    )

    # Process OBX segments for ECP data (starting from the 4th OBX). CAP messages use
    # OBX-4 to connect a coded selection with its numeric or text companion, so stage
    # one logical captured value per normalized item/sub-ID group.
    captured_values: list[dict[str, Any]] = []
    active_groups: dict[tuple[int, str], dict[str, Any]] = {}
    for i in range(3, len(obx_segments)):
        obx_fields = obx_segments[i].split("|")
        obx_value_type = get_field(obx_fields, 2)
        obx_observation_id = get_field(obx_fields, 3)
        obx_sub_id = _normalize_obx_sub_id(get_field(obx_fields, 4))
        obx_value = get_field(obx_fields, 5)
        obx_units = _null_if_blank(get_field(obx_fields, 6))
        observation_date = (
            _parse_hl7_date(get_field(obx_fields, 14)) or report_observation_date
        )

        # Skip long narrative text (focus on structured ECP data).
        if obx_value_type == "ST" and len(obx_value) > 200:
            continue

        question_parts = obx_observation_id.split("^")
        question_identifier = question_parts[0] if question_parts else obx_observation_id
        numeric_value = None
        cwe_code = None
        text_value = None
        component_key = "value_text"

        if obx_value_type == "NM":
            numeric_value = _numeric_value(obx_value)
            if numeric_value is not None:
                component_key = "value_num"
            else:
                text_value = _null_if_blank(obx_value)
                logger.warning(
                    "preserving non-numeric NM value %r as text for %r",
                    obx_value,
                    obx_observation_id,
                )
        elif obx_value_type == "CWE":
            # Parse CWE: code^text^codingSystem^...
            if obx_value:
                cwe_code = _null_if_blank(obx_value.split("^")[0])
                if cwe_code is None:
                    text_value = _null_if_blank(obx_value)
                else:
                    component_key = "value_code"
        elif obx_value_type == "ST":
            # Some feeds encode numeric values in ST; treat as numeric when parsable.
            numeric_value = _numeric_value(obx_value)
            if numeric_value is not None:
                component_key = "value_num"
            else:
                text_value = _null_if_blank(obx_value)
        else:
            text_value = _null_if_blank(obx_value)

        item_num_text = question_identifier.split(".")[0]
        try:
            item_num = int(item_num_text)
        except ValueError:
            logger.warning(
                "skipping OBX with non-integer item number: "
                "obx_observation_id=%r (parsed %r)",
                obx_observation_id,
                item_num_text,
            )
            continue

        if obx_sub_id is None:
            # A blank OBX-4 cannot be grouped, so each one stands alone.
            captured = _new_captured_value(item_num, None, observation_date)
            captured_values.append(captured)
        else:
            group_key = (item_num, obx_sub_id)
            current = active_groups.get(group_key)
            repeats_component = (
                current is not None and current[component_key] is not None
            )
            if current is None or repeats_component:
                if repeats_component:
                    logger.warning(
                        "repeated %s component for item %s, OBX-4 %r; "
                        "starting another captured-value occurrence",
                        component_key,
                        item_num,
                        obx_sub_id,
                    )
                captured = _new_captured_value(item_num, obx_sub_id, observation_date)
                active_groups[group_key] = captured
                captured_values.append(captured)
            else:
                captured = current

        if captured["observation_date"] is None:
            captured["observation_date"] = observation_date
        if captured["value_unit_source"] is None:
            captured["value_unit_source"] = obx_units
        if component_key == "value_code":
            captured["value_code"] = cwe_code
        elif component_key == "value_num":
            captured["value_num"] = numeric_value
        else:
            captured["value_text"] = text_value

    for captured in captured_values:
        create_naaccr_value(
            cursor=cursor,
            person_id=person_id or 0,
            episode_key=report_accession if report_accession else template_instance_guid,
            report_accession=report_accession,
            item_num=captured["item_num"],
            obx_sub_id=captured["obx_sub_id"],
            value_code=captured["value_code"],
            value_num=captured["value_num"],
            value_text=captured["value_text"],
            value_unit_source=captured["value_unit_source"],
            observation_date=(
                captured["observation_date"].isoformat()
                if captured["observation_date"]
                else None
            ),
            sdc_report_id=sdc_report_id,
        )

    print(
        f"Successfully imported NAACCR V2 message with {len(captured_values)} "
        "logical ECP values"
    )
