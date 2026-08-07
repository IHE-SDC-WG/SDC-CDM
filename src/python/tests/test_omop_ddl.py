from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TABLE_DDL_PATH = (
    ROOT / "database/schemas/omop/ddl/sqlserver/1_OMOPCDM_sqlserver_5.4_ddl.sql"
)
CONSTRAINTS_DDL_PATH = (
    ROOT
    / "database/schemas/omop/ddl/sqlserver/3_OMOPCDM_sqlserver_5.4_constraints.sql"
)


def test_sqlserver_identities_are_limited_to_pipeline_generated_keys() -> None:
    ddl = TABLE_DDL_PATH.read_text(encoding="utf-8")
    identity_columns = {
        match.group(1).lower()
        for match in re.finditer(
            r"^\s*([a-z_]+)\s+(?:integer|bigint)\s+IDENTITY\(1,1\)",
            ddl,
            re.IGNORECASE | re.MULTILINE,
        )
    }

    assert identity_columns == {
        "condition_occurrence_id",
        "episode_id",
        "measurement_id",
        "note_id",
        "observation_id",
        "observation_period_id",
    }
    assert re.search(r"^\s*concept_id integer NOT NULL", ddl, re.MULTILINE)
    assert re.search(r"^\s*person_id integer NOT NULL", ddl, re.MULTILINE)
    assert not re.search(r"^\s*person_id bigint\b", ddl, re.IGNORECASE | re.MULTILINE)


def test_sqlserver_constraints_omit_invalid_reversed_cohort_foreign_key() -> None:
    constraints = CONSTRAINTS_DDL_PATH.read_text(encoding="utf-8")

    assert not re.search(
        r"ALTER TABLE\s+omop\.COHORT_DEFINITION\s+ADD CONSTRAINT\s+\S+\s+"
        r"FOREIGN KEY\s*\(cohort_definition_id\)\s+"
        r"REFERENCES\s+omop\.COHORT\s*\(COHORT_DEFINITION_ID\)",
        constraints,
        re.IGNORECASE,
    )
