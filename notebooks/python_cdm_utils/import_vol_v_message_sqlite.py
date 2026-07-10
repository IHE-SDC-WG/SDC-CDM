#!/usr/bin/env python3
"""Import a NAACCR Volume V (HL7 v2 ORU) synoptic report into the three-schema
SDC CDM.

Ported from SdcCdmLib/SdcCdm/ImportNaaccrVolV.cs. Writes:
  - omop.person          (create-or-find by source identifier)
  - sdc.sdc_report       (one synoptic report header per message)
  - naaccr.naaccr_value  (the captured answer values)

The bridge ETL (database/etl/sqlite/1_naaccr_sdc_to_omop.sql) later turns these
into stock omop.note / omop.measurement rows.
"""

import logging
import uuid
from datetime import date, datetime

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
    report_accession = (get_field(obr_fields, 3) or "").split("^")[0] or None
    report_loinc = report_type_code

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
    tumor_site = find_obx_value(
        lambda oid: "Tumor Site" in oid
        or "22371.100004300" in oid
        or "2118.1000043" in oid
    )
    procedure_type = find_obx_value(
        lambda oid: "Procedure" in oid
        or "51121.100004300" in oid
        or "820603.1000043" in oid
    )
    specimen_laterality = find_obx_value(
        lambda oid: "Tumor Focality" in oid
        or "8722.100004300" in oid
        or "Specimen Laterality" in oid
        or "52756.1000043" in oid
    )
    report_narrative = find_obx_value(
        lambda oid: "2168.1000043" in oid or "Comment" in oid
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
        report_template_source=template_source,
        report_template_id=template_id,
        report_template_version_id=template_version,
        tumor_site=tumor_site,
        procedure_type=procedure_type,
        specimen_laterality=specimen_laterality,
        report_accession=report_accession,
        report_loinc=report_loinc,
        is_duplicate_accession=is_duplicate_accession,
        first_seen_report_id=first_seen_report_id,
    )

    observation_date = date.today().isoformat()

    # Process OBX segments for ECP data (starting from the 4th OBX).
    for i in range(3, len(obx_segments)):
        obx_fields = obx_segments[i].split("|")
        obx_value_type = get_field(obx_fields, 2)
        obx_observation_id = get_field(obx_fields, 3)
        obx_value = get_field(obx_fields, 5)
        obx_units = get_field(obx_fields, 6)

        # Skip long narrative text (focus on structured ECP data).
        if obx_value_type == "ST" and len(obx_value) > 200:
            continue

        question_parts = obx_observation_id.split("^")
        question_identifier = question_parts[0] if question_parts else obx_observation_id
        response_type = "text"
        response_value = obx_value
        numeric_value = None
        cwe_code = None

        if obx_value_type == "NM":
            response_type = "numeric"
            try:
                numeric_value = float(obx_value)
            except ValueError:
                numeric_value = None
        elif obx_value_type == "CWE":
            response_type = "list_selection"
            if obx_value:
                parts = obx_value.split("^")
                cwe_code = parts[0] if len(parts) > 0 else None
        elif obx_value_type == "ST":
            try:
                numeric_value = float(obx_value)
                response_type = "numeric"
            except ValueError:
                response_type = "text"
        else:
            response_type = "text"

        item_num_text = question_identifier.split(".")[0]
        try:
            item_num = int(item_num_text)
        except ValueError:
            continue

        create_naaccr_value(
            cursor=cursor,
            person_id=person_id or 0,
            episode_key=report_accession if report_accession else template_instance_guid,
            report_accession=report_accession,
            item_num=item_num,
            value_code=None
            if response_type == "numeric"
            else (cwe_code or response_value),
            value_num=numeric_value,
            value_unit_source=obx_units,
            observation_date=observation_date,
            sdc_report_id=sdc_report_id,
        )

    print(
        f"Successfully imported NAACCR V2 message with {len(obx_segments) - 3} ECP data points"
    )
