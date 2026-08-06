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

COMMIT;
