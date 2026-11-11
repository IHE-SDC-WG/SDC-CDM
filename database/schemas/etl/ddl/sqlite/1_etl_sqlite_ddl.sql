PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS etl.concept_constant (
    constant_name TEXT NOT NULL PRIMARY KEY,
    concept_id INTEGER NOT NULL,
    vocabulary_id TEXT NOT NULL,
    concept_code TEXT NOT NULL,
    resolved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS etl.run (
    run_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    dialect TEXT NOT NULL CHECK (dialect IN ('sqlite', 'sqlserver')),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at TEXT NULL,
    error_message TEXT NULL
);

CREATE INDEX IF NOT EXISTS etl.idx_run_status ON run (status, started_at);

CREATE TABLE IF NOT EXISTS etl.schema_migration (
    migration_path TEXT NOT NULL PRIMARY KEY,
    file_sha256 TEXT NOT NULL CHECK (length(file_sha256) = 64),
    previous_sha256 TEXT NULL CHECK (previous_sha256 IS NULL OR length(previous_sha256) = 64),
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_run_id INTEGER NULL REFERENCES run(run_id)
);

-- How the bridge derived each omop.observation_period row, keyed by its
-- observation_period_id, and the naaccr.naaccr_value row or intake.inbound_envelope
-- that set its start and end dates. Logical references; not enforced FKs
-- (cross-schema/attached-DB).
CREATE TABLE IF NOT EXISTS etl.observation_period_derivation (
    observation_period_id INTEGER NOT NULL PRIMARY KEY,
    person_id INTEGER NOT NULL UNIQUE,
    derivation TEXT NOT NULL
        CHECK (derivation IN ('naaccr_diagnosis_to_last_contact', 'clinical_date_span')),
    start_naaccr_value_id INTEGER NULL,
    start_inbound_envelope_id INTEGER NULL,
    end_naaccr_value_id INTEGER NULL,
    end_inbound_envelope_id INTEGER NULL,
    -- Each boundary comes from exactly one source; the NAACCR rule only from values.
    CHECK ((start_naaccr_value_id IS NULL AND start_inbound_envelope_id IS NOT NULL)
        OR (start_naaccr_value_id IS NOT NULL AND start_inbound_envelope_id IS NULL)),
    CHECK ((end_naaccr_value_id IS NULL AND end_inbound_envelope_id IS NOT NULL)
        OR (end_naaccr_value_id IS NOT NULL AND end_inbound_envelope_id IS NULL)),
    CHECK (derivation = 'clinical_date_span'
        OR (start_naaccr_value_id IS NOT NULL AND end_naaccr_value_id IS NOT NULL))
);

-- The cdm_source seed row of the current bridge run. Python replaces it inside
-- the run's data transaction; the bridge adds the vocabulary version and the
-- CDM version concept when it writes omop.cdm_source.
CREATE TABLE IF NOT EXISTS etl.cdm_source_seed (
    cdm_source_name TEXT NOT NULL,
    cdm_source_abbreviation TEXT NOT NULL,
    cdm_holder TEXT NOT NULL,
    source_description TEXT NULL,
    source_documentation_reference TEXT NULL,
    cdm_etl_reference TEXT NULL,
    source_release_date TEXT NOT NULL,
    cdm_release_date TEXT NOT NULL,
    cdm_version TEXT NOT NULL
);

COMMIT;
