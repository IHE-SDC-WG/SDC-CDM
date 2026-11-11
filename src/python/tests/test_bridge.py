"""BRIDGE-03..05 and OMOP-11: bridge runner, person, observation period, and cdm_source."""

from __future__ import annotations

import copy
import csv
import dataclasses
import hashlib
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdc_cdm.bridge import BridgeError, run_bridge
from sdc_cdm.bridge.seeds import CDM_SOURCE_COLUMNS, read_cdm_source
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import EtlEntry, load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.hl7v2 import parse_hl7
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
    "omop.cdm_source", "omop.observation_period", "omop.person",
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
    """Loads one synthetic synoptic report per patient through intake."""

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend
        self.token = uuid.uuid4().hex[:10]
        self.algorithm = backend.fetch_one(
            "SELECT algorithm FROM naaccr.data_dictionary_version WHERE is_current = 1"
        )[0]

    def patient(self, name: str, values: list[dict], *, birth: dict | None = YEAR_1957,
                gender: str | None = "F", narrative_date: dict | None = None,
                message: str = "") -> int:
        """Load one report; with narrative_date, a value-less narrative report on that date."""
        raw = f"bridge-{self.token}-{name}-{message}".encode()
        envelope = copy.deepcopy(BASE_ENVELOPE)
        envelope["source"]["obr_ordinal"] = 1
        envelope["raw"].update(sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))
        envelope["patient"] = {
            "assigning_authority": "SYNTHLAB", "person_source_value": f"{name}-{self.token}",
            "gender": gender, "birth_date": birth,
        }
        envelope["report"]["accession"] = f"ACC-{name}-{self.token}"
        envelope["values"] = values
        if narrative_date is not None:
            envelope["report"].update(report_loinc="35265-8", narrative="Synthetic narrative.",
                                      observation_date=narrative_date)
            envelope.pop("values")
        envelope.pop("diagnostics", None)
        message_id = ingest_message(self.backend, raw, lambda _: [envelope],
                                    parser_name="test", parser_version="1").inbound_message_id
        load_message(self.backend, message_id, algorithm=self.algorithm)
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
