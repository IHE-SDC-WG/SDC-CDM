from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import pytest

from sdc_cdm.cdm.tables import TABLE_SPECS
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.vocab.constants import resolve_constants
from sdc_cdm.vocab.extract import inspect_extract
from sdc_cdm.vocab.loader import load_vocab


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
        _concept(0, "Unknown", concept_code="No matching concept"),
        _concept(1, "Metadata domain"),
        _concept(2, "Type Concept domain"),
        _concept(3, "None vocabulary"),
        _concept(4, "Type Concept vocabulary"),
        _concept(5, "CDM vocabulary"),
        _concept(6, "Undefined concept class"),
        _concept(7, "Type Concept class"),
        _concept(8, "Field concept class"),
        _concept(9, "Is a relationship"),
        _concept(10, "Gender domain"),
        _concept(11, "Gender vocabulary"),
        _concept(12, "Gender concept class"),
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
        _concept(8507, "Male", "Gender", "Gender", "Gender", "M"),
        _concept(8532, "Female", "Gender", "Gender", "Gender", "F"),
    ]
    return {
        "domain": [
            ["Metadata", "Metadata", "1"],
            ["Type Concept", "Type Concept", "2"],
            ["Gender", "Gender", "10"],
        ],
        "vocabulary": [
            ["None", "No vocabulary", "Synthetic", "test-v1", "3"],
            ["Type Concept", "Type Concept", "Synthetic", "test-v1", "4"],
            ["CDM", "CDM", "Synthetic", "test-v1", "5"],
            ["Gender", "Gender", "Synthetic", "test-v1", "11"],
        ],
        "concept_class": [
            ["Undefined", "Undefined", "6"],
            ["Type Concept", "Type Concept", "7"],
            ["Field", "Field", "8"],
            ["Gender", "Gender", "12"],
        ],
        "relationship": [["Is a", "Is a", "1", "1", "Is a", "9"]],
        "concept": concepts,
        "concept_relationship": [
            ["32879", "32817", "Is a", "19700101", "20991231", ""]
        ],
        "concept_synonym": [["32879", "Registry type", "0"]],
        "concept_ancestor": [["32817", "32879", "1", "1"]],
        "drug_strength": [
            [
                "8507",
                "8507",
                "",
                "",
                "1.25",
                "8507",
                "",
                "",
                "",
                "19700101",
                "20991231",
                "",
            ]
        ],
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
                handle, delimiter="\t", quotechar='"', lineterminator="\n"
            )
            writer.writerow(column.upper() for column in spec.columns)
            writer.writerows(rows_by_table[spec.table_name])
    return rows_by_table


def _build_sqlite(control_path: Path) -> None:
    with SQLiteBackend(control_path) as backend:
        BuildRunner(load_manifest(), backend).run()


def _load_sqlite_fixture(tmp_path: Path) -> Path:
    vocab_dir = tmp_path / "vocab"
    _write_extract(vocab_dir)
    control_path = tmp_path / "control.db"
    _build_sqlite(control_path)
    with SQLiteBackend(control_path) as backend:
        load_vocab(backend, vocab_dir, "\t", batch_size=3)
    return control_path


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

    with pytest.raises(VocabularyError, match="missing CONCEPT.csv"):
        inspect_extract(vocab_dir, "\t")


def test_extract_check_reports_malformed_numeric_value(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _synthetic_rows()
    rows["concept"][0][0] = "not-an-integer"
    _write_extract(vocab_dir, rows)

    with pytest.raises(
        VocabularyError, match="CONCEPT.csv:2: invalid integer"
    ):
        inspect_extract(vocab_dir, "\t")


def _vocab_backend(dialect: str, tmp_path: Path) -> DatabaseBackend:
    if dialect == "sqlite":
        return SQLiteBackend(tmp_path / "load.db")
    connection_string = os.environ.get(
        "SDC_CDM_VOCAB_SQLSERVER_CONNECTION_STRING"
    )
    if not connection_string:
        pytest.skip("SDC_CDM_VOCAB_SQLSERVER_CONNECTION_STRING is not set")
    return SqlServerBackend(connection_string)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_load_populates_a_fresh_schema_and_validates_counts(
    dialect: str, tmp_path: Path
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _write_extract(vocab_dir)

    with _vocab_backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        report = load_vocab(backend, vocab_dir, "\t", batch_size=3)

        assert report.row_counts == {
            table: len(table_rows) for table, table_rows in rows.items()
        }
        assert ("None", "test-v1") in report.vocabulary_versions
        assert backend.fetch_one(
            "SELECT concept_name FROM omop.concept WHERE concept_id = 32879"
        )[0] == "Registry\tcanonical"
        assert backend.fetch_one(
            "SELECT numerator_value FROM omop.drug_strength"
        )[0] is not None
        if dialect == "sqlite":
            assert backend.fetch_all('PRAGMA "omop".foreign_key_check') == []
        assert len(resolve_constants(backend)) == 6


def test_sqlite_load_rolls_back_on_orphaned_relationship(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    rows = _synthetic_rows()
    rows["concept_relationship"] = [
        ["32879", "999999", "Is a", "19700101", "20991231", ""]
    ]
    _write_extract(vocab_dir, rows)
    control_path = tmp_path / "control.db"
    _build_sqlite(control_path)

    with SQLiteBackend(control_path) as backend:
        with pytest.raises(VocabularyError, match="foreign key violation"):
            load_vocab(backend, vocab_dir, "\t", batch_size=3)
        assert backend.fetch_one("SELECT COUNT(*) FROM omop.concept")[0] == 0
        assert backend.fetch_one("SELECT COUNT(*) FROM omop.vocabulary")[0] == 0


def test_sqlite_loader_refuses_an_existing_vocabulary(
    tmp_path: Path,
) -> None:
    vocab_dir = tmp_path / "vocab"
    _write_extract(vocab_dir)
    control_path = tmp_path / "control.db"
    _build_sqlite(control_path)

    with SQLiteBackend(control_path) as backend:
        load_vocab(backend, vocab_dir, "\t")
        with pytest.raises(VocabularyError, match="Vocabulary target is not fresh"):
            load_vocab(backend, vocab_dir, "\t")


def test_all_six_constants_resolve_from_the_loaded_fixture(
    tmp_path: Path,
) -> None:
    control_path = _load_sqlite_fixture(tmp_path)
    with SQLiteBackend(control_path) as backend:
        resolved = resolve_constants(backend)
        mappings = {
            constant.constant_name: constant.concept_id for constant in resolved
        }
        assert mappings == {
            "note_type_ehr": 32817,
            "measurement_type_registry": 32879,
            "field_note_note_id": 1147289,
            "unmapped": 0,
            "gender_male": 8507,
            "gender_female": 8532,
        }
        assert backend.fetch_one("SELECT COUNT(*) FROM etl.concept_constant")[0] == 6


def test_missing_constant_exits_one_and_does_not_modify_the_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control_path = _load_sqlite_fixture(tmp_path)
    with SQLiteBackend(control_path) as backend:
        backend.execute("DELETE FROM omop.concept WHERE concept_id = 8532")

    assert main(
        [
            "constants",
            "resolve",
            "--dialect",
            "sqlite",
            "--db",
            str(control_path),
        ]
    ) == 1
    error = capsys.readouterr().err
    assert "('Gender', 'F')" in error
    assert "etl.concept_constant was not modified" in error
    with SQLiteBackend(control_path) as backend:
        assert backend.fetch_one("SELECT COUNT(*) FROM etl.concept_constant")[0] == 0


def test_ambiguous_pair_names_every_candidate_id(tmp_path: Path) -> None:
    control_path = _load_sqlite_fixture(tmp_path)
    with SQLiteBackend(control_path) as backend:
        backend.execute(
            "INSERT INTO omop.concept ("
            "concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, "
            "standard_concept, concept_code, valid_start_date, valid_end_date"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                999_999,
                "Second EHR",
                "Type Concept",
                "Type Concept",
                "Type Concept",
                "S",
                "EHR",
                "1970-01-01",
                "2099-12-31",
            ),
        )
        with pytest.raises(VocabularyError) as exc_info:
            resolve_constants(backend)
        message = str(exc_info.value)
        assert "('Type Concept', 'EHR')" in message
        assert "32817" in message
        assert "999999" in message
        assert backend.fetch_one("SELECT COUNT(*) FROM etl.concept_constant")[0] == 0


def test_constants_resolve_is_idempotent(tmp_path: Path) -> None:
    control_path = _load_sqlite_fixture(tmp_path)
    with SQLiteBackend(control_path) as backend:
        first = resolve_constants(backend)
        second = resolve_constants(backend)
        assert second == first
        rows = backend.fetch_all(
            "SELECT constant_name, concept_id, vocabulary_id, concept_code "
            "FROM etl.concept_constant ORDER BY constant_name"
        )
        assert len(rows) == 6
        assert len({row[0] for row in rows}) == 6


def test_every_bridge_concept_literal_resolves_to_a_constant(
    tmp_path: Path,
) -> None:
    control_path = _load_sqlite_fixture(tmp_path)
    bridge_paths = (
        "database/etl/sqlite/1_naaccr_sdc_to_omop.sql",
        "database/etl/sqlserver/1_naaccr_sdc_to_omop.sql",
    )
    literal_sets = []
    for relative_path in bridge_paths:
        text = repository_path(relative_path).read_text(encoding="utf-8")
        literal_sets.append(
            {
                int(value)
                for value in re.findall(
                    r"(?<![A-Za-z0-9_])\d{4,}(?![A-Za-z0-9_])", text
                )
            }
        )
    assert literal_sets == [
        {32817, 32879, 1147289},
        {32817, 32879, 1147289},
    ]

    with SQLiteBackend(control_path) as backend:
        resolve_constants(backend)
        resolved_ids = {
            int(row[0])
            for row in backend.fetch_all(
                "SELECT concept_id FROM etl.concept_constant"
            )
        }
    assert literal_sets[0].issubset(resolved_ids)
