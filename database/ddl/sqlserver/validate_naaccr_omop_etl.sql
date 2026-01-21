/*
  Validation: NAACCR → OMOP CDM v5.4 ETL Outputs
  Purpose: Quick post-run checks for episodes, observations, measurements,
           and episode_event linkages using dbo.naaccr_staging as source.
*/

SET NOCOUNT ON;

-- Lookup helper concepts
DECLARE @EPISODE_TYPE_CANCER BIGINT;
SELECT TOP 1 @EPISODE_TYPE_CANCER = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'NAACCR_CANCER_EPISODE';

DECLARE @FIELD_OBS_ID BIGINT;
SELECT TOP 1 @FIELD_OBS_ID = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_OBSERVATION_ID';

DECLARE @FIELD_MEAS_ID BIGINT;
SELECT TOP 1 @FIELD_MEAS_ID = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_MEASUREMENT_ID';

DECLARE @TYPE_NAACCR BIGINT;
SELECT TOP 1 @TYPE_NAACCR = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'TYPE_NAACCR_DERIVED';

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
-- 2) Observation/Measurement counts
-----------------------------
SELECT 'Observations: expected vs actual' AS section,
       (SELECT COUNT(*) FROM dbo.naaccr_staging WHERE value_num IS NULL) AS expected_observations,
       (SELECT COUNT(*) FROM dbo.observation o WHERE o.observation_type_concept_id = @TYPE_NAACCR) AS actual_observations;

SELECT 'Measurements: expected vs actual' AS section,
       (SELECT COUNT(*) FROM dbo.naaccr_staging WHERE value_num IS NOT NULL) AS expected_measurements,
       (SELECT COUNT(*) FROM dbo.measurement m WHERE m.measurement_type_concept_id = @TYPE_NAACCR) AS actual_measurements;

-----------------------------
-- 3) Episode_event link checks
-----------------------------
SELECT 'Episode_event links (obs/meas)' AS section,
       (SELECT COUNT(*) FROM dbo.episode_event WHERE episode_event_field_concept_id = @FIELD_OBS_ID)  AS obs_links,
       (SELECT COUNT(*) FROM dbo.episode_event WHERE episode_event_field_concept_id = @FIELD_MEAS_ID) AS meas_links;

SELECT 'Observations missing links' AS section,
       COUNT(*) AS missing_obs_links
FROM dbo.observation o
LEFT JOIN dbo.episode_event ee
  ON ee.event_id = o.observation_id AND ee.episode_event_field_concept_id = @FIELD_OBS_ID
WHERE ee.event_id IS NULL;

SELECT 'Measurements missing links' AS section,
       COUNT(*) AS missing_meas_links
FROM dbo.measurement m
LEFT JOIN dbo.episode_event ee
  ON ee.event_id = m.measurement_id AND ee.episode_event_field_concept_id = @FIELD_MEAS_ID
WHERE ee.event_id IS NULL;

-----------------------------
-- 4) Per-episode summary (top 20)
-----------------------------
SELECT TOP 20 'Per episode summary' AS section,
       x.person_id,
       x.episode_source_value,
       x.obs_count,
       x.meas_count
FROM (
  SELECT e.person_id,
         e.episode_source_value,
         COUNT(DISTINCT CASE WHEN ee.episode_event_field_concept_id = @FIELD_OBS_ID  THEN ee.event_id END) AS obs_count,
         COUNT(DISTINCT CASE WHEN ee.episode_event_field_concept_id = @FIELD_MEAS_ID THEN ee.event_id END) AS meas_count
  FROM dbo.episode e
  LEFT JOIN dbo.episode_event ee ON ee.episode_id = e.episode_id
  GROUP BY e.person_id, e.episode_source_value
) AS x
ORDER BY (x.obs_count + x.meas_count) DESC, x.person_id;

-----------------------------
-- 5) Spot check for units (top 20 measurements with unit_source_value)
-----------------------------
SELECT TOP 20 'Measurement units' AS section,
       m.person_id, m.measurement_source_value, m.value_as_number, m.unit_source_value, m.measurement_date
FROM dbo.measurement m
WHERE NULLIF(m.unit_source_value, '') IS NOT NULL
ORDER BY m.measurement_date DESC;

-- End validation script
