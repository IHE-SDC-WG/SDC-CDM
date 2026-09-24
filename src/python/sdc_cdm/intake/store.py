"""Persist exact bytes before parsing and retain every ordered report envelope."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend


@dataclass(frozen=True)
class IntakeResult:
    inbound_message_id: int
    envelope_count: int
    parse_status: str
    is_content_duplicate: bool


def _insert_id(backend: DatabaseBackend, table: str, columns: tuple[str, ...], values: tuple[Any, ...]) -> int:
    markers = ", ".join("?" for _ in values)
    names = ", ".join(columns)
    if backend.dialect == "sqlite":
        sql = f"INSERT INTO intake.{table} ({names}) VALUES ({markers}) RETURNING {table}_id"
    else:
        sql = f"INSERT INTO intake.{table} ({names}) OUTPUT INSERTED.{table}_id VALUES ({markers})"
    row = backend.fetch_one(sql, values)
    if row is None:
        raise RuntimeError(f"no identifier returned for intake.{table}")
    return int(row[0])


def _diagnostic(backend: DatabaseBackend, message_id: int, severity: str, code: str, detail: str) -> None:
    backend.execute_uncommitted(
        "INSERT INTO intake.inbound_message_diagnostic "
        "(inbound_message_id, severity, code, detail) VALUES (?, ?, ?, ?)",
        (message_id, severity, code, detail),
    )


def ingest_message(
    backend: DatabaseBackend,
    raw: bytes,
    parser: Callable[[bytes], list[dict[str, Any]]],
    *,
    parser_name: str,
    parser_version: str,
    media_type: str = "application/hl7-v2+er7",
    received_by: str | None = None,
) -> IntakeResult:
    """Record an intake event, then parse it; failures remain stored for review.

    The first transaction commits the byte stream before invoking the parser.
    Parser `ValueError`s are recorded as failed parses. Other exceptions remain
    visible to the caller without deleting the raw intake event.
    """

    sha = hashlib.sha256(raw).hexdigest()
    with backend.transaction():
        candidates = backend.fetch_all(
            "SELECT inbound_message_id, raw_blob FROM intake.inbound_message "
            "WHERE raw_sha256 = ? ORDER BY inbound_message_id",
            (sha,),
        )
        first_id = next((int(row[0]) for row in candidates if bytes(row[1]) == raw), None)
        message_id = _insert_id(
            backend,
            "inbound_message",
            ("source_format", "media_type", "raw_blob", "raw_sha256", "byte_length",
             "is_content_duplicate", "first_seen_inbound_message_id", "received_by",
             "parser_name", "parser_version"),
            ("hl7v2", media_type, raw, sha, len(raw), int(first_id is not None),
             first_id, received_by, parser_name, parser_version),
        )
        if first_id is not None:
            _diagnostic(backend, message_id, "info", "DUPLICATE_BYTES", f"same bytes as intake {first_id}")

    try:
        envelopes = parser(raw)
        if not envelopes:
            raise ValueError("parser produced no report envelopes")
        for ordinal, envelope in enumerate(envelopes, 1):
            source = envelope.get("source", {})
            info = envelope.get("raw", {})
            if source.get("obr_ordinal") != ordinal or info.get("sha256") != sha or info.get("byte_length") != len(raw):
                raise ValueError(f"envelope {ordinal} does not match source bytes or OBR order")
    except ValueError as exc:
        with backend.transaction():
            backend.execute_uncommitted(
                "UPDATE intake.inbound_message SET parse_status = 'failed', parse_error = ? "
                "WHERE inbound_message_id = ?", (str(exc), message_id),
            )
            _diagnostic(backend, message_id, "error", "PARSE_FAILED", str(exc))
        return IntakeResult(message_id, 0, "failed", first_id is not None)

    first = envelopes[0]
    source = first["source"]
    with backend.transaction():
        backend.execute_uncommitted(
            "UPDATE intake.inbound_message SET parse_status = 'parsed', "
            "message_control_id = ?, sending_facility = ?, message_profile = ? "
            "WHERE inbound_message_id = ?",
            (source.get("message_control_id"), source.get("sending_facility"),
             source.get("message_profile"), message_id),
        )
        for ordinal, envelope in enumerate(envelopes, 1):
            serialized = json.dumps(envelope, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
            backend.execute_uncommitted(
                "INSERT INTO intake.inbound_envelope "
                "(inbound_message_id, ordinal, envelope_json, envelope_version) "
                "VALUES (?, ?, ?, ?)",
                (message_id, ordinal, serialized, envelope["envelope_version"]),
            )
            for diagnostic in envelope.get("diagnostics", []):
                _diagnostic(backend, message_id, diagnostic["severity"], diagnostic["code"],
                            f"OBR {ordinal}: {diagnostic['detail']}")
        patient = first["patient"]
        authority = patient.get("assigning_authority") or ""
        source_id = patient["person_source_value"]
        if backend.fetch_one(
            "SELECT patient_id FROM intake.patient WHERE assigning_authority = ? "
            "AND person_source_value = ?", (authority, source_id),
        ) is None:
            birth = patient.get("birth_date") or {}
            backend.execute_uncommitted(
                "INSERT INTO intake.patient (person_source_value, assigning_authority, "
                "birth_year, birth_month, birth_day, gender_source_value, "
                "first_seen_inbound_message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, authority, birth.get("y"), birth.get("m"), birth.get("d"),
                 patient.get("gender"), message_id),
            )
    return IntakeResult(message_id, len(envelopes), "parsed", first_id is not None)
