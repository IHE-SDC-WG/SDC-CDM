from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.intake import ingest_message


ROOT = Path(__file__).resolve().parents[3]
RAW = (ROOT / "contracts/fixtures/two-obr-synthetic.hl7").read_bytes()
GOLDENS = [
    json.loads((ROOT / f"contracts/golden/two-obr-synthetic.{i}.envelope.json").read_text())
    for i in (1, 2)
]


def _backend(tmp_path: Path) -> SQLiteBackend:
    backend = SQLiteBackend(tmp_path / "intake.db")
    BuildRunner(load_manifest(), backend).run()
    return backend


def test_exact_bytes_envelopes_duplicate_flag_and_diagnostics(tmp_path: Path) -> None:
    with _backend(tmp_path) as backend:
        first = ingest_message(backend, RAW, lambda _: GOLDENS,
                               parser_name="test", parser_version="1")
        again = ingest_message(backend, RAW, lambda _: GOLDENS,
                               parser_name="test", parser_version="1")
        assert (first.envelope_count, again.envelope_count) == (2, 2)
        assert not first.is_content_duplicate and again.is_content_duplicate
        rows = backend.fetch_all(
            "SELECT inbound_message_id, raw_blob, raw_sha256, byte_length, "
            "first_seen_inbound_message_id, parse_status FROM intake.inbound_message "
            "ORDER BY inbound_message_id"
        )
        assert len(rows) == 2
        assert all(bytes(row[1]) == RAW and row[2] == hashlib.sha256(RAW).hexdigest()
                   and row[3] == len(RAW) and row[5] == "parsed" for row in rows)
        assert rows[1][4] == rows[0][0]
        envelopes = backend.fetch_all(
            "SELECT inbound_message_id, ordinal, envelope_json FROM intake.inbound_envelope "
            "ORDER BY inbound_envelope_id"
        )
        assert [(row[0], row[1]) for row in envelopes] == [
            (first.inbound_message_id, 1), (first.inbound_message_id, 2),
            (again.inbound_message_id, 1), (again.inbound_message_id, 2),
        ]
        assert json.loads(envelopes[0][2]) == GOLDENS[0]
        assert backend.fetch_one("SELECT COUNT(*) FROM intake.patient")[0] == 1
        assert backend.fetch_one(
            "SELECT code FROM intake.inbound_message_diagnostic "
            "WHERE inbound_message_id = ?", (again.inbound_message_id,)
        )[0] == "DUPLICATE_BYTES"


def test_failed_parse_keeps_raw_bytes(tmp_path: Path) -> None:
    with _backend(tmp_path) as backend:
        def fail(_: bytes) -> list[dict]:
            raise ValueError("missing OBR")

        result = ingest_message(backend, b"invalid\x00", fail,
                                parser_name="test", parser_version="1")
        assert result.parse_status == "failed"
        row = backend.fetch_one(
            "SELECT raw_blob, parse_error FROM intake.inbound_message "
            "WHERE inbound_message_id = ?", (result.inbound_message_id,)
        )
        assert bytes(row[0]) == b"invalid\x00"
        assert row[1] == "missing OBR"
        assert backend.fetch_one("SELECT COUNT(*) FROM intake.inbound_envelope")[0] == 0
        assert backend.fetch_one("SELECT code FROM intake.inbound_message_diagnostic")[0] == "PARSE_FAILED"


def test_patient_key_is_authority_qualified(tmp_path: Path) -> None:
    with _backend(tmp_path) as backend:
        for authority in ("HOSPITAL-A", "HOSPITAL-B"):
            raw = authority.encode()
            envelope = json.loads(json.dumps(GOLDENS[0]))
            envelope["raw"]["sha256"] = hashlib.sha256(raw).hexdigest()
            envelope["raw"]["byte_length"] = len(raw)
            envelope["patient"]["assigning_authority"] = authority
            ingest_message(backend, raw, lambda _, value=envelope: [value],
                           parser_name="test", parser_version="1")
        rows = backend.fetch_all(
            "SELECT assigning_authority, person_source_value FROM intake.patient "
            "ORDER BY assigning_authority"
        )
        assert rows == [("HOSPITAL-A", "SYN-P001"), ("HOSPITAL-B", "SYN-P001")]
