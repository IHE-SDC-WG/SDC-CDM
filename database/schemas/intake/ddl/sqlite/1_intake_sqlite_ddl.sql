PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS intake.inbound_message (
    inbound_message_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    source_format TEXT NOT NULL,
    media_type TEXT NOT NULL,
    raw_blob BLOB NOT NULL,
    raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
    byte_length INTEGER NOT NULL CHECK (byte_length >= 0),
    is_content_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (is_content_duplicate IN (0, 1)),
    first_seen_inbound_message_id INTEGER NULL REFERENCES inbound_message(inbound_message_id),
    received_datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    received_by TEXT NULL,
    message_control_id TEXT NULL,
    sending_facility TEXT NULL,
    message_profile TEXT NULL,
    envelope_json TEXT NULL,
    envelope_version TEXT NULL,
    parser_name TEXT NULL,
    parser_version TEXT NULL,
    parse_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'failed', 'quarantined')),
    parse_error TEXT NULL,
    CHECK (
        (is_content_duplicate = 0 AND first_seen_inbound_message_id IS NULL)
        OR (is_content_duplicate = 1 AND first_seen_inbound_message_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS intake.idx_inbound_message_sha256
    ON inbound_message (raw_sha256);
CREATE INDEX IF NOT EXISTS intake.idx_inbound_message_control_id
    ON inbound_message (message_control_id);

CREATE TABLE IF NOT EXISTS intake.inbound_message_diagnostic (
    inbound_message_diagnostic_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    inbound_message_id INTEGER NOT NULL REFERENCES inbound_message(inbound_message_id),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    code TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS intake.idx_inbound_message_diagnostic_message
    ON inbound_message_diagnostic (inbound_message_id);

CREATE TABLE IF NOT EXISTS intake.patient (
    patient_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    person_source_value TEXT NOT NULL,
    assigning_authority TEXT NOT NULL DEFAULT '',
    birth_year INTEGER NULL,
    birth_month INTEGER NULL,
    birth_day INTEGER NULL,
    gender_source_value TEXT NULL,
    first_seen_inbound_message_id INTEGER NULL REFERENCES inbound_message(inbound_message_id),
    created_datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (assigning_authority, person_source_value),
    CHECK (birth_year IS NULL OR birth_year BETWEEN 1 AND 9999),
    CHECK (birth_month IS NULL OR birth_month BETWEEN 1 AND 12),
    CHECK (birth_day IS NULL OR birth_day BETWEEN 1 AND 31),
    CHECK (birth_year IS NOT NULL OR birth_month IS NULL),
    CHECK (birth_month IS NOT NULL OR birth_day IS NULL)
);

COMMIT;
