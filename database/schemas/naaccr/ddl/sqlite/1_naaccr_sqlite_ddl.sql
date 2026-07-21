PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS naaccr.staging_schema (
    schema_id_number TEXT NOT NULL PRIMARY KEY,
    schema_id TEXT NULL,
    schema_name TEXT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.schema_selection_rule (
    schema_selection_rule_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    schema_id_number TEXT NOT NULL REFERENCES staging_schema(schema_id_number),
    site TEXT NULL,
    histology TEXT NULL,
    behavior TEXT NULL,
    sex_at_birth TEXT NULL,
    discriminator_1 TEXT NULL,
    discriminator_2 TEXT NULL,
    year_dx TEXT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_item (
    item_num INTEGER NOT NULL PRIMARY KEY,
    name TEXT NULL,
    xml_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item (
    schema_id_number TEXT NOT NULL REFERENCES staging_schema(schema_id_number),
    item_num INTEGER NOT NULL REFERENCES naaccr_item(item_num),
    used_for_staging TEXT NULL,
    default_value TEXT NULL,
    description TEXT NULL,
    rationale TEXT NULL,
    additional_info TEXT NULL,
    table_notes TEXT NULL,
    coding_guidelines TEXT NULL,
    PRIMARY KEY (schema_id_number, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.registry (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item_requirement (
    schema_item_requirement_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    registry_id INTEGER NOT NULL REFERENCES registry(id),
    is_required INTEGER NOT NULL,
    FOREIGN KEY (schema_id_number, item_num) REFERENCES schema_item(schema_id_number, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item_code (
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    code TEXT NOT NULL,
    description TEXT NULL,
    PRIMARY KEY (schema_id_number, item_num, code),
    FOREIGN KEY (schema_id_number, item_num) REFERENCES schema_item(schema_id_number, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_concept_map (
    item_num INTEGER NOT NULL PRIMARY KEY REFERENCES naaccr_item(item_num),
    concept_id INTEGER NOT NULL,
    concept_code TEXT NULL,
    concept_name TEXT NULL,
    domain_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_value_concept_map (
    item_num INTEGER NOT NULL,
    code TEXT NOT NULL,
    concept_id INTEGER NOT NULL,
    concept_code TEXT NULL,
    concept_name TEXT NULL,
    PRIMARY KEY (item_num, code)
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_value (
    naaccr_value_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    episode_key TEXT NOT NULL,
    -- logical reference to sdc.sdc_report.sdc_report_id; not an enforced FK (cross-schema/attached-DB)
    sdc_report_id INTEGER NULL,
    report_accession TEXT NULL,
    schema_id_number TEXT NULL,
    item_num INTEGER NOT NULL,
    value_code TEXT NULL,
    value_num REAL NULL,
    value_unit_source TEXT NULL,
    observation_date TEXT NULL
);

CREATE INDEX IF NOT EXISTS naaccr.idx_naaccr_value_person_episode
    ON naaccr_value (person_id, episode_key);
CREATE INDEX IF NOT EXISTS naaccr.idx_naaccr_value_report_item
    ON naaccr_value (report_accession, item_num);
CREATE INDEX IF NOT EXISTS naaccr.idx_naaccr_value_item_code
    ON naaccr_value (item_num, value_code);
CREATE INDEX IF NOT EXISTS naaccr.idx_naaccr_value_sdc_report
    ON naaccr_value (sdc_report_id);

COMMIT;
