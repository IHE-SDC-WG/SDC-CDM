/*
  Bridge script 4: one thin omop.condition_occurrence per selected
  naaccr.report_group with a primary-site value (item 400), and one disease
  omop.episode per (person, naaccr_value.episode_key) whose omop.episode_event
  rows link every bridged measurement, observation, and condition of that tumor.
  naaccr.group_condition and naaccr.person_episode name the rows this bridge
  owns, and it owns every episode_event row of an owned episode.

  Condition: the group's lowest naaccr_value_id with item_num 400 and a
  non-blank value_code or value_text. Its date and cut source value come from
  that value's script-3 row, so no date or length rule is repeated here.
  condition_source_concept_id is the (400, value_code) value map source concept,
  else 0. condition_concept_id is that map's standard target only when it is
  nonzero, in the Condition domain, and not listed by naaccr.value_code_collision
  (#100). Otherwise it is 0, and condition_target says why. Codes match exactly,
  as in SQLite. No histology or ICD-O-3 combination logic.

  Episode: episode_start_date is the earliest linked event date and
  episode_end_date stays NULL. episode_object_concept_id is the nonzero
  condition_concept_id of the episode's lowest-report_group_id condition, else 0.
  The hashed episode_key is not a source code and stays in naaccr.person_episode.

  Updates occur only when state differs; condition and episode IDs stay stable
  per group and per (person, episode_key), and a deleted ID is never reused.
*/

DROP TABLE IF EXISTS #bridge_condition;
GO

WITH site AS (
    SELECT g.report_group_id, g.person_id, v.naaccr_value_id, v.episode_key, v.value_code,
           l.event_table, l.event_id,
           ROW_NUMBER() OVER (PARTITION BY g.report_group_id
                              ORDER BY v.naaccr_value_id) AS site_rank
    FROM naaccr.value_event l
    JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
    JOIN sdc.note_report link ON link.sdc_report_id = v.sdc_report_id
    JOIN naaccr.report_group g ON g.report_group_id = link.report_group_id
    WHERE v.item_num = 400
      AND (NULLIF(TRIM(v.value_code), '') IS NOT NULL
           OR NULLIF(TRIM(v.value_text), '') IS NOT NULL)
),
collision AS (
    SELECT DISTINCT item_num, code FROM naaccr.value_code_collision WHERE item_num = 400
),
targeted AS (
    SELECT s.report_group_id, s.person_id, s.naaccr_value_id, s.episode_key,
           COALESCE(m.measurement_date, o.observation_date) AS start_date,
           COALESCE(m.value_source_value, o.value_source_value) AS source_value,
           vm.concept_id AS map_concept_id, vm.source_concept_id AS map_source_concept_id,
           CASE WHEN c.item_num IS NOT NULL THEN 'collision_suppressed'
                WHEN vm.item_num IS NULL THEN 'no_map'
                WHEN vm.concept_id = 0 THEN 'no_target'
                WHEN vm.target_domain_id = 'Condition' THEN 'mapped'
                ELSE 'other_domain' END AS condition_target
    FROM site s
    LEFT JOIN omop.measurement m
      ON s.event_table = 'measurement' AND m.measurement_id = s.event_id
    LEFT JOIN omop.observation o
      ON s.event_table = 'observation' AND o.observation_id = s.event_id
    LEFT JOIN naaccr.naaccr_value_concept_map vm
      ON vm.item_num = 400 AND vm.code = s.value_code
     AND CAST(vm.code AS varbinary(510)) = CAST(s.value_code AS varbinary(510))
    LEFT JOIN collision c
      ON c.item_num = 400 AND c.code = s.value_code
     AND CAST(c.code AS varbinary(510)) = CAST(s.value_code AS varbinary(510))
    WHERE s.site_rank = 1
)
SELECT t.report_group_id, t.person_id, t.naaccr_value_id, t.episode_key,
       CAST(t.condition_target AS varchar(30)) AS condition_target,
       CAST(CASE WHEN t.condition_target = 'mapped' THEN t.map_concept_id
                 ELSE unmapped.concept_id END AS int) AS concept_id,
       CAST(COALESCE(t.map_source_concept_id, unmapped.concept_id) AS int) AS source_concept_id,
       t.start_date, t.source_value,
       condition_type.concept_id AS type_concept_id,
       CASE WHEN EXISTS (
                SELECT 1 FROM omop.condition_occurrence o
                WHERE o.condition_occurrence_id = old.condition_occurrence_id)
            THEN old.condition_occurrence_id END AS condition_occurrence_id
INTO #bridge_condition
FROM targeted t
LEFT JOIN naaccr.group_condition old ON old.report_group_id = t.report_group_id
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant condition_type
  ON condition_type.constant_name = 'condition_type_registry';
GO

-- Remove owned conditions whose group no longer has a site value or whose row is gone.
DELETE o
FROM omop.condition_occurrence o
JOIN naaccr.group_condition l ON l.condition_occurrence_id = o.condition_occurrence_id
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_condition b
    WHERE b.report_group_id = l.report_group_id
      AND b.condition_occurrence_id = l.condition_occurrence_id
);
GO

DELETE l
FROM naaccr.group_condition l
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_condition b
    WHERE b.report_group_id = l.report_group_id
      AND b.condition_occurrence_id = l.condition_occurrence_id
);
GO

UPDATE o
SET person_id = b.person_id,
    condition_concept_id = b.concept_id,
    condition_start_date = b.start_date,
    condition_start_datetime = NULL,
    condition_end_date = NULL,
    condition_end_datetime = NULL,
    condition_type_concept_id = b.type_concept_id,
    condition_status_concept_id = NULL,
    stop_reason = NULL,
    provider_id = NULL,
    visit_occurrence_id = NULL,
    visit_detail_id = NULL,
    condition_source_value = b.source_value,
    condition_source_concept_id = b.source_concept_id,
    condition_status_source_value = NULL
FROM omop.condition_occurrence o
JOIN #bridge_condition b ON b.condition_occurrence_id = o.condition_occurrence_id
WHERE EXISTS (
    -- Text collation ignores some case/spacing changes; compare the stored bytes.
    SELECT o.person_id, o.condition_concept_id, o.condition_start_date,
        o.condition_start_datetime, o.condition_end_date, o.condition_end_datetime,
        o.condition_type_concept_id, o.condition_status_concept_id,
        CAST(o.stop_reason AS varbinary(MAX)), o.provider_id, o.visit_occurrence_id,
        o.visit_detail_id, CAST(o.condition_source_value AS varbinary(MAX)),
        o.condition_source_concept_id, CAST(o.condition_status_source_value AS varbinary(MAX))
    EXCEPT
    SELECT b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL, b.type_concept_id,
        NULL, NULL, NULL, NULL, NULL, CAST(b.source_value AS varbinary(MAX)),
        b.source_concept_id, NULL
);
GO

UPDATE l
SET naaccr_value_id = b.naaccr_value_id, condition_target = b.condition_target
FROM naaccr.group_condition l
JOIN #bridge_condition b ON b.report_group_id = l.report_group_id
WHERE EXISTS (
    SELECT l.naaccr_value_id, CAST(l.condition_target AS varbinary(60))
    EXCEPT
    SELECT b.naaccr_value_id, CAST(b.condition_target AS varbinary(60))
);
GO

DROP TABLE IF EXISTS #bridge_new_condition;
GO

CREATE TABLE #bridge_new_condition (
    report_group_id INT NOT NULL, condition_occurrence_id INT NOT NULL
);
GO

-- OUTPUT INTO records group identity without returning a result set to the runner.
MERGE omop.condition_occurrence AS target
USING (SELECT * FROM #bridge_condition WHERE condition_occurrence_id IS NULL) AS b
ON 1 = 0
WHEN NOT MATCHED THEN
    INSERT (person_id, condition_concept_id, condition_start_date, condition_start_datetime,
        condition_end_date, condition_end_datetime, condition_type_concept_id,
        condition_status_concept_id, stop_reason, provider_id, visit_occurrence_id,
        visit_detail_id, condition_source_value, condition_source_concept_id,
        condition_status_source_value)
    VALUES (b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL, b.type_concept_id,
        NULL, NULL, NULL, NULL, NULL, b.source_value, b.source_concept_id, NULL)
OUTPUT b.report_group_id, inserted.condition_occurrence_id
    INTO #bridge_new_condition (report_group_id, condition_occurrence_id);
GO

UPDATE #bridge_condition
SET condition_occurrence_id = (
    SELECT n.condition_occurrence_id FROM #bridge_new_condition n
    WHERE n.report_group_id = #bridge_condition.report_group_id)
WHERE condition_occurrence_id IS NULL;
GO

INSERT INTO naaccr.group_condition (report_group_id, condition_occurrence_id, naaccr_value_id,
    condition_target)
SELECT b.report_group_id, b.condition_occurrence_id, b.naaccr_value_id, b.condition_target
FROM #bridge_condition b
JOIN #bridge_new_condition n ON n.report_group_id = b.report_group_id;
GO

DROP TABLE IF EXISTS #bridge_episode_event;
GO

-- Every bridged clinical row and condition, keyed by its tumor within its person.
SELECT g.person_id, v.episode_key, CAST(l.event_id AS bigint) AS event_id,
       CASE WHEN l.event_table = 'measurement' THEN measurement_field.concept_id
            ELSE observation_field.concept_id END AS field_concept_id,
       COALESCE(m.measurement_date, o.observation_date) AS event_date
INTO #bridge_episode_event
FROM naaccr.value_event l
JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
JOIN sdc.note_report link ON link.sdc_report_id = v.sdc_report_id
JOIN naaccr.report_group g ON g.report_group_id = link.report_group_id
LEFT JOIN omop.measurement m ON l.event_table = 'measurement' AND m.measurement_id = l.event_id
LEFT JOIN omop.observation o ON l.event_table = 'observation' AND o.observation_id = l.event_id
JOIN etl.concept_constant measurement_field
  ON measurement_field.constant_name = 'field_measurement_measurement_id'
JOIN etl.concept_constant observation_field
  ON observation_field.constant_name = 'field_observation_observation_id'
UNION ALL
SELECT c.person_id, c.episode_key, CAST(c.condition_occurrence_id AS bigint),
       condition_field.concept_id, c.start_date
FROM #bridge_condition c
JOIN etl.concept_constant condition_field
  ON condition_field.constant_name = 'field_condition_occurrence_id';
GO

DROP TABLE IF EXISTS #bridge_episode;
GO

WITH grouped AS (
    SELECT person_id, episode_key, MIN(event_date) AS start_date
    FROM #bridge_episode_event
    GROUP BY person_id, episode_key
)
SELECT g.person_id, g.episode_key, g.start_date,
       disease.concept_id AS concept_id,
       episode_type.concept_id AS type_concept_id,
       COALESCE((
           SELECT TOP (1) c.concept_id FROM #bridge_condition c
           WHERE c.person_id = g.person_id AND c.episode_key = g.episode_key
             AND c.concept_id <> 0
           ORDER BY c.report_group_id
       ), unmapped.concept_id) AS object_concept_id,
       unmapped.concept_id AS source_concept_id,
       CASE WHEN EXISTS (
                SELECT 1 FROM omop.episode o WHERE o.episode_id = old.episode_id)
            THEN old.episode_id END AS episode_id
INTO #bridge_episode
FROM grouped g
LEFT JOIN naaccr.person_episode old
  ON old.person_id = g.person_id AND old.episode_key = g.episode_key
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant disease ON disease.constant_name = 'episode_disease'
JOIN etl.concept_constant episode_type
  ON episode_type.constant_name = 'episode_type_registry';
GO

-- Remove owned episode events that are no longer staged for their kept episode.
DELETE x
FROM omop.episode_event x
JOIN naaccr.person_episode l ON l.episode_id = x.episode_id
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_episode b
    JOIN #bridge_episode_event e
      ON e.person_id = b.person_id AND e.episode_key = b.episode_key
    WHERE b.episode_id = x.episode_id AND e.event_id = x.event_id
      AND e.field_concept_id = x.episode_event_field_concept_id
);
GO

DELETE o
FROM omop.episode o
JOIN naaccr.person_episode l ON l.episode_id = o.episode_id
WHERE NOT EXISTS (SELECT 1 FROM #bridge_episode b WHERE b.episode_id = l.episode_id);
GO

DELETE l
FROM naaccr.person_episode l
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_episode b
    WHERE b.episode_id = l.episode_id AND b.person_id = l.person_id
      AND b.episode_key = l.episode_key
);
GO

UPDATE o
SET person_id = b.person_id,
    episode_concept_id = b.concept_id,
    episode_start_date = b.start_date,
    episode_start_datetime = NULL,
    episode_end_date = NULL,
    episode_end_datetime = NULL,
    episode_parent_id = NULL,
    episode_number = NULL,
    episode_object_concept_id = b.object_concept_id,
    episode_type_concept_id = b.type_concept_id,
    episode_source_value = NULL,
    episode_source_concept_id = b.source_concept_id
FROM omop.episode o
JOIN #bridge_episode b ON b.episode_id = o.episode_id
WHERE EXISTS (
    SELECT o.person_id, o.episode_concept_id, o.episode_start_date, o.episode_start_datetime,
        o.episode_end_date, o.episode_end_datetime, o.episode_parent_id, o.episode_number,
        o.episode_object_concept_id, o.episode_type_concept_id,
        CAST(o.episode_source_value AS varbinary(MAX)), o.episode_source_concept_id
    EXCEPT
    SELECT b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL, NULL, NULL,
        b.object_concept_id, b.type_concept_id, NULL, b.source_concept_id
);
GO

DROP TABLE IF EXISTS #bridge_new_episode;
GO

-- Take the database collation, not tempdb's, so keys compare with #bridge_episode.
CREATE TABLE #bridge_new_episode (
    person_id INT NOT NULL, episode_key NVARCHAR(100) COLLATE DATABASE_DEFAULT NOT NULL,
    episode_id BIGINT NOT NULL
);
GO

MERGE omop.episode AS target
USING (SELECT * FROM #bridge_episode WHERE episode_id IS NULL) AS b
ON 1 = 0
WHEN NOT MATCHED THEN
    INSERT (person_id, episode_concept_id, episode_start_date, episode_start_datetime,
        episode_end_date, episode_end_datetime, episode_parent_id, episode_number,
        episode_object_concept_id, episode_type_concept_id, episode_source_value,
        episode_source_concept_id)
    VALUES (b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL, NULL, NULL,
        b.object_concept_id, b.type_concept_id, NULL, b.source_concept_id)
OUTPUT b.person_id, b.episode_key, inserted.episode_id
    INTO #bridge_new_episode (person_id, episode_key, episode_id);
GO

UPDATE #bridge_episode
SET episode_id = (
    SELECT n.episode_id FROM #bridge_new_episode n
    WHERE n.person_id = #bridge_episode.person_id
      AND n.episode_key = #bridge_episode.episode_key)
WHERE episode_id IS NULL;
GO

INSERT INTO naaccr.person_episode (episode_id, person_id, episode_key)
SELECT b.episode_id, b.person_id, b.episode_key
FROM #bridge_episode b
JOIN #bridge_new_episode n ON n.person_id = b.person_id AND n.episode_key = b.episode_key;
GO

INSERT INTO omop.episode_event (episode_id, event_id, episode_event_field_concept_id)
SELECT b.episode_id, e.event_id, e.field_concept_id
FROM #bridge_episode_event e
JOIN #bridge_episode b ON b.person_id = e.person_id AND b.episode_key = e.episode_key
WHERE NOT EXISTS (
    SELECT 1 FROM omop.episode_event x
    WHERE x.episode_id = b.episode_id AND x.event_id = e.event_id
      AND x.episode_event_field_concept_id = e.field_concept_id
);
GO
