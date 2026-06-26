/*
  Validation: NAACCR → OMOP CDM v5.4 ETL Outputs
  Purpose: Quick post-run checks for episodes, measurements, the report NOTE,
           and episode_event linkages using dbo.naaccr_staging as source.
  Note: eCP synoptic Q&A defaults to MEASUREMENT (qualitatively/quantitatively
        derived). See ECP_OMOP_MAPPING.md.
*/

SET NOCOUNT ON;

-- Lookup helper concepts
DECLARE @EPISODE_TYPE_CANCER BIGINT;
SELECT TOP 1 @EPISODE_TYPE_CANCER = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'NAACCR_CANCER_EPISODE';

DECLARE @FIELD_MEAS_ID BIGINT;
SELECT TOP 1 @FIELD_MEAS_ID = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_MEASUREMENT_ID';

DECLARE @TYPE_NAACCR BIGINT;
SELECT TOP 1 @TYPE_NAACCR = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'TYPE_NAACCR_DERIVED';

DECLARE @FIELD_NOTE_ID BIGINT = 1147289; -- note.note_id field concept (TODO confirm)

-----------------------------
-- 1) Episode counts and coverage
-----------------------------
SELECT 'Episodes: expected vs actual' AS section,
       (SELECT COUNT(*) FROM (SELECT DISTINCT person_id, episode_key FROM dbo.naaccr_staging) s) AS expected_distinct_episodes,
       (SELECT COUNT(*) FROM dbo.episode WHERE episode_concept_id = @EPISODE_TYPE_CANCER) AS actual_cancer_episodes;

SELECT TOP 20 'Missing episodes (examples)' AS section, s.person_id, s.episode_key
FROM (SELECT DISTINCT person_id, episode_key FROM dbo.naaccr_staging) s
LEFT JOIN dbo.episode e
  ON e.person_id = s.person_id AND e.episode_source_value = s.episode_key
WHERE e.episode_id IS NULL
ORDER BY s.person_id, s.episode_key;

-----------------------------
-- 2) Measurement counts (ALL staged items become measurements)
-----------------------------
SELECT 'Measurements: expected vs actual' AS section,
       (SELECT COUNT(*) FROM dbo.naaccr_staging) AS expected_measurements,
       (SELECT COUNT(*) FROM dbo.measurement m WHERE m.measurement_type_concept_id = @TYPE_NAACCR) AS actual_measurements;

-----------------------------
-- 3) Report NOTE checks (one per person/episode) + measurement→note linkage
-----------------------------
SELECT 'Report notes: expected vs actual' AS section,
       (SELECT COUNT(*) FROM (SELECT DISTINCT person_id, episode_key FROM dbo.naaccr_staging) s) AS expected_notes,
       (SELECT COUNT(*) FROM dbo.note) AS actual_notes;

SELECT 'Measurements missing note anchor' AS section,
       COUNT(*) AS missing_note_anchor
FROM dbo.measurement m
WHERE m.measurement_type_concept_id = @TYPE_NAACCR
  AND (m.measurement_event_id IS NULL OR m.meas_event_field_concept_id <> @FIELD_NOTE_ID);

-----------------------------
-- 4) Episode_event link checks (measurements)
-----------------------------
SELECT 'Episode_event meas links' AS section,
       (SELECT COUNT(*) FROM dbo.episode_event WHERE episode_event_field_concept_id = @FIELD_MEAS_ID) AS meas_links;

SELECT 'Measurements missing episode links' AS section,
       COUNT(*) AS missing_meas_links
FROM dbo.measurement m
LEFT JOIN dbo.episode_event ee
  ON ee.event_id = m.measurement_id AND ee.episode_event_field_concept_id = @FIELD_MEAS_ID
WHERE ee.event_id IS NULL;

-----------------------------
-- 5) Per-episode summary (top 20)
-----------------------------
SELECT TOP 20 'Per episode summary' AS section,
       x.person_id,
       x.episode_source_value,
       x.meas_count
FROM (
  SELECT e.person_id,
         e.episode_source_value,
         COUNT(DISTINCT CASE WHEN ee.episode_event_field_concept_id = @FIELD_MEAS_ID THEN ee.event_id END) AS meas_count
  FROM dbo.episode e
  LEFT JOIN dbo.episode_event ee ON ee.episode_id = e.episode_id
  GROUP BY e.person_id, e.episode_source_value
) AS x
ORDER BY x.meas_count DESC, x.person_id;

-----------------------------
-- 6) Spot check for units (top 20 numeric measurements with unit_source_value)
-----------------------------
SELECT TOP 20 'Measurement units' AS section,
       m.person_id, m.measurement_source_value, m.value_as_number, m.unit_source_value, m.measurement_date
FROM dbo.measurement m
WHERE NULLIF(m.unit_source_value, '') IS NOT NULL
ORDER BY m.measurement_date DESC;

-- End validation script
