/*
  NAACCR → OMOP CDM v5.4 Vocabulary Ingestion Report (SQL Server)
  Purpose:
    Summarize how NAACCR Item/Value concepts were assigned, inserted,
    and linked within OMOP (concepts, relationships, source mappings).
  Notes:
    - Requires NAACCR metadata in cap.* (cap.NAACCR_ITEM, cap.SCHEMA_ITEM_CODE, cap.REGISTRY)
    - Requires prior execution of naaccr_omop_vocab.sql
    - Uses literal schema dbo.* for OMOP tables
*/

SET NOCOUNT ON;

-----------------------------
-- 0) Quick context: vocabulary and special seed concepts
-----------------------------
SELECT 'Vocabulary presence' AS section,
  COUNT(*) AS naaccr_vocabulary_count
FROM dbo.vocabulary
WHERE vocabulary_id = 'NAACCR2026';

SELECT 'Concept classes presence' AS section,
  x.concept_class_id,
  CASE WHEN cc.concept_class_id IS NOT NULL THEN 1 ELSE 0 END AS exists_flag
FROM (VALUES
    ('NAACCR Item'),
    ('NAACCR Value'),
    ('Registry'),
    ('Episode Type'),
    ('Field'),
    ('Relationship')) AS x(concept_class_id)
  LEFT JOIN dbo.concept_class cc ON cc.concept_class_id = x.concept_class_id
ORDER BY x.concept_class_id;

SELECT 'Domain presence' AS section,
  'Meas Value' AS domain_id,
  CASE WHEN EXISTS (SELECT 1
  FROM dbo.domain d
  WHERE d.domain_id = 'Meas Value') THEN 1 ELSE 0 END AS exists_flag;

SELECT 'Special NAACCR seed concepts' AS section,
  c.concept_code,
  c.concept_id,
  c.concept_name
FROM dbo.concept c
WHERE c.vocabulary_id = 'NAACCR2026'
  AND c.concept_code IN ('NAACCR_CANCER_EPISODE', 'FIELD_OBSERVATION_ID', 'FIELD_MEASUREMENT_ID', 'TYPE_NAACCR_DERIVED')
ORDER BY c.concept_code;

-----------------------------
-- 1) Overall NAACCR concept footprint in OMOP
-----------------------------
SELECT 'NAACCR concept footprint' AS section,
  MIN(c.concept_id) AS min_concept_id,
  MAX(c.concept_id) AS max_concept_id,
  COUNT(*) AS total_concepts
FROM dbo.concept c
WHERE c.vocabulary_id = 'NAACCR2026';

SELECT 'Concepts by class' AS section,
  c.concept_class_id,
  COUNT(*) AS count_by_class
FROM dbo.concept c
WHERE c.vocabulary_id = 'NAACCR2026'
GROUP BY c.concept_class_id
ORDER BY count_by_class DESC, c.concept_class_id;

-----------------------------
-- 2) Items: metadata vs mapping vs OMOP concepts
-----------------------------
SELECT 'Items: metadata vs map vs OMOP' AS section,
  (SELECT COUNT(*)
  FROM cap.NAACCR_ITEM) AS total_metadata_items,
  (SELECT COUNT(*)
  FROM cap.NAACCR_CONCEPT_MAP) AS mapped_items,
  (SELECT COUNT(*)
  FROM dbo.concept c
    JOIN cap.NAACCR_CONCEPT_MAP m ON m.concept_id = c.concept_id) AS omop_item_concepts;

SELECT TOP 20
  'Items: sample mapping' AS section,
  m.item_num,
  m.concept_id,
  m.concept_code,
  m.concept_name,
  c.concept_name AS omop_concept_name,
  c.domain_id,
  c.concept_class_id
FROM cap.NAACCR_CONCEPT_MAP m
  LEFT JOIN dbo.concept c ON c.concept_id = m.concept_id
ORDER BY m.item_num;

SELECT TOP 20
  'Items: missing mappings (if any)' AS section,
  i.item_num
FROM cap.NAACCR_ITEM i
  LEFT JOIN cap.NAACCR_CONCEPT_MAP m ON m.item_num = i.item_num
WHERE m.item_num IS NULL
ORDER BY i.item_num;

-----------------------------
-- 3) Values: metadata vs mapping vs OMOP concepts
-----------------------------
SELECT 'Values: metadata vs map vs OMOP' AS section,
  (SELECT COUNT(*)
  FROM cap.SCHEMA_ITEM_CODE) AS total_item_values,
  (SELECT COUNT(*)
  FROM cap.NAACCR_VALUE_CONCEPT_MAP) AS mapped_item_values,
  (SELECT COUNT(*)
  FROM dbo.concept c
    JOIN cap.NAACCR_VALUE_CONCEPT_MAP v ON v.concept_id = c.concept_id) AS omop_value_concepts;

SELECT TOP 20
  'Values: sample mapping' AS section,
  v.item_num,
  v.code AS value_code,
  v.concept_id,
  v.concept_code,
  v.concept_name,
  c.concept_name AS omop_concept_name,
  c.domain_id,
  c.concept_class_id
FROM cap.NAACCR_VALUE_CONCEPT_MAP v
  LEFT JOIN dbo.concept c ON c.concept_id = v.concept_id
ORDER BY v.item_num, v.code;

SELECT TOP 20
  'Values: missing mappings (if any)' AS section,
  sic.item_num,
  sic.code AS value_code,
  sic.description AS value_name
FROM cap.SCHEMA_ITEM_CODE sic
  LEFT JOIN cap.NAACCR_VALUE_CONCEPT_MAP v
  ON v.item_num = sic.item_num AND v.code = sic.code
WHERE v.item_num IS NULL
ORDER BY sic.item_num, sic.code;

-----------------------------
-- 4) Item ↔ Value relationships (Has value / Value of)
-----------------------------
;WITH
  item_concepts
  AS
  (
    SELECT m.item_num, m.concept_id AS item_concept_id
    FROM cap.NAACCR_CONCEPT_MAP m
  ),
  value_concepts
  AS
  (
    SELECT v.item_num, v.code, v.concept_id AS value_concept_id
    FROM cap.NAACCR_VALUE_CONCEPT_MAP v
  )
SELECT 'Relationships: counts' AS section,
  (SELECT COUNT(*)
  FROM dbo.concept_relationship cr
    JOIN dbo.concept c1 ON c1.concept_id = cr.concept_id_1 AND c1.vocabulary_id = 'NAACCR2026'
    JOIN dbo.concept c2 ON c2.concept_id = cr.concept_id_2 AND c2.vocabulary_id = 'NAACCR2026'
  WHERE cr.relationship_id = 'Has value') AS has_value_links,
  (SELECT COUNT(*)
  FROM dbo.concept_relationship cr
    JOIN dbo.concept c1 ON c1.concept_id = cr.concept_id_1 AND c1.vocabulary_id = 'NAACCR2026'
    JOIN dbo.concept c2 ON c2.concept_id = cr.concept_id_2 AND c2.vocabulary_id = 'NAACCR2026'
  WHERE cr.relationship_id = 'Value of') AS value_of_links;

;WITH
  item_concepts
  AS
  (
    SELECT m.item_num, m.concept_id AS item_concept_id
    FROM cap.NAACCR_CONCEPT_MAP m
  ),
  value_concepts
  AS
  (
    SELECT v.item_num, v.code, v.concept_id AS value_concept_id
    FROM cap.NAACCR_VALUE_CONCEPT_MAP v
  )
SELECT TOP 20
  'Relationships: sample item→value' AS section,
  ic.item_num,
  vc.code AS value_code,
  ic.item_concept_id AS item_concept_id,
  vc.value_concept_id AS value_concept_id,
  cr.relationship_id
FROM item_concepts ic
  JOIN value_concepts vc ON vc.item_num = ic.item_num
  JOIN dbo.concept_relationship cr
  ON cr.concept_id_1 = ic.item_concept_id AND cr.concept_id_2 = vc.value_concept_id
WHERE cr.relationship_id = 'Has value'
ORDER BY ic.item_num, vc.code;

-----------------------------
-- 5) Source-to-concept maps (for ETL convenience)
-----------------------------
SELECT 'S2C maps: counts' AS section,
  (SELECT COUNT(*)
  FROM dbo.source_to_concept_map s2c
  WHERE s2c.source_vocabulary_id = 'NAACCR2026'
    AND TRY_CONVERT(INT, s2c.source_code) IS NOT NULL) AS item_s2c_count,
  (SELECT COUNT(*)
  FROM dbo.source_to_concept_map s2c
  WHERE s2c.source_vocabulary_id = 'NAACCR2026'
    AND CHARINDEX(':', s2c.source_code) > 0) AS value_s2c_count;

SELECT TOP 20
  'S2C: sample items' AS section,
  s2c.source_code,
  s2c.target_concept_id,
  c.concept_name,
  c.concept_class_id
FROM dbo.source_to_concept_map s2c
  LEFT JOIN dbo.concept c ON c.concept_id = s2c.target_concept_id
WHERE s2c.source_vocabulary_id = 'NAACCR2026'
  AND TRY_CONVERT(INT, s2c.source_code) IS NOT NULL
ORDER BY TRY_CONVERT(INT, s2c.source_code);

SELECT TOP 20
  'S2C: sample item values' AS section,
  s2c.source_code,
  s2c.target_concept_id,
  c.concept_name,
  c.concept_class_id
FROM dbo.source_to_concept_map s2c
  LEFT JOIN dbo.concept c ON c.concept_id = s2c.target_concept_id
WHERE s2c.source_vocabulary_id = 'NAACCR2026'
  AND CHARINDEX(':', s2c.source_code) > 0
ORDER BY s2c.source_code;

-----------------------------
-- 6) Integrity checks
-----------------------------
SELECT 'Integrity: item map missing OMOP concept' AS section,
  COUNT(*) AS missing_item_concepts
FROM cap.NAACCR_CONCEPT_MAP m
  LEFT JOIN dbo.concept c ON c.concept_id = m.concept_id
WHERE c.concept_id IS NULL;

SELECT 'Integrity: value map missing OMOP concept' AS section,
  COUNT(*) AS missing_value_concepts
FROM cap.NAACCR_VALUE_CONCEPT_MAP v
  LEFT JOIN dbo.concept c ON c.concept_id = v.concept_id
WHERE c.concept_id IS NULL;

SELECT TOP 20
  'Integrity: items w/o any relationships' AS section,
  m.item_num,
  m.concept_id
FROM cap.NAACCR_CONCEPT_MAP m
  LEFT JOIN dbo.concept_relationship cr ON cr.concept_id_1 = m.concept_id AND cr.relationship_id = 'Has value'
WHERE cr.concept_id_1 IS NULL
ORDER BY m.item_num;

SELECT TOP 20
  'Integrity: values w/o item relationship' AS section,
  v.item_num,
  v.code,
  v.concept_id
FROM cap.NAACCR_VALUE_CONCEPT_MAP v
  LEFT JOIN dbo.concept_relationship cr ON cr.concept_id_1 = v.concept_id AND cr.relationship_id = 'Value of'
WHERE cr.concept_id_1 IS NULL
ORDER BY v.item_num, v.code;

-- End report
