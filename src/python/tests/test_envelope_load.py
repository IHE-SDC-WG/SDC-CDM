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
SYNTHETIC = (ROOT / "contracts/fixtures/two-obr-synthetic.hl7").read_bytes()
ADRENAL = (ROOT / "sample_data/naaccr_v2/obx-Adrenal.hl7").read_bytes()


def _ingest(backend: SQLiteBackend, raw: bytes) -> int:
    return ingest_message(backend, raw, parse_hl7,
                          parser_name="sdc-cdm-hl7v2", parser_version="1").inbound_message_id


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
