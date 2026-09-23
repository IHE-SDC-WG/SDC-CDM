/*
  NAACCR 2026 → OMOP CDM v5.4 Vocabulary Seeding (SQL Server)

  Purpose
  - Register a custom vocabulary for NAACCR 2026
  - Create custom concept classes and relationships needed for NAACCR items/values
  - Assign custom concept_ids for NAACCR items and their allowed values. omop.concept is
    the persistence: existing NAACCR2026 concepts are reused and only missing ones are
    minted, so re-running the script mints nothing new.
  - Populate concept, concept_relationship, and source_to_concept_map

  Ownership
  - This script does not create or write the NAACCR item / value mapping tables. Those
    are owned by the manifest DDL for concept maps and populated by `maps build`.
  - Item and value concepts are staged in session temp tables for the duration of one run.

  Assumptions
  - OMOP CDM v5.4 schema (incl. vocabulary tables) exists in omop
  - Source NAACCR 3NF tables exist in schema: naaccr (naaccr.NAACCR_ITEM, naaccr.SCHEMA_ITEM_CODE, naaccr.REGISTRY)
  - This script uses literal schema-qualified object names.

  Custom concept_id range used here: [2,000,000,000 .. 2,099,999,999]
  Rationale: stay below SQL Server INT max (2,147,483,647) and avoid collisions.
  The NAACCR_LOCAL mint range used by `maps build` is [2,100,000,000 .. 2,147,483,647]
  and is disjoint from this one.
*/

------------------------------------------------------------
-- Parameters
------------------------------------------------------------
-- Using literal schema names (omop.*) to ensure valid T-SQL; no variable-qualified objects

------------------------------------------------------------
-- Note: In this environment, concept_id is an INT. We must assign IDs below INT max.
------------------------------------------------------------

-- Vocabulary entry for NAACCR 2026
IF NOT EXISTS (SELECT 1
FROM omop.vocabulary
WHERE vocabulary_id = 'NAACCR2026')
BEGIN
  INSERT INTO omop.vocabulary
  (
      vocabulary_id, vocabulary_name, vocabulary_reference,
      vocabulary_version, vocabulary_concept_id
  )
  VALUES
  (
      'NAACCR2026',
      'NAACCR (Version 2026)',
      'https://naaccr.org/standards/',
      '2026.0',
      0
  );
END;

-- Concept classes used by this vocabulary (create paired concept and set concept_class_concept_id)
DECLARE @customLow   BIGINT = 2000000000;
DECLARE @customHigh  BIGINT = 2099999999;
DECLARE @nextCcId    BIGINT;

IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'NAACCR Item')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'NAACCR Data Item', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'NAACCR Item', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('NAACCR Item', 'NAACCR Data Item', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'NAACCR Value')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'NAACCR Item Allowed Value', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'NAACCR Value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('NAACCR Value', 'NAACCR Item Allowed Value', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Registry')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Registry', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Registry', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Registry', 'Registry', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Episode Type')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Episode Type', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Episode Type', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Episode Type', 'Episode Type', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Field')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Field Identifier', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Field', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Field', 'Field Identifier', @nextCcId);
END;

-- Ensure needed domains exist (most will already exist)
-- Also seed a representing concept so domain_concept_id is not NULL
IF NOT EXISTS (SELECT 1 FROM omop.domain WHERE domain_id = 'Meas Value')
BEGIN
  DECLARE @measValueConceptId BIGINT;
  SELECT @measValueConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  -- Ensure 'Domain' concept class exists (paired concept)
  IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Domain')
  BEGIN
    DECLARE @nextCcIdLocal BIGINT;
    SELECT @nextCcIdLocal = ISNULL(MAX(c.concept_id), @customLow) + 1
    FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

    INSERT INTO omop.concept
    (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
     standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
    VALUES
    (@nextCcIdLocal, N'Domain', N'Metadata', N'NAACCR2026', N'Concept Class',
     NULL, N'Domain', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

    INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
    VALUES ('Domain', 'Domain', @nextCcIdLocal);
  END;

  -- Create representing concept for 'Meas Value' domain
  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@measValueConceptId, N'Measurement Value', N'Metadata', N'NAACCR2026', N'Domain',
   NULL, N'Meas Value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.domain (domain_id, domain_name, domain_concept_id)
  VALUES ('Meas Value', 'Measurement Value', @measValueConceptId);
END;

-- Relationships for item/value modeling (usually already present)
-- Ensure 'Relationship' concept class exists (paired concept)
IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Relationship')
BEGIN
  DECLARE @nextCcRel BIGINT;
  SELECT @nextCcRel = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcRel, N'Relationship', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Relationship', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Relationship', 'Relationship', @nextCcRel);
END;

IF NOT EXISTS (SELECT 1 FROM omop.relationship WHERE relationship_id = 'Has value')
BEGIN
  DECLARE @hasValueConceptId BIGINT;
  SELECT @hasValueConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@hasValueConceptId, N'Has value', N'Metadata', N'NAACCR2026', N'Relationship',
   NULL, N'Has value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.relationship
  (relationship_id, relationship_name, is_hierarchical, defines_ancestry, reverse_relationship_id, relationship_concept_id)
  VALUES ('Has value', 'Has value', '0', '0', 'Value of', @hasValueConceptId);
END;

IF NOT EXISTS (SELECT 1 FROM omop.relationship WHERE relationship_id = 'Value of')
BEGIN
  DECLARE @valueOfConceptId BIGINT;
  SELECT @valueOfConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@valueOfConceptId, N'Value of', N'Metadata', N'NAACCR2026', N'Relationship',
   NULL, N'Value of', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.relationship
  (relationship_id, relationship_name, is_hierarchical, defines_ancestry, reverse_relationship_id, relationship_concept_id)
  VALUES ('Value of', 'Value of', '0', '0', 'Has value', @valueOfConceptId);
END;

------------------------------------------------------------
-- 2) Session staging for item / value concepts
--    omop.concept is the persistence; these temp tables exist only for this run.
------------------------------------------------------------
DROP TABLE IF EXISTS #naaccr_item_concept;
DROP TABLE IF EXISTS #naaccr_value_concept;

CREATE TABLE #naaccr_item_concept
(
  item_num INT NOT NULL PRIMARY KEY,
  concept_id BIGINT NOT NULL,
  concept_code NVARCHAR(50) NOT NULL,
  concept_name NVARCHAR(255) NULL
);

CREATE TABLE #naaccr_value_concept
(
  item_num INT NOT NULL,
  code NVARCHAR(255) NOT NULL,
  concept_id BIGINT NOT NULL,
  concept_code NVARCHAR(100) NOT NULL,
  concept_name NVARCHAR(MAX) NULL,
  PRIMARY KEY (item_num, code)
);

------------------------------------------------------------
-- 3) Assign concept_ids for NAACCR items (naaccr.NAACCR_ITEM)
--    Items are version-independent, so collapse NAACCR_ITEM across dd_version_id.
------------------------------------------------------------
-- Reuse concepts already minted on a previous run.
;WITH
  items
  AS
  (
    SELECT item_num, MAX(name) AS name
    FROM naaccr.NAACCR_ITEM
    GROUP BY item_num
  )
INSERT INTO #naaccr_item_concept
  (item_num, concept_id, concept_code, concept_name)
SELECT i.item_num, c.concept_id, c.concept_code, i.name
FROM items i
  JOIN omop.concept c
  ON c.vocabulary_id = 'NAACCR2026'
    AND c.concept_class_id = 'NAACCR Item'
    AND c.concept_code = CAST(i.item_num AS NVARCHAR(50));

DECLARE @nextItemId  BIGINT;

SELECT @nextItemId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM omop.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  items
  AS
  (
    SELECT item_num, MAX(name) AS name
    FROM naaccr.NAACCR_ITEM
    GROUP BY item_num
  ),
  missing_items
  AS
  (
    SELECT i.item_num,
      i.name,
      CAST(i.item_num AS NVARCHAR(50)) AS concept_code
    FROM items i
    WHERE NOT EXISTS (SELECT 1
      FROM #naaccr_item_concept t
      WHERE t.item_num = i.item_num)
  ),
  numbered
  AS
  (
    SELECT item_num, name, concept_code,
      @nextItemId + ROW_NUMBER() OVER (ORDER BY item_num) - 1 AS concept_id
    FROM missing_items
  )
INSERT INTO #naaccr_item_concept
  (item_num, concept_id, concept_code, concept_name)
SELECT item_num, concept_id, concept_code, name
FROM numbered;

-- Persist newly minted item concepts into OMOP concept table
INSERT INTO omop.concept
(
  concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
  standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
)
SELECT m.concept_id,
  LEFT(REPLACE(REPLACE(m.concept_name, CHAR(13), N' '), CHAR(10), N' '), 255) AS concept_name,
  N'Observation' AS domain_id,
  'NAACCR2026'  AS vocabulary_id,
  'NAACCR Item' AS concept_class_id,
  NULL          AS standard_concept,
  m.concept_code,
  CAST('2026-01-01' AS DATE) AS valid_start_date,
  CAST('2099-12-31' AS DATE) AS valid_end_date,
  NULL AS invalid_reason
FROM #naaccr_item_concept m
LEFT JOIN omop.concept c ON c.concept_id = m.concept_id
WHERE c.concept_id IS NULL;

------------------------------------------------------------
-- 4) Assign concept_ids for NAACCR value codes (naaccr.SCHEMA_ITEM_CODE)
--    Note: codes are defined at (item_num, code) granularity
------------------------------------------------------------
-- Reuse concepts already minted on a previous run.
;WITH
  src_values AS (
    SELECT
      sic.item_num,
      COALESCE(sic.code, N'') AS code,
      MAX(COALESCE(NULLIF(sic.description, N''), N'')) AS concept_name,
      CONCAT(CAST(sic.item_num AS NVARCHAR(50)), N'^', COALESCE(sic.code, N'')) AS concept_code
    FROM naaccr.SCHEMA_ITEM_CODE sic
    GROUP BY sic.item_num, COALESCE(sic.code, N'')
  )
INSERT INTO #naaccr_value_concept
  (item_num, code, concept_id, concept_code, concept_name)
SELECT v.item_num, v.code, c.concept_id, c.concept_code, v.concept_name
FROM src_values v
  JOIN omop.concept c
  ON c.vocabulary_id = 'NAACCR2026'
    AND c.concept_class_id = 'NAACCR Value'
    AND c.concept_code = v.concept_code;

DECLARE @nextValueId BIGINT;
SELECT @nextValueId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM omop.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  src_values AS (
    SELECT
      sic.item_num,
      COALESCE(sic.code, N'') AS code,
      MAX(COALESCE(NULLIF(sic.description, N''), N'')) AS concept_name,
      CONCAT(CAST(sic.item_num AS NVARCHAR(50)), N'^', COALESCE(sic.code, N'')) AS concept_code
    FROM naaccr.SCHEMA_ITEM_CODE sic
    GROUP BY sic.item_num, COALESCE(sic.code, N'')
  ),
  missing_values
  AS
  (
    SELECT v.*
    FROM src_values v
    WHERE NOT EXISTS (SELECT 1
      FROM #naaccr_value_concept t
      WHERE t.item_num = v.item_num AND t.code = v.code)
  ),
  numbered_vals
  AS
  (
    SELECT item_num, code, concept_name, concept_code,
      @nextValueId + ROW_NUMBER() OVER (ORDER BY item_num, code) - 1 AS concept_id
    FROM missing_values
  )
INSERT INTO #naaccr_value_concept
  (item_num, code, concept_id, concept_code, concept_name)
SELECT item_num, code, concept_id, concept_code, concept_name
FROM numbered_vals;

-- Persist newly minted value concepts into OMOP concept table
INSERT INTO omop.concept
(
  concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
  standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
)
SELECT m.concept_id,
  NULLIF(LEFT(REPLACE(REPLACE(m.concept_name, CHAR(13), N' '), CHAR(10), N' '), 255), N'') AS concept_name,
  'Meas Value' AS domain_id,
  'NAACCR2026' AS vocabulary_id,
  'NAACCR Value' AS concept_class_id,
  NULL AS standard_concept,
  m.concept_code,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM #naaccr_value_concept m
LEFT JOIN omop.concept c ON c.concept_id = m.concept_id
WHERE c.concept_id IS NULL;

-- Preserve full value descriptions as synonyms (language_concept_id=0 due to no standard vocabs)
;WITH full_value_names AS (
  SELECT
    m.concept_id,
    -- Normalize CR/LF to spaces and cap length to 1000
    LEFT(REPLACE(REPLACE(m.concept_name, CHAR(13), N' '), CHAR(10), N' '), 1000) AS full_name
  FROM #naaccr_value_concept m
  WHERE NULLIF(m.concept_name, N'') IS NOT NULL
)
INSERT INTO omop.concept_synonym (concept_id, concept_synonym_name, language_concept_id)
SELECT f.concept_id, f.full_name, 0
FROM full_value_names f
WHERE LEN(f.full_name) > 255
  AND NOT EXISTS (
    SELECT 1 FROM omop.concept_synonym cs
    WHERE cs.concept_id = f.concept_id AND cs.concept_synonym_name = f.full_name
  );

------------------------------------------------------------
-- 5) Relationships: Items ↔ Values (Has value / Value of)
------------------------------------------------------------
-- Has value (item → value)
INSERT INTO omop.concept_relationship
(
  concept_id_1, concept_id_2, relationship_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT i.concept_id AS concept_id_1,
  v.concept_id AS concept_id_2,
  'Has value'  AS relationship_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM #naaccr_item_concept i
  JOIN #naaccr_value_concept v
  ON v.item_num = i.item_num
LEFT JOIN omop.concept_relationship cr
  ON cr.concept_id_1 = i.concept_id
 AND cr.concept_id_2 = v.concept_id
 AND cr.relationship_id = 'Has value'
WHERE cr.concept_id_1 IS NULL;

-- Value of (value → item)
INSERT INTO omop.concept_relationship
(
  concept_id_1, concept_id_2, relationship_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT v.concept_id AS concept_id_1,
  i.concept_id AS concept_id_2,
  'Value of'   AS relationship_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM #naaccr_item_concept i
  JOIN #naaccr_value_concept v
  ON v.item_num = i.item_num
LEFT JOIN omop.concept_relationship cr
  ON cr.concept_id_1 = v.concept_id
 AND cr.concept_id_2 = i.concept_id
 AND cr.relationship_id = 'Value of'
WHERE cr.concept_id_1 IS NULL;

------------------------------------------------------------
-- 6) Source to concept mapping (for ETL convenience)
------------------------------------------------------------
-- Items
INSERT INTO omop.source_to_concept_map
(
  source_code, source_concept_id, source_vocabulary_id, source_code_description,
  target_concept_id, target_vocabulary_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT CAST(item_num AS NVARCHAR(50)) AS source_code,
  0 AS source_concept_id,
  'NAACCR2026' AS source_vocabulary_id,
  LEFT(REPLACE(REPLACE(concept_name, CHAR(13), N' '), CHAR(10), N' '), 255) AS source_code_description,
  concept_id AS target_concept_id,
  'NAACCR2026' AS target_vocabulary_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM #naaccr_item_concept m
LEFT JOIN omop.source_to_concept_map s2c
  ON s2c.source_code = CAST(m.item_num AS NVARCHAR(50))
 AND s2c.source_vocabulary_id = 'NAACCR2026'
WHERE s2c.source_code IS NULL;

-- Item values: source_code = "<item_num>:<code>"
INSERT INTO omop.source_to_concept_map
(
  source_code, source_concept_id, source_vocabulary_id, source_code_description,
  target_concept_id, target_vocabulary_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT CONCAT(CAST(v.item_num AS NVARCHAR(50)), N':', v.code) AS source_code,
  0 AS source_concept_id,
  'NAACCR2026' AS source_vocabulary_id,
  LEFT(REPLACE(REPLACE(v.concept_name, CHAR(13), N' '), CHAR(10), N' '), 255) AS source_code_description,
  v.concept_id AS target_concept_id,
  'NAACCR2026' AS target_vocabulary_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM #naaccr_value_concept v
LEFT JOIN omop.source_to_concept_map s2c
  ON s2c.source_code = CONCAT(CAST(v.item_num AS NVARCHAR(50)), N':', v.code)
 AND s2c.source_vocabulary_id = 'NAACCR2026'
WHERE s2c.source_code IS NULL;

DROP TABLE IF EXISTS #naaccr_item_concept;
DROP TABLE IF EXISTS #naaccr_value_concept;

------------------------------------------------------------
-- 7) Seed registry concepts (SEER, NPCR, COC, CCCR) from naaccr.REGISTRY
------------------------------------------------------------
DECLARE @nextRegId BIGINT;
SELECT @nextRegId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM omop.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  missing_regs
  AS
  (
    SELECT r.code, r.name,
      @nextRegId + ROW_NUMBER() OVER (ORDER BY r.code) - 1 AS concept_id
    FROM naaccr.REGISTRY r
    WHERE NOT EXISTS (
    SELECT 1
    FROM omop.concept c
    WHERE c.vocabulary_id = 'NAACCR2026' AND c.concept_code = r.code
  )
  )
INSERT INTO omop.concept
(
  concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
  standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
)
SELECT concept_id, name, 'Observation', 'NAACCR2026', 'Registry',
  NULL, code, CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL
FROM missing_regs;

------------------------------------------------------------
-- 8) Seed Episode Type and Field concepts used by Episode/Event linkage
------------------------------------------------------------
-- Cancer Disease Episode Type
IF NOT EXISTS (
  SELECT 1
FROM omop.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'NAACCR_CANCER_EPISODE'
)
BEGIN
  DECLARE @nextEpisodeType BIGINT;
  SELECT @nextEpisodeType = ISNULL(MAX(concept_id), @customLow) + 1
  FROM omop.concept
  WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (
    concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
    standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
  ) VALUES
  (
    @nextEpisodeType,
    N'Cancer Disease Episode (NAACCR)',
    N'Episode',
    N'NAACCR2026',
    N'Episode Type',
    NULL,
    N'NAACCR_CANCER_EPISODE',
    CAST
  ('2026-01-01' AS DATE),
    CAST
  ('2099-12-31' AS DATE),
    NULL
  );
END;

-- Field concept for episode_event_field_concept_id = observation_id
IF NOT EXISTS (
  SELECT 1
FROM omop.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_OBSERVATION_ID'
)
BEGIN
  DECLARE @nextFieldObs BIGINT;
  SELECT @nextFieldObs = ISNULL(MAX(concept_id), @customLow) + 1
  FROM omop.concept
  WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (
    concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
    standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
  ) VALUES
  (
    @nextFieldObs,
    N'Observation Identifier Field',
    N'Metadata',
    N'NAACCR2026',
    N'Field',
    NULL,
    N'FIELD_OBSERVATION_ID',
    CAST
  ('2026-01-01' AS DATE),
    CAST
  ('2099-12-31' AS DATE),
    NULL
  );
END;

-- Field concept for episode_event_field_concept_id = measurement_id (future use)
IF NOT EXISTS (
  SELECT 1 FROM omop.concept
  WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_MEASUREMENT_ID'
)
BEGIN
  DECLARE @nextFieldMeas BIGINT;
  SELECT @nextFieldMeas = ISNULL(MAX(concept_id), @customLow) + 1
  FROM omop.concept WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept (
    concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
    standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
  ) VALUES (
    @nextFieldMeas,
    N'Measurement Identifier Field',
    N'Metadata',
    N'NAACCR2026',
    N'Field',
    NULL,
    N'FIELD_MEASUREMENT_ID',
    CAST('2026-01-01' AS DATE),
    CAST('2099-12-31' AS DATE),
    NULL
  );
END;

-- Local Type Concept class and concept
IF NOT EXISTS (SELECT 1 FROM omop.concept_class WHERE concept_class_id = 'Type Concept')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM omop.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Type Concept', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Type Concept', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO omop.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Type Concept', 'Type Concept', @nextCcId);
END;

IF NOT EXISTS (
  SELECT 1 FROM omop.concept
  WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'TYPE_NAACCR_DERIVED'
)
BEGIN
  DECLARE @nextTypeId BIGINT;
  SELECT @nextTypeId = ISNULL(MAX(concept_id), @customLow) + 1
  FROM omop.concept WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO omop.concept (
    concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
    standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
  ) VALUES (
    @nextTypeId,
    N'NAACCR Derived Data',
    N'Type Concept',
    N'NAACCR2026',
    N'Type Concept',
    NULL,
    N'TYPE_NAACCR_DERIVED',
    CAST('2026-01-01' AS DATE),
    CAST('2099-12-31' AS DATE),
    NULL
  );
END;

-- End of script
