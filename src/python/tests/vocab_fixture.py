from __future__ import annotations

import csv
from pathlib import Path

from sdc_cdm.cdm.tables import TABLE_SPECS


def _concept(
    concept_id: int,
    name: str,
    domain_id: str = "Metadata",
    vocabulary_id: str = "None",
    concept_class_id: str = "Undefined",
    concept_code: str | None = None,
    standard_concept: str = "S",
) -> list[str]:
    return [
        str(concept_id),
        name,
        domain_id,
        vocabulary_id,
        concept_class_id,
        standard_concept,
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
        _concept(13, "Observation domain"),
        _concept(14, "Measurement Value domain"),
        _concept(15, "Vocabulary class"),
        _concept(16, "Concept Class class"),
        _concept(17, "NAACCR item class"),
        _concept(18, "NAACCR value class"),
        _concept(19, "NAACCR vocabulary"),
        _concept(20, "Maps to relationship"),
        _concept(21, "Mapped from relationship"),
        _concept(9001, "ER observation target", "Observation", "CDM", "Field"),
        _concept(9002, "Stage value target A", "Meas Value", "CDM", "Field"),
        _concept(9003, "Stage value target B", "Meas Value", "CDM", "Field"),
        _concept(9101, "ER NAACCR source", "Observation", "NAACCR", "NAACCR Item", "3827", ""),
        _concept(9102, "Stage NAACCR source", "Meas Value", "NAACCR", "NAACCR Value", "3605@1", ""),
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
            ["Observation", "Observation", "13"],
            ["Meas Value", "Meas Value", "14"],
        ],
        "vocabulary": [
            ["None", "No vocabulary", "Synthetic", "test-v1", "3"],
            ["Type Concept", "Type Concept", "Synthetic", "test-v1", "4"],
            ["CDM", "CDM", "Synthetic", "test-v1", "5"],
            ["Gender", "Gender", "Synthetic", "test-v1", "11"],
            ["NAACCR", "NAACCR", "Synthetic", "test-v1", "19"],
        ],
        "concept_class": [
            ["Undefined", "Undefined", "6"],
            ["Type Concept", "Type Concept", "7"],
            ["Field", "Field", "8"],
            ["Gender", "Gender", "12"],
            ["Vocabulary", "Vocabulary", "15"],
            ["Concept Class", "Concept Class", "16"],
            ["NAACCR Item", "NAACCR Item", "17"],
            ["NAACCR Value", "NAACCR Value", "18"],
        ],
        "relationship": [
            ["Is a", "Is a", "1", "1", "Is a", "9"],
            ["Maps to", "Maps to", "0", "0", "Mapped from", "20"],
            ["Mapped from", "Mapped from", "0", "0", "Maps to", "21"],
        ],
        "concept": concepts,
        "concept_relationship": [
            ["32879", "32817", "Is a", "19700101", "20991231", ""],
            ["9101", "9001", "Maps to", "19700101", "20991231", ""],
            ["9102", "9003", "Maps to", "19700101", "20991231", ""],
            ["9102", "9002", "Maps to", "19700101", "20991231", ""],
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
