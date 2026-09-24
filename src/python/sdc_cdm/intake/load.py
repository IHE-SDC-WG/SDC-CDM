"""Load OBR envelopes into separate SDC reports and NAACCR answers."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend


@dataclass(frozen=True)
class LoadResult:
    report_count: int
    value_count: int
    skipped_duplicate_messages: int


def episode_key(envelope: dict[str, Any]) -> str:
    episode = envelope.get("episode")
    if episode and episode.get("episode_source_value"):
        parts = (
            episode.get("assigning_authority") or "",
            episode["episode_source_value"],
            str(episode.get("sequence_number") or ""),
        )
        source = "\x1f".join(unicodedata.normalize("NFC", part) for part in parts)
        return "e:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
    accession = envelope["report"].get("accession")
    if accession:
        return "a:" + hashlib.sha256(unicodedata.normalize("NFC", accession).encode("utf-8")).hexdigest()
    return "m:" + envelope["raw"]["sha256"]


def _date_only(value: dict[str, Any] | None) -> str | None:
    """The value table carries a SQL DATE; the envelope retains exact precision and offset."""
    if not value or value.get("d") is None:
        return None
    return f"{value['y']:04d}-{value['m']:02d}-{value['d']:02d}"


def _staging_schema(backend: DatabaseBackend, envelope: dict[str, Any],
                    dd_version_id: int) -> str | None:
    """Resolve only an unambiguous exact staging rule with complete source inputs."""
    by_item = {
        row["item_num"]: row.get("value_code") or row.get("value_text") or row.get("value_num")
        for row in envelope.get("values", []) if row.get("item_num") is not None
    }
    if not all(by_item.get(number) for number in (400, 522, 523, 220, 390)):
        return None
    inputs = {
        "site": str(by_item[400]), "histology": str(by_item[522]),
        "behavior": str(by_item[523]), "sex_at_birth": str(by_item[220]),
        "year_dx": str(by_item[390])[:4],
    }
    rules = backend.fetch_all(
        "SELECT schema_id_number, site, histology, behavior, sex_at_birth, "
        "discriminator_1, discriminator_2, year_dx "
        "FROM naaccr.schema_selection_rule WHERE dd_version_id = ?", (dd_version_id,),
    )
    matches = {
        str(row[0]) for row in rules
        if row[5] is None and row[6] is None
        and all(row[index] is None or str(row[index]) == inputs[field]
                for index, field in enumerate(("site", "histology", "behavior", "sex_at_birth"), 1))
        and (row[7] is None or str(row[7]) == inputs["year_dx"])
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _report_id(backend: DatabaseBackend, envelope: dict[str, Any], envelope_id: int,
               person_id: int, duplicate: int, first_id: int | None) -> int:
    report = envelope["report"]
    guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sdc-cdm:{envelope['raw']['sha256']}:{envelope['source']['obr_ordinal']}"))
    columns = (
        "template_name", "template_version", "template_instance_guid", "person_id",
        "report_text", "report_template_source", "report_template_id",
        "report_template_version_id", "tumor_site", "procedure_type",
        "specimen_laterality", "report_accession", "report_loinc",
        "is_duplicate_accession", "first_seen_report_id",
    )
    values = (
        report.get("template_id") or report.get("report_loinc") or "unknown",
        report.get("template_version") or "",
        guid, person_id, report.get("narrative"), report.get("template_source"),
        report.get("template_id"), report.get("template_version"),
        report.get("tumor_site"), report.get("procedure"), report.get("laterality"),
        report.get("accession"), report.get("report_loinc"), duplicate, first_id,
    )
    names = ", ".join(columns)
    markers = ", ".join("?" for _ in columns)
    if backend.dialect == "sqlite":
        sql = f"INSERT INTO sdc.sdc_report ({names}) VALUES ({markers}) RETURNING sdc_report_id"
    else:
        sql = f"INSERT INTO sdc.sdc_report ({names}) OUTPUT INSERTED.sdc_report_id VALUES ({markers})"
    row = backend.fetch_one(sql, values)
    if row is None:
        raise RuntimeError(f"no sdc_report_id for envelope {envelope_id}")
    return int(row[0])


def _value_ids(backend: DatabaseBackend, envelope: dict[str, Any], person_id: int,
               report_id: int, key: str, dd_version_id: int,
               schema_id_number: str | None) -> list[int]:
    values = envelope.get("values", [])
    if not values:
        return []
    prepared = [
        {**value, "observation_date_sql": _date_only(value.get("observation_date"))}
        for value in values
    ]
    payload = json.dumps(prepared, ensure_ascii=False)
    accession = envelope["report"].get("accession")
    if backend.dialect == "sqlite":
        sql = """
            INSERT INTO naaccr.naaccr_value
                (person_id, episode_key, sdc_report_id, report_accession,
                 schema_id_number, item_num, ecp_code, obx_sub_id, value_code,
                 value_num, value_text, value_unit_source, observation_date, dd_version_id)
            SELECT ?, ?, ?, ?, ?,
                   json_extract(j.value, '$.item_num'),
                   json_extract(j.value, '$.ecp_code'),
                   json_extract(j.value, '$.obx_sub_id'),
                   json_extract(j.value, '$.value_code'),
                   CAST(json_extract(j.value, '$.value_num') AS REAL),
                   json_extract(j.value, '$.value_text'),
                   json_extract(j.value, '$.unit_source'),
                   json_extract(j.value, '$.observation_date_sql'), ?
            FROM json_each(?) AS j
            RETURNING naaccr_value_id
        """
    else:
        sql = """
            INSERT INTO naaccr.naaccr_value
                (person_id, episode_key, sdc_report_id, report_accession,
                 schema_id_number, item_num, ecp_code, obx_sub_id, value_code,
                 value_num, value_text, value_unit_source, observation_date, dd_version_id)
            OUTPUT INSERTED.naaccr_value_id
            SELECT ?, ?, ?, ?, ?,
                   j.item_num, j.ecp_code, j.obx_sub_id, j.value_code,
                   TRY_CONVERT(FLOAT, j.value_num), j.value_text, j.unit_source,
                   TRY_CONVERT(DATE, j.observation_date_sql), ?
            FROM OPENJSON(?) WITH (
                item_num INT '$.item_num',
                ecp_code NVARCHAR(50) '$.ecp_code',
                obx_sub_id NVARCHAR(255) '$.obx_sub_id',
                value_code NVARCHAR(255) '$.value_code',
                value_num NVARCHAR(100) '$.value_num',
                value_text NVARCHAR(MAX) '$.value_text',
                unit_source NVARCHAR(50) '$.unit_source',
                observation_date_sql NVARCHAR(10) '$.observation_date_sql'
            ) AS j
        """
    rows = backend.fetch_all(
        sql, (person_id, key, report_id, accession, schema_id_number, dd_version_id, payload)
    )
    return [int(row[0]) for row in rows]


def load_message(backend: DatabaseBackend, message_id: int, *, algorithm: str) -> LoadResult:
    """Load all envelopes of a parsed message atomically, skipping exact-byte resends."""

    version = backend.fetch_one(
        "SELECT dd_version_id FROM naaccr.data_dictionary_version "
        "WHERE algorithm = ? AND is_current = 1", (algorithm,),
    )
    if version is None:
        raise ValueError(f"no current data dictionary version for {algorithm}")
    dd_version_id = int(version[0])
    message = backend.fetch_one(
        "SELECT is_content_duplicate, parse_status FROM intake.inbound_message "
        "WHERE inbound_message_id = ?", (message_id,),
    )
    if message is None:
        raise ValueError(f"unknown inbound message {message_id}")
    if message[1] != "parsed":
        raise ValueError(f"inbound message {message_id} is {message[1]}")
    if message[0]:
        return LoadResult(0, 0, 1)
    rows = backend.fetch_all(
        "SELECT inbound_envelope_id, envelope_json FROM intake.inbound_envelope "
        "WHERE inbound_message_id = ? ORDER BY ordinal", (message_id,),
    )
    if not rows:
        raise ValueError(f"inbound message {message_id} has no envelopes")
    report_count = value_count = 0
    with backend.transaction():
        for envelope_id_raw, serialized in rows:
            envelope_id = int(envelope_id_raw)
            if backend.fetch_one(
                "SELECT 1 FROM intake.envelope_load WHERE inbound_envelope_id = ?",
                (envelope_id,),
            ):
                continue
            envelope = json.loads(serialized)
            patient = envelope["patient"]
            identity = backend.fetch_one(
                "SELECT patient_id FROM intake.patient WHERE assigning_authority = ? "
                "AND person_source_value = ?",
                (patient.get("assigning_authority") or "", patient["person_source_value"]),
            )
            if identity is None:
                raise ValueError(f"patient identity missing for envelope {envelope_id}")
            person_id = int(identity[0])
            report = envelope["report"]
            accession = report.get("accession")
            prior = backend.fetch_one(
                "SELECT sdc_report_id FROM sdc.sdc_report WHERE person_id = ? "
                "AND report_accession = ? AND report_loinc = ? ORDER BY sdc_report_id",
                (person_id, accession, report.get("report_loinc")),
            ) if accession else None
            first_id = int(prior[0]) if prior else None
            key = episode_key(envelope)
            report_id = _report_id(backend, envelope, envelope_id, person_id,
                                   int(first_id is not None), first_id)
            schema_id_number = _staging_schema(backend, envelope, dd_version_id)
            ids = _value_ids(backend, envelope, person_id, report_id, key,
                             dd_version_id, schema_id_number)
            backend.execute_uncommitted(
                "INSERT INTO intake.envelope_load "
                "(inbound_envelope_id, sdc_report_id, person_id, episode_key, dd_version_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (envelope_id, report_id, person_id, key, dd_version_id),
            )
            if ids:
                backend.bulk_insert(
                    "intake", "envelope_value", ("inbound_envelope_id", "naaccr_value_id"),
                    ((envelope_id, value_id) for value_id in ids),
                )
                if schema_id_number is None:
                    backend.execute_uncommitted(
                        "INSERT INTO intake.inbound_message_diagnostic "
                        "(inbound_message_id, severity, code, detail) "
                        "VALUES (?, 'warning', 'STAGING_SCHEMA_UNRESOLVED', ?)",
                        (message_id, f"OBR {envelope['source']['obr_ordinal']}: "
                         "complete inputs or a unique exact staging rule unavailable"),
                    )
            report_count += 1
            value_count += len(ids)
    return LoadResult(report_count, value_count, 0)
