from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlscript import split_script
from sdc_cdm.db.sqlserver_backend import SqlServerBackend


def _insert_id(
    backend: DatabaseBackend,
    sqlite_sql: str,
    sqlserver_sql: str,
    parameters: tuple[object, ...],
) -> int:
    if backend.dialect == "sqlite":
        return int(backend.execute(sqlite_sql, parameters))
    return int(backend.execute(sqlserver_sql, parameters, return_scalar=True))


def _ensure_bridge_map_tables(backend: DatabaseBackend) -> None:
    if backend.dialect != "sqlserver":
        return
    # TODO(phase-2): maps build will own these tables. Phase 0's SQL Server
    # dictionary DDL does not create them, but the existing bridge reads them.
    sql = """
    IF OBJECT_ID('naaccr.naaccr_concept_map', 'U') IS NULL
    BEGIN
        CREATE TABLE naaccr.naaccr_concept_map (
            item_num INT NOT NULL,
            concept_id INT NULL
        );
    END
    GO
    IF OBJECT_ID('naaccr.naaccr_value_concept_map', 'U') IS NULL
    BEGIN
        CREATE TABLE naaccr.naaccr_value_concept_map (
            item_num INT NOT NULL,
            code NVARCHAR(255) NOT NULL,
            concept_id INT NULL
        );
    END
    GO
    """
    backend.execute_units(split_script(backend.dialect, sql).executable)


def _seed_concepts(backend: DatabaseBackend) -> None:
    concepts = (
        (0, "Unknown", "Metadata", "None", "None", "0"),
        (32817, "EHR", "Type Concept", "Type Concept", "Type Concept", "EHR"),
        (32879, "Registry", "Type Concept", "Type Concept", "Type Concept", "Registry"),
        (1147289, "note.note_id", "Metadata", "CDM", "Field", "note.note_id"),
    )
    for concept in concepts:
        if backend.fetch_one(
            "SELECT concept_id FROM omop.concept WHERE concept_id = ?", (concept[0],)
        ):
            continue
        backend.execute(
            "INSERT INTO omop.concept ("
            "concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, "
            "concept_code, valid_start_date, valid_end_date"
            ") VALUES (?, ?, ?, ?, ?, ?, '1970-01-01', '2099-12-31')",
            concept,
        )


def _seed_source_rows(backend: DatabaseBackend) -> tuple[int, str]:
    token = uuid.uuid4().hex[:12]
    accession = f"ACC-{token}"
    patient_id = _insert_id(
        backend,
        "INSERT INTO intake.patient (person_source_value, assigning_authority) VALUES (?, ?)",
        "INSERT INTO intake.patient (person_source_value, assigning_authority) "
        "OUTPUT INSERTED.patient_id VALUES (?, ?)",
        (f"patient-{token}", "phase-0-test"),
    )
    backend.execute(
        "INSERT INTO omop.person ("
        "person_id, gender_concept_id, year_of_birth, race_concept_id, "
        "ethnicity_concept_id, person_source_value"
        ") VALUES (?, 0, 1970, 0, 0, ?)",
        (patient_id, f"patient-{token}"),
    )

    def insert_report(
        guid_suffix: str,
        report_accession: str | None,
        report_text: str,
        duplicate: int,
        first_seen: int | None,
    ) -> int:
        parameters = (
            "Adrenal",
            "1",
            f"report-{token}-{guid_suffix}",
            patient_id,
            report_accession,
            report_text,
            duplicate,
            first_seen,
        )
        columns = (
            "template_name, template_version, template_instance_guid, person_id, "
            "report_accession, report_text, is_duplicate_accession, first_seen_report_id"
        )
        return _insert_id(
            backend,
            f"INSERT INTO sdc.sdc_report ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            f"INSERT INTO sdc.sdc_report ({columns}) OUTPUT INSERTED.sdc_report_id "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            parameters,
        )

    primary_report = insert_report("1", accession, "Report text", 0, None)
    duplicate_report = insert_report(
        "2", accession, "Duplicate report text", 1, primary_report
    )
    null_accession_report = insert_report(
        "3", None, "No-accession report (NULL)", 0, None
    )
    empty_accession_report = insert_report(
        "4", "", "No-accession report (empty)", 0, None
    )

    backend.execute(
        "INSERT INTO sdc.sdc_form_answer (question_sdcid, question_text, response) "
        "VALUES (?, 'Question text', 'Answer text')",
        (f"100.{token}",),
    )
    values = (
        (primary_report, accession, 100, "A"),
        (primary_report, accession, 200, "B"),
        (primary_report, accession, 400, "D"),
        (primary_report, accession, 400, "D"),
        (duplicate_report, accession, 100, "A"),
        (duplicate_report, accession, 100, "A"),
        (null_accession_report, None, 100, "A"),
        (empty_accession_report, "", 100, "A"),
    )
    for report_id, report_accession, item_num, value_code in values:
        backend.execute(
            "INSERT INTO naaccr.naaccr_value ("
            "person_id, episode_key, sdc_report_id, report_accession, item_num, "
            "value_code, observation_date"
            ") VALUES (?, ?, ?, ?, ?, ?, '2026-06-22')",
            (
                patient_id,
                f"episode-{token}",
                report_id,
                report_accession,
                item_num,
                value_code,
            ),
        )
    return patient_id, accession


def _apply_bridge(backend: DatabaseBackend) -> None:
    # TODO(phase-4): replace this direct script call with the bridge verb.
    relative_path = f"database/etl/{backend.dialect}/1_naaccr_sdc_to_omop.sql"
    sql = repository_path(relative_path).read_text(encoding="utf-8")
    backend.execute_units(split_script(backend.dialect, sql).executable)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_bridge_reruns_do_not_double_count(
    dialect: str, tmp_path: Path
) -> None:
    if dialect == "sqlite":
        backend: DatabaseBackend = SQLiteBackend(tmp_path / "bridge.db")
    else:
        connection_string = os.environ.get("SDC_CDM_SQLSERVER_DSN")
        if not connection_string:
            pytest.skip("SDC_CDM_SQLSERVER_DSN is not set")
        backend = SqlServerBackend(connection_string)

    with backend:
        BuildRunner(load_manifest(), backend).run()
        _ensure_bridge_map_tables(backend)
        _seed_concepts(backend)
        patient_id, accession = _seed_source_rows(backend)

        _apply_bridge(backend)
        note_row = backend.fetch_one(
            "SELECT note_id FROM omop.note WHERE person_id = ? AND note_source_value = ?",
            (patient_id, accession),
        )
        assert note_row is not None
        note_id = int(note_row[0])
        measurements = backend.fetch_all(
            "SELECT measurement_source_value, value_source_value, "
            "measurement_type_concept_id, measurement_event_id, "
            "meas_event_field_concept_id FROM omop.measurement "
            "WHERE measurement_event_id = ? ORDER BY measurement_id",
            (note_id,),
        )
        assert [tuple(row) for row in measurements] == [
            ("100", "A", 32879, note_id, 1147289),
            ("200", "B", 32879, note_id, 1147289),
            ("400", "D", 32879, note_id, 1147289),
            ("400", "D", 32879, note_id, 1147289),
        ]

        for _ in range(2):
            _apply_bridge(backend)
            assert backend.fetch_one(
                "SELECT COUNT(*) FROM omop.measurement WHERE measurement_event_id = ?",
                (note_id,),
            )[0] == 4

        backend.execute(
            "DELETE FROM omop.measurement WHERE measurement_event_id = ? "
            "AND measurement_source_value = '200'",
            (note_id,),
        )
        _apply_bridge(backend)
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.measurement WHERE measurement_event_id = ?",
            (note_id,),
        )[0] == 4

        report_id = backend.fetch_one(
            "SELECT sdc_report_id FROM sdc.sdc_report "
            "WHERE person_id = ? AND report_accession = ? AND is_duplicate_accession = 0",
            (patient_id, accession),
        )[0]
        backend.execute(
            "INSERT INTO naaccr.naaccr_value ("
            "person_id, episode_key, sdc_report_id, report_accession, item_num, "
            "value_code, observation_date"
            ") VALUES (?, ?, ?, ?, 300, 'C', '2026-06-22')",
            (patient_id, f"episode-{accession}", report_id, accession),
        )
        _apply_bridge(backend)
        _apply_bridge(backend)

        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.note WHERE person_id = ? AND note_source_value = ?",
            (patient_id, accession),
        )[0] == 1
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.measurement WHERE measurement_event_id = ?",
            (note_id,),
        )[0] == 5
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.measurement WHERE measurement_event_id = ? "
            "AND measurement_type_concept_id <> 32879",
            (note_id,),
        )[0] == 0
