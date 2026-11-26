"""`sdc-cdm export`: one CSV per OMOP table plus manifest.json.

The bundle is read from `omop` only: _write_tables builds every statement the
CSV phase runs, and each names VOCABULARY_SCHEMA. Nothing outside `omop` (raw
message bytes, intake PID fields) can reach a CSV. The bundle is not
de-identified: omop.person.person_source_value is the MRN, note_source_value the
accession, and note_text the narrative report.

CSV format: UTF-8 without BOM, comma, "\\n", RFC 4180 quoting, upper-case
headers, dates YYYY-MM-DD, floats as repr(float), NULL as an empty field. An
empty-string text value cannot be told from NULL there, so export fails and
names it rather than change it. Rows are ordered by every column in spec order,
so two exports of an unchanged database are byte-identical.

All tables are read in one transaction that sees one database state (see
db.isolation). The bundle is written to a temporary sibling directory and
renamed into place only when complete, so a failure leaves no bundle.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO

from sdc_cdm import __version__
from sdc_cdm.cdm.tables import (
    CDM_VERSION,
    CLINICAL_TABLE_SPECS,
    TABLE_SPECS,
    VOCABULARY_SCHEMA,
    TableSpec,
    expected_headers,
)
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import SdcCdmError
from sdc_cdm.db.isolation import consistent_reads
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.maps.coverage import layer_totals


BUNDLE_FORMAT = 1
MANIFEST_FILE = "manifest.json"
CSV_FORMAT = {
    "encoding": "utf-8",
    "delimiter": ",",
    "line_terminator": "\n",
    "null": "",
    "date": "YYYY-MM-DD",
}
# Binary order on SQL Server, so rows that differ only in case still sort the
# same way on every export.
_SQLSERVER_TEXT_ORDER = "COLLATE Latin1_General_BIN2"


class ExportError(SdcCdmError):
    """Raised when the database cannot be exported as a faithful bundle."""


@dataclass(frozen=True)
class ExportedTable:
    table: str
    file: str
    rows: int
    sha256: str


@dataclass(frozen=True)
class ExportResult:
    run_id: int
    output_dir: Path
    tables: tuple[ExportedTable, ...]
    manifest: dict[str, Any]


class _HashingWriter:
    """The text sink csv.writer writes to: encodes, hashes, and writes bytes."""

    def __init__(self, handle: BinaryIO):
        self.handle = handle
        self.digest = hashlib.sha256()

    def write(self, text: str) -> int:
        data = text.encode("utf-8")
        self.digest.update(data)
        self.handle.write(data)
        return len(text)


def _format(value: Any, kind: str, spec: TableSpec, column: str) -> str | None:
    if value is None:
        return None
    try:
        if kind == "text":
            text = str(value)
            if text == "":
                raise ExportError(
                    f"{VOCABULARY_SCHEMA}.{spec.table_name}.{column} holds an "
                    "empty string, which the bundle's CSV cannot tell from NULL; "
                    "set it to NULL or a non-empty value and export again"
                )
            return text
        if kind == "integer":
            return str(int(value))
        if kind == "float":
            return repr(float(value))
        if kind == "decimal":
            if isinstance(value, Decimal):
                return format(value, "f")
            if isinstance(value, int):
                return str(value)
            return repr(float(value))
        if kind == "date":
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            return date.fromisoformat(str(value)).isoformat()
        if kind == "datetime":
            if isinstance(value, datetime):
                return value.isoformat(sep=" ")
            return datetime.fromisoformat(str(value)).isoformat(sep=" ")
    except (TypeError, ValueError) as exc:
        # The value itself is not echoed: it may be PHI.
        raise ExportError(
            f"{VOCABULARY_SCHEMA}.{spec.table_name}.{column}: a "
            f"{type(value).__name__} value is not a valid {kind}"
        ) from exc
    raise AssertionError(f"Unsupported field kind: {kind}")


def _select(backend: DatabaseBackend, spec: TableSpec) -> str:
    """The one statement that reads a table for its CSV."""

    columns = ", ".join(spec.columns)
    order = ", ".join(
        f"{column} {_SQLSERVER_TEXT_ORDER}"
        if backend.dialect == "sqlserver" and kind == "text" else column
        for column, kind in zip(spec.columns, spec.kinds)
    )
    return (
        f"SELECT {columns} "
        f"FROM {backend.qualified_name(VOCABULARY_SCHEMA, spec.table_name)} "
        f"ORDER BY {order}"
    )


def _write_tables(
    backend: DatabaseBackend, specs: Sequence[TableSpec], directory: Path,
) -> tuple[ExportedTable, ...]:
    """The CSV phase: every statement it runs reads one `omop` table."""

    exported: list[ExportedTable] = []
    for spec in specs:
        with (directory / spec.file_name).open("wb") as handle:
            sink = _HashingWriter(handle)
            writer = csv.writer(sink, delimiter=",", quotechar='"',
                                lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(expected_headers(spec))
            rows = 0
            # closing(): a value that fails to format must not leave SQL Server
            # results pending, or the rollback and failed-run update would fail.
            with closing(backend.iter_rows(_select(backend, spec))) as result:
                for row in result:
                    writer.writerow([
                        _format(value, kind, spec, column)
                        for value, kind, column in zip(row, spec.kinds, spec.columns)
                    ])
                    rows += 1
        exported.append(
            ExportedTable(spec.table_name, spec.file_name, rows, sink.digest.hexdigest())
        )
    return tuple(exported)


def _cdm_source_vocabulary_version(backend: DatabaseBackend) -> str:
    table = backend.qualified_name(VOCABULARY_SCHEMA, "cdm_source")
    rows = backend.fetch_all(f"SELECT vocabulary_version FROM {table}")
    if len(rows) != 1:
        raise ExportError(
            f"export requires exactly one {VOCABULARY_SCHEMA}.cdm_source row, found "
            f"{len(rows)}; run `sdc-cdm bridge` first"
        )
    return str(rows[0][0])


def _source_database(backend: DatabaseBackend) -> dict[str, str | None]:
    """Identify the database without its connection string or full path."""

    if backend.dialect == "sqlserver":
        server, database = backend.fetch_one("SELECT @@SERVERNAME, DB_NAME()")
        return {"dialect": "sqlserver",
                "server": None if server is None else str(server), "name": str(database)}
    path = getattr(backend, "database_path", None)
    return {"dialect": backend.dialect, "name": path.name if path else ":memory:"}


def _metadata(backend: DatabaseBackend) -> dict[str, Any]:
    vocabulary = backend.qualified_name(VOCABULARY_SCHEMA, "vocabulary")
    bridge_run = backend.fetch_one(
        "SELECT MAX(run_id) FROM etl.run "
        "WHERE command IN ('bridge', 'supersede') AND status = 'succeeded'"
    )[0]
    return {
        "source_database": _source_database(backend),
        "bridge_run_id": None if bridge_run is None else int(bridge_run),
        "vocabularies": [
            {"vocabulary_id": str(row[0]),
             "vocabulary_version": None if row[1] is None else str(row[1])}
            for row in backend.fetch_all(
                f"SELECT vocabulary_id, vocabulary_version FROM {vocabulary} "
                "ORDER BY vocabulary_id"
            )
        ],
        "concept_map_coverage": layer_totals(backend),
    }


def _require_empty(output_dir: Path) -> None:
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ExportError(
            f"output directory {output_dir} already exists and is not an empty "
            "directory; choose a new path"
        )


def export_bundle(
    backend: DatabaseBackend, output_dir: Path, *, include_vocabulary: bool = False,
) -> ExportResult:
    """Write the OMOP tables and manifest.json to output_dir in one snapshot."""

    output_dir = Path(output_dir)
    specs = CLINICAL_TABLE_SPECS + (TABLE_SPECS if include_vocabulary else ())
    run_log = RunLog(backend)
    run_id = run_log.start("export")
    staging: Path | None = None
    try:
        _require_empty(output_dir)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(
            prefix=f".{output_dir.name}.", suffix=".partial", dir=output_dir.parent,
        ))
        with consistent_reads(backend), backend.transaction():
            vocabulary_version = _cdm_source_vocabulary_version(backend)
            tables = _write_tables(backend, specs, staging)
            metadata = _metadata(backend)
        manifest = {
            "bundle_format": BUNDLE_FORMAT,
            "tool": {"name": "sdc-cdm", "version": __version__},
            "cdm_version": CDM_VERSION,
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_database": metadata["source_database"],
            "etl_run_id": run_id,
            "bridge_run_id": metadata["bridge_run_id"],
            "vocabulary": {
                "included": include_vocabulary,
                "cdm_source_vocabulary_version": vocabulary_version,
                "vocabularies": metadata["vocabularies"],
            },
            "concept_map_coverage": metadata["concept_map_coverage"],
            "csv": CSV_FORMAT,
            "tables": [
                {"table": table.table, "file": table.file, "rows": table.rows,
                 "sha256": table.sha256}
                for table in tables
            ],
        }
        (staging / MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            output_dir.rmdir()
        staging.rename(output_dir)
        staging = None
    except Exception as exc:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        run_log.finish(run_id, error=str(exc))
        raise
    run_log.finish(run_id)
    return ExportResult(run_id, output_dir, tables, manifest)
