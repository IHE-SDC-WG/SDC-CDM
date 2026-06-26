/*
  Validation: NAACCR 2026 → OMOP CDM v5.4 Vocabulary Seeding
  Purpose: Run read-only checks to verify seeded vocabulary, classes, domains,
           relationships, concepts, mappings, ID ranges, and reciprocity.
  Assumptions:
    - OMOP CDM v5.4 objects in dbo schema
    - NAACCR staging metadata in cap schema
    - NAACCR2026 vocabulary seeded by naaccr_omop_vocab.sql
*/

SET NOCOUNT ON;

-----------------------------
-- 1) Vocabulary & Metadata
-----------------------------
SELECT 'Vocabulary' AS section, v.vocabulary_id, v.vocabulary_name, v.vocabulary_version
FROM dbo.vocabulary v
WHERE v.vocabulary_id = 'NAACCR2026';

SELECT 'Concept Classes' AS section, concept_class_id, concept_class_name, concept_class_concept_id
FROM dbo.concept_class
WHERE concept_class_id IN ('NAACCR Item','NAACCR Value','Registry','Episode Type','Field','Type Concept','Domain','Relationship')
ORDER BY concept_class_id;

SELECT 'Domain Meas Value' AS section, domain_id, domain_name, domain_concept_id
FROM dbo.domain
WHERE domain_id = 'Meas Value';

SELECT 'Relationships' AS section, relationship_id, relationship_name, relationship_concept_id
FROM dbo.relationship
WHERE relationship_id IN ('Has value','Value of')
ORDER BY relationship_id;

-----------------------------
-- 2) Counts & Coverage
-----------------------------
-- NAACCR Items
SELECT 'Item Counts' AS section,
  (SELECT COUNT(*)
  FROM cap.NAACCR_ITEM)              AS naaccr_items,
  (SELECT COUNT(*)
  FROM cap.NAACCR_CONCEPT_MAP)       AS item_map_rows,
  (SELECT COUNT(*)
  FROM dbo.concept
  WHERE vocabulary_id='NAACCR2026' AND concept_class_id='NAACCR Item') AS item_concepts;

-- NAACCR Values
SELECT 'Value Counts' AS section,
  (SELECT COUNT(*)
  FROM cap.NAACCR_VALUE_CONCEPT_MAP) AS value_map_rows,
  (SELECT COUNT(*)
  FROM dbo.concept
  WHERE vocabulary_id='NAACCR2026' AND concept_class_id='NAACCR Value') AS value_concepts,
  (SELECT COUNT(*)
  FROM dbo.concept_relationship
  WHERE relationship_id='Has value')  AS has_value_links,
  (SELECT COUNT(*)
  FROM dbo.concept_relationship
  WHERE relationship_id='Value of')   AS value_of_links;

-- Source mappings
SELECT 'Source To Concept Counts' AS section,
  (SELECT COUNT(*)
  FROM dbo.source_to_concept_map
  WHERE source_vocabulary_id='NAACCR2026' AND source_code NOT LIKE '%:%') AS s2c_items,
  (SELECT COUNT(*)
  FROM dbo.source_to_concept_map
  WHERE source_vocabulary_id='NAACCR2026' AND source_code LIKE '%:%')     AS s2c_values;

-----------------------------
-- 3) ID Ranges & Text Normalization
-----------------------------
SELECT 'Concept ID Range' AS section,
  MIN(concept_id) AS min_concept_id,
  MAX(concept_id) AS max_concept_id
FROM dbo.concept
WHERE vocabulary_id='NAACCR2026';

SELECT TOP 5
  'Longest Concept Names' AS section,
  concept_id, LEN(concept_name) AS name_len, concept_name
FROM dbo.concept
WHERE vocabulary_id='NAACCR2026'
ORDER BY LEN(concept_name) DESC, concept_id DESC;

SELECT TOP 5
  'Longest S2C Descriptions' AS section,
  source_code, LEN(source_code_description) AS desc_len, source_code_description
FROM dbo.source_to_concept_map
WHERE source_vocabulary_id='NAACCR2026'
ORDER BY LEN(source_code_description) DESC, source_code DESC;

-----------------------------
-- 4) Synonyms (Full Descriptions)
-----------------------------
SELECT 'Synonym Counts' AS section,
  (SELECT COUNT(*)
  FROM dbo.concept_synonym) AS total_synonyms,
  (SELECT COUNT(*)
  FROM dbo.concept_synonym
  WHERE LEN(concept_synonym_name) > 255) AS long_synonyms;

SELECT TOP 5
  'Example Long Synonyms' AS section,
  concept_id, LEN(concept_synonym_name) AS syn_len,
  concept_synonym_name
FROM dbo.concept_synonym
ORDER BY LEN(concept_synonym_name) DESC, concept_id DESC;

-----------------------------
-- 5) Relationship Reciprocity
-----------------------------
SELECT 'Missing Reciprocity Count' AS section,
  COUNT(*) AS missing_reciprocals
FROM dbo.concept_relationship hv
WHERE hv.relationship_id='Has value'
  AND NOT EXISTS (
    SELECT 1
  FROM dbo.concept_relationship vo
  WHERE vo.relationship_id='Value of'
    AND vo.concept_id_1 = hv.concept_id_2
    AND vo.concept_id_2 = hv.concept_id_1
  );

SELECT TOP 10
  'Missing Reciprocity Examples' AS section,
  hv.concept_id_1 AS item_concept_id,
  hv.concept_id_2 AS value_concept_id
FROM dbo.concept_relationship hv
WHERE hv.relationship_id='Has value'
  AND NOT EXISTS (
    SELECT 1
  FROM dbo.concept_relationship vo
  WHERE vo.relationship_id='Value of'
    AND vo.concept_id_1 = hv.concept_id_2
    AND vo.concept_id_2 = hv.concept_id_1
  )
ORDER BY hv.concept_id_1, hv.concept_id_2;

-----------------------------
-- 6) Spot Checks
-----------------------------
-- Example: values for item 1068
SELECT 'Spot Check: 1068 Values' AS section,
  m.item_num, m.code, m.concept_id, c.concept_name
FROM cap.NAACCR_VALUE_CONCEPT_MAP m
  JOIN dbo.concept c ON c.concept_id = m.concept_id
WHERE m.item_num = 1068
ORDER BY m.code;

-- Source mapping for 1068:1
SELECT 'Spot Check: s2c 1068:1' AS section,
  source_code, source_code_description, target_concept_id
FROM dbo.source_to_concept_map
WHERE source_vocabulary_id='NAACCR2026' AND source_code='1068:1';

-- Items concept coverage for 10 random items
SELECT TOP 10
  'Random Items Coverage' AS section,
  i.item_num, i.name, m.concept_id, c.concept_name
FROM cap.NAACCR_ITEM i
  LEFT JOIN cap.NAACCR_CONCEPT_MAP m ON m.item_num = i.item_num
  LEFT JOIN dbo.concept c ON c.concept_id = m.concept_id
ORDER BY NEWID();

-- End of validation script
