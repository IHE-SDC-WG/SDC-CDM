"""Pre-commit checks for a newly loaded Athena vocabulary."""

from __future__ import annotations

from sdc_cdm.cdm.tables import TABLE_SPECS, VOCABULARY_SCHEMA
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import constraint_violations
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.vocab.constants import read_constant_specs, valid_exact_candidates


def target_row_counts(backend: DatabaseBackend) -> dict[str, int]:
    return {
        spec.table_name: int(
            backend.fetch_one(
                f"SELECT COUNT(*) FROM "
                f"{backend.qualified_name(VOCABULARY_SCHEMA, spec.table_name)}"
            )[0]
        )
        for spec in TABLE_SPECS
    }


def _integrity_queries(
    backend: DatabaseBackend,
) -> tuple[tuple[str, str], ...]:
    def table(name: str) -> str:
        return backend.qualified_name(VOCABULARY_SCHEMA, name)

    return (
        (
            "concept.domain_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('domain')} d ON d.domain_id = c.domain_id
            WHERE d.domain_id IS NULL
            """,
        ),
        (
            "concept.vocabulary_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('vocabulary')} v
              ON v.vocabulary_id = c.vocabulary_id
            WHERE v.vocabulary_id IS NULL
            """,
        ),
        (
            "concept.concept_class_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept')} c
            LEFT JOIN {table('concept_class')} cc
              ON cc.concept_class_id = c.concept_class_id
            WHERE cc.concept_class_id IS NULL
            """,
        ),
        (
            "vocabulary.vocabulary_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('vocabulary')} v
            LEFT JOIN {table('concept')} c
              ON c.concept_id = v.vocabulary_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "domain.domain_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('domain')} d
            LEFT JOIN {table('concept')} c
              ON c.concept_id = d.domain_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "concept_class.concept_class_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_class')} cc
            LEFT JOIN {table('concept')} c
              ON c.concept_id = cc.concept_class_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "relationship.reverse_relationship_id",
            f"""
            SELECT COUNT(*)
            FROM {table('relationship')} r
            LEFT JOIN {table('relationship')} reverse_r
              ON reverse_r.relationship_id = r.reverse_relationship_id
            WHERE reverse_r.relationship_id IS NULL
            """,
        ),
        (
            "relationship.relationship_concept_id",
            f"""
            SELECT COUNT(*)
            FROM {table('relationship')} r
            LEFT JOIN {table('concept')} c
              ON c.concept_id = r.relationship_concept_id
            WHERE c.concept_id IS NULL
            """,
        ),
        (
            "concept_relationship references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_relationship')} cr
            LEFT JOIN {table('concept')} c1
              ON c1.concept_id = cr.concept_id_1
            LEFT JOIN {table('concept')} c2
              ON c2.concept_id = cr.concept_id_2
            LEFT JOIN {table('relationship')} r
              ON r.relationship_id = cr.relationship_id
            WHERE c1.concept_id IS NULL
               OR c2.concept_id IS NULL
               OR r.relationship_id IS NULL
            """,
        ),
        (
            "concept_synonym references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_synonym')} cs
            LEFT JOIN {table('concept')} c
              ON c.concept_id = cs.concept_id
            LEFT JOIN {table('concept')} language_c
              ON language_c.concept_id = cs.language_concept_id
            WHERE c.concept_id IS NULL OR language_c.concept_id IS NULL
            """,
        ),
        (
            "concept_ancestor references",
            f"""
            SELECT COUNT(*)
            FROM {table('concept_ancestor')} ca
            LEFT JOIN {table('concept')} ancestor_c
              ON ancestor_c.concept_id = ca.ancestor_concept_id
            LEFT JOIN {table('concept')} descendant_c
              ON descendant_c.concept_id = ca.descendant_concept_id
            WHERE ancestor_c.concept_id IS NULL
               OR descendant_c.concept_id IS NULL
            """,
        ),
        (
            "drug_strength required references",
            f"""
            SELECT COUNT(*)
            FROM {table('drug_strength')} ds
            LEFT JOIN {table('concept')} drug_c
              ON drug_c.concept_id = ds.drug_concept_id
            LEFT JOIN {table('concept')} ingredient_c
              ON ingredient_c.concept_id = ds.ingredient_concept_id
            WHERE drug_c.concept_id IS NULL
               OR ingredient_c.concept_id IS NULL
            """,
        ),
        (
            "drug_strength unit references",
            f"""
            SELECT COUNT(*)
            FROM {table('drug_strength')} ds
            LEFT JOIN {table('concept')} amount_c
              ON amount_c.concept_id = ds.amount_unit_concept_id
            LEFT JOIN {table('concept')} numerator_c
              ON numerator_c.concept_id = ds.numerator_unit_concept_id
            LEFT JOIN {table('concept')} denominator_c
              ON denominator_c.concept_id = ds.denominator_unit_concept_id
            WHERE (ds.amount_unit_concept_id IS NOT NULL
                   AND amount_c.concept_id IS NULL)
               OR (ds.numerator_unit_concept_id IS NOT NULL
                   AND numerator_c.concept_id IS NULL)
               OR (ds.denominator_unit_concept_id IS NOT NULL
                   AND denominator_c.concept_id IS NULL)
            """,
        ),
    )


def validate_loaded_data(
    backend: DatabaseBackend, expected_counts: dict[str, int]
) -> None:
    actual_counts = target_row_counts(backend)
    count_errors = [
        f"{table}: file={expected_counts[table]}, database={actual_counts[table]}"
        for table in expected_counts
        if expected_counts[table] != actual_counts[table]
    ]
    if count_errors:
        raise VocabularyError(
            "Vocabulary row-count validation failed:\n- " + "\n- ".join(count_errors)
        )

    missing_pairs = [
        (spec.vocabulary_id, spec.concept_code)
        for spec in read_constant_specs()
        if not valid_exact_candidates(backend, spec)
    ]
    if missing_pairs:
        raise VocabularyError(
            "Athena extract does not contain valid concepts required by "
            "database/seed/concept_constants.csv: "
            + ", ".join(repr(pair) for pair in missing_pairs)
        )

    orphan_errors: list[str] = []
    for label, sql in _integrity_queries(backend):
        count = int(backend.fetch_one(sql)[0])
        if count:
            orphan_errors.append(f"{label}: {count}")
    foreign_key_rows = constraint_violations(backend, VOCABULARY_SCHEMA)
    if foreign_key_rows:
        orphan_errors.append(f"database foreign-key check: {len(foreign_key_rows)}")
    if orphan_errors:
        raise VocabularyError(
            "Vocabulary integrity validation failed:\n- "
            + "\n- ".join(orphan_errors)
        )
