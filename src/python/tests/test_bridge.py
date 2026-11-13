"""BRIDGE-03..06 and OMOP-02/07/11: runner, person/period/source, notes and provenance."""

from __future__ import annotations

import copy
import csv
import dataclasses
import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdc_cdm.bridge import BridgeError, run_bridge, supersede_and_refresh
from sdc_cdm.bridge.seeds import CDM_SOURCE_COLUMNS, read_cdm_source
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import EtlEntry, load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.hl7v2.parser import NARRATIVE_LOINCS, SYNOPTIC_LOINCS
from sdc_cdm.intake import ingest_message, load_message
from sdc_cdm.maps.build import build_concept_maps
from sdc_cdm.maps.seeds import EXCLUSION_COLUMNS, OVERRIDE_COLUMNS
from sdc_cdm.naaccr.csv_io import write_csv
from sdc_cdm.naaccr.load import load_dictionary
from sdc_cdm.vocab.constants import resolve_constants
from sdc_cdm.vocab.loader import load_vocab
from vocab_fixture import _write_extract

ROOT = Path(__file__).resolve().parents[3]
DICTIONARY = ROOT / "sample_data/test-fixtures/naaccr-dict/csv"
BASE_ENVELOPE = parse_hl7((ROOT / "sample_data/naaccr_v2/two-obr-synthetic.hl7").read_bytes())[1]
SEED = repository_path("database/seed/cdm_source.csv")
DIALECTS = pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))

# Every OMOP clinical table the bridge will own once Phase 4 is complete.
OMOP_TABLES = (
    "omop.person", "omop.observation_period", "omop.cdm_source", "omop.note",
    "omop.measurement", "omop.observation", "omop.condition_occurrence", "omop.episode",
    "omop.episode_event",
)
# Rows a bridge test can leave behind, in an order that satisfies every FK. The
# SQL Server bridge database is dedicated to this module, so each test starts
# from empty source and derived tables.
RESET = (
    "sdc.note_report", "omop.note", "omop.cdm_source", "omop.observation_period", "omop.person",
    "etl.observation_period_derivation", "etl.cdm_source_seed",
    "naaccr.report_version", "naaccr.report_group", "naaccr.naaccr_value",
    "intake.envelope_value", "intake.envelope_load", "intake.inbound_message_diagnostic",
    "sdc.sdc_report", "intake.patient", "intake.inbound_envelope", "intake.inbound_message",
)
DERIVED = (
    ("omop.person", "person_id"),
    ("omop.observation_period", "person_id"),
    ("etl.observation_period_derivation", "observation_period_id"),
    ("omop.cdm_source", "cdm_source_name"),
    ("omop.note", "note_id"),
    ("sdc.note_report", "note_id, sdc_report_id"),
)
PERIODS = (
    "SELECT o.person_id, o.observation_period_start_date, o.observation_period_end_date, "
    "o.period_type_concept_id, d.derivation, d.start_naaccr_value_id, d.end_naaccr_value_id "
    "FROM omop.observation_period o "
    "JOIN etl.observation_period_derivation d "
    "ON d.observation_period_id = o.observation_period_id AND d.person_id = o.person_id "
    "ORDER BY o.person_id"
)

YEAR_1957 = {"y": 1957, "m": None, "d": None, "precision": "year"}


def _day(year: int, month: int, day: int) -> dict:
    return {"y": year, "m": month, "d": day, "precision": "day"}


def _clinical(observation_date: dict | None) -> dict:
    value = {"ecp_code": "20791.100004300", "value_num": "1.20", "unit_source": "cm"}
    if observation_date is not None:
        value["observation_date"] = observation_date
    return value


def _naaccr_date(item_num: int, value: str) -> dict:
    return {"item_num": item_num, "value_code": value}


def _empty_map_seeds(tmp_path: Path) -> Path:
    directory = tmp_path / "map-seeds"
    directory.mkdir(exist_ok=True)
    write_csv(directory / "concept_map_overrides.csv", OVERRIDE_COLUMNS, [])
    write_csv(directory / "naaccr_item_exclusions.csv", EXCLUSION_COLUMNS, [])
    return directory


@contextmanager
def _database(dialect: str, tmp_path: Path) -> Iterator[tuple[DatabaseBackend, list[str]]]:
    """A built target with vocabulary, dictionary, concept map, and constants."""
    if dialect == "sqlite":
        control = tmp_path / "bridge.db"
        backend: DatabaseBackend = SQLiteBackend(control)
        target = ["--dialect", "sqlite", "--db", str(control)]
    else:
        connection_string = os.environ.get("SDC_CDM_BRIDGE_SQLSERVER_CONNECTION_STRING")
        if not connection_string:
            pytest.skip("SDC_CDM_BRIDGE_SQLSERVER_CONNECTION_STRING is not set")
        backend = SqlServerBackend(connection_string)
        target = ["--dialect", "sqlserver", "--connection-string", connection_string]
    try:
        BuildRunner(load_manifest(), backend).run()
        for table in RESET:
            backend.execute(f"DELETE FROM {table}")
        if backend.fetch_one("SELECT 1 FROM omop.concept") is None:
            _write_extract(tmp_path / "vocab")
            load_vocab(backend, tmp_path / "vocab", "\t")
        if backend.fetch_one(
            "SELECT 1 FROM naaccr.data_dictionary_version WHERE is_current = 1"
        ) is None:
            load_dictionary(backend, csv_dir=DICTIONARY)
        build_concept_maps(backend, csv_dir=_empty_map_seeds(tmp_path))
        resolve_constants(backend)
        yield backend, target
    finally:
        backend.close()


class _Source:
    """Loads synthetic reports through intake, retaining each original byte payload."""

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend
        self.token = uuid.uuid4().hex[:10]
        self.sent = 0
        self.raw: dict[int, bytes] = {}
        self.last_report_id = 0
        self.algorithm = backend.fetch_one(
            "SELECT algorithm FROM naaccr.data_dictionary_version WHERE is_current = 1"
        )[0]

    def patient(self, name: str, values: list[dict], *, birth: dict | None = YEAR_1957,
                gender: str | None = "F", narrative_date: dict | None = None,
                message: str = "", accession: str | None = "ACC", loinc: str = "60569-1",
                facility: str = "SYNTHLAB", narrative: str | None = None,
                report_date: dict | None = None) -> int:
        """Load one report; narrative_date also selects the narrative report type."""
        self.sent += 1
        raw = f"bridge-{self.token}-{name}-{message}-{self.sent}".encode()
        envelope = copy.deepcopy(BASE_ENVELOPE)
        envelope["source"]["obr_ordinal"] = 1
        envelope["source"]["sending_facility"] = f"{facility}-{self.token}"
        envelope["raw"].update(sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))
        envelope["patient"] = {
            "assigning_authority": "SYNTHLAB", "person_source_value": f"{name}-{self.token}",
            "gender": gender, "birth_date": birth,
        }
        envelope["report"].update(
            accession=f"{accession}-{self.token}" if accession else accession,
            report_loinc=loinc,
        )
        if report_date is not None:
            envelope["report"]["observation_date"] = report_date
        envelope["values"] = values
        if narrative_date is not None:
            envelope["report"].update(report_loinc="35265-8", narrative="Synthetic narrative.",
                                      observation_date=narrative_date)
            envelope.pop("values")
        elif loinc in NARRATIVE_LOINCS:
            envelope.pop("values")
        if narrative is not None:
            envelope["report"]["narrative"] = narrative
        envelope.pop("diagnostics", None)
        message_id = ingest_message(self.backend, raw, lambda _: [envelope],
                                    parser_name="test", parser_version="1").inbound_message_id
        load_message(self.backend, message_id, algorithm=self.algorithm)
        self.last_report_id = int(self.backend.fetch_one(
            "SELECT l.sdc_report_id FROM intake.envelope_load l "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = l.inbound_envelope_id "
            "WHERE e.inbound_message_id = ?", (message_id,),
        )[0])
        self.raw[self.last_report_id] = raw
        return int(self.backend.fetch_one(
            "SELECT patient_id FROM intake.patient WHERE person_source_value = ?",
            (f"{name}-{self.token}",),
        )[0])

    def envelope_id(self, person_id: int, report_loinc: str) -> int:
        return int(self.backend.fetch_one(
            "SELECT r.inbound_envelope_id FROM sdc.sdc_report r "
            "WHERE r.person_id = ? AND r.report_loinc = ?", (person_id, report_loinc),
        )[0])

    def value_id(self, person_id: int, *, item_num: int | None = None,
                 observation_date: str | None = None) -> int:
        if item_num is not None:
            row = self.backend.fetch_one(
                "SELECT naaccr_value_id FROM naaccr.naaccr_value "
                "WHERE person_id = ? AND item_num = ?", (person_id, item_num),
            )
        else:
            row = self.backend.fetch_one(
                "SELECT naaccr_value_id FROM naaccr.naaccr_value "
                "WHERE person_id = ? AND observation_date = ?", (person_id, observation_date),
            )
        return int(row[0])


def _count(backend: DatabaseBackend, table: str) -> int:
    return int(backend.fetch_one(f"SELECT COUNT(*) FROM {table}")[0])


def _normalize(value: object) -> object:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _snapshot(backend: DatabaseBackend) -> dict[str, list[tuple]]:
    return {
        table: [
            tuple(_normalize(value) for value in row)
            for row in backend.fetch_all(f"SELECT * FROM {table} ORDER BY {key}")
        ]
        for table, key in DERIVED
    }


def _last_run(backend: DatabaseBackend) -> tuple:
    return tuple(backend.fetch_one(
        "SELECT command, status, error_message, completed_at FROM etl.run "
        "WHERE run_id = (SELECT MAX(run_id) FROM etl.run)"
    ))


@DIALECTS
def test_bridge_derives_person_period_and_source_and_reruns_unchanged(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        registry = source.patient("registry", [
            _naaccr_date(390, "20240115"), _naaccr_date(1750, "20250301"),
            _clinical(_day(2024, 2, 1)),
        ])
        clinical = source.patient("clinical", [
            _clinical(_day(2024, 5, 1)), _clinical(_day(2024, 3, 10)),
            _naaccr_date(390, "2024"), _naaccr_date(1750, "20250101"),
        ], birth=_day(1960, 3, 12), gender="M")
        one_day = source.patient("one-day", [_clinical(_day(2024, 6, 1))], gender="U")

        # OMOP-11 importer boundary: intake and load write no OMOP rows.
        assert {table: _count(backend, table) for table in OMOP_TABLES} == dict.fromkeys(
            OMOP_TABLES, 0)

        assert main(["bridge", *target]) == 0
        output = capsys.readouterr().out
        assert f"database/etl/{dialect}/1_person_and_period.sql" in output
        assert "  omop.person | 3" in output and "  omop.cdm_source | 1" in output
        assert _last_run(backend)[:3] == ("bridge", "succeeded", None)

        # OMOP-11: one person per intake patient, keyed by the intake identity.
        assert _count(backend, "omop.person") == _count(backend, "intake.patient") == 3
        persons = [tuple(row) for row in backend.fetch_all(
            "SELECT person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth, "
            "birth_datetime, race_concept_id, ethnicity_concept_id, person_source_value, "
            "gender_source_value FROM omop.person ORDER BY person_id"
        )]
        assert persons == [
            (registry, 8532, 1957, None, None, None, 0, 0, f"registry-{source.token}", "F"),
            (clinical, 8507, 1960, 3, 12, None, 0, 0, f"clinical-{source.token}", "M"),
            (one_day, 0, 1957, None, None, None, 0, 0, f"one-day-{source.token}", "U"),
        ]

        # BRIDGE-04: the period follows the derivation order and is never padded.
        periods = [tuple(_normalize(value) for value in row)
                   for row in backend.fetch_all(PERIODS)]
        assert periods == [
            (registry, "2024-01-15", "2025-03-01", 32879, "naaccr_diagnosis_to_last_contact",
             source.value_id(registry, item_num=390), source.value_id(registry, item_num=1750)),
            (clinical, "2024-03-10", "2024-05-01", 32879, "clinical_date_span",
             source.value_id(clinical, observation_date="2024-03-10"),
             source.value_id(clinical, observation_date="2024-05-01")),
            (one_day, "2024-06-01", "2024-06-01", 32879, "clinical_date_span",
             source.value_id(one_day, observation_date="2024-06-01"),
             source.value_id(one_day, observation_date="2024-06-01")),
        ]

        # BRIDGE-04: cdm_source is the seed row plus the loaded vocabulary version
        # and the resolved CDM version concept.
        seed = read_cdm_source(SEED)
        columns = ", ".join(name for name, _limit, _required in CDM_SOURCE_COLUMNS)
        rows = backend.fetch_all(
            f"SELECT {columns}, cdm_version_concept_id, vocabulary_version FROM omop.cdm_source"
        )
        assert [tuple(_normalize(value) for value in row) for row in rows] == [
            (*seed, 756265, "test-v1"),
        ]

        # OMOP-06/OMOP-11: an unchanged second run adds and changes nothing.
        first = _snapshot(backend)
        assert main(["bridge", *target]) == 0
        assert _snapshot(backend) == first
        assert _last_run(backend)[:3] == ("bridge", "succeeded", None)


@DIALECTS
def test_report_date_of_a_value_less_report_sets_clinical_boundaries(
    dialect: str, tmp_path: Path,
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        narrative = source.patient("narrative", [], narrative_date={
            "y": 2024, "m": 7, "d": 4, "hh": 9, "mi": 30, "ss": None, "precision": "minute",
        })
        mixed = source.patient("mixed", [_clinical(_day(2024, 3, 1))])
        source.patient("mixed", [], narrative_date=_day(2024, 8, 1), message="narrative")
        # A month-precision report date never sets a boundary.
        partial = source.patient("partial", [_clinical(_day(2024, 2, 2))])
        source.patient("partial", [], message="narrative",
                       narrative_date={"y": 2024, "m": 9, "d": None, "precision": "month"})

        assert main(["bridge", *target]) == 0
        rows = backend.fetch_all(
            "SELECT o.person_id, o.observation_period_start_date, "
            "o.observation_period_end_date, d.derivation, d.start_naaccr_value_id, "
            "d.start_inbound_envelope_id, d.end_naaccr_value_id, d.end_inbound_envelope_id "
            "FROM omop.observation_period o JOIN etl.observation_period_derivation d "
            "ON d.observation_period_id = o.observation_period_id ORDER BY o.person_id"
        )
        narrative_envelope = source.envelope_id(narrative, "35265-8")
        assert [tuple(_normalize(value) for value in row) for row in rows] == [
            (narrative, "2024-07-04", "2024-07-04", "clinical_date_span",
             None, narrative_envelope, None, narrative_envelope),
            (mixed, "2024-03-01", "2024-08-01", "clinical_date_span",
             source.value_id(mixed, observation_date="2024-03-01"), None,
             None, source.envelope_id(mixed, "35265-8")),
            (partial, "2024-02-02", "2024-02-02", "clinical_date_span",
             source.value_id(partial, observation_date="2024-02-02"), None,
             source.value_id(partial, observation_date="2024-02-02"), None),
        ]

        first = _snapshot(backend)
        assert main(["bridge", *target]) == 0
        assert _snapshot(backend) == first


@DIALECTS
def test_year_zero_naaccr_dates_fall_back_to_clinical_dates(
    dialect: str, tmp_path: Path,
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        person = source.patient("year-zero", [
            _naaccr_date(390, "00000101"), _naaccr_date(1750, "00000102"),
            _clinical(_day(2024, 4, 5)),
        ])
        assert main(["bridge", *target]) == 0
        clinical = source.value_id(person, observation_date="2024-04-05")
        assert [tuple(_normalize(value) for value in row)
                for row in backend.fetch_all(PERIODS)] == [
            (person, "2024-04-05", "2024-04-05", 32879, "clinical_date_span",
             clinical, clinical),
        ]


@DIALECTS
def test_missing_prerequisites_fail_before_any_write_and_are_named(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        _Source(backend).patient("ready", [_clinical(_day(2024, 1, 2))])
        version = backend.fetch_one(
            "SELECT vocabulary_version FROM omop.vocabulary WHERE vocabulary_id = 'None'"
        )[0]
        backend.execute(
            "DELETE FROM etl.concept_constant WHERE constant_name = 'period_type_registry'"
        )
        backend.execute(
            "UPDATE etl.concept_constant SET concept_id = 8507 WHERE constant_name = 'cdm_version'"
        )
        backend.execute("DELETE FROM naaccr.concept_map_build_state")
        backend.execute("UPDATE omop.vocabulary SET vocabulary_version = '' "
                        "WHERE vocabulary_id = 'None'")
        empty_seeds = tmp_path / "no-seeds"
        empty_seeds.mkdir()
        try:
            assert main(["bridge", *target, "--seed-dir", str(empty_seeds)]) == 1
            error = capsys.readouterr().err
            for named in (
                "nothing was written",
                f"seed cdm_source.csv: not found at {empty_seeds / 'cdm_source.csv'}",
                "constant period_type_registry: not in etl.concept_constant",
                "constant cdm_version: concept 8507 is not a valid ('CDM', 'CDM v5.4.0')",
                "concept map: naaccr.concept_map_build_state is empty",
                "vocabulary version: omop.vocabulary has no 'None' row",
            ):
                assert named in error
            assert {table: _count(backend, table) for table in OMOP_TABLES} == dict.fromkeys(
                OMOP_TABLES, 0)
            assert _count(backend, "etl.cdm_source_seed") == 0
            command, status, message, completed_at = _last_run(backend)
            assert (command, status) == ("bridge", "failed") and completed_at is not None
            assert "constant period_type_registry" in message
        finally:
            backend.execute("UPDATE omop.vocabulary SET vocabulary_version = ? "
                            "WHERE vocabulary_id = 'None'", (version,))


@pytest.mark.parametrize(("content", "defect"), (
    ("name\nx\n", "header must be"),
    (",".join(name for name, _l, _r in CDM_SOURCE_COLUMNS) + "\n", "exactly one data row"),
    (",".join(name for name, _l, _r in CDM_SOURCE_COLUMNS)
     + "\nn,a,h,,,,2026-02-30,2026-01-01,5.4\n", "source_release_date must be a YYYY-MM-DD"),
    (",".join(name for name, _l, _r in CDM_SOURCE_COLUMNS)
     + "\nn,,h,,,,2026-01-01,2026-01-01,5.4\n", "cdm_source_abbreviation is required"),
    (",".join(name for name, _l, _r in CDM_SOURCE_COLUMNS)
     + "\nn,a,h,,,,2026-01-01,2026-01-01,5.3\n", "cdm_version must be '5.4'"),
))
def test_cdm_source_seed_defects_are_named(tmp_path: Path, content: str, defect: str) -> None:
    path = tmp_path / "cdm_source.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=defect):
        read_cdm_source(path)


def test_tracked_cdm_source_seed_is_the_synthetic_test_source() -> None:
    with SEED.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["cdm_source_name"] == "SDC-CDM synthetic test source"
    assert row["cdm_version"] == "5.4"
    assert "replaces this row" in row["source_description"]
    assert len(read_cdm_source(SEED)) == len(CDM_SOURCE_COLUMNS)


@DIALECTS
def test_missing_birth_year_or_clinical_date_rolls_back_and_names_rows(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        source.patient("kept", [_clinical(_day(2024, 1, 2))])
        assert main(["bridge", *target]) == 0
        before = _snapshot(backend)

        no_birth = source.patient("no-birth", [_clinical(_day(2024, 1, 3))], birth=None)
        partial_only = source.patient("partial-only", [
            _clinical({"y": 2024, "m": 4, "d": None, "precision": "month"}),
            _naaccr_date(390, "202404"), _naaccr_date(1750, "20240901"),
        ])
        reversed_span = source.patient("reversed", [
            _naaccr_date(390, "20250101"), _naaccr_date(1750, "20240101"),
            _clinical(_day(2024, 6, 1)),
        ])
        capsys.readouterr()
        assert main(["bridge", *target]) == 1
        error = capsys.readouterr().err
        assert "1_person_and_period.sql: 3 source row(s) cannot be bridged" in error
        assert f"intake.patient {no_birth}: birth year is missing" in error
        assert (f"intake.patient {partial_only}: no selected report has a day-precision "
                "clinical date") in error
        assert (
            f"intake.patient {reversed_span}: date of last contact 2024-01-01 "
            f"(naaccr_value {source.value_id(reversed_span, item_num=1750)}) precedes date "
            f"of diagnosis 2025-01-01 "
            f"(naaccr_value {source.value_id(reversed_span, item_num=390)})"
        ) in error

        # BRIDGE-05: no derived row from the failed run survives, and no date was
        # substituted for the missing ones.
        assert _snapshot(backend) == before
        assert _count(backend, "omop.person") == 1
        command, status, message, _completed = _last_run(backend)
        assert (command, status) == ("bridge", "failed")
        assert f"intake.patient {no_birth}: birth year is missing" in message


@DIALECTS
def test_a_later_script_failure_rolls_back_every_earlier_script(
    dialect: str, tmp_path: Path,
) -> None:
    """Entries run in manifest order inside one transaction."""
    failing = tmp_path / "2_fail.sql"
    if dialect == "sqlite":
        failing.write_text(
            "UPDATE omop.person SET year_of_birth = 1;\n"
            "SELECT 'forced failure after ' || COUNT(*) || ' person row(s)' "
            "FROM omop.person WHERE year_of_birth = 1;\n"
        )
    else:
        failing.write_text(
            "UPDATE omop.person SET year_of_birth = 1\nGO\n"
            "SELECT CONCAT('forced failure after ', COUNT(*), ' person row(s)') "
            "FROM omop.person WHERE year_of_birth = 1\nGO\n"
        )
    manifest = load_manifest()
    entries = (*manifest.bridge_entries_for(dialect),
               EtlEntry(str(failing), (), (), ("omop.person",)))
    manifest = dataclasses.replace(manifest, bridge={**manifest.bridge, dialect: entries})
    with _database(dialect, tmp_path) as (backend, _target):
        _Source(backend).patient("rolled-back", [_clinical(_day(2024, 1, 2))])
        with pytest.raises(BridgeError, match=r"forced failure after 1 person row\(s\)"):
            run_bridge(backend, manifest)
        assert {table: _count(backend, table) for table in OMOP_TABLES} == dict.fromkeys(
            OMOP_TABLES, 0)
        assert _count(backend, "etl.observation_period_derivation") == 0
        assert _last_run(backend)[:2] == ("bridge", "failed")


def _notes(backend: DatabaseBackend) -> list[tuple]:
    return [tuple(_normalize(value) for value in row) for row in backend.fetch_all(
        "SELECT n.note_id, n.person_id, n.note_date, n.note_text, n.note_source_value, "
        "r.report_group_id, r.sdc_report_id FROM omop.note n "
        "JOIN sdc.note_report r ON r.note_id = n.note_id AND r.is_anchor = 1 "
        "ORDER BY n.note_id"
    )]


def _links(backend: DatabaseBackend) -> list[tuple]:
    return [tuple(row) for row in backend.fetch_all(
        "SELECT note_id, sdc_report_id, is_anchor FROM sdc.note_report ORDER BY sdc_report_id"
    )]


@DIALECTS
def test_combined_note_and_every_contributor_recover_exact_message_bytes(
    dialect: str, tmp_path: Path,
) -> None:
    """OMOP-02/07: actual HL7, two OBRs, one note, every raw contributor."""
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        token = source.token
        raw = (
            f"MSH|^~\\&|SYNTH|LAB-{token}|SDC|TEST|202609241200||"
            f"ORU^R01^ORU_R01|{token}|P|2.5.1\n"
            f"PID|1||P-{token}^^^SYNTHLAB^MR||Example^Synthetic||1957|F\n"
            f"ORC|RE||A-{token}\n"
            f"OBR|1||A-{token}|35265-8^REPORT^LN|||2026092512\n"
            "OBX|1|TX|22637-3^Diagnosis^LN|1|Selected narrative.\n"
            f"OBR|2||A-{token}|60569-1^REPORT^LN|||2026092412\n"
            "OBX|1|NM|20791.100004300^Tumor Size^CAPECP||1.20|cm\n"
        ).encode()
        message = ingest_message(backend, raw, parse_hl7, parser_name="test", parser_version="1")
        load_message(backend, message.inbound_message_id, algorithm=source.algorithm)
        run_bridge(backend, load_manifest())
        (note,) = _notes(backend)
        assert note[2:5] == ("2026-09-24", "Selected narrative.", f"A-{token}")
        constants = dict(backend.fetch_all(
            "SELECT constant_name, concept_id FROM etl.concept_constant"
        ))
        assert tuple(backend.fetch_one(
            "SELECT note_type_concept_id, note_class_concept_id, encoding_concept_id, "
            "language_concept_id, note_title, note_datetime, provider_id, "
            "visit_occurrence_id, visit_detail_id, note_event_id, note_event_field_concept_id "
            "FROM omop.note WHERE note_id = ?", (note[0],),
        )) == (constants["note_type_ehr"], *([constants["unmapped"]] * 3), *([None] * 7))
        walk = backend.fetch_all(
            "SELECT r.sdc_report_id, r.report_loinc, link.is_anchor, m.raw_blob "
            "FROM sdc.note_report link JOIN sdc.sdc_report r "
            "ON r.sdc_report_id = link.sdc_report_id "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id "
            "JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id "
            "WHERE link.note_id = ? ORDER BY r.sdc_report_id", (note[0],),
        )
        assert [(row[1], bool(row[2]), bytes(row[3])) for row in walk] == [
            ("35265-8", False, raw), ("60569-1", True, raw),
        ]
        assert note[6] == walk[1][0]
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before


@DIALECTS
@pytest.mark.parametrize("narrative_first", (False, True))
def test_late_complementary_report_keeps_note_id_and_reconciles_anchor_and_provenance(
    dialect: str, tmp_path: Path, narrative_first: bool,
) -> None:
    """BRIDGE-06: late narrative and late synoptic, with separate raw messages."""
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        first, second = (("35265-8", "60569-1") if narrative_first
                         else ("60569-1", "35265-8"))
        source.patient("paired", [_clinical(_day(2024, 1, 2))], loinc=first,
                       narrative="" if narrative_first else "Anchor comment.",
                       report_date=_day(2024, 1, 3))
        first_report = source.last_report_id
        run_bridge(backend, load_manifest())
        (before,) = _notes(backend)
        assert before[3] == ("Narrative report" if narrative_first else "Anchor comment.")
        source.patient("paired", [_clinical(_day(2024, 1, 1))], loinc=second,
                       narrative="Narrative received later." if not narrative_first else "Synoptic comment.",
                       report_date=_day(2024, 1, 4))
        second_report = source.last_report_id
        run_bridge(backend, load_manifest())
        (after,) = _notes(backend)
        anchor = second_report if narrative_first else first_report
        assert after[0] == before[0]
        assert after[2:4] == (("2024-01-01", "Synoptic comment.") if narrative_first
                              else ("2024-01-02", "Narrative received later."))
        assert after[6] == anchor
        assert _links(backend) == [
            (before[0], report, int(report == anchor)) for report in (first_report, second_report)
        ]
        walk = backend.fetch_all(
            "SELECT r.sdc_report_id, m.raw_blob FROM sdc.note_report link "
            "JOIN sdc.sdc_report r ON r.sdc_report_id = link.sdc_report_id "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id "
            "JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id"
        )
        assert {int(row[0]): bytes(row[1]) for row in walk} == source.raw
        before_rerun = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before_rerun


@DIALECTS
def test_same_accession_for_other_patients_or_facilities_gets_separate_notes(
    dialect: str, tmp_path: Path,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        for name, facility in (("P", "LAB"), ("Q", "LAB"), ("P", "ELSEWHERE")):
            source.patient(name, [_clinical(_day(2024, 1, 2))], facility=facility)
        run_bridge(backend, load_manifest())
        notes = _notes(backend)
        assert len(notes) == len({row[0] for row in notes}) == len({row[5] for row in notes}) == 3
        assert len({row[1] for row in notes}) == 2
        assert {row[4] for row in notes} == {f"ACC-{source.token}"}


@DIALECTS
@pytest.mark.parametrize("accession", (None, ""))
def test_accession_less_reports_have_no_note_or_provenance_link(
    dialect: str, tmp_path: Path, accession: str | None,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [_clinical(_day(2024, 1, 2))], accession=accession)
        excluded = source.last_report_id
        source.patient("P", [_clinical(_day(2024, 1, 3))])
        run_bridge(backend, load_manifest())
        assert len(_notes(backend)) == 1
        assert [row[1] for row in _links(backend)] == [source.last_report_id]
        assert source.last_report_id != excluded


@DIALECTS
@pytest.mark.parametrize("defect", ("date", "accession", "both"))
def test_unusable_note_data_names_group_and_anchor_and_rolls_back(
    dialect: str, tmp_path: Path, defect: str,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [_clinical(_day(2024, 1, 2))])
        run_bridge(backend, load_manifest())
        before = _snapshot(backend)
        partial = {"y": 2024, "m": 1, "d": None, "precision": "month"}
        source.patient("P", [_clinical(partial if defect != "accession" else _day(2024, 1, 3))],
                       accession="X" * 45 if defect != "date" else "BAD",
                       report_date=partial)
        anchor = source.last_report_id
        group = backend.fetch_one(
            "SELECT report_group_id FROM naaccr.report_version WHERE sdc_report_id = ?",
            (anchor,),
        )[0]
        with pytest.raises(BridgeError) as error:
            run_bridge(backend, load_manifest())
        text = str(error.value)
        assert f"naaccr.report_group {group} (anchor sdc_report {anchor})" in text
        if defect != "accession":
            assert "no day-precision note date" in text
        if defect != "date":
            assert "accession is longer than 50 characters" in text
        if defect == "both":
            assert text.index("no day-precision") < text.index("accession is longer")
        assert _snapshot(backend) == before
        assert _last_run(backend)[:2] == ("bridge", "failed")


@DIALECTS
def test_supersession_refreshes_notes_links_periods_and_pending_loads_atomically(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    with _database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        person = source.patient("P", [_clinical(_day(2024, 1, 2))], narrative="First comment.")
        predecessor = source.last_report_id
        source.patient("Q", [_clinical(_day(2024, 2, 3))], narrative="Other group.")
        run_bridge(backend, load_manifest())
        before = _notes(backend)
        other = tuple(backend.fetch_one("SELECT * FROM omop.note WHERE note_id = ?", (before[1][0],)))
        source.patient("P", [_clinical(_day(2024, 3, 4))], narrative="Corrected comment.")
        successor = source.last_report_id
        source.patient("pending", [_clinical(_day(2024, 4, 5))])
        assert main(["reports", "supersede", str(predecessor), str(successor),
                     *target, "--seed-dir", str(SEED.parent)]) == 0
        assert "bridge refreshed" in capsys.readouterr().out
        after = _notes(backend)
        assert after[0][0] == before[0][0]
        assert after[0][2:4] == ("2024-03-04", "Corrected comment.")
        assert after[0][6] == successor
        assert len(after) == 3
        assert predecessor not in {row[1] for row in _links(backend)}
        assert tuple(backend.fetch_one("SELECT * FROM omop.note WHERE note_id = ?", (before[1][0],))) == other
        period = backend.fetch_one(
            "SELECT observation_period_start_date, observation_period_end_date "
            "FROM omop.observation_period WHERE person_id = ?", (person,),
        )
        assert tuple(_normalize(value) for value in period) == ("2024-03-04", "2024-03-04")
        assert _last_run(backend)[:3] == ("supersede", "succeeded", None)
        before_rerun = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before_rerun


@DIALECTS
@pytest.mark.parametrize("failure", ("date", "prerequisites"))
def test_failed_supersession_refresh_rolls_back_selection_note_and_links(
    dialect: str, tmp_path: Path, failure: str,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [_clinical(_day(2024, 1, 2))], narrative="Kept comment.")
        predecessor = source.last_report_id
        # Another group dates the patient, so a bad successor fails in script 2.
        source.patient("P", [_clinical(_day(2024, 2, 3))], accession="OTHER")
        run_bridge(backend, load_manifest())
        partial = {"y": 2024, "m": 1, "d": None, "precision": "month"}
        source.patient("P", [_clinical(partial)], report_date=partial, narrative="Bad successor.")
        successor = source.last_report_id
        before = _snapshot(backend)
        versions_sql = ("SELECT * FROM naaccr.report_version ORDER BY sdc_report_id")
        versions = [tuple(row) for row in backend.fetch_all(versions_sql)]
        seeds = SEED.parent if failure == "date" else tmp_path / "missing-seeds"
        with pytest.raises(BridgeError, match="no day-precision note date" if failure == "date"
                           else "seed cdm_source.csv"):
            supersede_and_refresh(backend, load_manifest(), predecessor, successor, seed_dir=seeds)
        assert [tuple(row) for row in backend.fetch_all(versions_sql)] == versions
        assert _snapshot(backend) == before
        assert _last_run(backend)[:2] == ("supersede", "failed")


def test_note_sql_loinc_sets_match_parser() -> None:
    for dialect in ("sqlite", "sqlserver"):
        sql = repository_path(f"database/etl/{dialect}/2_note.sql").read_text()
        sets = [set(re.findall(r"'([0-9]+-[0-9]+)'", group))
                for group in re.findall(r"report_loinc IN \(([^)]+)\)", sql)]
        assert sets and SYNOPTIC_LOINCS in sets and NARRATIVE_LOINCS in sets
        assert all(group in (SYNOPTIC_LOINCS, NARRATIVE_LOINCS) for group in sets)


@DIALECTS
def test_note_anchor_text_and_date_precedence_and_unowned_notes(
    dialect: str, tmp_path: Path,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        def send(accession: str, loinc: str, text: str | None, values: list[dict] | None = None) -> int:
            source.patient("P", values if values is not None else [_clinical(_day(2024, 1, 2))],
                           accession=accession, loinc=loinc, narrative=text,
                           report_date=_day(2024, 8, 9))
            return source.last_report_id

        # Anchor preference and ties, multiple narratives (including empty text),
        # and an unselected revision that must never supply text or provenance.
        send("rank", "35265-8", "  ")
        send("rank", "11529-5", "Other non-narrative.")
        first_text = send("rank", "33717-0", " First narrative text. ")
        send("rank", "33716-2", "Later narrative text.")
        anchor = send("rank", "60571-7", "Anchor comment.", [
            _clinical(_day(2024, 5, 6)), _clinical(_day(2024, 3, 4)),
        ])
        send("rank", "60568-3", "Later synoptic.")
        historical = send("rank", "33717-0", "Unselected revision.")
        other = send("other", "11529-5", "  Preserve comment spacing.  ", [_clinical(None)])
        send("other", "35265-8", "")
        synoptic = send("synoptic", "60569-1", None)
        narrative = send("narrative", "35265-8", "")
        run_bridge(backend, load_manifest())
        notes = {row[4].removesuffix(f"-{source.token}"): row for row in _notes(backend)}
        assert notes["rank"][2:4] == ("2024-03-04", " First narrative text. ")
        assert notes["rank"][6] == anchor
        assert notes["other"][2:4] == ("2024-08-09", "  Preserve comment spacing.  ")
        assert notes["other"][6] == other
        assert notes["synoptic"][3] == "Synoptic report"
        assert notes["synoptic"][6] == synoptic
        assert notes["narrative"][3] == "Narrative report"
        assert notes["narrative"][6] == narrative
        assert first_text in {row[1] for row in _links(backend)}
        assert historical not in {row[1] for row in _links(backend)}

        # A note with the exact same accession, person, and contents but no link
        # belongs to another writer. It must neither be adopted nor rewritten.
        columns = ("person_id, note_date, note_type_concept_id, note_class_concept_id, "
                   "note_text, encoding_concept_id, language_concept_id, note_source_value")
        backend.execute(f"INSERT INTO omop.note ({columns}) SELECT {columns} FROM omop.note "
                        "WHERE note_id = ?", (notes["rank"][0],))
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before
        assert _count(backend, "omop.note") == 5


@DIALECTS
def test_unchanged_non_ascii_note_rerun_does_not_issue_an_update(
    dialect: str, tmp_path: Path,
) -> None:
    """Compare in the stored SQL Server varchar type, even for lossy text."""
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        text = "Clinical café, 漢字."
        source.patient("unicode", [_clinical(_day(2024, 1, 2))], narrative=text)
        run_bridge(backend, load_manifest())
        expected = text if dialect == "sqlite" else backend.fetch_one(
            "SELECT CAST(? AS varchar(MAX))", (text,),
        )[0]
        assert _notes(backend)[0][3] == expected
        backend.execute("CREATE TABLE omop.bridge_note_update_test (note_id INT NOT NULL)")
        trigger = (
            "CREATE TRIGGER omop.bridge_note_update_audit AFTER UPDATE ON note "
            "BEGIN INSERT INTO bridge_note_update_test VALUES (NEW.note_id); END"
            if dialect == "sqlite" else
            "CREATE TRIGGER omop.bridge_note_update_audit ON omop.note AFTER UPDATE AS "
            "INSERT INTO omop.bridge_note_update_test SELECT note_id FROM inserted"
        )
        try:
            backend.execute(trigger)
            before = _snapshot(backend)
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before
            assert _count(backend, "omop.bridge_note_update_test") == 0
        finally:
            backend.execute("DROP TRIGGER IF EXISTS omop.bridge_note_update_audit")
            backend.execute("DROP TABLE omop.bridge_note_update_test")
