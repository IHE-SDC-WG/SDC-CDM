#!/usr/bin/env python3
"""CCR_LabReportECP parser and three-schema ingestion tests."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ccr_labreport_to_naaccr import (
    build_import_payload,
    build_test_output,
    import_rows,
    parse_obx_segments,
    process_row,
)  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]

SAMPLE_OBX_JSON = json.dumps(
    [
        {
            "0": "OBX",
            "1": "1",
            "2": "ST",
            "3": "60573-3^Report template source^LN",
            "5": "CAP Cancer Protocols",
            "11": "C",
            "14": "20250918102100",
            "15": "ST JUDE MEDICAL CENTER^05D0576873^CLIA",
        },
        {
            "0": "OBX",
            "1": "2",
            "2": "CWE",
            "3": "60572-5^Report template ID^LN",
            "5": "189.100004300^INVASIVE CARCINOMA OF THE BREAST: Resection^CAPECC",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "3",
            "2": "ST",
            "3": "60574-1^Report template version ID^LN",
            "5": "4.010.001.REL",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "4",
            "2": "CWE",
            "3": "58807.100004300^Procedure^CAPECC",
            "5": "40307.100004300^Excision (less than total mastectomy)^CAPECC",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "5",
            "2": "ST",
            "3": "30148.100004300^Tumor Size^CAPECC",
            "4": "31357",
            "5": "45",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "6",
            "2": "NM",
            "3": "43798.100004300^Ki-67 Percentage of Positive Nuclei^CAPECC",
            "5": "10",
            "6": "^^UCUM",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "7",
            "2": "ST",
            "3": "351700.100004300^Margin Comment^CAPECC",
            "5": "All other margins >3 mm",
            "11": "C",
            "14": "20250918102100",
        },
        {
            "0": "OBX",
            "1": "8",
            "2": "ST",
            "3": "NOT-AN-ITEM^Unsupported identifier^LOCAL",
            "5": "answer",
            "11": "C",
        },
        {
            "0": "OBX",
            "1": "9",
            "2": "ST",
            "3": "2168.1000043^Comment^CAPECC",
            "5": "x" * 201,
            "11": "C",
        },
    ]
)


def sample_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": 1001,
        "sending_lab": "ST JUDE MEDICAL CENTER",
        "date_of_diagnosis_yyyy": 2025,
        "date_of_diagnosis_mm": 9,
        "ReporttemplateID": "189.100004300",
        "ReportTemplateVersionID": "4.010.001.REL",
        "OBXCAPECPSegment": SAMPLE_OBX_JSON,
        "PatientID": 123,
        "CTCID": "CASE-7",
    }
    row.update(overrides)
    return row


class FakeCursor:
    def __init__(
        self,
        *,
        person_ids: set[Any] | None = None,
        imported_guids: set[str] | None = None,
        fail_naaccr_insert: bool = False,
    ) -> None:
        self.person_ids = {123} if person_ids is None else person_ids
        self.imported_guids = imported_guids or set()
        self.fail_naaccr_insert = fail_naaccr_insert
        self.queries: list[tuple[str, tuple[Any, ...]]] = []
        self._result: tuple[Any, ...] | None = None
        self.closed = False

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        normalized = " ".join(query.split()).lower()
        params = tuple(params)
        self.queries.append((normalized, params))
        self._result = None

        if "from omop.person" in normalized:
            self._result = (1,) if params[0] in self.person_ids else None
        elif "from sdc.sdc_report" in normalized:
            self._result = (1,) if params[0] in self.imported_guids else None
        elif "output inserted.sdc_report_id" in normalized:
            self._result = (41,)
        elif (
            normalized.startswith("insert into naaccr.naaccr_value")
            and self.fail_naaccr_insert
        ):
            raise RuntimeError("forced NAACCR insert failure")
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._result
        self._result = None
        return result

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _value_for(payload: dict[str, Any], item_num: int) -> dict[str, Any]:
    matches = [
        value for value in payload["values"] if value["item_num"] == item_num
    ]
    assert len(matches) == 1, item_num
    return matches[0]


def test_parser_and_naaccr_staging_transform() -> None:
    obxs = parse_obx_segments(SAMPLE_OBX_JSON)
    assert len(obxs) == 9
    assert all(obx.is_metadata for obx in obxs[:3])
    assert obxs[0].performing_org == "ST JUDE MEDICAL CENTER"
    assert obxs[4].observation_sub_id == "31357"
    assert obxs[5].units == "^^UCUM"
    assert obxs[5].observation_datetime is not None
    assert obxs[5].observation_datetime.date().isoformat() == "2025-09-18"

    payload = build_import_payload(sample_row())
    report = payload["report"]
    assert report["report_accession"] == "1001"
    assert report["template_instance_guid"] == "CCR_LabReportECP:1001"
    assert report["template_name"] == "189.100004300"
    assert report["template_version"] == "4.010.001.REL"
    assert report["report_template_source"] == "CAP Cancer Protocols"
    assert report["report_template_id"].startswith("189.100004300^")
    assert report["report_loinc"] == "60568-3"
    assert report["procedure_type"].startswith("40307.100004300^")
    assert report["report_text"] == "All other margins >3 mm"

    assert len(payload["values"]) == 4
    assert payload["metadata_skipped"] == 3
    assert payload["narrative_skipped"] == 1
    assert payload["invalid_item_skipped"] == 1
    assert {value["episode_key"] for value in payload["values"]} == {"CASE-7"}
    assert all(value["sdc_report_id"] is None for value in payload["values"])
    assert all(value["schema_id_number"] is None for value in payload["values"])
    assert all(value["dd_version_id"] is None for value in payload["values"])

    procedure = _value_for(payload, 58807)
    assert procedure["value_code"] == "40307.100004300"
    assert procedure["value_num"] is None
    assert procedure["observation_date"].isoformat() == "2025-09-18"

    tumor_size = _value_for(payload, 30148)
    assert tumor_size["value_num"] == 45.0
    assert tumor_size["value_code"] is None

    ki67 = _value_for(payload, 43798)
    assert ki67["value_num"] == 10.0
    assert ki67["value_unit_source"] == "^^UCUM"

    margin_comment = _value_for(payload, 351700)
    assert margin_comment["value_code"] == "All other margins >3 mm"


def test_nested_parser_tracks_groups() -> None:
    nested_json = json.dumps(
        [
            [
                {
                    "1": "1",
                    "2": "ST",
                    "3": "60573-3^Report template source^LN",
                    "5": "CAP Cancer Protocols",
                }
            ],
            [],
            [
                {
                    "1": "2",
                    "2": "NM",
                    "3": "43798.100004300^Ki-67^CAPECC",
                    "5": "25",
                    "6": "^^UCUM",
                    "14": "20250101120000",
                    "15": "SOME LAB^12345^CLIA",
                }
            ],
        ]
    )
    obxs = parse_obx_segments(nested_json)
    assert [obx.group_index for obx in obxs] == [0, 2]
    assert obxs[1].performing_org == "SOME LAB"
    assert obxs[1].units == "^^UCUM"


def test_missing_person_dry_run_and_deterministic_rerun() -> None:
    missing_cursor = FakeCursor(person_ids=set())
    missing = process_row(missing_cursor, sample_row(), dry_run=True)
    assert missing["missing_persons"] == 1
    assert missing["reports"] == 0

    imported_cursor = FakeCursor(
        imported_guids={"CCR_LabReportECP:1001"}
    )
    imported = process_row(imported_cursor, sample_row(), dry_run=True)
    assert imported["already_imported"] == 1
    assert imported["reports"] == 0

    dry_cursor = FakeCursor()
    dry_run = process_row(dry_cursor, sample_row(), dry_run=True)
    assert dry_run["reports"] == 1
    assert dry_run["naaccr_values"] == 4
    assert not any(
        query.startswith("insert into")
        for query, _ in dry_cursor.queries
    )


def test_json_preview_uses_three_schema_resources() -> None:
    output = build_test_output(FakeCursor(), [sample_row()])
    assert "pending_reference_data" not in output
    assert output["summary"]["reports"] == 1
    assert output["summary"]["naaccr_values"] == 4
    assert output["rows"][0]["status"] == "ready"
    tables = [
        resource["table"]
        for resource in output["rows"][0]["resources"]
    ]
    assert tables[0] == "sdc_report"
    assert tables.count("sdc_report") == 1
    assert tables.count("naaccr_value") == 4


def test_json_preview_reports_missing_person_ids() -> None:
    output = build_test_output(
        FakeCursor(person_ids=set()),
        [sample_row(PatientID=987), sample_row(record_id=1002, PatientID=None)],
    )
    assert output["summary"]["missing_persons"] == 2
    assert output["summary"]["missing_person_ids"] == [987, None]
    assert output["rows"][0]["status"] == "missing_person"
    assert output["rows"][0]["resources"] == []
    assert output["rows"][1]["status"] == "missing_person"
    assert output["rows"][1]["resources"] == []


def test_sqlserver_writer_links_values_to_inserted_report() -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    totals = import_rows(connection, [sample_row()], batch_size=100)

    assert totals["reports"] == 1
    assert totals["naaccr_values"] == 4
    assert connection.commits == 1
    assert connection.rollbacks == 0

    report_inserts = [
        params
        for query, params in cursor.queries
        if query.startswith("insert into sdc.sdc_report")
    ]
    value_inserts = [
        params
        for query, params in cursor.queries
        if query.startswith("insert into naaccr.naaccr_value")
    ]
    assert len(report_inserts) == 1
    assert len(value_inserts) == 4
    assert {params[2] for params in value_inserts} == {41}


def test_failed_value_insert_rolls_back_current_batch() -> None:
    cursor = FakeCursor(fail_naaccr_insert=True)
    connection = FakeConnection(cursor)
    try:
        import_rows(connection, [sample_row()], batch_size=1)
    except RuntimeError as error:
        assert str(error) == "forced NAACCR insert failure"
    else:
        raise AssertionError("forced insert failure did not propagate")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert cursor.closed


def _exec_script(connection: sqlite3.Connection, relative_path: str) -> None:
    connection.executescript((ROOT / relative_path).read_text())


def _sqlite_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _insert_sqlite(
    connection: sqlite3.Connection,
    table: str,
    resource: dict[str, Any],
) -> int:
    columns = tuple(resource)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(_sqlite_value(resource[column]) for column in columns),
    )
    return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_transformed_ccr_payload_bridges_to_omop(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "control.db")
    connection.executescript(
        f"""
        ATTACH DATABASE '{tmp_path / "omop.db"}' AS omop;
        ATTACH DATABASE '{tmp_path / "naaccr.db"}' AS naaccr;
        ATTACH DATABASE '{tmp_path / "sdc.db"}' AS sdc;
        """
    )
    _exec_script(
        connection,
        "database/schemas/omop/ddl/sqlite/1_OMOPCDM_sqlite_5.4_ddl.sql",
    )
    _exec_script(
        connection,
        "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql",
    )
    _exec_script(
        connection,
        "database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql",
    )
    connection.executescript(
        """
        INSERT INTO omop.concept (
            concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
            concept_code, valid_start_date, valid_end_date
        )
        VALUES
            (0, 'Unknown', 'Metadata', 'None', 'None', '0', '1970-01-01', '2099-12-31'),
            (32817, 'EHR', 'Type Concept', 'Type Concept', 'Type Concept', 'EHR', '1970-01-01', '2099-12-31'),
            (32879, 'Registry', 'Type Concept', 'Type Concept', 'Type Concept', 'Registry', '1970-01-01', '2099-12-31'),
            (1147289, 'note.note_id', 'Metadata', 'CDM', 'Field', 'note.note_id', '1970-01-01', '2099-12-31');

        INSERT INTO omop.person (
            person_id, gender_concept_id, year_of_birth, race_concept_id,
            ethnicity_concept_id, person_source_value
        )
        VALUES (123, 0, 1970, 0, 0, 'patient-123');
        """
    )

    payload = build_import_payload(sample_row())
    report_id = _insert_sqlite(connection, "sdc.sdc_report", payload["report"])
    for value in payload["values"]:
        _insert_sqlite(
            connection,
            "naaccr.naaccr_value",
            dict(value, sdc_report_id=report_id),
        )

    _exec_script(
        connection,
        "database/etl/sqlite/1_naaccr_sdc_to_omop.sql",
    )
    assert connection.execute(
        "SELECT note_source_value FROM omop.note"
    ).fetchall() == [("1001",)]
    assert connection.execute(
        "SELECT COUNT(*) FROM omop.measurement"
    ).fetchone()[0] == 4
    assert connection.execute(
        """
        SELECT value_as_number, unit_source_value, measurement_type_concept_id
        FROM omop.measurement
        WHERE measurement_source_value = '43798'
        """
    ).fetchone() == (10.0, "^^UCUM", 32879)
    connection.close()


if __name__ == "__main__":
    import tempfile

    test_parser_and_naaccr_staging_transform()
    test_nested_parser_tracks_groups()
    test_missing_person_dry_run_and_deterministic_rerun()
    test_json_preview_uses_three_schema_resources()
    test_json_preview_reports_missing_person_ids()
    test_sqlserver_writer_links_values_to_inserted_report()
    test_failed_value_insert_rolls_back_current_batch()
    with tempfile.TemporaryDirectory() as temp_dir:
        test_transformed_ccr_payload_bridges_to_omop(Path(temp_dir))
    print("CCR NAACCR-first ingestion tests passed")
