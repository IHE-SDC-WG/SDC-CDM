"""CSV-01..06: `sdc-cdm export` writes one CSV per OMOP table plus manifest.json.

Every test builds on test_bridge's per-test database, which it resets, so the
SQL Server cases share that module's dedicated database.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdc_cdm import __version__
from sdc_cdm.bridge import run_bridge
from sdc_cdm.cdm.tables import (
    CLINICAL_TABLE_SPECS,
    TABLE_SPECS,
    VOCABULARY_SCHEMA,
    TableSpec,
    expected_headers,
)
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import suspend_constraints, verify_constraints
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.export import MANIFEST_FILE, ExportError, export_bundle
from sdc_cdm.export import bundle as bundle_module
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.intake import ingest_message, load_message
from sdc_cdm.maps.coverage import MAPPING_LAYERS
from sdc_cdm.vocab.extract import iter_table_rows
from sdc_cdm.vocab.loader import load_vocab
from test_bridge import (
    DIALECTS,
    RESET,
    _count,
    _database,
    _day,
    _last_run,
    _mapped_database,
    _normalize,
    _routing_values,
    _site,
    _Source,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = sorted((ROOT / "sample_data/naaccr_v2").glob("*.hl7"))
DDL = {
    "sqlite": ROOT / "database/schemas/omop/ddl/sqlite/1_OMOPCDM_sqlite_5.4_ddl.sql",
    "sqlserver": ROOT / "database/schemas/omop/ddl/sqlserver/1_OMOPCDM_sqlserver_5.4_ddl.sql",
}
# A narrative that needs RFC 4180 quoting and is not ASCII.
NARRATIVE = 'Margins, "clear".\r\nSecond line\nThird line \u2014 na\u00efve '
# PID-5 name, PID-3 SSN, PID-11 street, and PID-13 local number from the sample messages.
PID_PHI = (
    "TEST-CCR", "MESSAGE1", "999999999", "1234 TESTING DR", "5551234",
    "TestFourteen-Menethil", "Arthus", "667415923", "65 10th St", "2695588",
)
# Bridge-derived rows, deleted in an order that satisfies every FK.
DERIVED_TABLES = RESET[:RESET.index("etl.cdm_source_seed")]
MANIFEST_KEYS = {
    "bundle_format", "tool", "cdm_version", "exported_at", "source_database",
    "etl_run_id", "bridge_run_id", "vocabulary", "concept_map_coverage", "csv", "tables",
}


@contextmanager
def _bridged(dialect: str, tmp_path: Path) -> Iterator[tuple[DatabaseBackend, list[str]]]:
    """Every routing case, a mapped condition, and a narrative note, bridged."""
    with _mapped_database(dialect, tmp_path) as (backend, target):
        source = _Source(backend)
        source.patient("routed", [*_routing_values(), _site("C504")])
        source.patient("narrative", [], narrative_date=_day(2024, 3, 1), narrative=NARRATIVE)
        run_bridge(backend, load_manifest())
        yield backend, target


def _manifest(bundle: Path) -> dict:
    return json.loads((bundle / MANIFEST_FILE).read_text(encoding="utf-8"))


def _hashes(bundle: Path) -> dict[str, str]:
    return {table["file"]: table["sha256"] for table in _manifest(bundle)["tables"]}


def _rows(backend: DatabaseBackend, spec: TableSpec) -> list[tuple]:
    table = backend.qualified_name(VOCABULARY_SCHEMA, spec.table_name)
    rows = backend.fetch_all(f"SELECT {', '.join(spec.columns)} FROM {table}")
    return sorted((tuple(_normalize(value) for value in row) for row in rows), key=repr)


def _load(backend: DatabaseBackend, bundle: Path, specs: Sequence[TableSpec]) -> None:
    """Test-only loader built from product pieces: the same reader as `vocab load`."""
    tables = tuple(spec.table_name for spec in specs)
    with suspend_constraints(backend, VOCABULARY_SCHEMA, tables):
        with backend.transaction():
            for spec in specs:
                name = backend.qualified_name(VOCABULARY_SCHEMA, spec.table_name)
                identity = backend.dialect == "sqlserver" and backend.fetch_one(
                    "SELECT OBJECTPROPERTY(OBJECT_ID(?), 'TableHasIdentity')",
                    (f"{VOCABULARY_SCHEMA}.{spec.table_name}",),
                )[0] == 1
                if identity:
                    backend.execute_uncommitted(f"SET IDENTITY_INSERT {name} ON")
                backend.bulk_insert(
                    VOCABULARY_SCHEMA, spec.table_name, spec.columns,
                    iter_table_rows(spec, bundle / spec.file_name, ","),
                )
                if identity:
                    backend.execute_uncommitted(f"SET IDENTITY_INSERT {name} OFF")
            verify_constraints(backend, VOCABULARY_SCHEMA, tables)


@DIALECTS
def test_export_round_trips_row_for_row_and_reexports_byte_identically(
    dialect: str, tmp_path: Path,
) -> None:
    """CSV-01: export, load into an empty OMOP schema, compare, and export again."""
    with _bridged(dialect, tmp_path) as (backend, _target):
        specs = CLINICAL_TABLE_SPECS + TABLE_SPECS
        before = {spec.table_name: _rows(backend, spec) for spec in specs}
        assert all(before[spec.table_name] for spec in specs)
        first = tmp_path / "first"
        export_bundle(backend, first, include_vocabulary=True)
        quoted = '"Margins, ""clear"".\r\nSecond line\nThird line \u2014 na\u00efve "'
        assert quoted.encode() in (first / "NOTE.csv").read_bytes()

        if dialect == "sqlite":
            # A brand-new database, vocabulary included.
            target: DatabaseBackend = SQLiteBackend(tmp_path / "fresh" / "fresh.db")
            BuildRunner(load_manifest(), target).run()
            load_vocab(target, first, ",")
        else:
            # The dedicated bridge database with its clinical tables emptied.
            target = backend
            for table in DERIVED_TABLES:
                backend.execute(f"DELETE FROM {table}")
            assert all(_count(backend, f"omop.{spec.table_name}") == 0
                       for spec in CLINICAL_TABLE_SPECS)
        try:
            _load(target, first, CLINICAL_TABLE_SPECS)
            assert {spec.table_name: _rows(target, spec) for spec in specs} == before
            second = tmp_path / "second"
            export_bundle(target, second, include_vocabulary=True)
        finally:
            if target is not backend:
                target.close()
        assert _hashes(second) == _hashes(first)
        for spec in specs:
            assert (second / spec.file_name).read_bytes() == (
                first / spec.file_name).read_bytes(), spec.file_name


@DIALECTS
def test_manifest_matches_the_database_and_every_file(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """CSV-02: counts, hashes, every #95 field, and the export's etl.run row."""
    with _bridged(dialect, tmp_path) as (backend, target):
        bundle = tmp_path / "bundle"
        assert main(["export", *target, str(bundle)]) == 0
        output = capsys.readouterr().out
        manifest = _manifest(bundle)

        assert set(manifest) == MANIFEST_KEYS
        assert manifest["bundle_format"] == 1
        assert manifest["tool"] == {"name": "sdc-cdm", "version": __version__}
        assert manifest["cdm_version"] == "5.4"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", manifest["exported_at"])
        assert manifest["source_database"]["dialect"] == dialect
        if dialect == "sqlite":
            assert manifest["source_database"] == {"dialect": "sqlite", "name": "bridge.db"}
        else:
            server, name = backend.fetch_one("SELECT @@SERVERNAME, DB_NAME()")
            assert manifest["source_database"] == {
                "dialect": "sqlserver", "server": server, "name": name}
            assert "connection" not in json.dumps(manifest).lower()
        assert manifest["csv"] == {"encoding": "utf-8", "delimiter": ",",
                                   "line_terminator": "\n", "null": "", "date": "YYYY-MM-DD"}

        run_id = manifest["etl_run_id"]
        assert tuple(backend.fetch_one(
            "SELECT command, status FROM etl.run WHERE run_id = ?", (run_id,))) == (
            "export", "succeeded")
        assert manifest["bridge_run_id"] == int(backend.fetch_one(
            "SELECT MAX(run_id) FROM etl.run WHERE command = 'bridge' "
            "AND status = 'succeeded'")[0])

        vocabulary = manifest["vocabulary"]
        assert vocabulary["included"] is False
        assert vocabulary["cdm_source_vocabulary_version"] == backend.fetch_one(
            "SELECT vocabulary_version FROM omop.cdm_source")[0]
        assert vocabulary["vocabularies"] == [
            {"vocabulary_id": row[0], "vocabulary_version": row[1]}
            for row in backend.fetch_all(
                "SELECT vocabulary_id, vocabulary_version FROM omop.vocabulary "
                "ORDER BY vocabulary_id")]

        coverage = manifest["concept_map_coverage"]
        assert coverage["algorithm"] == backend.fetch_one(
            "SELECT algorithm FROM naaccr.concept_map_build_state")[0]
        for scope in ("item", "value"):
            assert set(coverage[scope]) == set(MAPPING_LAYERS)
            assert sum(coverage[scope].values()) == int(backend.fetch_one(
                "SELECT COALESCE(SUM(item_count), 0) FROM naaccr.concept_map_coverage "
                "WHERE scope = ?", (scope,))[0])

        assert [table["table"] for table in manifest["tables"]] == [
            spec.table_name for spec in CLINICAL_TABLE_SPECS]
        lines = output.splitlines()
        assert lines[0] == "file | rows | sha256"
        for spec, table in zip(CLINICAL_TABLE_SPECS, manifest["tables"], strict=True):
            data = (bundle / spec.file_name).read_bytes()
            assert table["file"] == spec.file_name
            assert table["rows"] == _count(backend, f"omop.{spec.table_name}")
            assert table["rows"] == len(list(
                iter_table_rows(spec, bundle / spec.file_name, ",")))
            assert table["sha256"] == hashlib.sha256(data).hexdigest()
            assert f"{spec.file_name} | {table['rows']} | {table['sha256']}" in lines
            assert not data.startswith(b"\xef\xbb\xbf")
        assert all(table["rows"] for table in manifest["tables"])
        assert f"(run {run_id})" in output


@DIALECTS
def test_no_byte_outside_omop_reaches_the_bundle(
    dialect: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV-03: PID PHI retained in raw_blob never appears in any bundle byte."""
    with _database(dialect, tmp_path) as (backend, target):
        algorithm = backend.fetch_one(
            "SELECT algorithm FROM naaccr.data_dictionary_version WHERE is_current = 1")[0]
        for path in FIXTURES:
            intake = ingest_message(backend, path.read_bytes(), parse_hl7,
                                    parser_name="hl7v2", parser_version="test")
            assert intake.parse_status == "parsed", path.name
            load_message(backend, intake.inbound_message_id, algorithm=algorithm)
        assert main(["bridge", *target]) == 0

        raw = b"".join(bytes(row[0]) for row in backend.fetch_all(
            "SELECT raw_blob FROM intake.inbound_message"))
        assert [value for value in PID_PHI if value.encode() not in raw] == []

        statements: list[str] = []
        write_tables = bundle_module._write_tables

        def traced(backend_, specs, directory):
            if dialect != "sqlite":
                return write_tables(backend_, specs, directory)
            backend_.connection.set_trace_callback(statements.append)
            try:
                return write_tables(backend_, specs, directory)
            finally:
                backend_.connection.set_trace_callback(None)

        monkeypatch.setattr(bundle_module, "_write_tables", traced)
        bundle = tmp_path / "bundle"
        export_bundle(backend, bundle, include_vocabulary=True)

        files = sorted(bundle.iterdir())
        assert len(files) == len(CLINICAL_TABLE_SPECS) + len(TABLE_SPECS) + 1
        data = b"".join(path.read_bytes() for path in files)
        assert _count(backend, "omop.person") == len(FIXTURES)
        assert [value for value in PID_PHI if value.encode() in data] == []
        if dialect == "sqlite":
            assert len(statements) == len(CLINICAL_TABLE_SPECS) + len(TABLE_SPECS)
            assert all(statement.startswith('SELECT ') and ' FROM "omop".' in statement
                       for statement in statements), statements
            assert [statement for statement in statements
                    if re.search(r"\b(intake|sdc|naaccr)\b", statement)] == []


def _ddl_columns(dialect: str) -> dict[str, tuple[str, ...]]:
    tables: dict[str, tuple[str, ...]] = {}
    for match in re.finditer(r"CREATE TABLE\s+(?:\w+\.)?(\w+)\s*\((.*?)\);",
                             DDL[dialect].read_text(encoding="utf-8"), re.S | re.I):
        tables[match.group(1).lower()] = tuple(
            line.split()[0].strip('"[]').lower()
            for line in match.group(2).splitlines() if line.strip())
    return tables


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_every_spec_matches_the_ddl_column_order(dialect: str) -> None:
    """CSV-04 (static): each spec's columns are its CDM 5.4 table's, in DDL order."""
    ddl = _ddl_columns(dialect)
    for spec in CLINICAL_TABLE_SPECS + TABLE_SPECS:
        assert spec.columns == ddl[spec.table_name], spec.table_name
        assert len(spec.kinds) == len(spec.columns)
        assert spec.file_name == f"{spec.table_name.upper()}.csv"


@DIALECTS
def test_each_file_header_is_its_spec(dialect: str, tmp_path: Path) -> None:
    """CSV-04: upper-case headers in spec order, as Athena writes them."""
    with _bridged(dialect, tmp_path) as (backend, _target):
        bundle = tmp_path / "bundle"
        export_bundle(backend, bundle, include_vocabulary=True)
        for spec in CLINICAL_TABLE_SPECS + TABLE_SPECS:
            with (bundle / spec.file_name).open("rb") as handle:
                header = handle.readline()
            assert header == (",".join(expected_headers(spec)) + "\n").encode()


def _non_empty_directory(backend: DatabaseBackend, bundle: Path) -> str:
    bundle.mkdir()
    (bundle / "keep.txt").write_text("keep", encoding="utf-8")
    return "already exists and is not an empty directory"


def _no_cdm_source(backend: DatabaseBackend, bundle: Path) -> str:
    backend.execute("DELETE FROM omop.cdm_source")
    return "exactly one omop.cdm_source row, found 0; run `sdc-cdm bridge` first"


def _empty_text(backend: DatabaseBackend, bundle: Path) -> str:
    backend.execute("UPDATE omop.measurement SET unit_source_value = '' "
                    "WHERE unit_source_value IS NOT NULL")
    return "omop.measurement.unit_source_value holds an empty string"


@DIALECTS
@pytest.mark.parametrize("defect", (_non_empty_directory, _no_cdm_source, _empty_text),
                         ids=("non-empty-directory", "no-cdm-source", "empty-string"))
def test_a_failed_export_is_named_leaves_no_bundle_and_records_the_run(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], defect,
) -> None:
    """CSV-05."""
    with _bridged(dialect, tmp_path) as (backend, target):
        parent = tmp_path / "out"
        parent.mkdir()
        bundle = parent / "bundle"
        message = defect(backend, bundle)
        before = sorted(path.relative_to(parent) for path in parent.rglob("*"))

        assert main(["export", *target, str(bundle), "--include-vocabulary"]) == 1
        assert message in capsys.readouterr().err
        assert sorted(path.relative_to(parent) for path in parent.rglob("*")) == before
        command, status, error = _last_run(backend)[:3]
        assert (command, status) == ("export", "failed") and message in error

        with pytest.raises(ExportError, match=re.escape(message)):
            export_bundle(backend, bundle)


@DIALECTS
def test_vocabulary_is_opt_in_and_unchanged_data_hashes_the_same(
    dialect: str, tmp_path: Path,
) -> None:
    """CSV-06."""
    with _bridged(dialect, tmp_path) as (backend, _target):
        clinical = tmp_path / "clinical"
        export_bundle(backend, clinical)
        assert sorted(path.name for path in clinical.iterdir()) == sorted(
            [MANIFEST_FILE, *(spec.file_name for spec in CLINICAL_TABLE_SPECS)])

        everything = tmp_path / "everything"
        export_bundle(backend, everything, include_vocabulary=True)
        assert sorted(path.name for path in everything.iterdir()) == sorted(
            [MANIFEST_FILE, *(spec.file_name for spec in CLINICAL_TABLE_SPECS + TABLE_SPECS)])
        assert _manifest(everything)["vocabulary"]["included"] is True

        again = tmp_path / "again"
        export_bundle(backend, again, include_vocabulary=True)
        assert _hashes(again) == _hashes(everything)
        assert {name: digest for name, digest in _hashes(everything).items()
                if name in _hashes(clinical)} == _hashes(clinical)
        assert _manifest(again)["etl_run_id"] > _manifest(everything)["etl_run_id"]
