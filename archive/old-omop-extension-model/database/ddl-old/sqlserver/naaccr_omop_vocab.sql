/*
  NAACCR 2026 → OMOP CDM v5.4 Vocabulary Seeding (SQL Server)

  Purpose
  - Register a custom vocabulary for NAACCR 2026
  - Create custom concept classes and relationships needed for NAACCR items/values
  - Persistently assign custom concept_ids for NAACCR items and their allowed values
  - Populate concept, concept_relationship, and source_to_concept_map

  Assumptions
  - OMOP CDM v5.4 schema (incl. vocabulary tables) exists in @cdmDatabaseSchema
  - Source NAACCR 3NF tables exist in schema: cap (cap.NAACCR_ITEM, cap.SCHEMA_ITEM_CODE, cap.REGISTRY)
  - This script follows OHDSI style where @cdmDatabaseSchema is replaced pre-execution

  Custom concept_id range used here: [2,000,000,000 .. 2,099,999,999]
  Rationale: stay below SQL Server INT max (2,147,483,647) and avoid collisions
*/

------------------------------------------------------------
-- Parameters (replace @cdmDatabaseSchema before execution)
------------------------------------------------------------
-- Using literal schema names (dbo.*) to ensure valid T-SQL; no variable-qualified objects

------------------------------------------------------------
-- Note: In this environment, concept_id is an INT. We must assign IDs below INT max.
------------------------------------------------------------

-- Vocabulary entry for NAACCR 2026
IF NOT EXISTS (SELECT 1
FROM dbo.vocabulary
WHERE vocabulary_id = 'NAACCR2026')
BEGIN
  INSERT INTO dbo.vocabulary
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

IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'NAACCR Item')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'NAACCR Data Item', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'NAACCR Item', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('NAACCR Item', 'NAACCR Data Item', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'NAACCR Value')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'NAACCR Item Allowed Value', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'NAACCR Value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('NAACCR Value', 'NAACCR Item Allowed Value', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Registry')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Registry', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Registry', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Registry', 'Registry', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Episode Type')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Episode Type', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Episode Type', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Episode Type', 'Episode Type', @nextCcId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Field')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Field Identifier', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Field', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Field', 'Field Identifier', @nextCcId);
END;

-- Ensure needed domains exist (most will already exist)
-- Also seed a representing concept so domain_concept_id is not NULL
IF NOT EXISTS (SELECT 1 FROM dbo.domain WHERE domain_id = 'Meas Value')
BEGIN
  DECLARE @measValueConceptId BIGINT;
  SELECT @measValueConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  -- Ensure 'Domain' concept class exists (paired concept)
  IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Domain')
  BEGIN
    DECLARE @nextCcIdLocal BIGINT;
    SELECT @nextCcIdLocal = ISNULL(MAX(c.concept_id), @customLow) + 1
    FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

    INSERT INTO dbo.concept
    (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
     standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
    VALUES
    (@nextCcIdLocal, N'Domain', N'Metadata', N'NAACCR2026', N'Concept Class',
     NULL, N'Domain', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

    INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
    VALUES ('Domain', 'Domain', @nextCcIdLocal);
  END;

  -- Create representing concept for 'Meas Value' domain
  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@measValueConceptId, N'Measurement Value', N'Metadata', N'NAACCR2026', N'Domain',
   NULL, N'Meas Value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.domain (domain_id, domain_name, domain_concept_id)
  VALUES ('Meas Value', 'Measurement Value', @measValueConceptId);
END;

-- Relationships for item/value modeling (usually already present)
-- Ensure 'Relationship' concept class exists (paired concept)
IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Relationship')
BEGIN
  DECLARE @nextCcRel BIGINT;
  SELECT @nextCcRel = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcRel, N'Relationship', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Relationship', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Relationship', 'Relationship', @nextCcRel);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.relationship WHERE relationship_id = 'Has value')
BEGIN
  DECLARE @hasValueConceptId BIGINT;
  SELECT @hasValueConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@hasValueConceptId, N'Has value', N'Metadata', N'NAACCR2026', N'Relationship',
   NULL, N'Has value', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.relationship
  (relationship_id, relationship_name, is_hierarchical, defines_ancestry, reverse_relationship_id, relationship_concept_id)
  VALUES ('Has value', 'Has value', '0', '0', 'Value of', @hasValueConceptId);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.relationship WHERE relationship_id = 'Value of')
BEGIN
  DECLARE @valueOfConceptId BIGINT;
  SELECT @valueOfConceptId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@valueOfConceptId, N'Value of', N'Metadata', N'NAACCR2026', N'Relationship',
   NULL, N'Value of', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.relationship
  (relationship_id, relationship_name, is_hierarchical, defines_ancestry, reverse_relationship_id, relationship_concept_id)
  VALUES ('Value of', 'Value of', '0', '0', 'Has value', @valueOfConceptId);
END;

------------------------------------------------------------
-- 2) Persistent mapping tables for assigned concept_ids
------------------------------------------------------------
IF OBJECT_ID('cap.NAACCR_CONCEPT_MAP', 'U') IS NULL
BEGIN
  CREATE TABLE cap.NAACCR_CONCEPT_MAP
  (
    item_num INT NOT NULL PRIMARY KEY,
    concept_id BIGINT NOT NULL,
    concept_code NVARCHAR(50) NOT NULL,
    concept_name NVARCHAR(255) NOT NULL,
    created_utc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
  );
END;

IF OBJECT_ID('cap.NAACCR_VALUE_CONCEPT_MAP', 'U') IS NULL
BEGIN
  CREATE TABLE cap.NAACCR_VALUE_CONCEPT_MAP
  (
    item_num INT NOT NULL,
    code NVARCHAR(255) NOT NULL,
    concept_id BIGINT NOT NULL,
    concept_code NVARCHAR(100) NOT NULL,
    concept_name NVARCHAR(MAX) NULL,
    created_utc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_NAACCR_VALUE_CONCEPT_MAP PRIMARY KEY (item_num, code)
  );
END;

------------------------------------------------------------
-- 3) Assign concept_ids for NAACCR items (cap.NAACCR_ITEM)
------------------------------------------------------------
DECLARE @nextItemId  BIGINT;

SELECT @nextItemId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM dbo.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  missing_items
  AS
  (
    SELECT ni.item_num,
      ni.name,
      CAST(ni.item_num AS NVARCHAR(50)) AS concept_code
    FROM cap.NAACCR_ITEM ni
      LEFT JOIN cap.NAACCR_CONCEPT_MAP m
      ON m.item_num = ni.item_num
    WHERE m.item_num IS NULL
  ),
  numbered
  AS
  (
    SELECT item_num, name, concept_code,
      @nextItemId + ROW_NUMBER() OVER (ORDER BY item_num) - 1 AS concept_id
    FROM missing_items
  )
INSERT INTO cap.NAACCR_CONCEPT_MAP
  (item_num, concept_id, concept_code, concept_name)
SELECT item_num, concept_id, concept_code, name
FROM numbered;

-- Upsert item concepts into OMOP concept table
INSERT INTO dbo.concept
(
  concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
  standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason
)
SELECT m.concept_id,
  LEFT(REPLACE(REPLACE(m.concept_name, CHAR(13), N' '), CHAR(10), N' '), 255) AS concept_name,
  'Observation' AS domain_id,
  'NAACCR2026'  AS vocabulary_id,
  'NAACCR Item' AS concept_class_id,
  NULL          AS standard_concept,
  m.concept_code,
  CAST('2026-01-01' AS DATE) AS valid_start_date,
  CAST('2099-12-31' AS DATE) AS valid_end_date,
  NULL AS invalid_reason
FROM cap.NAACCR_CONCEPT_MAP m
LEFT JOIN dbo.concept c ON c.concept_id = m.concept_id
WHERE c.concept_id IS NULL;

------------------------------------------------------------
-- 4) Assign concept_ids for NAACCR value codes (cap.SCHEMA_ITEM_CODE)
--    Note: codes are defined at (item_num, code) granularity
------------------------------------------------------------
DECLARE @nextValueId BIGINT;
SELECT @nextValueId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM dbo.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  src_values AS (
    SELECT
      sic.item_num,
      COALESCE(sic.code, N'') AS code,
      MAX(COALESCE(NULLIF(sic.description, N''), N'')) AS concept_name,
      CONCAT(CAST(sic.item_num AS NVARCHAR(50)), N'^', COALESCE(sic.code, N'')) AS concept_code
    FROM cap.SCHEMA_ITEM_CODE sic
    GROUP BY sic.item_num, COALESCE(sic.code, N'')
  ),
  missing_values
  AS
  (
    SELECT v.*
    FROM src_values v
      LEFT JOIN cap.NAACCR_VALUE_CONCEPT_MAP m
      ON m.item_num = v.item_num AND m.code = v.code
    WHERE m.item_num IS NULL
  ),
  numbered_vals
  AS
  (
    SELECT item_num, code, concept_name, concept_code,
      @nextValueId + ROW_NUMBER() OVER (ORDER BY item_num, code) - 1 AS concept_id
    FROM missing_values
  )
MERGE cap.NAACCR_VALUE_CONCEPT_MAP AS target
USING numbered_vals AS src
ON target.item_num = src.item_num AND target.code = src.code
WHEN NOT MATCHED THEN
  INSERT (item_num, code, concept_id, concept_code, concept_name)
  VALUES (src.item_num, src.code, src.concept_id, src.concept_code, src.concept_name)
WHEN MATCHED THEN
  UPDATE SET
    target.concept_name = CASE WHEN ISNULL(target.concept_name, N'') = N'' THEN src.concept_name ELSE target.concept_name END,
    target.concept_code = src.concept_code
;

-- Upsert value concepts into OMOP concept table
INSERT INTO dbo.concept
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
FROM cap.NAACCR_VALUE_CONCEPT_MAP m
LEFT JOIN dbo.concept c ON c.concept_id = m.concept_id
WHERE c.concept_id IS NULL;

-- Preserve full value descriptions as synonyms (language_concept_id=0 due to no standard vocabs)
;WITH full_value_names AS (
  SELECT
    m.concept_id,
    -- Normalize CR/LF to spaces and cap length to 1000
    LEFT(REPLACE(REPLACE(m.concept_name, CHAR(13), N' '), CHAR(10), N' '), 1000) AS full_name
  FROM cap.NAACCR_VALUE_CONCEPT_MAP m
  WHERE NULLIF(m.concept_name, N'') IS NOT NULL
)
INSERT INTO dbo.concept_synonym (concept_id, concept_synonym_name, language_concept_id)
SELECT f.concept_id, f.full_name, 0
FROM full_value_names f
WHERE LEN(f.full_name) > 255
  AND NOT EXISTS (
    SELECT 1 FROM dbo.concept_synonym cs
    WHERE cs.concept_id = f.concept_id AND cs.concept_synonym_name = f.full_name
  );

------------------------------------------------------------
-- 5) Relationships: Items ↔ Values (Has value / Value of)
------------------------------------------------------------
-- Has value (item → value)
INSERT INTO dbo.concept_relationship
(
  concept_id_1, concept_id_2, relationship_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT i.concept_id AS concept_id_1,
  v.concept_id AS concept_id_2,
  'Has value'  AS relationship_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM cap.NAACCR_CONCEPT_MAP i
  JOIN cap.NAACCR_VALUE_CONCEPT_MAP v
  ON v.item_num = i.item_num
LEFT JOIN dbo.concept_relationship cr
  ON cr.concept_id_1 = i.concept_id
 AND cr.concept_id_2 = v.concept_id
 AND cr.relationship_id = 'Has value'
WHERE cr.concept_id_1 IS NULL;

-- Value of (value → item)
INSERT INTO dbo.concept_relationship
(
  concept_id_1, concept_id_2, relationship_id, valid_start_date, valid_end_date, invalid_reason
)
SELECT v.concept_id AS concept_id_1,
  i.concept_id AS concept_id_2,
  'Value of'   AS relationship_id,
  CAST('2026-01-01' AS DATE),
  CAST('2099-12-31' AS DATE),
  NULL
FROM cap.NAACCR_CONCEPT_MAP i
  JOIN cap.NAACCR_VALUE_CONCEPT_MAP v
  ON v.item_num = i.item_num
LEFT JOIN dbo.concept_relationship cr
  ON cr.concept_id_1 = v.concept_id
 AND cr.concept_id_2 = i.concept_id
 AND cr.relationship_id = 'Value of'
WHERE cr.concept_id_1 IS NULL;

------------------------------------------------------------
-- 6) Source to concept mapping (for ETL convenience)
------------------------------------------------------------
-- Items
INSERT INTO dbo.source_to_concept_map
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
FROM cap.NAACCR_CONCEPT_MAP m
LEFT JOIN dbo.source_to_concept_map s2c
  ON s2c.source_code = CAST(m.item_num AS NVARCHAR(50))
 AND s2c.source_vocabulary_id = 'NAACCR2026'
WHERE s2c.source_code IS NULL;

-- Item values: source_code = "<item_num>:<code>"
INSERT INTO dbo.source_to_concept_map
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
FROM cap.NAACCR_VALUE_CONCEPT_MAP v
LEFT JOIN dbo.source_to_concept_map s2c
  ON s2c.source_code = CONCAT(CAST(v.item_num AS NVARCHAR(50)), N':', v.code)
 AND s2c.source_vocabulary_id = 'NAACCR2026'
WHERE s2c.source_code IS NULL;

------------------------------------------------------------
-- 7) Seed registry concepts (SEER, NPCR, COC, CCCR) from cap.REGISTRY
------------------------------------------------------------
DECLARE @nextRegId BIGINT;
SELECT @nextRegId = ISNULL(MAX(c.concept_id), @customLow) + 1
FROM dbo.concept c
WHERE c.concept_id BETWEEN @customLow AND @customHigh;

;WITH
  missing_regs
  AS
  (
    SELECT r.code, r.name,
      @nextRegId + ROW_NUMBER() OVER (ORDER BY r.code) - 1 AS concept_id
    FROM cap.REGISTRY r
    WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.concept c
    WHERE c.vocabulary_id = 'NAACCR2026' AND c.concept_code = r.code
  )
  )
INSERT INTO dbo.concept
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
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'NAACCR_CANCER_EPISODE'
)
BEGIN
  DECLARE @nextEpisodeType BIGINT;
  SELECT @nextEpisodeType = ISNULL(MAX(concept_id), @customLow) + 1
  FROM dbo.concept
  WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
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
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_OBSERVATION_ID'
)
BEGIN
  DECLARE @nextFieldObs BIGINT;
  SELECT @nextFieldObs = ISNULL(MAX(concept_id), @customLow) + 1
  FROM dbo.concept
  WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
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
  SELECT 1 FROM dbo.concept
  WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_MEASUREMENT_ID'
)
BEGIN
  DECLARE @nextFieldMeas BIGINT;
  SELECT @nextFieldMeas = ISNULL(MAX(concept_id), @customLow) + 1
  FROM dbo.concept WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept (
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
IF NOT EXISTS (SELECT 1 FROM dbo.concept_class WHERE concept_class_id = 'Type Concept')
BEGIN
  SELECT @nextCcId = ISNULL(MAX(c.concept_id), @customLow) + 1
  FROM dbo.concept c WHERE c.concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept
  (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
   standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
  VALUES
  (@nextCcId, N'Type Concept', N'Metadata', N'NAACCR2026', N'Concept Class',
   NULL, N'Type Concept', CAST('2026-01-01' AS DATE), CAST('2099-12-31' AS DATE), NULL);

  INSERT INTO dbo.concept_class (concept_class_id, concept_class_name, concept_class_concept_id)
  VALUES ('Type Concept', 'Type Concept', @nextCcId);
END;

IF NOT EXISTS (
  SELECT 1 FROM dbo.concept
  WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'TYPE_NAACCR_DERIVED'
)
BEGIN
  DECLARE @nextTypeId BIGINT;
  SELECT @nextTypeId = ISNULL(MAX(concept_id), @customLow) + 1
  FROM dbo.concept WHERE concept_id BETWEEN @customLow AND @customHigh;

  INSERT INTO dbo.concept (
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
