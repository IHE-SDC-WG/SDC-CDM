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

-- Older loads defaulted every version to current. Keep the newest row for each
-- algorithm before adding the one-current invariant on a re-applied build.
UPDATE naaccr.data_dictionary_version
SET is_current = 0
WHERE is_current = 1
  AND dd_version_id NOT IN (
      SELECT MAX(dd_version_id)
      FROM naaccr.data_dictionary_version
      WHERE is_current = 1
      GROUP BY algorithm
  );

CREATE UNIQUE INDEX IF NOT EXISTS naaccr.idx_dd_version_current_algorithm
    ON data_dictionary_version (algorithm) WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS naaccr.staging_schema (
    dd_version_id INTEGER NOT NULL REFERENCES data_dictionary_version(dd_version_id),
    schema_id_number TEXT NOT NULL,
    schema_id TEXT NOT NULL,
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
    -- Gap #2b: field metadata from SEER*API's NAACCR Data Dictionary endpoints.
    -- Nullable because the upstream DTO omits some fields and staging-only rows may be stubs.
    data_type TEXT NULL,
    length INTEGER NULL,
    -- No NAACCR-published source supplies padding, alignment, or trim. These
    -- fields existed only in the fixed-column layouts retired after v18.
    padding TEXT NULL,
    alignment TEXT NULL,
    trim TEXT NULL,
    section TEXT NULL,
    parent_xml_element TEXT NULL,
    record_types TEXT NULL, -- compact JSON array
    alternate_names TEXT NULL, -- compact JSON array
    source_of_standard TEXT NULL,
    allowable_values TEXT NULL,
    code_description TEXT NULL,
    code_note TEXT NULL,
    item_format TEXT NULL,
    description TEXT NULL,
    rationale TEXT NULL,
    general_notes TEXT NULL,
    clarification TEXT NULL,
    version_implemented TEXT NULL,
    year_implemented INTEGER NULL,
    version_retired TEXT NULL,
    year_retired INTEGER NULL,
    date_created TEXT NULL,
    date_modified TEXT NULL,
    PRIMARY KEY (dd_version_id, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_item_allowed_code (
    dd_version_id INTEGER NOT NULL,
    item_num INTEGER NOT NULL,
    code_seq INTEGER NOT NULL,
    code TEXT NOT NULL,
    description TEXT NULL,
    PRIMARY KEY (dd_version_id, item_num, code_seq),
    FOREIGN KEY (dd_version_id, item_num)
        REFERENCES naaccr_item(dd_version_id, item_num)
);

CREATE INDEX IF NOT EXISTS naaccr.idx_naaccr_item_allowed_code_lookup
    ON naaccr_item_allowed_code (dd_version_id, item_num, code);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_item_registry_requirement (
    dd_version_id INTEGER NOT NULL,
    item_num INTEGER NOT NULL,
    registry_code TEXT NOT NULL,
    collect_status TEXT NOT NULL,
    PRIMARY KEY (dd_version_id, item_num, registry_code),
    FOREIGN KEY (dd_version_id, item_num)
        REFERENCES naaccr_item(dd_version_id, item_num)
);

CREATE TABLE IF NOT EXISTS naaccr.schema_item (
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    -- Gap #4: distinguish captured inputs from derived staging outputs.
    item_role TEXT NOT NULL DEFAULT 'input',
    used_for_staging INTEGER NOT NULL DEFAULT 0
        CHECK (used_for_staging IN (0, 1)),
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
    dd_version_id INTEGER NOT NULL,
    schema_id_number TEXT NOT NULL,
    item_num INTEGER NOT NULL,
    registry_id INTEGER NOT NULL REFERENCES registry(id),
    is_required INTEGER NOT NULL,
    PRIMARY KEY (dd_version_id, schema_id_number, item_num, registry_id),
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

CREATE INDEX IF NOT EXISTS naaccr.idx_selection_schema
    ON schema_selection_rule (dd_version_id, schema_id_number);
CREATE INDEX IF NOT EXISTS naaccr.idx_item_schema
    ON schema_item (dd_version_id, schema_id_number);
CREATE INDEX IF NOT EXISTS naaccr.idx_req_schema_item
    ON schema_item_requirement (dd_version_id, schema_id_number, item_num);
CREATE INDEX IF NOT EXISTS naaccr.idx_code_schema_item
    ON schema_item_code (dd_version_id, schema_id_number, item_num);

-- Gap #3: persist the SEER staging lookup tables (the value-validation / staging
-- building blocks). Natural-keyed on (dd_version_id, table_key). Row cells are stored
-- as a JSON array of strings so the shape is portable across both supported dialects.
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
--
-- Two-slot contract (Phase 2): source_concept_id is the NAACCR source concept (Athena
-- NAACCR or a NAACCR_LOCAL mint) and is never 0; concept_id is the standard OMOP target,
-- 0 when no standard target exists. mapping_layer records which build layer produced the
-- row. created_at is written by Python as ISO-8601 UTC in both dialects (no DB default).
-- Rows are derived by `maps build`; the tables carry no dictionary version.
CREATE TABLE IF NOT EXISTS naaccr.naaccr_concept_map (
    item_num INTEGER NOT NULL PRIMARY KEY,
    source_concept_id INTEGER NOT NULL CHECK (source_concept_id <> 0),
    concept_id INTEGER NOT NULL,
    target_domain_id TEXT NULL,
    concept_code TEXT NULL,
    concept_name TEXT NULL,
    mapping_layer TEXT NOT NULL
        CHECK (mapping_layer IN ('athena_standard', 'curated_override', 'local_mint')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS naaccr.naaccr_value_concept_map (
    item_num INTEGER NOT NULL,
    code TEXT NOT NULL,
    source_concept_id INTEGER NOT NULL CHECK (source_concept_id <> 0),
    concept_id INTEGER NOT NULL,
    target_domain_id TEXT NULL,
    concept_code TEXT NULL,
    concept_name TEXT NULL,
    mapping_layer TEXT NOT NULL
        CHECK (mapping_layer IN ('athena_standard', 'curated_override', 'local_mint')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_num, code)
);

-- Append-only ledger of locally minted NAACCR_LOCAL concept ids, so layer-3 mints keep
-- the same id across rebuilds. Ids are allocated from 2,100,000,000 through
-- 2,199,999,999 (the SQL-Server-only NAACCR2026 supplement owns 2,000,000,000 through
-- 2,099,999,999). item_num = 0 and code = '' are sentinels for kinds without an item or
-- code, so UNIQUE (concept_kind, item_num, code) behaves the same in both dialects
-- (SQLite treats NULLs as distinct in UNIQUE; SQL Server does not).
-- allocated_at is written by Python as ISO-8601 UTC.
CREATE TABLE IF NOT EXISTS naaccr.local_concept_allocation (
    concept_id INTEGER NOT NULL PRIMARY KEY
        CHECK (concept_id BETWEEN 2100000000 AND 2199999999),
    concept_kind TEXT NOT NULL
        CHECK (concept_kind IN ('vocabulary', 'concept_class', 'item', 'value')),
    item_num INTEGER NOT NULL DEFAULT 0,
    code TEXT NOT NULL DEFAULT '',
    concept_code TEXT NOT NULL,
    concept_name TEXT NULL,
    allocated_at TEXT NOT NULL,
    CHECK (
        (concept_kind IN ('vocabulary', 'concept_class') AND item_num = 0 AND code = '')
        OR (concept_kind = 'item' AND item_num <> 0 AND code = '')
        OR (concept_kind = 'value' AND item_num <> 0)
    ),
    UNIQUE (concept_kind, item_num, code),
    UNIQUE (concept_code)
);

-- Coverage by (algorithm, scope, section, mapping_layer). dd_version_id is taken from the
-- single is_current row per algorithm (enforced by idx_dd_version_current_algorithm),
-- never from MAX(dd_version_id). Retired items (year_retired IS NOT NULL) are excluded.
-- scope is 'item' or 'value'; mapping_layer is 'unmapped' for rows with no map entry.
-- The view cannot read the exclusions CSV; `maps coverage` reports exclusions separately.
-- DROP + CREATE (not IF NOT EXISTS) so a changed definition takes effect when this file is
-- reapplied. The body stays unqualified: a view in an attached database may only
-- reference objects in that database.
DROP VIEW IF EXISTS naaccr.concept_map_coverage;
CREATE VIEW naaccr.concept_map_coverage AS
WITH current_version AS (
    SELECT algorithm, dd_version_id
    FROM data_dictionary_version
    WHERE is_current = 1
),
item_scope AS (
    SELECT cv.algorithm,
           'item' AS scope,
           ni.section,
           COALESCE(m.mapping_layer, 'unmapped') AS mapping_layer
    FROM current_version cv
    JOIN naaccr_item ni
      ON ni.dd_version_id = cv.dd_version_id
     AND ni.year_retired IS NULL
    LEFT JOIN naaccr_concept_map m
      ON m.item_num = ni.item_num
),
value_scope AS (
    SELECT cv.algorithm,
           'value' AS scope,
           ni.section,
           COALESCE(m.mapping_layer, 'unmapped') AS mapping_layer
    FROM current_version cv
    JOIN naaccr_item ni
      ON ni.dd_version_id = cv.dd_version_id
     AND ni.year_retired IS NULL
    JOIN (
        SELECT DISTINCT dd_version_id, item_num, code
        FROM naaccr_item_allowed_code
    ) ac
      ON ac.dd_version_id = ni.dd_version_id
     AND ac.item_num = ni.item_num
    LEFT JOIN naaccr_value_concept_map m
      ON m.item_num = ac.item_num
     AND m.code = ac.code
)
SELECT algorithm, scope, section, mapping_layer, COUNT(*) AS item_count
FROM (
    SELECT algorithm, scope, section, mapping_layer FROM item_scope
    UNION ALL
    SELECT algorithm, scope, section, mapping_layer FROM value_scope
) scoped
GROUP BY algorithm, scope, section, mapping_layer;

-- Value-code collisions (#100). The value map is keyed on (item_num, code) while
-- schema_item_code is keyed per staging schema, so one pair can carry several site-specific
-- meanings. Lists, for each algorithm's is_current generation, every (item_num, code) whose
-- trimmed, case-folded descriptions differ across schemas; NULL/blank descriptions are ignored.
-- description_min/max are two guaranteed-different, nonblank meanings: the MIN and MAX of the
-- same normalized expression, each shown as a trimmed original description (no list
-- aggregation: group_concat and STRING_AGG are not portable). The LEFT JOIN shows any existing
-- map row. SSDI year-split
-- schemas already carry distinct schema_id_numbers (Brain 00721 for 2018-2022 vs 09721 for
-- 2023+), so versioned meanings separate by schema. `maps coverage` (#119) reports this view.
-- DROP + CREATE and an unqualified body, as for concept_map_coverage above.
DROP VIEW IF EXISTS naaccr.value_code_collision;
CREATE VIEW naaccr.value_code_collision AS
WITH current_version AS (
    SELECT algorithm, dd_version_id
    FROM data_dictionary_version
    WHERE is_current = 1
),
collisions AS (
    SELECT cv.algorithm,
           cv.dd_version_id,
           sic.item_num,
           sic.code,
           COUNT(*) AS schema_count,
           COUNT(DISTINCT NULLIF(UPPER(LTRIM(RTRIM(sic.description))), '')) AS description_count,
           SUM(CASE WHEN UPPER(sic.description) LIKE '%OBSOLETE%' THEN 1 ELSE 0 END)
               AS obsolete_count,
           MIN(NULLIF(UPPER(LTRIM(RTRIM(sic.description))), '')) AS norm_min,
           MAX(NULLIF(UPPER(LTRIM(RTRIM(sic.description))), '')) AS norm_max
    FROM current_version cv
    JOIN schema_item_code sic
      ON sic.dd_version_id = cv.dd_version_id
    GROUP BY cv.algorithm, cv.dd_version_id, sic.item_num, sic.code
    HAVING COUNT(DISTINCT NULLIF(UPPER(LTRIM(RTRIM(sic.description))), '')) > 1
)
SELECT c.algorithm, c.dd_version_id, c.item_num, c.code,
       c.schema_count, c.description_count, c.obsolete_count,
       (SELECT MIN(LTRIM(RTRIM(s.description)))
        FROM schema_item_code s
        WHERE s.dd_version_id = c.dd_version_id
          AND s.item_num = c.item_num
          AND s.code = c.code
          AND UPPER(LTRIM(RTRIM(s.description))) = c.norm_min) AS description_min,
       (SELECT MIN(LTRIM(RTRIM(s.description)))
        FROM schema_item_code s
        WHERE s.dd_version_id = c.dd_version_id
          AND s.item_num = c.item_num
          AND s.code = c.code
          AND UPPER(LTRIM(RTRIM(s.description))) = c.norm_max) AS description_max,
       m.source_concept_id, m.concept_id, m.mapping_layer
FROM collisions c
LEFT JOIN naaccr_value_concept_map m
  ON m.item_num = c.item_num
 AND m.code = c.code;

CREATE TABLE IF NOT EXISTS naaccr.naaccr_value (
    naaccr_value_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    episode_key TEXT NOT NULL,
    -- logical reference to sdc.sdc_report.sdc_report_id; not an enforced FK (cross-schema/attached-DB)
    sdc_report_id INTEGER NULL,
    report_accession TEXT NULL,
    schema_id_number TEXT NULL,
    item_num INTEGER NOT NULL,
    obx_sub_id TEXT NULL,
    value_code TEXT NULL,
    value_num REAL NULL,
    value_text TEXT NULL,
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
