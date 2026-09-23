-- NAACCR -> OMOP concept map tables, local concept allocation, and coverage view.
-- Owned by manifest DDL and reapplied on change; rows are written by `maps build`.
-- The SQL-Server-only NAACCR2026 vocabulary supplement no longer creates or writes
-- these tables. Object names are lower-case to match the bridge ETL joins.
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'naaccr') EXEC('CREATE SCHEMA naaccr');
GO

-- One-time upgrade. An earlier revision of the NAACCR2026 supplement created both map
-- tables without mapping_layer. Their rows are derived and `maps build` regenerates them,
-- so drop that shape and let the guarded CREATE below rebuild it. No-op once the new
-- shape exists. Under a case-sensitive collation the legacy upper-case names would be
-- separate objects; CI and default installs are case-insensitive.
IF OBJECT_ID('naaccr.naaccr_concept_map', 'U') IS NOT NULL
   AND COL_LENGTH('naaccr.naaccr_concept_map', 'mapping_layer') IS NULL
  DROP TABLE naaccr.naaccr_concept_map;
IF OBJECT_ID('naaccr.naaccr_value_concept_map', 'U') IS NOT NULL
   AND COL_LENGTH('naaccr.naaccr_value_concept_map', 'mapping_layer') IS NULL
  DROP TABLE naaccr.naaccr_value_concept_map;
GO

-- Two-slot contract (Phase 2): source_concept_id is the NAACCR source concept (Athena
-- NAACCR or a NAACCR_LOCAL mint) and is never 0; concept_id is the standard OMOP target,
-- 0 when no standard target exists. mapping_layer records which build layer produced the
-- row. created_at is written by Python as ISO-8601 UTC in both dialects (no DB default).
-- Keys stay version-independent: item_num and (item_num, code).
IF OBJECT_ID('naaccr.naaccr_concept_map', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.naaccr_concept_map (
    item_num INT NOT NULL,
    source_concept_id BIGINT NOT NULL,
    concept_id BIGINT NOT NULL,
    target_domain_id NVARCHAR(20) NULL,
    concept_code NVARCHAR(50) NULL,
    concept_name NVARCHAR(255) NULL,
    mapping_layer NVARCHAR(20) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    CONSTRAINT PK_naaccr_concept_map PRIMARY KEY (item_num),
    CONSTRAINT CK_naaccr_concept_map_source_concept_id CHECK (source_concept_id <> 0),
    CONSTRAINT CK_naaccr_concept_map_mapping_layer
      CHECK (mapping_layer IN ('athena_standard', 'curated_override', 'local_mint'))
  );
END
GO

IF OBJECT_ID('naaccr.naaccr_value_concept_map', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.naaccr_value_concept_map (
    item_num INT NOT NULL,
    code NVARCHAR(255) NOT NULL,
    source_concept_id BIGINT NOT NULL,
    concept_id BIGINT NOT NULL,
    target_domain_id NVARCHAR(20) NULL,
    concept_code NVARCHAR(100) NULL,
    concept_name NVARCHAR(MAX) NULL,
    mapping_layer NVARCHAR(20) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    CONSTRAINT PK_naaccr_value_concept_map PRIMARY KEY (item_num, code),
    CONSTRAINT CK_naaccr_value_concept_map_source_concept_id CHECK (source_concept_id <> 0),
    CONSTRAINT CK_naaccr_value_concept_map_mapping_layer
      CHECK (mapping_layer IN ('athena_standard', 'curated_override', 'local_mint'))
  );
END
GO

-- Append-only ledger of locally minted NAACCR_LOCAL concept ids, so layer-3 mints keep
-- the same id across rebuilds. Ids are allocated from 2,100,000,000 through
-- 2,147,483,647 (the NAACCR2026 supplement owns 2,000,000,000 through 2,099,999,999).
-- item_num = 0 and code = '' are sentinels for kinds without an item or code, so the
-- UNIQUE key behaves the same in both dialects. allocated_at is written by Python as
-- ISO-8601 UTC.
IF OBJECT_ID('naaccr.local_concept_allocation', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.local_concept_allocation (
    concept_id BIGINT NOT NULL,
    concept_kind NVARCHAR(20) NOT NULL,
    item_num INT NOT NULL CONSTRAINT DF_local_concept_allocation_item_num DEFAULT 0,
    code NVARCHAR(255) NOT NULL CONSTRAINT DF_local_concept_allocation_code DEFAULT '',
    concept_code NVARCHAR(100) NOT NULL,
    concept_name NVARCHAR(255) NULL,
    allocated_at NVARCHAR(40) NOT NULL,
    CONSTRAINT PK_local_concept_allocation PRIMARY KEY (concept_id),
    CONSTRAINT CK_local_concept_allocation_range
      CHECK (concept_id BETWEEN 2100000000 AND 2147483647),
    CONSTRAINT CK_local_concept_allocation_kind
      CHECK (concept_kind IN ('vocabulary', 'concept_class', 'item', 'value')),
    CONSTRAINT CK_local_concept_allocation_sentinels CHECK (
        (concept_kind = 'vocabulary' AND item_num = 0 AND code = '')
        OR (concept_kind = 'concept_class' AND item_num = 0 AND code <> '')
        OR (concept_kind = 'item' AND item_num <> 0 AND code = '')
        OR (concept_kind = 'value' AND item_num <> 0)
    ),
    CONSTRAINT UQ_local_concept_allocation_key UNIQUE (concept_kind, item_num, code),
    CONSTRAINT UQ_local_concept_allocation_code UNIQUE (concept_code)
  );
END
GO

-- Coverage by (algorithm, scope, section, mapping_layer). dd_version_id is taken from the
-- single is_current row per algorithm (enforced by idx_dd_version_current_algorithm),
-- never from MAX(dd_version_id). Retired items (year_retired IS NOT NULL) are excluded.
-- scope is 'item' or 'value'; mapping_layer is 'unmapped' for rows with no map entry.
-- The view cannot read the exclusions CSV; `maps coverage` reports exclusions separately.
-- CREATE OR ALTER must open its batch, hence the GO above.
CREATE OR ALTER VIEW naaccr.concept_map_coverage AS
WITH current_version AS (
    SELECT algorithm, dd_version_id
    FROM naaccr.DATA_DICTIONARY_VERSION
    WHERE is_current = 1
),
item_scope AS (
    SELECT cv.algorithm,
           'item' AS scope,
           ni.section,
           COALESCE(m.mapping_layer, 'unmapped') AS mapping_layer
    FROM current_version cv
    JOIN naaccr.NAACCR_ITEM ni
      ON ni.dd_version_id = cv.dd_version_id
     AND ni.year_retired IS NULL
    LEFT JOIN naaccr.naaccr_concept_map m
      ON m.item_num = ni.item_num
),
value_scope AS (
    SELECT cv.algorithm,
           'value' AS scope,
           ni.section,
           COALESCE(m.mapping_layer, 'unmapped') AS mapping_layer
    FROM current_version cv
    JOIN naaccr.NAACCR_ITEM ni
      ON ni.dd_version_id = cv.dd_version_id
     AND ni.year_retired IS NULL
    JOIN (
        SELECT DISTINCT dd_version_id, item_num, code
        FROM naaccr.NAACCR_ITEM_ALLOWED_CODE
    ) ac
      ON ac.dd_version_id = ni.dd_version_id
     AND ac.item_num = ni.item_num
    LEFT JOIN naaccr.naaccr_value_concept_map m
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
GO
