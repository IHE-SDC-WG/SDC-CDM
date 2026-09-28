from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.intake import episode_key, ingest_message, load_message


ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC = (ROOT / "sample_data/naaccr_v2/two-obr-synthetic.hl7").read_bytes()
ADRENAL = (ROOT / "sample_data/naaccr_v2/obx-Adrenal.hl7").read_bytes()


ADRENAL_TUMOR_SIZE_OBX = (
    b"OBX|10|NM|2129.1000043^Tumor Size (Notes E, F)^CAPECC|+2131.1000043|10|cm^CentiMeter^UCUM"
)
SYNTHETIC_NARRATIVE_OBX = b"OBX|1|TX|22637-3^Path report.final diagnosis^LN|1|Synthetic diagnosis"

# The walk from a loaded row to the exact source bytes, using only the row's own column.
VALUE_SOURCE = (
    "SELECT m.raw_blob FROM naaccr.naaccr_value v "
    "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id "
    "JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id "
    "WHERE e.inbound_message_id = ? AND v.ecp_code = ? AND v.value_num IS NOT NULL"
)
REPORT_SOURCE = (
    "SELECT m.raw_blob FROM sdc.sdc_report r "
    "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id "
    "JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id "
    "WHERE e.inbound_message_id = ? AND r.report_text IS NOT NULL"
)
# Rows of the given messages whose column is missing or disagrees with the load ledger.
LEDGER_MISMATCHES = (
    "SELECT "
    "(SELECT COUNT(*) FROM intake.envelope_value ev "
    " JOIN intake.inbound_envelope e ON e.inbound_envelope_id = ev.inbound_envelope_id "
    " JOIN naaccr.naaccr_value v ON v.naaccr_value_id = ev.naaccr_value_id "
    " WHERE e.inbound_message_id IN (?, ?) "
    " AND (v.inbound_envelope_id IS NULL OR v.inbound_envelope_id <> ev.inbound_envelope_id)), "
    "(SELECT COUNT(*) FROM intake.envelope_load l "
    " JOIN intake.inbound_envelope e ON e.inbound_envelope_id = l.inbound_envelope_id "
    " JOIN sdc.sdc_report r ON r.sdc_report_id = l.sdc_report_id "
    " WHERE e.inbound_message_id IN (?, ?) "
    " AND (r.inbound_envelope_id IS NULL OR r.inbound_envelope_id <> l.inbound_envelope_id))"
)


def _ingest(backend: SQLiteBackend, raw: bytes) -> int:
    return ingest_message(backend, raw, parse_hl7,
                          parser_name="sdc-cdm-hl7v2", parser_version="1").inbound_message_id


def _assert_provenance_walk(backend: SQLiteBackend | SqlServerBackend,
                            synthetic_id: int, adrenal_id: int) -> None:
    value_blobs = backend.fetch_all(VALUE_SOURCE, (adrenal_id, "2129.1000043"))
    assert len(value_blobs) == 1 and ADRENAL_TUMOR_SIZE_OBX in bytes(value_blobs[0][0])
    report_blobs = backend.fetch_all(REPORT_SOURCE, (synthetic_id,))
    assert len(report_blobs) == 1 and SYNTHETIC_NARRATIVE_OBX in bytes(report_blobs[0][0])
    ids = (synthetic_id, adrenal_id, synthetic_id, adrenal_id)
    assert tuple(backend.fetch_one(LEDGER_MISMATCHES, ids)) == (0, 0)


def test_episode_source_accession_and_message_fallbacks() -> None:
    envelope = parse_hl7(SYNTHETIC)[0]
    assert episode_key(envelope) == "a:" + hashlib.sha256(b"SYN-ACC-1").hexdigest()
    envelope["episode"] = {
        "assigning_authority": "SYNTHLAB", "episode_source_value": "EP-1", "sequence_number": 2,
    }
    assert episode_key(envelope) == "e:" + hashlib.sha256(b"SYNTHLAB\x1fEP-1\x1f2").hexdigest()
    del envelope["episode"]
    envelope["report"]["accession"] = None
    assert episode_key(envelope) == "m:" + hashlib.sha256(SYNTHETIC).hexdigest()


def test_two_reports_narrative_values_provenance_and_duplicate_bytes(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "load.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version "
            "(algorithm, version) VALUES (?, ?)", ("TEST_PHASE3", "1"),
        )
        first_id = _ingest(backend, SYNTHETIC)
        duplicate_id = _ingest(backend, SYNTHETIC)
        assert load_message(backend, first_id, algorithm="TEST_PHASE3").report_count == 2
        assert load_message(backend, first_id, algorithm="TEST_PHASE3").report_count == 0
        assert load_message(backend, duplicate_id, algorithm="TEST_PHASE3").skipped_duplicate_messages == 1
        reports = backend.fetch_all(
            "SELECT sdc_report_id, report_loinc, report_text FROM sdc.sdc_report "
            "ORDER BY sdc_report_id"
        )
        assert len(reports) == 2
        assert [row[1] for row in reports] == ["35265-8", "60569-1"]
        assert reports[0][2] == "Synthetic diagnosis\nsecond line"
        assert reports[1][2] is None
        values = backend.fetch_all(
            "SELECT sdc_report_id, episode_key, dd_version_id FROM naaccr.naaccr_value"
        )
        assert len(values) == 1
        assert values[0][0] == reports[1][0]
        assert values[0][1] == "a:" + hashlib.sha256(b"SYN-ACC-1").hexdigest()
        assert values[0][2] is not None
        provenance = backend.fetch_all(
            "SELECT l.sdc_report_id, e.ordinal FROM intake.envelope_load l "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = l.inbound_envelope_id "
            "ORDER BY e.ordinal"
        )
        assert provenance == [(reports[0][0], 1), (reports[1][0], 2)]
        assert backend.fetch_one("SELECT COUNT(*) FROM intake.envelope_value")[0] == 1
        assert backend.fetch_one("SELECT COUNT(*) FROM sdc.sdc_form_answer")[0] == 0
        assert backend.fetch_one("SELECT COUNT(*) FROM sdc.template_instance")[0] == 0
        assert backend.fetch_one(
            "SELECT assigning_authority, person_source_value, birth_year, gender_source_value "
            "FROM intake.patient"
        ) == ("SYNTHLAB", "SYN-P001", 1957, "F")
        assert backend.fetch_one(
            "SELECT value_unit_source FROM naaccr.naaccr_value"
        )[0] == "cm"


def test_adrenal_19_values_have_dictionary_and_envelope_provenance(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "adrenal.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version "
            "(algorithm, version) VALUES (?, ?)", ("TEST_ADRENAL", "1"),
        )
        message_id = _ingest(backend, ADRENAL)
        result = load_message(backend, message_id, algorithm="TEST_ADRENAL")
        assert (result.report_count, result.value_count) == (1, 19)
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.naaccr_value "
            "WHERE dd_version_id IS NOT NULL AND episode_key IS NOT NULL"
        )[0] == 19
        assert backend.fetch_one("SELECT COUNT(*) FROM intake.envelope_value")[0] == 19
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.naaccr_value WHERE ecp_code = '2129.1000043' "
            "AND obx_sub_id = '2131' AND value_code = '2131.1000043' AND value_num = 10"
        )[0] == 1


def test_provenance_walks_from_rows_to_originating_raw_bytes(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "provenance.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version "
            "(algorithm, version) VALUES (?, ?)", ("TEST_PROVENANCE", "1"),
        )
        synthetic_id = _ingest(backend, SYNTHETIC)
        adrenal_id = _ingest(backend, ADRENAL)
        load_message(backend, synthetic_id, algorithm="TEST_PROVENANCE")
        load_message(backend, adrenal_id, algorithm="TEST_PROVENANCE")
        _assert_provenance_walk(backend, synthetic_id, adrenal_id)
        for table in ("naaccr.naaccr_value", "sdc.sdc_report"):
            assert backend.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE inbound_envelope_id IS NULL"
            )[0] == 0


def _staging_envelope(raw: bytes) -> dict:
    envelope = parse_hl7(SYNTHETIC)[1]
    envelope["source"]["obr_ordinal"] = 1
    envelope["raw"] = {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
    envelope["values"] = [
        {"item_num": number, "value_code": code}
        for number, code in ((400, "C740"), (522, "8370"), (523, "3"), (220, "2"), (390, "20240115"))
    ]
    envelope.pop("diagnostics", None)
    return envelope


def _staging_diagnostics(backend: SQLiteBackend, message_id: int) -> list[str]:
    return [row[0] for row in backend.fetch_all(
        "SELECT detail FROM intake.inbound_message_diagnostic "
        "WHERE inbound_message_id = ? AND code = 'STAGING_SCHEMA_UNRESOLVED'", (message_id,),
    )]


def test_staging_schema_resolves_from_complete_item_inputs(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "staging.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        dd_version_id = backend.fetch_one(
            "INSERT INTO naaccr.data_dictionary_version (algorithm, version) "
            "VALUES (?, ?) RETURNING dd_version_id", ("TEST_STAGING", "1"),
        )[0]
        backend.execute(
            "INSERT INTO naaccr.staging_schema (dd_version_id, schema_id_number, schema_id) "
            "VALUES (?, ?, ?)", (dd_version_id, "00580", "adrenal_gland"),
        )
        backend.execute(
            "INSERT INTO naaccr.schema_selection_rule "
            "(dd_version_id, schema_id_number, site, histology, behavior) VALUES (?, ?, ?, ?, ?)",
            (dd_version_id, "00580", "C740", "8370", "3"),
        )
        raw = b"staging-positive"
        envelope = _staging_envelope(raw)
        message_id = ingest_message(backend, raw, lambda _: [envelope],
                                    parser_name="test", parser_version="1").inbound_message_id
        assert load_message(backend, message_id, algorithm="TEST_STAGING").value_count == 5
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.naaccr_value v JOIN naaccr.staging_schema s "
            "ON s.dd_version_id = v.dd_version_id AND s.schema_id_number = v.schema_id_number "
            "WHERE s.schema_id = 'adrenal_gland'"
        )[0] == 5
        assert _staging_diagnostics(backend, message_id) == []


def test_staging_schema_is_null_with_diagnostic_for_hl7_ecp_input(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "unresolved.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version "
            "(algorithm, version) VALUES (?, ?)", ("TEST_UNRESOLVED", "1"),
        )
        message_id = _ingest(backend, SYNTHETIC)
        load_message(backend, message_id, algorithm="TEST_UNRESOLVED")
        assert backend.fetch_all("SELECT schema_id_number FROM naaccr.naaccr_value") == [(None,)]
        details = _staging_diagnostics(backend, message_id)
        assert len(details) == 1 and details[0].startswith("OBR 2:")


def test_sqlserver_two_obr_and_19_value_load() -> None:
    connection_string = os.environ.get("SDC_CDM_SQLSERVER_CONNECTION_STRING")
    if not connection_string:
        pytest.skip("SDC_CDM_SQLSERVER_CONNECTION_STRING is not set")
    with SqlServerBackend(connection_string) as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version (algorithm, version) "
            "VALUES (?, ?)", ("TEST_PHASE3_SQLSERVER", "1"),
        )
        synthetic_id = ingest_message(
            backend, SYNTHETIC, parse_hl7, parser_name="test", parser_version="1"
        ).inbound_message_id
        adrenal_id = ingest_message(
            backend, ADRENAL, parse_hl7, parser_name="test", parser_version="1"
        ).inbound_message_id
        two = load_message(backend, synthetic_id, algorithm="TEST_PHASE3_SQLSERVER")
        adrenal = load_message(backend, adrenal_id, algorithm="TEST_PHASE3_SQLSERVER")
        assert (two.report_count, two.value_count) == (2, 1)
        assert (adrenal.report_count, adrenal.value_count) == (1, 19)
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM intake.envelope_value ev "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = ev.inbound_envelope_id "
            "WHERE e.inbound_message_id IN (?, ?)", (synthetic_id, adrenal_id),
        )[0] == 20
        _assert_provenance_walk(backend, synthetic_id, adrenal_id)
