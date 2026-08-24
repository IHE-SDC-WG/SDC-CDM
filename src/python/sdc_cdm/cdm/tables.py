"""OMOP CDM vocabulary table metadata shared by import and export paths."""

from __future__ import annotations

from dataclasses import dataclass


VOCABULARY_SCHEMA = "omop"


@dataclass(frozen=True)
class TableSpec:
    file_name: str
    table_name: str
    columns: tuple[str, ...]
    kinds: tuple[str, ...]


TABLE_SPECS = (
    TableSpec(
        "DOMAIN.csv",
        "domain",
        ("domain_id", "domain_name", "domain_concept_id"),
        ("text", "text", "integer"),
    ),
    TableSpec(
        "VOCABULARY.csv",
        "vocabulary",
        (
            "vocabulary_id",
            "vocabulary_name",
            "vocabulary_reference",
            "vocabulary_version",
            "vocabulary_concept_id",
        ),
        ("text", "text", "text", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT_CLASS.csv",
        "concept_class",
        (
            "concept_class_id",
            "concept_class_name",
            "concept_class_concept_id",
        ),
        ("text", "text", "integer"),
    ),
    TableSpec(
        "RELATIONSHIP.csv",
        "relationship",
        (
            "relationship_id",
            "relationship_name",
            "is_hierarchical",
            "defines_ancestry",
            "reverse_relationship_id",
            "relationship_concept_id",
        ),
        ("text", "text", "text", "text", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT.csv",
        "concept",
        (
            "concept_id",
            "concept_name",
            "domain_id",
            "vocabulary_id",
            "concept_class_id",
            "standard_concept",
            "concept_code",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        (
            "integer",
            "text",
            "text",
            "text",
            "text",
            "text",
            "text",
            "date",
            "date",
            "text",
        ),
    ),
    TableSpec(
        "CONCEPT_RELATIONSHIP.csv",
        "concept_relationship",
        (
            "concept_id_1",
            "concept_id_2",
            "relationship_id",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        ("integer", "integer", "text", "date", "date", "text"),
    ),
    TableSpec(
        "CONCEPT_SYNONYM.csv",
        "concept_synonym",
        ("concept_id", "concept_synonym_name", "language_concept_id"),
        ("integer", "text", "integer"),
    ),
    TableSpec(
        "CONCEPT_ANCESTOR.csv",
        "concept_ancestor",
        (
            "ancestor_concept_id",
            "descendant_concept_id",
            "min_levels_of_separation",
            "max_levels_of_separation",
        ),
        ("integer", "integer", "integer", "integer"),
    ),
    TableSpec(
        "DRUG_STRENGTH.csv",
        "drug_strength",
        (
            "drug_concept_id",
            "ingredient_concept_id",
            "amount_value",
            "amount_unit_concept_id",
            "numerator_value",
            "numerator_unit_concept_id",
            "denominator_value",
            "denominator_unit_concept_id",
            "box_size",
            "valid_start_date",
            "valid_end_date",
            "invalid_reason",
        ),
        (
            "integer",
            "integer",
            "decimal",
            "integer",
            "decimal",
            "integer",
            "decimal",
            "integer",
            "integer",
            "date",
            "date",
            "text",
        ),
    ),
)

EXPECTED_HEADERS = {
    spec.file_name: tuple(column.upper() for column in spec.columns)
    for spec in TABLE_SPECS
}
