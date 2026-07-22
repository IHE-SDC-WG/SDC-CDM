PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Gap #1: algorithm + version as a first-class dimension. Every dictionary row is
-- scoped to a (algorithm, version) generation so multiple NAACCR/staging versions
-- can coexist and captured answers can record the version they were coded against.
CREATE TABLE IF NOT EXISTS naaccr.data_dictionary_version (
    dd_version_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    algorithm TEXT NOT NULL,
    version TEXT NOT NULL,
    naaccr_version TEXT NULL,
    valid_start_date TEXT NULL,
    valid_end_date TEXT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    source_api TEXT NULL,
    loaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (algorithm, version)
);

CREATE TABLE IF NOT EXISTS naaccr.staging_schema (
    dd_version_id INTEGER NOT NULL REFERENCES data_dictionary_version(dd_version_id),
    schema_id_number TEXT NOT NULL,
    schema_id TEXT NULL,
    schema_name TEXT NULL,
    PRIMARY KEY (dd_version_id, schema_id_number)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_selection_rule (
    schema_selection_rule_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    site TEXT NULL,
    histology TEXT NULL,
    behavior TEXT NULL,
    sex_at_birth TEXT NULL,
    discriminator_1 TEXT NULL,
    discriminator_2 TEXT NULL,
    year_dx TEXT NULL,
    FOREIGN KEY (dd_version_id, schema_id_number)
        REFERENCES staging_schema(dd_version_id, schema_id_number)
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_item (
    dd_version_id INTEGER NOT NULL REFERENCES data_dictionary_version(dd_version_id),
    item_num INTEGER NOT NULL,
    name TEXT NULL,
    xml_id TEXT NULL,
    -- Gap #2a: field metadata available from the SEER Staging API (per-input unit/decimals).
    unit TEXT NULL,
    decimal_places INTEGER NULL,
    -- Gap #2b: field metadata from the NAACCR Data Dictionary API / imsweb layout.
    -- Nullable so the staging-only load works before the DD-API enrichment runs.
    data_type TEXT NULL,
    length INTEGER NULL,
    padding TEXT NULL,
    alignment TEXT NULL,
    trim TEXT NULL,
    section TEXT NULL,
    parent_xml_element TEXT NULL,
    PRIMARY KEY (dd_version_id, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item (
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    -- Gap #4: distinguish captured inputs from derived staging outputs.
    item_role TEXT NOT NULL DEFAULT 'input',
    used_for_staging TEXT NULL,
    default_value TEXT NULL,
    description TEXT NULL,
    rationale TEXT NULL,
    additional_info TEXT NULL,
    table_notes TEXT NULL,
    coding_guidelines TEXT NULL,
    PRIMARY KEY (dd_version_id, schema_id_number, item_num),
    FOREIGN KEY (dd_version_id, schema_id_number)
        REFERENCES staging_schema(dd_version_id, schema_id_number),
    FOREIGN KEY (dd_version_id, item_num)
        REFERENCES naaccr_item(dd_version_id, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.registry (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item_requirement (
    schema_item_requirement_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    registry_id INTEGER NOT NULL REFERENCES registry(id),
    is_required INTEGER NOT NULL,
    UNIQUE (dd_version_id, schema_id_number, item_num, registry_id),
    FOREIGN KEY (dd_version_id, schema_id_number, item_num)
        REFERENCES schema_item(dd_version_id, schema_id_number, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item_code (
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    code TEXT NOT NULL,
    description TEXT NULL,
    PRIMARY KEY (dd_version_id, schema_id_number, item_num, code),
    FOREIGN KEY (dd_version_id, schema_id_number, item_num)
        REFERENCES schema_item(dd_version_id, schema_id_number, item_num)
);

-- Gap #3: persist the SEER staging lookup tables (the value-validation / staging
-- building blocks). Natural-keyed on (dd_version_id, table_key). Row cells are stored
-- as a JSON array of strings so the shape is portable across all three dialects.
CREATE TABLE IF NOT EXISTS naaccr.staging_table (
    dd_version_id INTEGER NOT NULL REFERENCES data_dictionary_version(dd_version_id),
    table_key TEXT NOT NULL,
    name TEXT NULL,
    title TEXT NULL,
    subtitle TEXT NULL,
    description TEXT NULL,
    notes TEXT NULL,
    coding_guidelines TEXT NULL,
    PRIMARY KEY (dd_version_id, table_key)
);

CREATE TABLE IF NOT EXISTS naaccr.staging_table_column (
    dd_version_id INTEGER NOT NULL,
    table_key TEXT NOT NULL,
    col_index INTEGER NOT NULL,
    col_key TEXT NULL,
    col_name TEXT NULL,
    col_type TEXT NULL,
    col_source TEXT NULL,
    PRIMARY KEY (dd_version_id, table_key, col_index),
    FOREIGN KEY (dd_version_id, table_key)
        REFERENCES staging_table(dd_version_id, table_key)
);

CREATE TABLE IF NOT EXISTS naaccr.staging_table_row (
    dd_version_id INTEGER NOT NULL,
    table_key TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    cells TEXT NULL, -- JSON array of cell values, ordered by col_index
    PRIMARY KEY (dd_version_id, table_key, row_index),
    FOREIGN KEY (dd_version_id, table_key)
        REFERENCES staging_table(dd_version_id, table_key)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_involved_table (
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    table_key TEXT NOT NULL,
    PRIMARY KEY (dd_version_id, schema_id_number, table_key),
    FOREIGN KEY (dd_version_id, schema_id_number)
        REFERENCES staging_schema(dd_version_id, schema_id_number),
    FOREIGN KEY (dd_version_id, table_key)
        REFERENCES staging_table(dd_version_id, table_key)
);

-- OMOP concept maps are version-independent: a NAACCR item / value code maps to the
-- same OMOP concept regardless of dictionary version, and the ETL bridge joins on
-- item_num / (item_num, code) alone. So they are keyed on item_num only and reference
-- naaccr_item logically (no composite FK).
CREATE TABLE IF NOT EXISTS naaccr.naaccr_concept_map (
    item_num INTEGER NOT NULL PRIMARY KEY,
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
    observation_date TEXT NULL,
    -- Gap #1: the dictionary version this answer was coded against. Nullable so existing
    -- import paths that do not yet supply it keep working; populate going forward.
    dd_version_id INTEGER NULL REFERENCES data_dictionary_version(dd_version_id)
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
