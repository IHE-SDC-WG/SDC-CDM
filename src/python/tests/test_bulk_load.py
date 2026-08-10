from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import (
    constraint_violations,
    suspend_constraints,
    verify_constraints,
)
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend


_VOCABULARY_TABLES = ("concept", "vocabulary", "domain", "concept_class")
_CONCEPT_COLUMNS = (
    "concept_id",
    "concept_name",
    "domain_id",
    "vocabulary_id",
    "concept_class_id",
    "concept_code",
    "valid_start_date",
    "valid_end_date",
)


def _open_backend(dialect: str, tmp_path: Path) -> DatabaseBackend:
    if dialect == "sqlite":
        return SQLiteBackend(tmp_path / "bulk.db")
    connection_string = os.environ.get("SDC_CDM_SQLSERVER_DSN")
    if not connection_string:
        pytest.skip("SDC_CDM_SQLSERVER_DSN is not set")
    return SqlServerBackend(connection_string)


def _concept_id_window() -> int:
    return 900_000_000 + (uuid.uuid4().int % 1_000_000) * 100


def _concept_rows(
    first_id: int, domain_id: str, vocabulary_id: str, concept_class_id: str
) -> list[tuple[object, ...]]:
    return [
        (
            first_id + offset,
            f"Bulk concept {offset}",
            domain_id,
            vocabulary_id,
            concept_class_id,
            f"BULK-{first_id + offset}",
            "2026-01-01",
            "2099-12-31",
        )
        for offset in range(5)
    ]


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_bulk_insert_round_trips_omop_concept_across_batch_boundaries(
    dialect: str, tmp_path: Path
) -> None:
    """A streaming insert crosses 2/2/1 batches and remains FK-clean."""

    with _open_backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        first_id = _concept_id_window()
        domain_id = f"D{first_id}"
        vocabulary_id = f"V{first_id}"
        concept_class_id = f"C{first_id}"
        rows = _concept_rows(
            first_id, domain_id, vocabulary_id, concept_class_id
        )

        with suspend_constraints(
            backend, "omop", _VOCABULARY_TABLES
        ), backend.transaction():
            inserted = backend.bulk_insert(
                "omop",
                "concept",
                _CONCEPT_COLUMNS,
                (row for row in rows),
                batch_size=2,
            )
            backend.bulk_insert(
                "omop",
                "domain",
                ("domain_id", "domain_name", "domain_concept_id"),
                [(domain_id, "Bulk domain", first_id)],
            )
            backend.bulk_insert(
                "omop",
                "vocabulary",
                (
                    "vocabulary_id",
                    "vocabulary_name",
                    "vocabulary_reference",
                    "vocabulary_version",
                    "vocabulary_concept_id",
                ),
                [(vocabulary_id, "Bulk vocabulary", None, None, first_id + 1)],
            )
            backend.bulk_insert(
                "omop",
                "concept_class",
                (
                    "concept_class_id",
                    "concept_class_name",
                    "concept_class_concept_id",
                ),
                [(concept_class_id, "Bulk class", first_id + 2)],
            )
            verify_constraints(backend, "omop", _VOCABULARY_TABLES)

        assert inserted == 5
        read_back = backend.fetch_all(
            "SELECT concept_id, concept_code, valid_start_date, valid_end_date "
            "FROM omop.concept WHERE concept_id >= ? AND concept_id < ? "
            "ORDER BY concept_id",
            (first_id, first_id + 5),
        )
        assert [
            (int(row[0]), row[1], str(row[2])[:10], str(row[3])[:10])
            for row in read_back
        ] == [
            (row[0], row[5], row[6], row[7])
            for row in rows
        ]


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_rolling_back_a_transaction_leaves_no_bulk_inserted_rows(
    dialect: str, tmp_path: Path
) -> None:
    """A raised load rolls back rows that were visible inside its transaction."""

    with _open_backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        concept_id = _concept_id_window()
        row = _concept_rows(concept_id, "missing-d", "missing-v", "missing-c")[:1]

        with pytest.raises(RuntimeError, match="force rollback"):
            with suspend_constraints(
                backend, "omop", _VOCABULARY_TABLES
            ), backend.transaction():
                assert (
                    backend.bulk_insert(
                        "omop", "concept", _CONCEPT_COLUMNS, row
                    )
                    == 1
                )
                assert backend.fetch_one(
                    "SELECT COUNT(*) FROM omop.concept WHERE concept_id = ?",
                    (concept_id,),
                )[0] == 1
                raise RuntimeError("force rollback")

        assert backend.fetch_one(
            "SELECT COUNT(*) FROM omop.concept WHERE concept_id = ?", (concept_id,)
        )[0] == 0


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_execute_is_refused_inside_a_transaction_but_fetches_stay_usable(
    dialect: str, tmp_path: Path
) -> None:
    """Committing helpers are blocked while pre-commit reads remain available."""

    with _open_backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        with backend.transaction():
            with pytest.raises(RuntimeError, match="transaction"):
                backend.execute("SELECT 1")
            assert backend.fetch_one("SELECT 1")[0] == 1
            assert [tuple(row) for row in backend.fetch_all("SELECT 1")] == [(1,)]


def test_only_the_schema_qualified_pragma_reports_an_orphan_in_an_attached_schema(
    tmp_path: Path,
) -> None:
    """Deleting the schema qualifier in constraint_violations makes this fail."""

    with SQLiteBackend(tmp_path / "qualified-pragma.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.execute("PRAGMA foreign_keys = OFF")
        backend.execute(
            "INSERT INTO omop.vocabulary ("
            "vocabulary_id, vocabulary_name, vocabulary_concept_id"
            ") VALUES (?, ?, ?)",
            ("orphan", "Orphan vocabulary", 9_000_001),
        )
        backend.execute("PRAGMA foreign_keys = ON")

        assert backend.fetch_all("PRAGMA foreign_key_check") == []
        assert backend.fetch_all('PRAGMA "main".foreign_key_check') == []
        violations = constraint_violations(backend, "omop")
        assert violations
        assert violations[0][0] == "vocabulary"
        with pytest.raises(VocabularyError, match="foreign key violation"):
            verify_constraints(backend, "omop", _VOCABULARY_TABLES)


def test_suspend_constraints_raises_when_sqlite_silently_ignored_the_pragma(
    tmp_path: Path,
) -> None:
    """Deleting _sqlite_suspend's pragma read-back makes this fail."""

    with SQLiteBackend(tmp_path / "ignored-pragma.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        backend.connection.execute("BEGIN IMMEDIATE")
        try:
            assert backend.fetch_one("PRAGMA foreign_keys")[0] == 1
            with pytest.raises(VocabularyError, match="did not take effect"):
                with suspend_constraints(backend, "omop", _VOCABULARY_TABLES):
                    pass
        finally:
            backend.connection.rollback()
        assert backend.fetch_one("PRAGMA foreign_keys")[0] == 1
