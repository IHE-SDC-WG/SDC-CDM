/*
  NAACCR → OMOP CDM v5.4 ETL Scaffolding (SQL Server)

  Goal
  - Materialize NAACCR items as OMOP Observation/Measurement records
  - Anchor all NAACCR-derived events to an Oncology Episode using EPISODE/EPISODE_EVENT

  Notes
  - This is a scaffolding script: adapt to your source case-level tables.
  - Expects NAACCR vocabulary seeding in dbo (see naaccr_omop_vocab.sql).
  - Uses cap.* as source 3NF metadata only; patient-level values should come from your feeds.

  Requirements
  - Identify patient/tumor (episode) keys from source
  - Identify NAACCR items (item_num) and values (code or numeric), and date context
*/

------------------------------------------------------------
-- Parameters (replace @cdmDatabaseSchema before execution)
------------------------------------------------------------
--DECLARE @cdmDatabaseSchema SYSNAME = 'dbo'; -- set via preprocessor if needed
--DECLARE @srcSchema SYSNAME = 'cap';          -- NAACCR 3NF schema (metadata)

/*
Interface: Supply a staging table or temp table with patient-level NAACCR values.
Expected minimal shape (example below creates a temp table for illustration):

CREATE TABLE #naaccr_source (
  person_id            INT           NOT NULL,
  episode_key          NVARCHAR(100) NOT NULL,  -- source tumor/episode identifier
  schema_id_number     NVARCHAR(255) NULL,      -- e.g., '00060'
  item_num             INT           NOT NULL,
  value_code           NVARCHAR(255) NULL,      -- categorical code (may be empty)
  value_num            FLOAT         NULL,      -- numeric value (if applicable)
  value_unit_source    NVARCHAR(50)  NULL,      -- unit (if numeric)
  observation_date     DATE          NULL       -- best available date
);
*/

-- Source table: this ETL uses dbo.naaccr_staging directly (no temp table)

------------------------------------------------------------
-- 0) Lookup helper: get concept_ids for episode type and field concepts
------------------------------------------------------------
DECLARE @EPISODE_TYPE_CANCER BIGINT;
SELECT TOP 1
  @EPISODE_TYPE_CANCER = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'NAACCR_CANCER_EPISODE';

DECLARE @FIELD_OBS_ID BIGINT;
SELECT TOP 1
  @FIELD_OBS_ID = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_OBSERVATION_ID';

DECLARE @FIELD_MEAS_ID BIGINT;
SELECT TOP 1
  @FIELD_MEAS_ID = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'FIELD_MEASUREMENT_ID';

DECLARE @TYPE_NAACCR BIGINT;
SELECT TOP 1
  @TYPE_NAACCR = concept_id
FROM dbo.concept
WHERE vocabulary_id = 'NAACCR2026' AND concept_code = 'TYPE_NAACCR_DERIVED';

------------------------------------------------------------
-- 1) Build/Upsert EPISODE for each (person_id, episode_key)
--    Adapt the episode dates to your source (diagnosis period, etc.)
------------------------------------------------------------
;WITH
  episodes_src
  AS
  (
    SELECT ns.person_id,
      ns.episode_key,
      MIN(ns.observation_date) AS episode_start_date,
      MAX(ns.observation_date) AS episode_end_date
    FROM dbo.naaccr_staging ns
    GROUP BY ns.person_id, ns.episode_key
  )
INSERT INTO dbo.episode
  (
  person_id, episode_concept_id, episode_start_datetime,
  episode_end_datetime, episode_parent_id, episode_number,
  episode_object_concept_id, episode_source_value, episode_source_concept_id
  )
SELECT
  e.person_id,
  @EPISODE_TYPE_CANCER AS episode_concept_id,
  CAST(e.episode_start_date AS DATETIME) AS episode_start_datetime,
  CAST(e.episode_end_date   AS DATETIME) AS episode_end_datetime,
  NULL AS episode_parent_id,
  NULL AS episode_number,
  NULL AS episode_object_concept_id, -- optional: SNOMED for primary cancer when available
  e.episode_key AS episode_source_value,
  NULL AS episode_source_concept_id
FROM episodes_src e
  LEFT JOIN dbo.episode tgt
  ON tgt.person_id = e.person_id
    AND tgt.episode_source_value = e.episode_key
WHERE tgt.episode_id IS NULL;

------------------------------------------------------------
-- 2) Insert NAACCR items as Observations
--    - observation_concept_id = NAACCR Item concept
--    - value_as_concept_id    = NAACCR Value concept (categorical)
--    - value_as_number/unit   = numeric where applicable
------------------------------------------------------------
;
WITH
  item_concepts
  AS
  (
    SELECT m.item_num, m.concept_id AS item_concept_id
    FROM cap.NAACCR_CONCEPT_MAP m
  ),
  value_concepts
  AS
  (
    SELECT vm.item_num, vm.code, vm.concept_id AS value_concept_id
    FROM cap.NAACCR_VALUE_CONCEPT_MAP vm
  ),
  input_rows
  AS
  (
    SELECT ns.person_id,
      ns.item_num,
      ns.value_code,
      ns.value_num,
      ns.value_unit_source,
      ns.observation_date
    FROM dbo.naaccr_staging ns
  )
-- 2a) Categorical items → Observations
INSERT INTO dbo.observation
  (
  person_id, observation_concept_id, observation_date, observation_datetime,
  observation_type_concept_id, value_as_number, value_as_string, value_as_concept_id,
  qualifier_concept_id, unit_concept_id, provider_id, visit_occurrence_id, visit_detail_id,
  observation_source_value, observation_source_concept_id, unit_source_value, qualifier_source_value
  )
SELECT
  i.person_id,
  ic.item_concept_id AS observation_concept_id,
  COALESCE(i.observation_date, CAST(GETDATE() AS DATE)) AS observation_date,
  CAST(COALESCE(i.observation_date, CAST(GETDATE() AS DATE)) AS DATETIME) AS observation_datetime,
  @TYPE_NAACCR AS observation_type_concept_id,
  i.value_num AS value_as_number,
  NULL AS value_as_string,
  vc.value_concept_id AS value_as_concept_id,
  NULL AS qualifier_concept_id,
  NULL AS unit_concept_id, -- map unit_source_value to a unit_concept_id if available
  NULL AS provider_id,
  NULL AS visit_occurrence_id,
  NULL AS visit_detail_id,
  CAST(i.item_num AS NVARCHAR(50)) AS observation_source_value,
  ic.item_concept_id AS observation_source_concept_id,
  i.value_unit_source AS unit_source_value,
  NULL AS qualifier_source_value
FROM input_rows i
  JOIN item_concepts ic
  ON ic.item_num = i.item_num
  LEFT JOIN value_concepts vc
  ON vc.item_num = i.item_num AND vc.code = COALESCE(i.value_code, N'')
WHERE i.value_num IS NULL;
-- use Observation only when no numeric value

------------------------------------------------------------
-- 2b) Numeric items → Measurements
------------------------------------------------------------
;
WITH
  item_concepts_m
  AS
  (
    SELECT m.item_num, m.concept_id AS item_concept_id
    FROM cap.NAACCR_CONCEPT_MAP m
  ),
  input_rows_m
  AS
  (
    SELECT ns.person_id, ns.item_num, ns.value_num, ns.value_unit_source, ns.observation_date
    FROM dbo.naaccr_staging ns
    WHERE ns.value_num IS NOT NULL
  )
INSERT INTO dbo.measurement
  (
  person_id, measurement_concept_id, measurement_date, measurement_datetime,
  measurement_type_concept_id, operator_concept_id, value_as_number, value_as_concept_id,
  unit_concept_id, range_low, range_high, provider_id, visit_occurrence_id, visit_detail_id,
  measurement_source_value, measurement_source_concept_id, unit_source_value, value_source_value
  )
SELECT
  i.person_id,
  ic.item_concept_id AS measurement_concept_id,
  COALESCE(i.observation_date, CAST(GETDATE() AS DATE)) AS measurement_date,
  CAST(COALESCE(i.observation_date, CAST(GETDATE() AS DATE)) AS DATETIME) AS measurement_datetime,
  @TYPE_NAACCR AS measurement_type_concept_id,
  NULL AS operator_concept_id,
  i.value_num AS value_as_number,
  NULL AS value_as_concept_id,
  NULL AS unit_concept_id, -- map when standard units are available
  NULL AS range_low,
  NULL AS range_high,
  NULL AS provider_id,
  NULL AS visit_occurrence_id,
  NULL AS visit_detail_id,
  CAST(i.item_num AS NVARCHAR(50)) AS measurement_source_value,
  ic.item_concept_id AS measurement_source_concept_id,
  i.value_unit_source AS unit_source_value,
  NULL AS value_source_value
FROM input_rows_m i
  JOIN item_concepts_m ic ON ic.item_num = i.item_num;

------------------------------------------------------------
-- 3) Link Observations to Episodes via EPISODE_EVENT
------------------------------------------------------------
;WITH
  obs_with_episode
  AS
  (
    SELECT o.observation_id,
      o.person_id,
      e.episode_id
    FROM dbo.observation o
      JOIN dbo.naaccr_staging ns
      ON ns.person_id = o.person_id
        AND CAST(ns.item_num AS NVARCHAR(50)) = o.observation_source_value
        AND o.observation_date = COALESCE(ns.observation_date, o.observation_date)
      JOIN dbo.episode e


      ON e.person_id = ns.person_id
        AND e.episode_source_value = ns.episode_key
  )
INSERT INTO dbo.episode_event
  (
  episode_id, event_id, episode_event_field_concept_id
  )
SELECT DISTINCT o.episode_id,
  o.observation_id AS event_id,
  @FIELD_OBS_ID    AS episode_event_field_concept_id
FROM obs_with_episode o
  LEFT JOIN dbo.episode_event ee
  ON ee.episode_id = o.episode_id
    AND ee.event_id = o.observation_id
    AND ee.episode_event_field_concept_id = @FIELD_OBS_ID
WHERE ee.episode_id IS NULL;

------------------------------------------------------------
-- 4) Link Measurements to Episodes via EPISODE_EVENT
------------------------------------------------------------
;
WITH
  meas_with_episode
  AS
  (
    SELECT m.measurement_id, m.person_id, e.episode_id
    FROM dbo.measurement m
      JOIN dbo.naaccr_staging ns
      ON ns.person_id = m.person_id
        AND CAST(ns.item_num AS NVARCHAR(50)) = m.measurement_source_value
        AND m.measurement_date = COALESCE(ns.observation_date, m.measurement_date)
      JOIN dbo.episode e

      ON e.person_id = ns.person_id
        AND e.episode_source_value = ns.episode_key
  )
INSERT INTO dbo.episode_event
  (episode_id, event_id, episode_event_field_concept_id)
SELECT DISTINCT o.episode_id,
  o.measurement_id AS event_id,
  @FIELD_MEAS_ID   AS episode_event_field_concept_id
FROM meas_with_episode o
  LEFT JOIN dbo.episode_event ee
  ON ee.episode_id = o.episode_id
    AND ee.event_id = o.measurement_id
    AND ee.episode_event_field_concept_id = @FIELD_MEAS_ID
WHERE ee.episode_id IS NULL;

-- End scaffolding
