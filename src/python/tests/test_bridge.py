"""BRIDGE-03..11, OMOP-02..07/11/12: runner, person/period/source, notes, clinical rows,
conditions, and episodes."""

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
    "omop.episode_event", "omop.episode", "naaccr.person_episode", "naaccr.group_condition",
    "omop.condition_occurrence",
    "naaccr.value_event", "omop.measurement", "omop.observation", "sdc.note_report", "omop.note", "omop.cdm_source", "omop.observation_period", "omop.person",
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
    ("omop.measurement", "measurement_id"),
    ("omop.observation", "observation_id"),
    ("naaccr.value_event", "naaccr_value_id"),
    ("omop.condition_occurrence", "condition_occurrence_id"),
    ("naaccr.group_condition", "report_group_id"),
    ("omop.episode", "episode_id"),
    ("naaccr.person_episode", "episode_id"),
    ("omop.episode_event", "episode_id, episode_event_field_concept_id, event_id"),
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


# Item 400 (Primary Site) is not in the dictionary excerpt, whose CSVs recompute
# byte-for-byte from verbatim SEER*API JSON, so this module adds it to the loaded
# generation: four synthetic allowed codes, and two schemas that disagree on C509
# so (400, 'C509') is a #100 collision.
PRIMARY_SITE = 400
SITE_CODES = (
    ("C500", "Nipple"), ("C504", "Upper-outer quadrant of breast"),
    ("C509", "Breast, NOS"), ("C619", "Prostate gland"),
)


def _add_primary_site(backend: DatabaseBackend) -> None:
    generation = backend.fetch_one(
        "SELECT dd_version_id FROM naaccr.data_dictionary_version WHERE is_current = 1"
    )[0]
    if backend.fetch_one(
        "SELECT 1 FROM naaccr.naaccr_item WHERE dd_version_id = ? AND item_num = ?",
        (generation, PRIMARY_SITE),
    ) is not None:
        return
    backend.execute(
        "INSERT INTO naaccr.naaccr_item (dd_version_id, item_num, name, section, "
        "parent_xml_element) VALUES (?, ?, 'Primary Site', 'Cancer Identification', 'Tumor')",
        (generation, PRIMARY_SITE),
    )
    for sequence, (code, description) in enumerate(SITE_CODES):
        backend.execute(
            "INSERT INTO naaccr.naaccr_item_allowed_code (dd_version_id, item_num, code_seq, "
            "code, description) VALUES (?, ?, ?, ?, ?)",
            (generation, PRIMARY_SITE, sequence, code, description),
        )
    for schema, meaning in (("00460", "Breast, NOS"), ("00580", "Fixture-B site")):
        backend.execute(
            "INSERT INTO naaccr.schema_item (dd_version_id, schema_id_number, item_num, "
            "item_role, used_for_staging) VALUES (?, ?, ?, 'input', 1)",
            (generation, schema, PRIMARY_SITE),
        )
        backend.execute(
            "INSERT INTO naaccr.schema_item_code (dd_version_id, schema_id_number, item_num, "
            "code, description) VALUES (?, ?, ?, 'C509', ?)",
            (generation, schema, PRIMARY_SITE, meaning),
        )


def _empty_map_seeds(tmp_path: Path) -> Path:
    directory = tmp_path / "map-seeds"
    directory.mkdir(exist_ok=True)
    write_csv(directory / "concept_map_overrides.csv", OVERRIDE_COLUMNS, [])
    write_csv(directory / "naaccr_item_exclusions.csv", EXCLUSION_COLUMNS, [])
    return directory


@contextmanager
def _database(
    dialect: str, tmp_path: Path, *,
    sqlserver_env: str = "SDC_CDM_BRIDGE_SQLSERVER_CONNECTION_STRING",
) -> Iterator[tuple[DatabaseBackend, list[str]]]:
    """A built target with vocabulary, dictionary, concept map, and constants."""
    if dialect == "sqlite":
        control = tmp_path / "bridge.db"
        backend: DatabaseBackend = SQLiteBackend(control)
        target = ["--dialect", "sqlite", "--db", str(control)]
    else:
        connection_string = os.environ.get(sqlserver_env)
        if not connection_string:
            pytest.skip(f"{sqlserver_env} is not set")
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
        _add_primary_site(backend)
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
                report_date: dict | None = None, episode: dict | None = None) -> int:
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
        if episode is not None:
            envelope["episode"] = episode
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
        self.last_envelope = envelope
        return int(self.backend.fetch_one(
            "SELECT patient_id FROM intake.patient WHERE person_source_value = ?",
            (f"{name}-{self.token}",),
        )[0])

    def resend_last(self) -> int:
        """Ingest and load the last report's exact bytes again; return the new message ID."""
        raw = self.raw[self.last_report_id]
        message_id = ingest_message(self.backend, raw, lambda _: [self.last_envelope],
                                    parser_name="test", parser_version="1").inbound_message_id
        load_message(self.backend, message_id, algorithm=self.algorithm)
        return message_id

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
        ], birth=_day(1960, 3, 12), gender="M", report_date=_day(2024, 4, 1))
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
        ], report_date=_day(2024, 4, 5))
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
        ], report_date={"y": 2024, "m": 4, "d": None, "precision": "month"})
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
        # OMOP-06b: the excluded report's values never fan out into clinical rows.
        assert [row[0] for row in backend.fetch_all(
            "SELECT v.sdc_report_id FROM naaccr.value_event l "
            "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id"
        )] == [source.last_report_id]
        assert _count(backend, "omop.measurement") + _count(backend, "omop.observation") == 1


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


@DIALECTS
@pytest.mark.parametrize("corrected_text", ("Stage II", "Stage ii "))
def test_supersession_and_reconciliation_preserve_case_and_trailing_spaces(
    dialect: str, tmp_path: Path, corrected_text: str,
) -> None:
    with _database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [], loinc="35265-8", narrative="Stage ii",
                       report_date=_day(2024, 1, 2))
        predecessor = source.last_report_id
        run_bridge(backend, load_manifest())
        (before,) = _notes(backend)
        source.patient("P", [], loinc="35265-8", narrative=corrected_text,
                       report_date=_day(2024, 1, 2))
        successor = source.last_report_id
        supersede_and_refresh(backend, load_manifest(), predecessor, successor)
        (after,) = _notes(backend)
        assert after[:3] == before[:3]
        assert after[3] == corrected_text
        assert _links(backend) == [(before[0], successor, 1)]

        # The accession comparison also needs exact stored-byte semantics.
        stale_source = before[4].lower() if corrected_text == "Stage II" else before[4] + " "
        assert stale_source != before[4]
        backend.execute("UPDATE omop.note SET note_source_value = ? WHERE note_id = ?",
                        (stale_source, before[0]))
        run_bridge(backend, load_manifest())
        assert _notes(backend)[0] == after
        before_rerun = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before_rerun


@pytest.mark.parametrize("accession", ("é" * 19 + "A", "é" * 20))
def test_utf8_accession_byte_limit_is_checked_before_narrowing(
    tmp_path: Path, accession: str,
) -> None:
    with _database("sqlserver", tmp_path,
                   sqlserver_env="SDC_CDM_BRIDGE_UTF8_SQLSERVER_CONNECTION_STRING") as (backend, _target):
        collation = backend.fetch_one(
            "SELECT CONVERT(varchar(128), DATABASEPROPERTYEX(DB_NAME(), 'Collation'))"
        )[0]
        assert collation.endswith("_UTF8"), "this regression requires a UTF-8 database"
        source = _Source(backend)
        source.patient("kept", [_clinical(_day(2024, 1, 2))])
        run_bridge(backend, load_manifest())
        before = _snapshot(backend)
        full_accession = f"{accession}-{source.token}"
        assert len(full_accession) < 50
        byte_length = len(full_accession.encode("utf-8"))
        assert byte_length in (50, 51)
        source.patient("P", [_clinical(_day(2024, 1, 2))], accession=accession)
        anchor = source.last_report_id
        if byte_length == 51:
            group = backend.fetch_one(
                "SELECT report_group_id FROM naaccr.report_version WHERE sdc_report_id = ?",
                (anchor,),
            )[0]
            with pytest.raises(BridgeError) as error:
                run_bridge(backend, load_manifest())
            assert (f"naaccr.report_group {group} (anchor sdc_report {anchor}): "
                    "accession exceeds the 50-byte note_source_value limit") in str(error.value)
            assert _snapshot(backend) == before
            assert _last_run(backend)[:2] == ("bridge", "failed")
        else:
            run_bridge(backend, load_manifest())
            assert _notes(backend)[1][4] == full_accession
            stored_length = backend.fetch_one(
                "SELECT DATALENGTH(note_source_value) FROM omop.note WHERE note_id = ?",
                (_notes(backend)[1][0],),
            )[0]
            assert stored_length == 50
            before_rerun = _snapshot(backend)
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before_rerun


# Phase 4.3: domain-routed measurements and observations.

# Reviewed-map rows for this module only: 3827 keeps its Athena Observation target
# (9001), 3605 gets a Measurement target, 3803 a target in another domain, and both
# codes of 3827 get value targets, including the #100 collision (3827, '1'). Primary
# site C504 and the C509 collision get a Condition target and C619 one in another
# domain; C500 keeps no target.
ROUTING_OVERRIDES = (
    (400, "C504", 9005, "Condition", "synthetic routing fixture", "tester", "2026-11-18"),
    (400, "C509", 9005, "Condition", "synthetic routing fixture", "tester", "2026-11-18"),
    (400, "C619", 9003, "Meas Value", "synthetic routing fixture", "tester", "2026-11-18"),
    (3605, "", 9004, "Measurement", "synthetic routing fixture", "tester", "2026-11-16"),
    (3803, "", 9003, "Meas Value", "synthetic routing fixture", "tester", "2026-11-16"),
    (3827, "0", 9003, "Meas Value", "synthetic routing fixture", "tester", "2026-11-16"),
    (3827, "1", 9002, "Meas Value", "synthetic routing fixture", "tester", "2026-11-16"),
)
ABSENT_ITEM = 99999
REPORT_DAY = "2026-09-24"  # the day-precision report date of the base envelope
EVENTS = (
    "SELECT v.obx_sub_id, l.event_table, l.route, l.value_target, l.is_truncated, "
    "e.concept_id, e.source_concept_id, e.source_value, e.value_as_number, "
    "e.value_as_concept_id, e.value_as_string, e.value_source_value, e.unit_source_value, "
    "e.event_date, e.type_concept_id, e.note_id, e.field_concept_id, e.person_id, "
    "l.naaccr_value_id, l.event_id, v.sdc_report_id "
    "FROM naaccr.value_event l "
    "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
    "JOIN (SELECT 'measurement' AS event_table, measurement_id AS id, "
    "measurement_concept_id AS concept_id, measurement_source_concept_id AS source_concept_id, "
    "measurement_source_value AS source_value, value_as_number, value_as_concept_id, "
    "NULL AS value_as_string, value_source_value, unit_source_value, "
    "measurement_date AS event_date, measurement_type_concept_id AS type_concept_id, "
    "measurement_event_id AS note_id, meas_event_field_concept_id AS field_concept_id, "
    "person_id FROM omop.measurement "
    "UNION ALL SELECT 'observation', observation_id, observation_concept_id, "
    "observation_source_concept_id, observation_source_value, value_as_number, "
    "value_as_concept_id, value_as_string, value_source_value, unit_source_value, "
    "observation_date, observation_type_concept_id, observation_event_id, "
    "obs_event_field_concept_id, person_id FROM omop.observation) e "
    "ON e.event_table = l.event_table AND e.id = l.event_id "
    "ORDER BY l.naaccr_value_id"
)
EVENT_COLUMNS = (
    "label", "event_table", "route", "value_target", "is_truncated", "concept_id",
    "source_concept_id", "source_value", "value_as_number", "value_as_concept_id",
    "value_as_string", "value_source_value", "unit_source_value", "event_date",
    "type_concept_id", "note_id", "field_concept_id", "person_id", "naaccr_value_id",
    "event_id", "sdc_report_id",
)
# Columns the bridge always leaves NULL.
UNSET = {
    "omop.measurement": (
        "measurement_datetime", "measurement_time", "operator_concept_id", "unit_concept_id",
        "range_low", "range_high", "provider_id", "visit_occurrence_id", "visit_detail_id",
        "unit_source_concept_id",
    ),
    "omop.observation": (
        "observation_datetime", "qualifier_concept_id", "unit_concept_id", "provider_id",
        "visit_occurrence_id", "visit_detail_id", "qualifier_source_value",
    ),
}


@contextmanager
def _mapped_database(
    dialect: str, tmp_path: Path, **kwargs: str,
) -> Iterator[tuple[DatabaseBackend, list[str]]]:
    with _database(dialect, tmp_path, **kwargs) as (backend, target):
        seeds = _empty_map_seeds(tmp_path)
        write_csv(seeds / "concept_map_overrides.csv", OVERRIDE_COLUMNS, ROUTING_OVERRIDES)
        build_concept_maps(backend, csv_dir=seeds)
        yield backend, target


def _events(backend: DatabaseBackend) -> list[dict[str, object]]:
    return [
        dict(zip(EVENT_COLUMNS, (_normalize(value) for value in row), strict=True))
        for row in backend.fetch_all(EVENTS)
    ]


def _by_label(backend: DatabaseBackend) -> dict[str, dict[str, object]]:
    events = _events(backend)
    labelled = {str(event["label"]): event for event in events}
    assert len(labelled) == len(events)
    return labelled


def _source_concepts(backend: DatabaseBackend) -> dict[int, int]:
    return {int(row[0]): int(row[1]) for row in backend.fetch_all(
        "SELECT item_num, source_concept_id FROM naaccr.naaccr_concept_map"
    )}


def _constants(backend: DatabaseBackend) -> dict[str, int]:
    return {str(row[0]): int(row[1]) for row in backend.fetch_all(
        "SELECT constant_name, concept_id FROM etl.concept_constant"
    )}


def _routing_values() -> list[dict]:
    """Every routing case once; obx_sub_id labels each source occurrence."""
    return [
        {"obx_sub_id": "er-negative", "item_num": 3827, "value_code": "0",
         "observation_date": _day(2024, 5, 6)},
        {"obx_sub_id": "er-positive", "item_num": 3827, "value_code": "1"},
        {"obx_sub_id": "stage", "item_num": 3605, "value_code": "1"},
        {"obx_sub_id": "stage-zero-target", "item_num": 3605, "value_code": "0A"},
        {"obx_sub_id": "stage-size", "item_num": 3605, "value_num": "2.5", "unit_source": "cm"},
        {"obx_sub_id": "stage-text", "item_num": 3605, "value_text": "Stage text"},
        {"obx_sub_id": "stage-empty", "item_num": 3605},
        {"obx_sub_id": "basaloid-text", "item_num": 3803, "value_text": "Basaloid present"},
        {"obx_sub_id": "basaloid-number", "item_num": 3803, "value_num": "40", "unit_source": "%"},
        {"obx_sub_id": "pediatric", "item_num": 1144, "value_code": "M1"},
        {"obx_sub_id": "absent-text", "item_num": ABSENT_ITEM, "value_text": "Free text"},
        {"obx_sub_id": "absent-code", "item_num": ABSENT_ITEM, "value_code": "7"},
        {"obx_sub_id": "ckey-code", "ecp_code": "3827.100004300", "value_code": "1"},
        {"obx_sub_id": "ckey-number", "ecp_code": "20791.100004300", "value_num": "1.20",
         "unit_source": "cm"},
        {"obx_sub_id": "ckey-both", "ecp_code": "22637.100004300", "value_code": "Y",
         "value_text": "Coded with text"},
        {"obx_sub_id": "ckey-blank", "ecp_code": "22638.100004300", "value_text": "   "},
    ]


@contextmanager
def _routed(
    dialect: str, tmp_path: Path,
) -> Iterator[tuple[DatabaseBackend, int, dict[str, dict[str, object]]]]:
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        person = source.patient("routed", _routing_values())
        run_bridge(backend, load_manifest())
        yield backend, person, _by_label(backend)


@DIALECTS
def test_values_route_to_their_domain_tables_with_both_concept_slots(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-07, OMOP-03, OMOP-12 (4.3 part): table, route, slots, and constants."""
    with _routed(dialect, tmp_path) as (backend, person, events):
        maps = {int(row[0]): (int(row[1]), row[2], row[3]) for row in backend.fetch_all(
            "SELECT item_num, concept_id, target_domain_id, mapping_layer "
            "FROM naaccr.naaccr_concept_map WHERE item_num IN (1144, 3605, 3803, 3827)"
        )}
        assert maps == {
            1144: (0, None, "local_mint"), 3605: (9004, "Measurement", "curated_override"),
            3803: (9003, "Meas Value", "curated_override"),
            3827: (9001, "Observation", "athena_standard"),
        }
        assert backend.fetch_one(
            "SELECT 1 FROM naaccr.naaccr_concept_map WHERE item_num = ?", (ABSENT_ITEM,),
        ) is None
        source = _source_concepts(backend)
        expected = {
            "er-negative": ("observation", "target_domain", 9001, source[3827], "3827"),
            "er-positive": ("observation", "target_domain", 9001, source[3827], "3827"),
            "stage": ("measurement", "target_domain", 9004, source[3605], "3605"),
            "stage-zero-target": ("measurement", "target_domain", 9004, source[3605], "3605"),
            "stage-size": ("measurement", "target_domain", 9004, source[3605], "3605"),
            # A Measurement-domain target keeps text in measurement, not observation.
            "stage-text": ("measurement", "target_domain", 9004, source[3605], "3605"),
            "stage-empty": ("measurement", "target_domain", 9004, source[3605], "3605"),
            # Every default keeps 0 in *_concept_id and routes by value shape.
            "basaloid-text": ("observation", "default_other_domain", 0, source[3803], "3803"),
            "basaloid-number": ("measurement", "default_other_domain", 0, source[3803], "3803"),
            "pediatric": ("measurement", "default_no_target", 0, source[1144], "1144"),
            "absent-text": ("observation", "default_no_map", 0, 0, str(ABSENT_ITEM)),
            "absent-code": ("measurement", "default_no_map", 0, 0, str(ABSENT_ITEM)),
            "ckey-code": ("measurement", "default_ecp_code", 0, 0, "3827.100004300"),
            "ckey-number": ("measurement", "default_ecp_code", 0, 0, "20791.100004300"),
            "ckey-both": ("observation", "default_ecp_code", 0, 0, "22637.100004300"),
            "ckey-blank": ("measurement", "default_ecp_code", 0, 0, "22638.100004300"),
        }
        assert {label: (event["event_table"], event["route"], event["concept_id"],
                        event["source_concept_id"], event["source_value"])
                for label, event in events.items()} == expected

        constants = _constants(backend)
        (note_id,) = {row[0] for row in _notes(backend)}
        for event in events.values():
            assert event["type_concept_id"] == constants[f"{event['event_table']}_type_registry"]
            assert event["field_concept_id"] == constants["field_note_note_id"] == 1147156
            assert (event["note_id"], event["person_id"]) == (note_id, person)
            assert event["event_date"] == ("2024-05-06" if event["label"] == "er-negative"
                                           else REPORT_DAY)
        for table, columns in UNSET.items():
            assert backend.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE "
                + " OR ".join(f"{column} IS NOT NULL" for column in columns)
            )[0] == 0
        # OMOP-12: nonzero standard slots hold standard concepts.
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.measurement m JOIN omop.concept c "
            "ON c.concept_id IN (m.measurement_concept_id, m.value_as_concept_id) "
            "WHERE c.concept_id <> 0 AND (c.standard_concept IS NULL OR c.standard_concept <> 'S')"
        )[0] == 0
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.observation o JOIN omop.concept c "
            "ON c.concept_id IN (o.observation_concept_id, o.value_as_concept_id) "
            "WHERE c.concept_id <> 0 AND (c.standard_concept IS NULL OR c.standard_concept <> 'S')"
        )[0] == 0
        assert _count(backend, "omop.measurement") + _count(backend, "omop.observation") \
            == _count(backend, "naaccr.value_event") == _count(backend, "naaccr.naaccr_value")


@DIALECTS
def test_coded_numeric_and_text_values_take_their_omop_shapes(
    dialect: str, tmp_path: Path,
) -> None:
    """OMOP-04: one synthetic NAACCR input per value shape."""
    with _routed(dialect, tmp_path) as (_backend, _person, events):
        shape = {label: (event["value_target"], event["value_as_concept_id"],
                         event["value_as_number"], event["unit_source_value"],
                         event["value_as_string"], event["value_source_value"])
                 for label, event in events.items()}
        # Coded: the nonzero value target; zero, absent, or suppressed targets give NULL.
        assert shape["stage"] == ("mapped", 9002, None, None, None, "1")
        assert shape["er-negative"] == ("mapped", 9003, None, None, None, "0")
        assert shape["stage-zero-target"] == ("unmapped", None, None, None, None, "0A")
        assert shape["pediatric"] == ("unmapped", None, None, None, None, "M1")
        assert shape["absent-code"] == ("unmapped", None, None, None, None, "7")
        assert shape["er-positive"] == ("collision_suppressed", None, None, None, None, "1")
        # Numeric: value_as_number and the unit source text; unit_concept_id stays NULL.
        assert shape["stage-size"] == ("none", None, 2.5, "cm", None, None)
        assert shape["basaloid-number"] == ("none", None, 40.0, "%", None, None)
        assert shape["ckey-number"] == ("none", None, 1.2, "cm", None, None)
        # Text: observation.value_as_string; a code still wins value_source_value.
        assert shape["basaloid-text"] == ("none", None, None, None, "Basaloid present",
                                          "Basaloid present")
        assert shape["absent-text"] == ("none", None, None, None, "Free text", "Free text")
        assert shape["ckey-both"] == ("unmapped", None, None, None, "Coded with text", "Y")
        assert shape["stage-text"] == ("none", None, None, None, None, "Stage text")
        # No value at all still yields one row; blank text routes to measurement.
        assert shape["stage-empty"] == ("none", None, None, None, None, None)
        assert shape["ckey-blank"] == ("none", None, None, None, None, "   ")
        assert not any(event["is_truncated"] for event in events.values())


@DIALECTS
def test_collision_codes_are_suppressed_kept_and_reported(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-08: a reviewed target never reaches a #100 collision code."""
    with _routed(dialect, tmp_path) as (backend, _person, events):
        collisions = {(int(row[0]), str(row[1]), int(row[2])) for row in backend.fetch_all(
            "SELECT item_num, code, concept_id FROM naaccr.value_code_collision"
        )}
        assert collisions == {(3827, "1", 9002), (400, "C509", 9005)}
        positive, negative = events["er-positive"], events["er-negative"]
        assert positive["value_as_concept_id"] is None
        assert positive["value_source_value"] == "1"
        assert positive["source_concept_id"] == _source_concepts(backend)[3827]
        assert positive["value_target"] == "collision_suppressed"
        assert negative["value_as_concept_id"] == 9003
        assert negative["value_target"] == "mapped"
        # The suppressed rows are reportable from the link table alone.
        assert [tuple(row) for row in backend.fetch_all(
            "SELECT v.item_num, v.value_code FROM naaccr.value_event l "
            "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
            "WHERE l.value_target = 'collision_suppressed'"
        )] == [(3827, "1")]


@DIALECTS
def test_ckey_values_are_kept_never_joined_by_prefix_and_counted(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-09: 3827.100004300 is not item 3827."""
    with _routed(dialect, tmp_path) as (backend, _person, events):
        ckey = events["ckey-code"]
        assert (ckey["source_value"], ckey["concept_id"], ckey["source_concept_id"],
                ckey["value_as_concept_id"], ckey["value_target"]) == (
            "3827.100004300", 0, 0, None, "unmapped")
        counts = {str(row[0]): int(row[1]) for row in backend.fetch_all(
            "SELECT route, COUNT(*) FROM naaccr.value_event GROUP BY route"
        )}
        assert counts == {"target_domain": 7, "default_other_domain": 2,
                          "default_no_target": 1, "default_no_map": 2, "default_ecp_code": 4}


def _owned(backend: DatabaseBackend, report_id: int) -> list[tuple]:
    rows: list[tuple] = []
    for table, key in (("measurement", "measurement_id"), ("observation", "observation_id")):
        rows += [("measurement" if table == "measurement" else "observation",
                  *(_normalize(value) for value in row)) for row in backend.fetch_all(
            f"SELECT o.* FROM omop.{table} o JOIN naaccr.value_event l "
            f"ON l.event_table = '{table}' AND l.event_id = o.{key} "
            "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
            f"WHERE v.sdc_report_id = ? ORDER BY o.{key}", (report_id,),
        )]
    return rows


def _orphan_episode_events(backend: DatabaseBackend) -> int:
    """Owned episode events whose episode or referenced row is missing."""
    constants = _constants(backend)
    return int(backend.fetch_one(
        "SELECT COUNT(*) FROM omop.episode_event x "
        "JOIN naaccr.person_episode l ON l.episode_id = x.episode_id "
        "WHERE NOT EXISTS (SELECT 1 FROM omop.episode e WHERE e.episode_id = x.episode_id) "
        "OR NOT ("
        "(x.episode_event_field_concept_id = ? AND EXISTS (SELECT 1 FROM omop.measurement o "
        "WHERE o.measurement_id = x.event_id)) "
        "OR (x.episode_event_field_concept_id = ? AND EXISTS (SELECT 1 FROM omop.observation o "
        "WHERE o.observation_id = x.event_id)) "
        "OR (x.episode_event_field_concept_id = ? AND EXISTS ("
        "SELECT 1 FROM omop.condition_occurrence o "
        "WHERE o.condition_occurrence_id = x.event_id)))",
        (constants["field_measurement_measurement_id"],
         constants["field_observation_observation_id"],
         constants["field_condition_occurrence_id"]),
    )[0])


def _assert_no_orphans(backend: DatabaseBackend) -> None:
    for table, key, event in (("measurement", "measurement_id", "measurement_event_id"),
                              ("observation", "observation_id", "observation_event_id")):
        assert backend.fetch_one(
            f"SELECT COUNT(*) FROM omop.{table} o "
            f"WHERE NOT EXISTS (SELECT 1 FROM omop.note n WHERE n.note_id = o.{event})"
        )[0] == 0
        assert backend.fetch_one(
            f"SELECT COUNT(*) FROM naaccr.value_event l WHERE l.event_table = '{table}' "
            f"AND NOT EXISTS (SELECT 1 FROM omop.{table} o WHERE o.{key} = l.event_id)"
        )[0] == 0
    # Every linked value belongs to a selected report.
    assert backend.fetch_one(
        "SELECT COUNT(*) FROM naaccr.value_event l "
        "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
        "WHERE NOT EXISTS (SELECT 1 FROM naaccr.report_version rv "
        "WHERE rv.sdc_report_id = v.sdc_report_id AND rv.is_selected = 1)"
    )[0] == 0
    # Every condition link names a live condition and a selected site value.
    assert backend.fetch_one(
        "SELECT COUNT(*) FROM naaccr.group_condition l "
        "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
        "WHERE v.item_num <> 400 OR NOT EXISTS (SELECT 1 FROM omop.condition_occurrence o "
        "WHERE o.condition_occurrence_id = l.condition_occurrence_id) "
        "OR NOT EXISTS (SELECT 1 FROM naaccr.report_version rv "
        "WHERE rv.sdc_report_id = v.sdc_report_id AND rv.is_selected = 1)"
    )[0] == 0
    assert backend.fetch_one(
        "SELECT COUNT(*) FROM naaccr.person_episode l WHERE NOT EXISTS "
        "(SELECT 1 FROM omop.episode e WHERE e.episode_id = l.episode_id)"
    )[0] == 0
    assert _orphan_episode_events(backend) == 0


@contextmanager
def _update_audit(backend: DatabaseBackend, dialect: str) -> Iterator[None]:
    """Record any UPDATE of a bridge-owned clinical row or link."""
    audits = (("omop", "measurement", "measurement_id"),
              ("omop", "observation", "observation_id"),
              ("naaccr", "value_event", "naaccr_value_id"),
              ("omop", "condition_occurrence", "condition_occurrence_id"),
              ("naaccr", "group_condition", "report_group_id"),
              ("omop", "episode", "episode_id"),
              ("naaccr", "person_episode", "episode_id"),
              ("omop", "episode_event", "episode_id"))
    created: list[tuple[str, str]] = []
    try:
        for schema, table, key in audits:
            backend.execute(f"CREATE TABLE {schema}.bridge_{table}_update_test (id INT NOT NULL)")
            created.append((schema, table))
            backend.execute(
                f"CREATE TRIGGER {schema}.bridge_{table}_update_audit AFTER UPDATE ON {table} "
                f"BEGIN INSERT INTO bridge_{table}_update_test VALUES (NEW.{key}); END"
                if dialect == "sqlite" else
                f"CREATE TRIGGER {schema}.bridge_{table}_update_audit ON {schema}.{table} "
                f"AFTER UPDATE AS INSERT INTO {schema}.bridge_{table}_update_test "
                f"SELECT {key} FROM inserted"
            )
        yield
        for schema, table in created:
            assert _count(backend, f"{schema}.bridge_{table}_update_test") == 0, table
    finally:
        for schema, table in created:
            backend.execute(f"DROP TRIGGER IF EXISTS {schema}.bridge_{table}_update_audit")
            backend.execute(f"DROP TABLE {schema}.bridge_{table}_update_test")


@DIALECTS
def test_supersession_replaces_clinical_rows_and_an_unchanged_rerun_updates_nothing(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-10, OMOP-05, OMOP-06: atomic replacement of one group's rows."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        size = {"item_num": 3605, "value_num": "2.5", "unit_source": "cm",
                "observation_date": _day(2024, 1, 2)}
        unicode_text = {"ecp_code": "22637.100004300", "value_text": "Clinical café, 漢字."}
        source.patient("P", [size, dict(size), {"item_num": 3827, "value_code": "1"},
                             unicode_text], narrative="First.")
        predecessor = source.last_report_id
        source.patient("Q", [dict(size), {"item_num": 3803, "value_text": "Other group"}])
        other_report = source.last_report_id
        run_bridge(backend, load_manifest())
        before = _owned(backend, predecessor)
        # Two identical answers stay two rows that differ only in their ID.
        assert [row[2:] for row in before if row[0] == "measurement"] == [before[0][2:]] * 2
        assert len(before) == 4
        other = _owned(backend, other_report)
        assert len(other) == 2

        source.patient("P", [size, dict(size), {"item_num": 3827, "value_code": "0"}],
                       narrative="Corrected.")
        successor = source.last_report_id
        supersede_and_refresh(backend, load_manifest(), predecessor, successor)

        assert _owned(backend, predecessor) == []
        after = _owned(backend, successor)
        assert len(after) == 3
        assert [row[2:] for row in after if row[0] == "measurement"] == [after[0][2:]] * 2
        assert {event["sdc_report_id"] for event in _events(backend)} == {successor, other_report}
        # Unrelated rows keep their IDs and every byte; source history is retained.
        assert _owned(backend, other_report) == other
        assert _count(backend, "naaccr.naaccr_value") == 4 + 2 + 3
        _assert_no_orphans(backend)
        # OMOP-05: the group's rows equal the selected version's answers, not N x M.
        assert _count(backend, "omop.measurement") + _count(backend, "omop.observation") \
            == _count(backend, "naaccr.value_event") == 3 + 2

        before_rerun = _snapshot(backend)
        with _update_audit(backend, dialect):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before_rerun


@DIALECTS
def test_unchanged_non_ascii_and_truncated_values_rerun_without_updates(
    dialect: str, tmp_path: Path,
) -> None:
    """OMOP-06: stored-type comparisons, including lossy and cut text."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [
            {"ecp_code": "22637.100004300", "value_text": "Clinical café, 漢字. " * 4},
            {"ecp_code": "22638.100004300", "value_code": "Stage ii ", "value_num": "3",
             "unit_source": "mm"},
            {"item_num": 3827, "value_code": "0", "observation_date": _day(2024, 1, 2)},
        ])
        run_bridge(backend, load_manifest())
        before = _snapshot(backend)
        with _update_audit(backend, dialect):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before


@DIALECTS
def test_every_clinical_row_walks_to_its_exact_message_bytes(
    dialect: str, tmp_path: Path,
) -> None:
    """OMOP-07: clinical row -> value_event -> naaccr_value -> envelope -> raw bytes."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [{"item_num": 3827, "value_code": "0"}, _clinical(_day(2024, 1, 2))])
        source.patient("P", [{"item_num": 3803, "value_text": "Late"}], loinc="11529-5")
        source.patient("Q", _routing_values())
        run_bridge(backend, load_manifest())
        walk = backend.fetch_all(
            "SELECT e.event_table, e.note_id, v.sdc_report_id, link.note_id, m.raw_blob, "
            "r.inbound_envelope_id, v.inbound_envelope_id "
            "FROM (SELECT 'measurement' AS event_table, measurement_id AS id, "
            "measurement_event_id AS note_id FROM omop.measurement UNION ALL "
            "SELECT 'observation', observation_id, observation_event_id FROM omop.observation) e "
            "JOIN naaccr.value_event l ON l.event_table = e.event_table AND l.event_id = e.id "
            "JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id "
            "JOIN sdc.note_report link ON link.sdc_report_id = v.sdc_report_id "
            "JOIN sdc.sdc_report r ON r.sdc_report_id = v.sdc_report_id "
            "JOIN intake.inbound_envelope env ON env.inbound_envelope_id = v.inbound_envelope_id "
            "JOIN intake.inbound_message m ON m.inbound_message_id = env.inbound_message_id"
        )
        assert len(walk) == _count(backend, "omop.measurement") + _count(
            backend, "omop.observation") == 3 + len(_routing_values())
        for _table, event_note, report, link_note, raw, report_envelope, value_envelope in walk:
            assert bytes(raw) == source.raw[int(report)]
            assert event_note == link_note
            assert report_envelope == value_envelope
        assert {int(row[2]) for row in walk} == set(source.raw)


@DIALECTS
def test_exact_byte_resend_before_the_first_bridge_does_not_double_rows(
    dialect: str, tmp_path: Path,
) -> None:
    """OMOP-06a on the runner."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [{"item_num": 3827, "value_code": "0"}, _clinical(_day(2024, 1, 2))])
        source.resend_last()
        assert _count(backend, "intake.inbound_message") == 2
        run_bridge(backend, load_manifest())
        assert _count(backend, "omop.measurement") + _count(backend, "omop.observation") == 2
        assert _count(backend, "naaccr.value_event") == 2


@DIALECTS
def test_undated_values_use_their_report_day_or_fail_and_roll_back(
    dialect: str, tmp_path: Path,
) -> None:
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("dated", [_clinical(_day(2024, 8, 1)), {"item_num": 3605, "value_num": "1"}],
                       report_date=_day(2024, 8, 9))
        run_bridge(backend, load_manifest())
        assert [event["event_date"] for event in _events(backend)] == ["2024-08-01", "2024-08-09"]
        before = _snapshot(backend)

        # The dated value dates the note and the period; its undated sibling has no day.
        source.patient("undated", [_clinical(_day(2024, 1, 2)), {"item_num": 3605, "value_num": "2"}],
                       report_date={"y": 2024, "m": 1, "d": None, "precision": "month"})
        report = source.last_report_id
        undated = backend.fetch_one(
            "SELECT naaccr_value_id FROM naaccr.naaccr_value WHERE sdc_report_id = ? "
            "AND item_num = 3605", (report,),
        )[0]
        with pytest.raises(BridgeError) as error:
            run_bridge(backend, load_manifest())
        text = str(error.value)
        assert "3_measurement_observation.sql: 1 source row(s) cannot be bridged" in text
        assert (f"naaccr.naaccr_value {undated} (sdc_report {report}): "
                "no day-precision clinical date") in text
        assert _snapshot(backend) == before
        assert _last_run(backend)[:2] == ("bridge", "failed")


@DIALECTS
def test_over_length_text_is_cut_to_omop_limits_and_flagged(
    dialect: str, tmp_path: Path,
) -> None:
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        text = "".join(chr(ord("a") + index % 26) for index in range(70))
        source.patient("P", [
            {"obx_sub_id": "text", "ecp_code": "22637.100004300", "value_text": text},
            {"obx_sub_id": "text-60", "ecp_code": "22637.100004300", "value_text": text[:60]},
            {"obx_sub_id": "code", "item_num": 3605, "value_code": "C" * 51},
            {"obx_sub_id": "unit", "item_num": 3605, "value_num": "1", "unit_source": "u" * 50},
            {"obx_sub_id": "measured-text", "item_num": 3605, "value_text": text[:55]},
            {"obx_sub_id": "dated", **_clinical(_day(2024, 1, 2))},
        ])
        run_bridge(backend, load_manifest())
        events = _by_label(backend)
        cut = {label: (event["value_as_string"], event["value_source_value"],
                       event["unit_source_value"], event["is_truncated"])
               for label, event in events.items() if label != "dated"}
        assert cut == {
            "text": (text[:60], text[:50], None, 1),
            # 60 characters fit value_as_string; value_source_value is still cut.
            "text-60": (text[:60], text[:50], None, 1),
            "code": (None, "C" * 50, None, 1),
            "unit": (None, None, "u" * 50, 0),
            # Measurement has no value_as_string, so only the 50-character limit applies.
            "measured-text": (None, text[:50], None, 1),
        }
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before


def test_utf8_text_is_cut_on_character_boundaries_and_long_ckeys_fail(tmp_path: Path) -> None:
    with _mapped_database(
        "sqlserver", tmp_path, sqlserver_env="SDC_CDM_BRIDGE_UTF8_SQLSERVER_CONNECTION_STRING",
    ) as (backend, _target):
        collation = backend.fetch_one(
            "SELECT CONVERT(varchar(128), DATABASEPROPERTYEX(DB_NAME(), 'Collation'))"
        )[0]
        assert collation.endswith("_UTF8"), "this regression requires a UTF-8 database"
        source = _Source(backend)
        # Three bytes per character: 21 characters are 63 bytes.
        text = "漢" * 21
        source.patient("P", [
            {"obx_sub_id": "wide", "ecp_code": "22637.100004300", "value_text": text},
            {"obx_sub_id": "unit", "item_num": 3605, "value_num": "1", "unit_source": "é" * 26,
             "observation_date": _day(2024, 1, 2)},
        ])
        run_bridge(backend, load_manifest())
        events = _by_label(backend)
        assert (events["wide"]["value_as_string"], events["wide"]["value_source_value"],
                events["wide"]["is_truncated"]) == ("漢" * 20, "漢" * 16, 1)
        assert (events["unit"]["unit_source_value"], events["unit"]["is_truncated"]) == (
            "é" * 25, 1)
        assert tuple(backend.fetch_one(
            "SELECT DATALENGTH(value_as_string), DATALENGTH(value_source_value) "
            "FROM omop.observation"
        )) == (60, 48)
        before = _snapshot(backend)
        with _update_audit(backend, "sqlserver"):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before

        # An identifier is never cut: 26 two-byte characters fit 50 characters, not 50 bytes.
        source.patient("P", [{"ecp_code": "é" * 26, "value_num": "1",
                              "observation_date": _day(2024, 1, 3)}], accession="WIDE")
        report = source.last_report_id
        value = backend.fetch_one(
            "SELECT naaccr_value_id FROM naaccr.naaccr_value WHERE sdc_report_id = ?", (report,),
        )[0]
        with pytest.raises(BridgeError) as error:
            run_bridge(backend, load_manifest())
        assert (f"naaccr.naaccr_value {value} (sdc_report {report}): "
                "ecp_code exceeds the 50-byte source value limit") in str(error.value)
        assert _snapshot(backend) == before


@DIALECTS
def test_a_clinical_row_without_a_link_is_never_adopted_or_changed(
    dialect: str, tmp_path: Path,
) -> None:
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        person = source.patient("P", [{"item_num": 3605, "value_num": "2.5", "unit_source": "cm",
                                       "observation_date": _day(2024, 1, 2)}])
        predecessor = source.last_report_id
        run_bridge(backend, load_manifest())
        (event,) = _events(backend)
        constants = _constants(backend)
        # Same person, note, content, and event field as the bridge row, but no link.
        backend.execute(
            "INSERT INTO omop.measurement (person_id, measurement_concept_id, measurement_date, "
            "measurement_type_concept_id, value_as_number, measurement_source_value, "
            "measurement_source_concept_id, unit_source_value, measurement_event_id, "
            "meas_event_field_concept_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (person, 9004, event["event_date"], constants["measurement_type_registry"], 2.5,
             "3605", event["source_concept_id"], "cm", event["note_id"],
             constants["field_note_note_id"]),
        )
        foreign = backend.fetch_all("SELECT * FROM omop.measurement WHERE measurement_id NOT IN "
                                    "(SELECT event_id FROM naaccr.value_event)")
        assert len(foreign) == 1
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before
        source.patient("P", [{"item_num": 3605, "value_num": "3",
                              "observation_date": _day(2024, 1, 3)}])
        supersede_and_refresh(backend, load_manifest(), predecessor, source.last_report_id)
        assert [tuple(row) for row in backend.fetch_all(
            "SELECT * FROM omop.measurement WHERE measurement_id NOT IN "
            "(SELECT event_id FROM naaccr.value_event)"
        )] == [tuple(row) for row in foreign]
        assert _count(backend, "omop.measurement") == 2


@DIALECTS
def test_superseded_clinical_ids_are_never_reused(dialect: str, tmp_path: Path) -> None:
    """A deleted event ID never identifies a different source occurrence."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        source.patient("P", [{"item_num": 3605, "value_num": "1", "observation_date": _day(2024, 1, 2)},
                             {"ecp_code": "22637.100004300", "value_text": "Old text",
                              "observation_date": _day(2024, 1, 2)}])
        predecessor = source.last_report_id
        run_bridge(backend, load_manifest())
        before = {(event["event_table"], event["event_id"]) for event in _events(backend)}
        source.patient("P", [{"item_num": 3605, "value_num": "2", "observation_date": _day(2024, 1, 3)},
                             {"ecp_code": "22637.100004300", "value_text": "New text",
                              "observation_date": _day(2024, 1, 3)}])
        supersede_and_refresh(backend, load_manifest(), predecessor, source.last_report_id)
        after = {(event["event_table"], event["event_id"]) for event in _events(backend)}
        assert len(after) == 2 and not before & after


@DIALECTS
def test_a_deleted_owned_row_is_repaired_and_a_late_value_is_appended(
    dialect: str, tmp_path: Path,
) -> None:
    """Retired old-bridge regressions: a partial load is repaired per value, and a value
    appended to an already-bridged report gets its own row without touching the note."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        person = source.patient("P", [
            {"item_num": 3605, "value_num": "1", "observation_date": _day(2024, 1, 2)},
            {"item_num": 3605, "value_num": "2", "observation_date": _day(2024, 1, 2)},
        ])
        report = source.last_report_id
        run_bridge(backend, load_manifest())
        notes = _notes(backend)
        first, second = _events(backend)
        backend.execute("DELETE FROM omop.measurement WHERE measurement_id = ?",
                        (second["event_id"],))

        run_bridge(backend, load_manifest())
        repaired = _events(backend)
        assert [event["naaccr_value_id"] for event in repaired] == [
            first["naaccr_value_id"], second["naaccr_value_id"]]
        assert repaired[0] == first
        # The lost row is re-created under a new ID and its link follows it.
        assert repaired[1]["event_id"] != second["event_id"]
        assert {key: value for key, value in repaired[1].items() if key != "event_id"} == {
            key: value for key, value in second.items() if key != "event_id"}
        _assert_no_orphans(backend)

        envelope = backend.fetch_one(
            "SELECT inbound_envelope_id, episode_key, dd_version_id FROM naaccr.naaccr_value "
            "WHERE naaccr_value_id = ?", (first["naaccr_value_id"],),
        )
        backend.execute(
            "INSERT INTO naaccr.naaccr_value (person_id, episode_key, sdc_report_id, "
            "report_accession, item_num, value_num, observation_date, dd_version_id, "
            "inbound_envelope_id, obx_sub_id) VALUES (?, ?, ?, ?, 3605, 3, '2024-01-02', ?, ?, "
            "'late')",
            (person, envelope[1], report, f"ACC-{source.token}", envelope[2], envelope[0]),
        )
        run_bridge(backend, load_manifest())
        events = _events(backend)
        assert len(events) == 3
        assert events[:2] == repaired
        assert (events[2]["label"], events[2]["value_as_number"], events[2]["note_id"]) == (
            "late", 3.0, first["note_id"])
        assert _notes(backend) == notes
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before


@DIALECTS
def test_report_day_of_an_undated_value_bounds_the_period_and_dates_the_event(
    dialect: str, tmp_path: Path,
) -> None:
    """Script 1 and script 3 share the date rule, so every event is inside its period."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        undated = source.patient("undated", [{"item_num": 3605, "value_num": "1"}],
                                 report_date=_day(2024, 8, 9))
        undated_envelope = source.envelope_id(undated, "60569-1")
        mixed = source.patient("mixed", [_clinical(_day(2024, 1, 2)),
                                         {"item_num": 3605, "value_num": "2"}],
                               report_date=_day(2024, 8, 9))
        mixed_envelope = source.envelope_id(mixed, "60569-1")
        run_bridge(backend, load_manifest())
        rows = backend.fetch_all(
            "SELECT o.person_id, o.observation_period_start_date, "
            "o.observation_period_end_date, d.derivation, d.start_naaccr_value_id, "
            "d.start_inbound_envelope_id, d.end_naaccr_value_id, d.end_inbound_envelope_id "
            "FROM omop.observation_period o JOIN etl.observation_period_derivation d "
            "ON d.observation_period_id = o.observation_period_id ORDER BY o.person_id"
        )
        assert [tuple(_normalize(value) for value in row) for row in rows] == [
            (undated, "2024-08-09", "2024-08-09", "clinical_date_span",
             None, undated_envelope, None, undated_envelope),
            (mixed, "2024-01-02", "2024-08-09", "clinical_date_span",
             source.value_id(mixed, observation_date="2024-01-02"), None,
             None, mixed_envelope),
        ]
        outside = backend.fetch_one(
            "SELECT COUNT(*) FROM (SELECT person_id, measurement_date AS day "
            "FROM omop.measurement UNION ALL SELECT person_id, observation_date "
            "FROM omop.observation) e JOIN omop.observation_period p "
            "ON p.person_id = e.person_id WHERE e.day < p.observation_period_start_date "
            "OR e.day > p.observation_period_end_date"
        )[0]
        assert outside == 0
        assert sorted(event["event_date"] for event in _events(backend)) == [
            "2024-01-02", "2024-08-09", "2024-08-09"]


# Phase 4.4: thin conditions and episodes.

CONDITIONS = (
    "SELECT l.report_group_id, l.naaccr_value_id, l.condition_target, "
    "o.condition_occurrence_id, o.person_id, o.condition_concept_id, o.condition_start_date, "
    "o.condition_type_concept_id, o.condition_source_value, o.condition_source_concept_id "
    "FROM naaccr.group_condition l JOIN omop.condition_occurrence o "
    "ON o.condition_occurrence_id = l.condition_occurrence_id ORDER BY l.report_group_id"
)
CONDITION_COLUMNS = (
    "report_group_id", "naaccr_value_id", "condition_target", "condition_occurrence_id",
    "person_id", "concept_id", "start_date", "type_concept_id", "source_value",
    "source_concept_id",
)
EPISODES = (
    "SELECT e.episode_id, e.person_id, l.episode_key, e.episode_concept_id, "
    "e.episode_start_date, e.episode_object_concept_id, e.episode_type_concept_id, "
    "e.episode_source_concept_id FROM omop.episode e "
    "JOIN naaccr.person_episode l ON l.episode_id = e.episode_id ORDER BY e.episode_id"
)
EPISODE_COLUMNS = (
    "episode_id", "person_id", "episode_key", "concept_id", "start_date", "object_concept_id",
    "type_concept_id", "source_concept_id",
)
UNSET_4 = {
    "omop.condition_occurrence": (
        "condition_start_datetime", "condition_end_date", "condition_end_datetime",
        "condition_status_concept_id", "stop_reason", "provider_id", "visit_occurrence_id",
        "visit_detail_id", "condition_status_source_value",
    ),
    "omop.episode": (
        "episode_start_datetime", "episode_end_date", "episode_end_datetime",
        "episode_parent_id", "episode_number", "episode_source_value",
    ),
}


def _site(code: str | None = None, *, text: str | None = None, label: str | None = None,
          observation_date: dict | None = None) -> dict:
    value: dict = {"item_num": PRIMARY_SITE}
    if code is not None:
        value["value_code"] = code
    if text is not None:
        value["value_text"] = text
    if label is not None:
        value["obx_sub_id"] = label
    if observation_date is not None:
        value["observation_date"] = observation_date
    return value


def _conditions(backend: DatabaseBackend) -> list[dict[str, object]]:
    return [dict(zip(CONDITION_COLUMNS, (_normalize(value) for value in row), strict=True))
            for row in backend.fetch_all(CONDITIONS)]


def _episodes(backend: DatabaseBackend) -> list[dict[str, object]]:
    return [dict(zip(EPISODE_COLUMNS, (_normalize(value) for value in row), strict=True))
            for row in backend.fetch_all(EPISODES)]


def _group(backend: DatabaseBackend, report_id: int) -> int:
    return int(backend.fetch_one(
        "SELECT report_group_id FROM naaccr.report_version WHERE sdc_report_id = ?",
        (report_id,),
    )[0])


def _site_source_concepts(backend: DatabaseBackend) -> dict[str, int]:
    return {str(row[0]): int(row[1]) for row in backend.fetch_all(
        "SELECT code, source_concept_id FROM naaccr.naaccr_value_concept_map WHERE item_num = ?",
        (PRIMARY_SITE,),
    )}


def _episode_events(backend: DatabaseBackend) -> list[tuple[int, int, int]]:
    return sorted((int(row[0]), int(row[1]), int(row[2])) for row in backend.fetch_all(
        "SELECT episode_id, episode_event_field_concept_id, event_id FROM omop.episode_event"
    ))


def _owned_4(backend: DatabaseBackend, report_group_id: int, person_id: int) -> dict:
    """One group's condition, its person's episodes, and their events, in full."""
    return {
        "condition": [tuple(_normalize(value) for value in row) for row in backend.fetch_all(
            "SELECT o.* FROM omop.condition_occurrence o JOIN naaccr.group_condition l "
            "ON l.condition_occurrence_id = o.condition_occurrence_id "
            "WHERE l.report_group_id = ?", (report_group_id,),
        )],
        "episode": [tuple(_normalize(value) for value in row) for row in backend.fetch_all(
            "SELECT * FROM omop.episode WHERE person_id = ? ORDER BY episode_id", (person_id,),
        )],
        "events": sorted(tuple(row) for row in backend.fetch_all(
            "SELECT x.episode_id, x.event_id, x.episode_event_field_concept_id "
            "FROM omop.episode_event x JOIN omop.episode e ON e.episode_id = x.episode_id "
            "WHERE e.person_id = ?", (person_id,),
        )),
    }


@DIALECTS
def test_one_thin_condition_per_selected_group_with_a_primary_site(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-11, OMOP-12 (4.4 part): condition slots, targets, and constants."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        reports: dict[str, int] = {}
        persons: dict[str, int] = {}

        def send(label: str, values: list[dict], **kwargs: object) -> None:
            persons[label] = source.patient(label, values, **kwargs)
            reports[label] = source.last_report_id

        # The lowest site value wins; a later repeat in the same group is ignored.
        send("mapped", [_site("C504", observation_date=_day(2024, 3, 4)), _site("C500"),
                        _clinical(_day(2024, 1, 2))])
        send("no-target", [_site("C500")])
        send("no-map", [_site("C999")])
        send("text", [_site(text="Left breast, upper outer")])
        send("other-domain", [_site("C619")])
        send("collision", [_site("C509")])
        # A blank site value is skipped in favor of the next non-blank one.
        send("blank-first", [_site("  "), _site(text=""), _site("C504")])
        send("blank", [_site("  "), {"item_num": 3605, "value_num": "1"}])
        send("site-less", [_clinical(_day(2024, 1, 2))])
        send("narrative", [], narrative_date=_day(2024, 7, 4))
        run_bridge(backend, load_manifest())

        constants = _constants(backend)
        sources = _site_source_concepts(backend)
        conditions = {
            next(label for label, report in reports.items()
                 if _group(backend, report) == row["report_group_id"]): row
            for row in _conditions(backend)
        }
        expected = {
            "mapped": ("mapped", 9005, sources["C504"], "C504", "2024-03-04"),
            "no-target": ("no_target", 0, sources["C500"], "C500", REPORT_DAY),
            "no-map": ("no_map", 0, 0, "C999", REPORT_DAY),
            "text": ("no_map", 0, 0, "Left breast, upper outer", REPORT_DAY),
            "other-domain": ("other_domain", 0, sources["C619"], "C619", REPORT_DAY),
            "collision": ("collision_suppressed", 0, sources["C509"], "C509", REPORT_DAY),
            "blank-first": ("mapped", 9005, sources["C504"], "C504", REPORT_DAY),
        }
        assert {label: (row["condition_target"], row["concept_id"], row["source_concept_id"],
                        row["source_value"], row["start_date"])
                for label, row in conditions.items()} == expected
        for label, row in conditions.items():
            assert row["person_id"] == persons[label]
            assert row["type_concept_id"] == constants["condition_type_registry"] == 32879
            # The chosen value is the group's lowest non-blank site value.
            chosen = backend.fetch_one(
                "SELECT MIN(naaccr_value_id) FROM naaccr.naaccr_value WHERE sdc_report_id = ? "
                "AND item_num = 400 AND (TRIM(value_code) <> '' OR TRIM(value_text) <> '')",
                (reports[label],),
            )[0]
            assert row["naaccr_value_id"] == chosen
        for table, columns in UNSET_4.items():
            assert backend.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE "
                + " OR ".join(f"{column} IS NOT NULL" for column in columns)
            )[0] == 0
        # OMOP-12: a nonzero condition target is a standard Condition-domain concept.
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.condition_occurrence o JOIN omop.concept c "
            "ON c.concept_id = o.condition_concept_id WHERE c.concept_id <> 0 "
            "AND (c.standard_concept IS NULL OR c.standard_concept <> 'S' "
            "OR c.domain_id <> 'Condition')"
        )[0] == 0
        assert _count(backend, "omop.condition_occurrence") == len(expected)

        before = _snapshot(backend)
        with _update_audit(backend, dialect):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before


@DIALECTS
def test_episodes_group_by_tumor_within_a_person_and_link_every_event(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-11, OMOP-11/12 (4.4 part): episode grain, slots, and event links."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        tumor = {"assigning_authority": "SYNTHLAB", "episode_source_value": "TUMOR-1",
                 "sequence_number": 1}
        # The same accession under two patients is two tumors.
        shared_p = source.patient("P", [_site("C504"), _clinical(_day(2024, 1, 2))],
                                  accession="SHARED")
        shared_q = source.patient("Q", [_site("C504"), _clinical(_day(2024, 1, 3))],
                                  accession="SHARED")
        # Two accessions with one source tumor identity are one episode; the object
        # concept skips the lower group's unmapped site for the next nonzero one.
        same = source.patient("R", [_site("C500"), _clinical(_day(2024, 2, 1))],
                              accession="R1", episode=tumor)
        same_first = source.last_report_id
        source.patient("R", [_site("C504"), {"ecp_code": "22637.100004300",
                                             "value_text": "Text", "observation_date":
                                             _day(2024, 1, 15)}],
                       accession="R2", episode=tumor)
        # Without that identity, two accessions are two episodes.
        split = source.patient("S", [_clinical(_day(2024, 3, 1))], accession="S1")
        source.patient("S", [_clinical(_day(2024, 4, 1))], accession="S2")
        run_bridge(backend, load_manifest())

        episodes = _episodes(backend)
        by_person: dict[int, list[dict[str, object]]] = {}
        for episode in episodes:
            by_person.setdefault(int(episode["person_id"]), []).append(episode)
        assert {person: len(rows) for person, rows in by_person.items()} == {
            shared_p: 1, shared_q: 1, same: 1, split: 2}
        keys = {(int(row[0]), str(row[1])) for row in backend.fetch_all(
            "SELECT DISTINCT person_id, episode_key FROM naaccr.naaccr_value")}
        assert {(int(e["person_id"]), str(e["episode_key"])) for e in episodes} == keys
        assert by_person[same][0]["episode_key"].startswith("e:")
        assert by_person[same][0]["start_date"] == "2024-01-15"
        assert by_person[same][0]["object_concept_id"] == 9005
        assert by_person[shared_p][0]["object_concept_id"] == 9005
        assert by_person[shared_p][0]["start_date"] == "2024-01-02"
        assert {e["object_concept_id"] for e in by_person[split]} == {0}
        assert sorted(e["start_date"] for e in by_person[split]) == ["2024-03-01", "2024-04-01"]
        assert _group(backend, same_first) != _group(backend, source.last_report_id)

        constants = _constants(backend)
        for episode in episodes:
            assert (episode["concept_id"], episode["type_concept_id"],
                    episode["source_concept_id"]) == (
                constants["episode_disease"], constants["episode_type_registry"],
                constants["unmapped"])
        assert (constants["episode_disease"], constants["episode_type_registry"]) == (32533, 32879)
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.episode e JOIN omop.concept c "
            "ON c.concept_id = e.episode_object_concept_id WHERE c.concept_id <> 0 "
            "AND (c.standard_concept <> 'S' OR c.domain_id <> 'Condition')"
        )[0] == 0
        for table, columns in UNSET_4.items():
            assert backend.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE "
                + " OR ".join(f"{column} IS NOT NULL" for column in columns)
            )[0] == 0

        # Every event references an existing row with its field constant, and every
        # measurement, observation, and condition is linked exactly once.
        assert _orphan_episode_events(backend) == 0
        events = _episode_events(backend)
        assert len(events) == len(set(events)) == (
            _count(backend, "omop.measurement") + _count(backend, "omop.observation")
            + _count(backend, "omop.condition_occurrence")) == 10 + 4
        assert {field for _episode, field, _event in events} == {
            constants["field_measurement_measurement_id"],
            constants["field_observation_observation_id"],
            constants["field_condition_occurrence_id"]}
        # Each event belongs to its own person's episode.
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.episode_event x "
            "JOIN omop.episode e ON e.episode_id = x.episode_id "
            "LEFT JOIN omop.measurement m ON x.episode_event_field_concept_id = ? "
            "AND m.measurement_id = x.event_id "
            "LEFT JOIN omop.observation o ON x.episode_event_field_concept_id = ? "
            "AND o.observation_id = x.event_id "
            "LEFT JOIN omop.condition_occurrence c ON x.episode_event_field_concept_id = ? "
            "AND c.condition_occurrence_id = x.event_id "
            "WHERE COALESCE(m.person_id, o.person_id, c.person_id) <> e.person_id",
            (constants["field_measurement_measurement_id"],
             constants["field_observation_observation_id"],
             constants["field_condition_occurrence_id"]),
        )[0] == 0
        # OMOP-11: every episode starts inside its person's observation period.
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.episode e JOIN omop.observation_period p "
            "ON p.person_id = e.person_id WHERE e.episode_start_date "
            "< p.observation_period_start_date "
            "OR e.episode_start_date > p.observation_period_end_date"
        )[0] == 0

        before = _snapshot(backend)
        with _update_audit(backend, dialect):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before


def test_episode_constants_resolve_without_naaccr2026(tmp_path: Path) -> None:
    """The episode and event-field constants come from Athena vocabularies alone."""
    with _mapped_database("sqlite", tmp_path) as (backend, _target):
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.concept WHERE vocabulary_id = 'NAACCR2026'"
        )[0] == 0
        assert backend.fetch_one(
            "SELECT 1 FROM omop.vocabulary WHERE vocabulary_id = 'NAACCR2026'"
        ) is None
        constants = {str(row[0]): (str(row[1]), str(row[2]), int(row[3])) for row in
                     backend.fetch_all(
                         "SELECT constant_name, vocabulary_id, concept_code, concept_id "
                         "FROM etl.concept_constant")}
        (entry,) = [entry for entry in load_manifest().bridge_entries_for("sqlite")
                    if entry.path.endswith("4_condition_and_episode.sql")]
        assert {name: constants[name] for name in entry.constants} == {
            "condition_type_registry": ("Type Concept", "OMOP4976952", 32879),
            "episode_type_registry": ("Type Concept", "OMOP4976952", 32879),
            "episode_disease": ("Episode", "OMOP4822254", 32533),
            "field_measurement_measurement_id": ("CDM", "CDM194", 1147138),
            "field_observation_observation_id": ("CDM", "CDM221", 1147165),
            "field_condition_occurrence_id": ("CDM", "CDM183", 1147127),
            "unmapped": ("None", "No matching concept", 0),
        }
        _Source(backend).patient("P", [_site("C504"), _clinical(_day(2024, 1, 2))])
        run_bridge(backend, load_manifest())
        assert _count(backend, "omop.episode") == 1
        # The site value's measurement, the clinical measurement, and the condition.
        assert _count(backend, "omop.episode_event") == 3


@DIALECTS
def test_supersession_replaces_condition_episode_and_events_atomically(
    dialect: str, tmp_path: Path,
) -> None:
    """BRIDGE-10 (4.4 part), BRIDGE-11: no obsolete condition, episode, or event survives."""
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        person = source.patient("P", [_site("C504"), _clinical(_day(2024, 1, 2))])
        first = source.last_report_id
        group = _group(backend, first)
        other = source.patient("Q", [_site("C500"), _clinical(_day(2024, 2, 3))])
        other_group = _group(backend, source.last_report_id)
        run_bridge(backend, load_manifest())
        (condition,) = [row for row in _conditions(backend) if row["report_group_id"] == group]
        (episode,) = [row for row in _episodes(backend) if row["person_id"] == person]
        untouched = _owned_4(backend, other_group, other)
        deleted_events = {event for event in _episode_events(backend)
                          if event[0] == episode["episode_id"]}

        # A changed site updates the group's condition in place.
        source.patient("P", [_site("C619"), _clinical(_day(2024, 1, 5))])
        second = source.last_report_id
        supersede_and_refresh(backend, load_manifest(), first, second)
        (changed,) = [row for row in _conditions(backend) if row["report_group_id"] == group]
        assert changed["condition_occurrence_id"] == condition["condition_occurrence_id"]
        assert (changed["condition_target"], changed["concept_id"], changed["source_value"],
                changed["start_date"]) == ("other_domain", 0, "C619", REPORT_DAY)
        (kept,) = [row for row in _episodes(backend) if row["person_id"] == person]
        assert kept["episode_id"] == episode["episode_id"]
        assert (kept["object_concept_id"], kept["start_date"]) == (0, "2024-01-05")
        events = {event for event in _episode_events(backend)
                  if event[0] == episode["episode_id"]}
        assert len(events) == 3
        # The condition event is the same row; the clinical events are new rows.
        assert len(events & deleted_events) == 1
        _assert_no_orphans(backend)
        assert _owned_4(backend, other_group, other) == untouched

        # A successor without a site removes the condition, and a new tumor identity
        # replaces the episode; neither ID is reused.
        source.patient("P", [_clinical(_day(2024, 1, 6))],
                       episode={"episode_source_value": "TUMOR-9"})
        third = source.last_report_id
        supersede_and_refresh(backend, load_manifest(), second, third)
        assert [row for row in _conditions(backend) if row["report_group_id"] == group] == []
        (replaced,) = [row for row in _episodes(backend) if row["person_id"] == person]
        assert replaced["episode_id"] != episode["episode_id"]
        assert str(replaced["episode_key"]).startswith("e:")
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.episode_event WHERE episode_id = ?",
            (episode["episode_id"],),
        )[0] == 0
        assert len([event for event in _episode_events(backend)
                    if event[0] == replaced["episode_id"]]) == 1
        _assert_no_orphans(backend)
        assert _owned_4(backend, other_group, other) == untouched
        assert _count(backend, "omop.condition_occurrence") == 1
        assert _count(backend, "omop.episode") == 2

        # A new group's condition never takes the deleted condition's ID.
        source.patient("R", [_site("C504"), _clinical(_day(2024, 5, 6))])
        run_bridge(backend, load_manifest())
        ids = {int(row["condition_occurrence_id"]) for row in _conditions(backend)}
        assert condition["condition_occurrence_id"] not in ids and len(ids) == 2

        before = _snapshot(backend)
        with _update_audit(backend, dialect):
            run_bridge(backend, load_manifest())
            assert _snapshot(backend) == before


@DIALECTS
def test_unowned_conditions_episodes_and_events_are_never_adopted_or_changed(
    dialect: str, tmp_path: Path,
) -> None:
    with _mapped_database(dialect, tmp_path) as (backend, _target):
        source = _Source(backend)
        person = source.patient("P", [_site("C504"), _clinical(_day(2024, 1, 2))])
        predecessor = source.last_report_id
        run_bridge(backend, load_manifest())
        (condition,) = _conditions(backend)
        (episode,) = _episodes(backend)
        constants = _constants(backend)
        # Same person and content as the bridge rows, but no link.
        backend.execute(
            "INSERT INTO omop.condition_occurrence (person_id, condition_concept_id, "
            "condition_start_date, condition_type_concept_id, condition_source_value, "
            "condition_source_concept_id) VALUES (?, ?, ?, ?, ?, ?)",
            (person, 9005, condition["start_date"], constants["condition_type_registry"],
             "C504", condition["source_concept_id"]),
        )
        backend.execute(
            "INSERT INTO omop.episode (person_id, episode_concept_id, episode_start_date, "
            "episode_object_concept_id, episode_type_concept_id, episode_source_concept_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (person, constants["episode_disease"], episode["start_date"], 9005,
             constants["episode_type_registry"], 0),
        )
        foreign_episode = backend.fetch_one(
            "SELECT MAX(episode_id) FROM omop.episode")[0]
        backend.execute(
            "INSERT INTO omop.episode_event (episode_id, event_id, "
            "episode_event_field_concept_id) VALUES (?, ?, ?)",
            (foreign_episode, condition["condition_occurrence_id"],
             constants["field_condition_occurrence_id"]),
        )
        foreign_sql = {
            "condition": "SELECT * FROM omop.condition_occurrence WHERE condition_occurrence_id "
                         "NOT IN (SELECT condition_occurrence_id FROM naaccr.group_condition)",
            "episode": "SELECT * FROM omop.episode WHERE episode_id NOT IN "
                       "(SELECT episode_id FROM naaccr.person_episode)",
            "events": "SELECT * FROM omop.episode_event WHERE episode_id NOT IN "
                      "(SELECT episode_id FROM naaccr.person_episode)",
        }

        def foreign() -> dict[str, list[tuple]]:
            return {name: [tuple(_normalize(value) for value in row)
                           for row in backend.fetch_all(sql)]
                    for name, sql in foreign_sql.items()}

        expected = foreign()
        assert {name: len(rows) for name, rows in expected.items()} == {
            "condition": 1, "episode": 1, "events": 1}
        before = _snapshot(backend)
        run_bridge(backend, load_manifest())
        assert _snapshot(backend) == before
        source.patient("P", [_clinical(_day(2024, 1, 3))])
        supersede_and_refresh(backend, load_manifest(), predecessor, source.last_report_id)
        assert foreign() == expected
        assert _conditions(backend) == []
        assert _count(backend, "omop.condition_occurrence") == 1
        assert _count(backend, "omop.episode") == 2
