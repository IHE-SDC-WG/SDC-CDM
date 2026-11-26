"""OMOP CDM 5.4 table metadata shared by import and export paths.

TABLE_SPECS is the Athena vocabulary set the loader, integrity checks, and CLI
iterate. CLINICAL_TABLE_SPECS is the set the bridge populates, in an order where
every foreign key names an earlier table; `sdc-cdm export` writes both. Column
lists and order follow the CDM 5.4 DDL under database/schemas/omop/ddl.

Kinds: text, integer, decimal (exact numeric), float (double precision), date
(YYYY-MM-DD), and datetime.
"""

from __future__ import annotations

from dataclasses import dataclass


VOCABULARY_SCHEMA = "omop"
CDM_VERSION = "5.4"


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


def _spec(file_name: str, table_name: str, *columns: tuple[str, str]) -> TableSpec:
    return TableSpec(
        file_name,
        table_name,
        tuple(column for column, _kind in columns),
        tuple(kind for _column, kind in columns),
    )


CLINICAL_TABLE_SPECS = (
    _spec(
        "PERSON.csv",
        "person",
        ("person_id", "integer"),
        ("gender_concept_id", "integer"),
        ("year_of_birth", "integer"),
        ("month_of_birth", "integer"),
        ("day_of_birth", "integer"),
        ("birth_datetime", "datetime"),
        ("race_concept_id", "integer"),
        ("ethnicity_concept_id", "integer"),
        ("location_id", "integer"),
        ("provider_id", "integer"),
        ("care_site_id", "integer"),
        ("person_source_value", "text"),
        ("gender_source_value", "text"),
        ("gender_source_concept_id", "integer"),
        ("race_source_value", "text"),
        ("race_source_concept_id", "integer"),
        ("ethnicity_source_value", "text"),
        ("ethnicity_source_concept_id", "integer"),
    ),
    _spec(
        "OBSERVATION_PERIOD.csv",
        "observation_period",
        ("observation_period_id", "integer"),
        ("person_id", "integer"),
        ("observation_period_start_date", "date"),
        ("observation_period_end_date", "date"),
        ("period_type_concept_id", "integer"),
    ),
    _spec(
        "NOTE.csv",
        "note",
        ("note_id", "integer"),
        ("person_id", "integer"),
        ("note_date", "date"),
        ("note_datetime", "datetime"),
        ("note_type_concept_id", "integer"),
        ("note_class_concept_id", "integer"),
        ("note_title", "text"),
        ("note_text", "text"),
        ("encoding_concept_id", "integer"),
        ("language_concept_id", "integer"),
        ("provider_id", "integer"),
        ("visit_occurrence_id", "integer"),
        ("visit_detail_id", "integer"),
        ("note_source_value", "text"),
        ("note_event_id", "integer"),
        ("note_event_field_concept_id", "integer"),
    ),
    _spec(
        "MEASUREMENT.csv",
        "measurement",
        ("measurement_id", "integer"),
        ("person_id", "integer"),
        ("measurement_concept_id", "integer"),
        ("measurement_date", "date"),
        ("measurement_datetime", "datetime"),
        ("measurement_time", "text"),
        ("measurement_type_concept_id", "integer"),
        ("operator_concept_id", "integer"),
        ("value_as_number", "float"),
        ("value_as_concept_id", "integer"),
        ("unit_concept_id", "integer"),
        ("range_low", "float"),
        ("range_high", "float"),
        ("provider_id", "integer"),
        ("visit_occurrence_id", "integer"),
        ("visit_detail_id", "integer"),
        ("measurement_source_value", "text"),
        ("measurement_source_concept_id", "integer"),
        ("unit_source_value", "text"),
        ("unit_source_concept_id", "integer"),
        ("value_source_value", "text"),
        ("measurement_event_id", "integer"),
        ("meas_event_field_concept_id", "integer"),
    ),
    _spec(
        "OBSERVATION.csv",
        "observation",
        ("observation_id", "integer"),
        ("person_id", "integer"),
        ("observation_concept_id", "integer"),
        ("observation_date", "date"),
        ("observation_datetime", "datetime"),
        ("observation_type_concept_id", "integer"),
        ("value_as_number", "float"),
        ("value_as_string", "text"),
        ("value_as_concept_id", "integer"),
        ("qualifier_concept_id", "integer"),
        ("unit_concept_id", "integer"),
        ("provider_id", "integer"),
        ("visit_occurrence_id", "integer"),
        ("visit_detail_id", "integer"),
        ("observation_source_value", "text"),
        ("observation_source_concept_id", "integer"),
        ("unit_source_value", "text"),
        ("qualifier_source_value", "text"),
        ("value_source_value", "text"),
        ("observation_event_id", "integer"),
        ("obs_event_field_concept_id", "integer"),
    ),
    _spec(
        "CONDITION_OCCURRENCE.csv",
        "condition_occurrence",
        ("condition_occurrence_id", "integer"),
        ("person_id", "integer"),
        ("condition_concept_id", "integer"),
        ("condition_start_date", "date"),
        ("condition_start_datetime", "datetime"),
        ("condition_end_date", "date"),
        ("condition_end_datetime", "datetime"),
        ("condition_type_concept_id", "integer"),
        ("condition_status_concept_id", "integer"),
        ("stop_reason", "text"),
        ("provider_id", "integer"),
        ("visit_occurrence_id", "integer"),
        ("visit_detail_id", "integer"),
        ("condition_source_value", "text"),
        ("condition_source_concept_id", "integer"),
        ("condition_status_source_value", "text"),
    ),
    _spec(
        "EPISODE.csv",
        "episode",
        ("episode_id", "integer"),
        ("person_id", "integer"),
        ("episode_concept_id", "integer"),
        ("episode_start_date", "date"),
        ("episode_start_datetime", "datetime"),
        ("episode_end_date", "date"),
        ("episode_end_datetime", "datetime"),
        ("episode_parent_id", "integer"),
        ("episode_number", "integer"),
        ("episode_object_concept_id", "integer"),
        ("episode_type_concept_id", "integer"),
        ("episode_source_value", "text"),
        ("episode_source_concept_id", "integer"),
    ),
    _spec(
        "EPISODE_EVENT.csv",
        "episode_event",
        ("episode_id", "integer"),
        ("event_id", "integer"),
        ("episode_event_field_concept_id", "integer"),
    ),
    _spec(
        "CDM_SOURCE.csv",
        "cdm_source",
        ("cdm_source_name", "text"),
        ("cdm_source_abbreviation", "text"),
        ("cdm_holder", "text"),
        ("source_description", "text"),
        ("source_documentation_reference", "text"),
        ("cdm_etl_reference", "text"),
        ("source_release_date", "date"),
        ("cdm_release_date", "date"),
        ("cdm_version", "text"),
        ("cdm_version_concept_id", "integer"),
        ("vocabulary_version", "text"),
    ),
)


def expected_headers(spec: TableSpec) -> tuple[str, ...]:
    """Return the upper-case header an Athena file must carry for ``spec``."""
    return tuple(column.upper() for column in spec.columns)
