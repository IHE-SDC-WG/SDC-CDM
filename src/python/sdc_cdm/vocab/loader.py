"""Transactional OHDSI Athena vocabulary loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.cdm.tables import TABLE_SPECS, VOCABULARY_SCHEMA
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import suspend_constraints, verify_constraints
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.vocab.extract import iter_table_rows, validate_source_files
from sdc_cdm.vocab.integrity import target_row_counts, validate_loaded_data


@dataclass(frozen=True)
class LoadReport:
    row_counts: dict[str, int]
    vocabulary_versions: tuple[tuple[str, str | None], ...]


def _require_target_tables(backend: DatabaseBackend) -> None:
    missing = [
        spec.table_name
        for spec in TABLE_SPECS
        if not backend.table_exists(VOCABULARY_SCHEMA, spec.table_name)
    ]
    if missing:
        raise VocabularyError(
            "Target is missing OMOP vocabulary tables: " + ", ".join(missing)
        )


def _prepare_fresh_target(backend: DatabaseBackend) -> None:
    populated = {
        table: count for table, count in target_row_counts(backend).items() if count
    }
    if populated:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(populated.items())
        )
        raise VocabularyError(
            "Vocabulary target is not fresh. Existing rows were found: "
            f"{details}. Create a fresh OMOP schema for the initial Athena load."
        )


def load_vocab(
    backend: DatabaseBackend,
    vocab_dir: Path,
    delimiter: str,
    *,
    batch_size: int = 10_000,
) -> LoadReport:
    if batch_size < 1:
        raise VocabularyError("--batch-size must be greater than zero")
    paths = validate_source_files(vocab_dir, delimiter)
    _require_target_tables(backend)
    table_names = tuple(spec.table_name for spec in TABLE_SPECS)
    run_log = RunLog(backend)
    run_id = run_log.start("vocab load")
    try:
        with suspend_constraints(
            backend, VOCABULARY_SCHEMA, table_names
        ):
            with backend.transaction():
                _prepare_fresh_target(backend)
                row_counts = {
                    spec.table_name: backend.bulk_insert(
                        VOCABULARY_SCHEMA,
                        spec.table_name,
                        spec.columns,
                        iter_table_rows(
                            spec, paths[spec.table_name], delimiter
                        ),
                        batch_size=batch_size,
                    )
                    for spec in TABLE_SPECS
                }
                verify_constraints(backend, VOCABULARY_SCHEMA, table_names)
                validate_loaded_data(backend, row_counts)
                versions = tuple(
                    (
                        str(row[0]),
                        None if row[1] is None else str(row[1]),
                    )
                    for row in backend.fetch_all(
                        "SELECT vocabulary_id, vocabulary_version FROM "
                        f"{backend.qualified_name(VOCABULARY_SCHEMA, 'vocabulary')} "
                        "ORDER BY vocabulary_id"
                    )
                )
        run_log.finish(run_id)
        return LoadReport(row_counts=row_counts, vocabulary_versions=versions)
    except Exception as exc:
        run_log.finish(run_id, error=str(exc))
        raise
