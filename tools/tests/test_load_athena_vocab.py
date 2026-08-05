#!/usr/bin/env python3
"""Tests for the OHDSI Athena vocabulary loader."""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from load_athena_vocab import (  # noqa: E402
    LoaderError,
    PostgresBackend,
    SqlServerBackend,
    SqliteBackend,
    TABLE_SPECS,
    inspect_extract,
    load_vocab,
)


def _concept(
    concept_id: int,
    name: str,
    domain_id: str = "Metadata",
    vocabulary_id: str = "None",
    concept_class_id: str = "Undefined",
    concept_code: str | None = None,
) -> list[str]:
    return [
        str(concept_id),
        name,
        domain_id,
        vocabulary_id,
        concept_class_id,
        "S",
        concept_code or str(concept_id),
        "19700101",
        "20991231",
        "",
    ]


def _synthetic_rows() -> dict[str, list[list[str]]]:
    concepts = [
        _concept(0, "Unknown"),
        _concept(1, "Metadata domain"),
        _concept(2, "Type Concept domain"),
        _concept(3, "None vocabulary"),
        _concept(4, "Type Concept vocabulary"),
        _concept(5, "CDM vocabulary"),
        _concept(6, "Undefined concept class"),
        _concept(7, "Type Concept class"),
        _concept(8, "Field concept class"),
        _concept(9, "Is a relationship"),
        _concept(
            32817,
            "EHR",
            "Type Concept",
            "Type Concept",
            "Type Concept",
            "EHR",
        ),
        _concept(
            32879,
            "Registry\tcanonical",
            "Type Concept",
            "Type Concept",
            "Type Concept",
            "Registry",
        ),
        _concept(
            1147289,
            "note.note_id",
            "Metadata",
            "CDM",
            "Field",
            "note.note_id",
        ),
    ]
    return {
        "domain": [
            ["Metadata", "Metadata", "1"],
            ["Type Concept", "Type Concept", "2"],
        ],
        "vocabulary": [
            ["None", "No vocabulary", "Synthetic", "test-v1", "3"],
            [
                "Type Concept",
                "Type Concept",
                "Synthetic",
                "test-v1",
                "4",
            ],
            ["CDM", "CDM", "Synthetic", "test-v1", "5"],
        ],
        "concept_class": [
            ["Undefined", "Undefined", "6"],
            ["Type Concept", "Type Concept", "7"],
            ["Field", "Field", "8"],
        ],
        "relationship": [
            ["Is a", "Is a", "1", "1", "Is a", "9"],
        ],
        "concept": concepts,
        "concept_relationship": [
            ["32879", "32817", "Is a", "19700101", "20991231", ""],
        ],
        "concept_synonym": [
            ["32879", "Registry type", "0"],
        ],
        "concept_ancestor": [
            ["32817", "32879", "1", "1"],
        ],
        "drug_strength": [],
    }


def _write_extract(
    vocab_dir: Path,
    rows_by_table: dict[str, list[list[str]]] | None = None,
) -> dict[str, list[list[str]]]:
    rows_by_table = rows_by_table or _synthetic_rows()
    vocab_dir.mkdir()
    for spec in TABLE_SPECS:
        with (vocab_dir / spec.file_name).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(
                handle,
                delimiter="\t",
                quotechar='"',
                lineterminator="\n",
            )
            writer.writerow(column.upper() for column in spec.columns)
            writer.writerows(rows_by_table[spec.table_name])
    return rows_by_table


def _create_sqlite_omop(tmp_path: Path) -> Path:
    control_path = tmp_path / "control.db"
    omop_path = tmp_path / "omop.db"
    connection = sqlite3.connect(control_path)
    connection.execute("ATTACH DATABASE ? AS omop", (str(omop_path),))
    connection.executescript(
        (
            ROOT
            / "database/schemas/omop/ddl/sqlite/"
            "1_OMOPCDM_sqlite_5.4_ddl.sql"
        ).read_text()
    )
    connection.close()
    return omop_path


def _seed_sqlite_concept(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO concept (
            concept_id, concept_name, domain_id, vocabulary_id,
            concept_class_id, standard_concept, concept_code,
            valid_start_date, valid_end_date, invalid_reason
        )
        VALUES (
            32879, 'placeholder', 'Type Concept', 'Type Concept',
            'Type Concept', 'S', 'Registry',
            '1970-01-01', '2099-12-31', NULL
        )
        """
    )
    connection.commit()
    connection.close()


def test_extract_check_parses_all_nine_tab_delimited_files(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _write_extract(vocab_dir)

    counts = inspect_extract(vocab_dir, "\t")

    assert counts == {
        table: len(table_rows) for table, table_rows in rows.items()
    }


def test_extract_check_reports_missing_file(tmp_path: Path) -> None:
    vocab_dir = tmp_path / "vocab"
    _write_extract(vocab_dir)
    (vocab_dir / "CONCEPT.csv").unlink()

    with pytest.raises(LoaderError, match="missing CONCEPT.csv"):
        inspect_extract(vocab_dir, "\t")


def test_extract_check_reports_malformed_numeric_value(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _synthetic_rows()
    rows["concept"][0][0] = "not-an-integer"
    _write_extract(vocab_dir, rows)

    with pytest.raises(
        LoaderError, match="CONCEPT.csv:2: invalid integer"
    ):
        inspect_extract(vocab_dir, "\t")


def test_sqlite_load_replaces_known_seed_and_validates_counts(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _write_extract(vocab_dir)
    omop_path = _create_sqlite_omop(tmp_path)
    _seed_sqlite_concept(omop_path)

    report = load_vocab(
        SqliteBackend(omop_path, batch_size=3),
        vocab_dir,
        "\t",
    )

    assert report.row_counts == {
        table: len(table_rows) for table, table_rows in rows.items()
    }
    assert ("None", "test-v1") in report.vocabulary_versions

    connection = sqlite3.connect(omop_path)
    registry_name = connection.execute(
        "SELECT concept_name FROM concept WHERE concept_id = 32879"
    ).fetchone()[0]
    assert registry_name == "Registry\tcanonical"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()


def test_sqlite_load_rolls_back_on_orphaned_relationship(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _synthetic_rows()
    rows["concept_relationship"] = [
        ["32879", "999999", "Is a", "19700101", "20991231", ""]
    ]
    _write_extract(vocab_dir, rows)
    omop_path = _create_sqlite_omop(tmp_path)
    _seed_sqlite_concept(omop_path)

    with pytest.raises(
        LoaderError, match="Vocabulary integrity validation failed"
    ):
        load_vocab(
            SqliteBackend(omop_path, batch_size=3),
            vocab_dir,
            "\t",
        )

    connection = sqlite3.connect(omop_path)
    assert connection.execute(
        "SELECT concept_id, concept_name FROM concept"
    ).fetchall() == [(32879, "placeholder")]
    assert connection.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0] == 0
    connection.close()


def test_sqlite_loader_refuses_an_existing_vocabulary(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    _write_extract(vocab_dir)
    omop_path = _create_sqlite_omop(tmp_path)
    load_vocab(SqliteBackend(omop_path, 10), vocab_dir, "\t")

    with pytest.raises(LoaderError, match="Vocabulary target is not fresh"):
        load_vocab(SqliteBackend(omop_path, 10), vocab_dir, "\t")


class _RecordingCursor:
    def __init__(self, statements: list[str]):
        self.statements = statements
        self.fast_executemany = False

    def execute(self, sql: str, _parameters: object = ()) -> None:
        self.statements.append(sql)


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self.statements)


def test_postgres_adapter_uses_quoted_schema_and_replication_role() -> None:
    backend = PostgresBackend("unused", "omop", 100)
    connection = _RecordingConnection()
    backend.connection = connection

    backend.begin_load()
    backend.enable_constraints_for_validation()

    assert backend.qualified_table("concept") == '"omop"."concept"'
    assert connection.statements == [
        "SET session_replication_role = replica",
        "SET session_replication_role = DEFAULT",
    ]


def test_sqlserver_adapter_disables_and_rechecks_each_target_table() -> None:
    backend = SqlServerBackend("unused", "omop", 100)
    connection = _RecordingConnection()
    backend.connection = connection

    backend.begin_load()
    backend.enable_constraints_for_validation()

    assert backend.qualified_table("concept") == "[omop].[concept]"
    assert len(connection.statements) == len(TABLE_SPECS) * 2
    assert connection.statements[0] == (
        "ALTER TABLE [omop].[domain] NOCHECK CONSTRAINT ALL"
    )
    assert connection.statements[-1] == (
        "ALTER TABLE [omop].[drug_strength] "
        "WITH CHECK CHECK CONSTRAINT ALL"
    )
