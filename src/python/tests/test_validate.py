"""BRIDGE-12, OMOP-08, OMOP-10, OMOP-12, NAACCR-05/06: `sdc-cdm validate`.

Every test builds on test_bridge's per-test database, which it resets, so the
SQL Server cases share that module's dedicated database.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdc_cdm.bridge import run_bridge, run_validate, supersede_and_refresh
from sdc_cdm.bridge.seeds import (
    VALIDATE_THRESHOLD_COLUMNS,
    VALIDATE_THRESHOLDS_FILE,
    read_validate_thresholds,
)
from sdc_cdm.bridge.validate import CATEGORIES, ZERO_CATEGORIES
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.intake import ingest_message, load_message
from test_bridge import (
    DIALECTS,
    _clinical,
    _constants,
    _count,
    _database,
    _day,
    _events,
    _last_run,
    _mapped_database,
    _routing_values,
    _site,
    _snapshot,
    _Source,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = sorted((ROOT / "sample_data/naaccr_v2").glob("*.hl7"))
EXPECTED_OMOP = ROOT / "contracts/expected/naaccr_v2.omop.json"
SHIPPED_SEEDS = repository_path("database/seed")
COVERAGE = (
    "unmapped_ckey_values", "unmapped_item_values", "other_domain_item_values",
    "unmapped_value_codes", "unmapped_conditions", "item_numbers_not_in_dictionary",
)
# Coverage of _routing_values() plus one mapped primary site (C504).
ROUTED_COVERAGE = {
    "unmapped_ckey_values": 4, "unmapped_item_values": 4, "other_domain_item_values": 2,
    "unmapped_value_codes": 3, "unmapped_conditions": 0, "item_numbers_not_in_dictionary": 2,
}


def _thresholds(directory: Path, limits: dict[str, int]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines = [",".join(VALIDATE_THRESHOLD_COLUMNS)]
    lines += [f"{name},{limit},test limit" for name, limit in limits.items()]
    (directory / VALIDATE_THRESHOLDS_FILE).write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")
    return directory


def _validate(target: list[str], seeds: Path, capsys: pytest.CaptureFixture[str],
              ) -> tuple[int, dict[str, tuple[str, int, str, str]], str]:
    """Run the CLI; return its exit code, its check lines by name, and all output."""
    code = main(["validate", *target, "--seed-dir", str(seeds)])
    captured = capsys.readouterr()
    lines: dict[str, tuple[str, int, str, str]] = {}
    for line in captured.out.splitlines():
        parts = line.split(" | ")
        if len(parts) == 5 and parts[0] != "check":
            assert parts[0] not in lines
            lines[parts[0]] = (parts[1], int(parts[2]), parts[3], parts[4])
    return code, lines, captured.out + captured.err


def _assert_zero_categories_pass(lines: dict[str, tuple[str, int, str, str]]) -> None:
    zero = {name: line for name, line in lines.items() if line[0] in ZERO_CATEGORIES}
    assert zero
    assert {name: line for name, line in zero.items() if line[1:] != (0, "0", "PASS")} == {}


@contextmanager
def _routed_dataset(dialect: str, tmp_path: Path) -> Iterator[
        tuple[DatabaseBackend, list[str], _Source]]:
    """Every routing case and a mapped primary site, bridged."""
    with _mapped_database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        source.patient("routed", [*_routing_values(), _site("C504")])
        run_bridge(backend, load_manifest())
        yield backend, target, source


@DIALECTS
def test_validate_passes_and_reconciles_selected_historical_and_excluded_inputs(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """BRIDGE-12, OMOP-10: the shipped bridge's output passes every zero-category check."""
    with _mapped_database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        source.patient("routed", [*_routing_values(), _site("C504")])
        # OMOP-06b: an accession-less report of the same patient is excluded.
        source.patient("routed", [_clinical(_day(2024, 5, 7))], accession=None)
        # A one-day period, and an exact-byte resend counted as a content duplicate.
        source.patient("one-day", [_clinical(_day(2024, 6, 1))])
        source.resend_last()
        # Supersession history: the first version and its values stay as history.
        size = {"item_num": 3605, "value_num": "1", "observation_date": _day(2024, 1, 2)}
        site = _site("C509", observation_date=_day(2024, 1, 2))
        source.patient("superseded", [size, site])
        predecessor = source.last_report_id
        run_bridge(backend, load_manifest())
        source.patient("superseded", [dict(size, value_num="2"), dict(site)])
        supersede_and_refresh(backend, load_manifest(), predecessor, source.last_report_id)

        # The one-day CKey value and the selected C509 site value (no item target) add
        # to the routed coverage.
        coverage = dict(ROUTED_COVERAGE, unmapped_ckey_values=5, unmapped_item_values=5)
        seeds = _thresholds(tmp_path / "seeds", coverage)
        before = _snapshot(backend)
        code, lines, output = _validate(target, seeds, capsys)

        assert code == 0, output
        assert "validate PASS" in output
        _assert_zero_categories_pass(lines)
        assert {line[0] for line in lines.values()} == set(CATEGORIES)
        assert {name: line[1:] for name, line in lines.items() if line[0] == "coverage"} == {
            name: (limit, str(limit), "PASS") for name, limit in coverage.items()}
        assert {name: line[1] for name, line in lines.items() if line[0] == "report"} == {
            "reports_selected": 3,
            "reports_historical": 1,
            "reports_excluded_accessionless": 1,
            "values_historical": 2,
            "values_excluded": 1,
            "content_duplicate_messages": 1,
            "one_day_observation_periods": 2,
            # (3827, '1') and both C509 site values' events, plus the C509 condition.
            "collision_suppressed_values": 3,
            "truncated_values": 0,
            "unowned_omop_rows": 0,
        }
        assert all(line[2:] == ("-", "INFO") for line in lines.values() if line[0] == "report")
        # Validation reads; only its run row is written.
        assert _snapshot(backend) == before
        assert _last_run(backend)[:3] == ("validate", "succeeded", None)


def _break_note(backend: DatabaseBackend) -> None:
    note_id = _events(backend)[0]["note_id"]
    backend.execute("DELETE FROM omop.note WHERE note_id = ?", (note_id,))


def _owned_target(backend: DatabaseBackend) -> dict[str, object]:
    return next(event for event in _events(backend)
                if event["event_table"] == "measurement" and event["route"] == "target_domain")


def _non_standard_target(backend: DatabaseBackend) -> None:
    event = _owned_target(backend)
    # A NAACCR source concept is never standard.
    backend.execute("UPDATE omop.measurement SET measurement_concept_id = ? "
                    "WHERE measurement_id = ?", (event["source_concept_id"], event["event_id"]))


def _wrong_type(backend: DatabaseBackend) -> None:
    backend.execute("UPDATE omop.measurement SET measurement_type_concept_id = ? "
                    "WHERE measurement_id = ?",
                    (_constants(backend)["note_type_ehr"], _owned_target(backend)["event_id"]))


def _broken_envelope(backend: DatabaseBackend) -> None:
    backend.execute("UPDATE naaccr.naaccr_value SET inbound_envelope_id = -1 "
                    "WHERE naaccr_value_id = ?", (_owned_target(backend)["naaccr_value_id"],))


def _lost_event(backend: DatabaseBackend) -> None:
    backend.execute("DELETE FROM naaccr.value_event WHERE naaccr_value_id = ?",
                    (_owned_target(backend)["naaccr_value_id"],))


@DIALECTS
@pytest.mark.parametrize(("defect", "check"), (
    (_break_note, "measurement_orphan_note_event"),
    (_non_standard_target, "measurement_target_not_standard"),
    (_wrong_type, "measurement_constant_slots"),
    (_broken_envelope, "measurement_without_message"),
    (_lost_event, "selected_value_without_event"),
), ids=("orphan", "non-standard", "type-constant", "provenance", "reconciliation"))
def test_a_damaged_bridge_output_fails_and_names_the_check(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], defect, check: str,
) -> None:
    with _routed_dataset(dialect, tmp_path) as (backend, target, _source):
        seeds = _thresholds(tmp_path / "seeds", ROUTED_COVERAGE)
        assert _validate(target, seeds, capsys)[0] == 0
        defect(backend)
        code, lines, output = _validate(target, seeds, capsys)
        assert code == 1
        assert lines[check][1] >= 1 and lines[check][3] == "FAIL"
        assert "validate FAIL: " in output and f"{check}: " in output
        status, error = _last_run(backend)[1:3]
        assert status == "failed" and f"{check}: " in error


@DIALECTS
def test_coverage_is_judged_by_threshold_separately_from_structural_checks(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """BRIDGE-12: a breached threshold fails by name; raising it is the reviewed fix."""
    with _routed_dataset(dialect, tmp_path) as (_backend, target, _source):
        tight = dict(ROUTED_COVERAGE, unmapped_ckey_values=3)
        code, lines, output = _validate(target, _thresholds(tmp_path / "tight", tight), capsys)
        assert code == 1
        assert lines["unmapped_ckey_values"] == ("coverage", 4, "3", "FAIL")
        assert "unmapped_ckey_values: 4 exceeds 3" in output
        _assert_zero_categories_pass(lines)

        code, lines, output = _validate(
            target, _thresholds(tmp_path / "raised", ROUTED_COVERAGE), capsys)
        assert code == 0, output
        assert lines["unmapped_ckey_values"] == ("coverage", 4, "4", "PASS")

        missing = {name: limit for name, limit in ROUTED_COVERAGE.items()
                   if name != "unmapped_conditions"}
        code, lines, output = _validate(
            target, _thresholds(tmp_path / "missing", missing), capsys)
        assert code == 1
        assert lines["unmapped_conditions"] == ("coverage", 0, "-", "FAIL")
        assert f"unmapped_conditions: no row in {VALIDATE_THRESHOLDS_FILE}" in output

        unknown = dict(ROUTED_COVERAGE, retired_check=5)
        code, _lines, output = _validate(
            target, _thresholds(tmp_path / "unknown", unknown), capsys)
        assert code == 1
        assert f"retired_check: {VALIDATE_THRESHOLDS_FILE} names no coverage check" in output


@DIALECTS
@pytest.mark.parametrize(("content", "defect"), (
    (None, "not found at"),
    ("name,max_count,reason\nunmapped_ckey_values,4,x\n",
     "header must be check_name,max_count,reason"),
))
def test_an_unreadable_threshold_file_is_named_and_nothing_is_judged(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    content: str | None, defect: str,
) -> None:
    with _routed_dataset(dialect, tmp_path) as (backend, target, _source):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        if content is not None:
            (seeds / VALIDATE_THRESHOLDS_FILE).write_text(content, encoding="utf-8")
        code, lines, output = _validate(target, seeds, capsys)
        assert code == 1 and lines == {}
        assert "validate prerequisites are missing; nothing was written" in output
        assert f"seed {VALIDATE_THRESHOLDS_FILE}: {defect}" in output
        assert _last_run(backend)[:2] == ("validate", "failed")


@pytest.mark.parametrize(("content", "defect"), (
    ("check_name,max_count,reason\na,1,x\na,2,y\n", "line 3: check_name 'a' is repeated"),
    ("check_name,max_count,reason\na,-1,x\n", "must be a non-negative integer, got '-1'"),
    ("check_name,max_count,reason\na,1.5,x\n", "must be a non-negative integer, got '1.5'"),
    ("check_name,max_count,reason\na,1, \n", "line 2: reason for 'a' is required"),
    ("check_name,max_count,reason\n,1,x\n", "line 2: check_name is required"),
    ("check_name,max_count,reason\na,1\n", "line 2 has 2 fields, expected 3"),
))
def test_threshold_seed_defects_are_named(tmp_path: Path, content: str, defect: str) -> None:
    path = tmp_path / VALIDATE_THRESHOLDS_FILE
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=defect):
        read_validate_thresholds(path)


def test_shipped_thresholds_cover_exactly_the_coverage_checks() -> None:
    assert set(read_validate_thresholds(SHIPPED_SEEDS / VALIDATE_THRESHOLDS_FILE)) == set(
        COVERAGE)


@DIALECTS
def test_unknown_items_and_unmapped_pairs_are_counted_and_fail_only_by_threshold(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """NAACCR-05/06: an item outside the dictionary and unmapped item/value pairs are
    reported coverage; a CKey is never joined to item 3827 by its numeric prefix."""
    with _mapped_database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        source.patient("P", [
            {"item_num": 99999, "value_code": "7"},
            {"item_num": 1144, "value_code": "M1"},
            {"ecp_code": "3827.100004300", "value_code": "0"},
        ])
        run_bridge(backend, load_manifest())
        counts = {"unmapped_ckey_values": 1, "unmapped_item_values": 2,
                  "other_domain_item_values": 0, "unmapped_value_codes": 2,
                  "unmapped_conditions": 0, "item_numbers_not_in_dictionary": 1}

        code, lines, _output = _validate(
            target, _thresholds(tmp_path / "zero", dict.fromkeys(COVERAGE, 0)), capsys)
        assert code == 1
        _assert_zero_categories_pass(lines)
        assert {name: lines[name][1] for name in COVERAGE} == counts
        assert {name for name in COVERAGE if lines[name][3] == "FAIL"} == {
            name for name, count in counts.items() if count}

        code, lines, output = _validate(target, _thresholds(tmp_path / "raised", counts), capsys)
        assert code == 0, output


def _rows(backend: DatabaseBackend, sql: str) -> list[dict[str, object]]:
    cursor = backend.connection.cursor()
    cursor.execute(sql)
    names = [str(column[0]) for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


# (table, primary key) in an order where every reference names an earlier table.
OMOP_ROWS = (
    ("person", "person_id"), ("observation_period", "observation_period_id"),
    ("note", "note_id"), ("measurement", "measurement_id"),
    ("observation", "observation_id"), ("condition_occurrence", "condition_occurrence_id"),
    ("episode", "episode_id"),
)
REFERENCES = {
    "person_id": "person", "measurement_event_id": "note", "observation_event_id": "note",
    "episode_id": "episode",
}
EVENT_FIELDS = {
    "field_measurement_measurement_id": "measurement",
    "field_observation_observation_id": "observation",
    "field_condition_occurrence_id": "condition_occurrence",
}


def _normalized_omop(backend: DatabaseBackend) -> dict[str, list[dict[str, object]]]:
    """Bridge output with surrogate IDs as per-table ordinals and every concept as
    vocabulary_id/concept_code, so the expectation pins no concept or row ID."""
    concepts = {int(row[0]): f"{row[1]}/{row[2]}" for row in backend.fetch_all(
        "SELECT concept_id, vocabulary_id, concept_code FROM omop.concept")}
    constants = _constants(backend)
    fields = {constants[name]: table for name, table in EVENT_FIELDS.items()}
    ordinals: dict[str, dict[int, int]] = {}
    result: dict[str, list[dict[str, object]]] = {}

    def value(table: str, column: str, raw: object, row: dict[str, object]) -> object:
        if raw is None:
            return None
        if column.endswith("_concept_id"):
            return concepts[int(raw)]
        if column == f"{table}_id":
            return ordinals[table][int(raw)]
        if column in REFERENCES:
            return ordinals[REFERENCES[column]][int(raw)]
        if table == "episode_event" and column == "event_id":
            target = fields[int(row["episode_event_field_concept_id"])]
            return ordinals[target][int(raw)]
        if hasattr(raw, "isoformat"):
            return raw.isoformat()
        return float(raw) if column == "value_as_number" else raw

    for table, key in OMOP_ROWS:
        rows = _rows(backend, f"SELECT * FROM omop.{table} ORDER BY {key}")
        ordinals[table] = {int(row[key]): index for index, row in enumerate(rows, start=1)}
        result[table] = [{column: value(table, column, raw, row) for column, raw in row.items()}
                         for row in rows]
    events = _rows(backend, "SELECT * FROM omop.episode_event")
    result["episode_event"] = sorted(
        ({column: value("episode_event", column, raw, row) for column, raw in row.items()}
         for row in events),
        key=lambda row: (row["episode_id"], row["episode_event_field_concept_id"],
                         row["event_id"]),
    )
    return result


@DIALECTS
def test_hl7_fixtures_flow_through_intake_bridge_and_validate_to_expected_omop_rows(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """OMOP-08: every sample_data/naaccr_v2 fixture, with the shipped thresholds."""
    with _database(dialect, tmp_path) as (backend, target):
        algorithm = backend.fetch_one(
            "SELECT algorithm FROM naaccr.data_dictionary_version WHERE is_current = 1")[0]
        for path in FIXTURES:
            intake = ingest_message(backend, path.read_bytes(), parse_hl7,
                                    parser_name="hl7v2", parser_version="test")
            assert intake.parse_status == "parsed", path.name
            load_message(backend, intake.inbound_message_id, algorithm=algorithm)
        assert main(["bridge", *target]) == 0
        capsys.readouterr()

        code, lines, output = _validate(target, SHIPPED_SEEDS, capsys)
        assert code == 0, output
        _assert_zero_categories_pass(lines)
        assert {name: lines[name][1] for name in COVERAGE} == read_validate_thresholds(
            SHIPPED_SEEDS / VALIDATE_THRESHOLDS_FILE)

        actual = _normalized_omop(backend)
        assert _count(backend, "omop.person") == len(FIXTURES)
        expected = json.loads(EXPECTED_OMOP.read_text(encoding="utf-8"))
        assert expected["fixtures"] == [path.relative_to(ROOT).as_posix() for path in FIXTURES]
        assert actual == expected["tables"]


def test_run_validate_returns_every_check_once_in_script_order(tmp_path: Path) -> None:
    with _routed_dataset("sqlite", tmp_path) as (backend, _target, _source):
        result = run_validate(backend, load_manifest(),
                              seed_dir=_thresholds(tmp_path / "seeds", ROUTED_COVERAGE))
        assert result.passed and result.failures == ()
        names = [check.name for check in result.checks]
        assert len(names) == len(set(names))
        categories = [check.category for check in result.checks]
        assert categories == sorted(categories, key=CATEGORIES.index)
