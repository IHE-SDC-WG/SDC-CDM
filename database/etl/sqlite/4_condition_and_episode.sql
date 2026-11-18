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
  (#100). Otherwise it is 0, and condition_target says why. No histology or
  ICD-O-3 combination logic.

  Episode: episode_start_date is the earliest linked event date and
  episode_end_date stays NULL. episode_object_concept_id is the nonzero
  condition_concept_id of the episode's lowest-report_group_id condition, else 0.
  The hashed episode_key is not a source code and stays in naaccr.person_episode.

  Updates occur only when state differs; condition and episode IDs stay stable
  per group and per (person, episode_key), and a deleted ID is never reused.
*/

DROP TABLE IF EXISTS temp.bridge_condition;

CREATE TEMP TABLE bridge_condition AS
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
    LEFT JOIN (SELECT DISTINCT item_num, code FROM naaccr.value_code_collision) c
      ON c.item_num = 400 AND c.code = s.value_code
    WHERE s.site_rank = 1
)
SELECT t.report_group_id, t.person_id, t.naaccr_value_id, t.episode_key, t.condition_target,
       CASE WHEN t.condition_target = 'mapped' THEN t.map_concept_id
            ELSE unmapped.concept_id END AS concept_id,
       COALESCE(t.map_source_concept_id, unmapped.concept_id) AS source_concept_id,
       t.start_date, t.source_value,
       condition_type.concept_id AS type_concept_id,
       CASE WHEN EXISTS (
                SELECT 1 FROM omop.condition_occurrence o
                WHERE o.condition_occurrence_id = old.condition_occurrence_id)
            THEN old.condition_occurrence_id END AS condition_occurrence_id
FROM targeted t
LEFT JOIN naaccr.group_condition old ON old.report_group_id = t.report_group_id
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant condition_type
  ON condition_type.constant_name = 'condition_type_registry';

-- Remove owned conditions whose group no longer has a site value or whose row is gone.
DELETE FROM omop.condition_occurrence
WHERE condition_occurrence_id IN (
    SELECT l.condition_occurrence_id FROM naaccr.group_condition l
    WHERE NOT EXISTS (
        SELECT 1 FROM temp.bridge_condition b
        WHERE b.report_group_id = l.report_group_id
          AND b.condition_occurrence_id = l.condition_occurrence_id
    )
);

DELETE FROM naaccr.group_condition
WHERE NOT EXISTS (
    SELECT 1 FROM temp.bridge_condition b
    WHERE b.report_group_id = naaccr.group_condition.report_group_id
      AND b.condition_occurrence_id = naaccr.group_condition.condition_occurrence_id
);

UPDATE omop.condition_occurrence AS o
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
FROM temp.bridge_condition b
WHERE o.condition_occurrence_id = b.condition_occurrence_id AND (
    o.person_id IS NOT b.person_id
    OR o.condition_concept_id IS NOT b.concept_id
    OR o.condition_start_date IS NOT b.start_date
    OR o.condition_start_datetime IS NOT NULL
    OR o.condition_end_date IS NOT NULL
    OR o.condition_end_datetime IS NOT NULL
    OR o.condition_type_concept_id IS NOT b.type_concept_id
    OR o.condition_status_concept_id IS NOT NULL
    OR o.stop_reason IS NOT NULL
    OR o.provider_id IS NOT NULL
    OR o.visit_occurrence_id IS NOT NULL
    OR o.visit_detail_id IS NOT NULL
    OR o.condition_source_value IS NOT b.source_value
    OR o.condition_source_concept_id IS NOT b.source_concept_id
    OR o.condition_status_source_value IS NOT NULL
);

UPDATE naaccr.group_condition AS l
SET naaccr_value_id = b.naaccr_value_id, condition_target = b.condition_target
FROM temp.bridge_condition b
WHERE b.report_group_id = l.report_group_id AND (
    l.naaccr_value_id IS NOT b.naaccr_value_id
    OR l.condition_target IS NOT b.condition_target
);

DROP TABLE IF EXISTS temp.bridge_new_condition;

-- Explicit IDs above the AUTOINCREMENT high-water mark, as in script 3.
CREATE TEMP TABLE bridge_new_condition AS
SELECT report_group_id,
       MAX((SELECT COALESCE(MAX(condition_occurrence_id), 0) FROM omop.condition_occurrence),
           COALESCE((SELECT seq FROM omop.sqlite_sequence
                     WHERE name = 'condition_occurrence'), 0))
           + ROW_NUMBER() OVER (ORDER BY report_group_id) AS condition_occurrence_id
FROM temp.bridge_condition WHERE condition_occurrence_id IS NULL;

UPDATE temp.bridge_condition
SET condition_occurrence_id = (
    SELECT n.condition_occurrence_id FROM temp.bridge_new_condition n
    WHERE n.report_group_id = temp.bridge_condition.report_group_id)
WHERE condition_occurrence_id IS NULL;

INSERT INTO omop.condition_occurrence (condition_occurrence_id, person_id,
    condition_concept_id, condition_start_date, condition_start_datetime, condition_end_date,
    condition_end_datetime, condition_type_concept_id, condition_status_concept_id,
    stop_reason, provider_id, visit_occurrence_id, visit_detail_id, condition_source_value,
    condition_source_concept_id, condition_status_source_value)
SELECT b.condition_occurrence_id, b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL,
    b.type_concept_id, NULL, NULL, NULL, NULL, NULL, b.source_value, b.source_concept_id, NULL
FROM temp.bridge_condition b
JOIN temp.bridge_new_condition n ON n.report_group_id = b.report_group_id
ORDER BY b.report_group_id;

INSERT INTO naaccr.group_condition (report_group_id, condition_occurrence_id, naaccr_value_id,
    condition_target)
SELECT b.report_group_id, b.condition_occurrence_id, b.naaccr_value_id, b.condition_target
FROM temp.bridge_condition b
JOIN temp.bridge_new_condition n ON n.report_group_id = b.report_group_id
ORDER BY b.report_group_id;

DROP TABLE IF EXISTS temp.bridge_episode_event;

-- Every bridged clinical row and condition, keyed by its tumor within its person.
CREATE TEMP TABLE bridge_episode_event AS
SELECT g.person_id, v.episode_key, l.event_id,
       CASE WHEN l.event_table = 'measurement' THEN measurement_field.concept_id
            ELSE observation_field.concept_id END AS field_concept_id,
       COALESCE(m.measurement_date, o.observation_date) AS event_date
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
SELECT c.person_id, c.episode_key, c.condition_occurrence_id, condition_field.concept_id,
       c.start_date
FROM temp.bridge_condition c
JOIN etl.concept_constant condition_field
  ON condition_field.constant_name = 'field_condition_occurrence_id';

DROP TABLE IF EXISTS temp.bridge_episode;

CREATE TEMP TABLE bridge_episode AS
WITH grouped AS (
    SELECT person_id, episode_key, MIN(event_date) AS start_date
    FROM temp.bridge_episode_event
    GROUP BY person_id, episode_key
)
SELECT g.person_id, g.episode_key, g.start_date,
       disease.concept_id AS concept_id,
       episode_type.concept_id AS type_concept_id,
       COALESCE((
           SELECT c.concept_id FROM temp.bridge_condition c
           WHERE c.person_id = g.person_id AND c.episode_key = g.episode_key
             AND c.concept_id <> 0
           ORDER BY c.report_group_id LIMIT 1
       ), unmapped.concept_id) AS object_concept_id,
       unmapped.concept_id AS source_concept_id,
       CASE WHEN EXISTS (
                SELECT 1 FROM omop.episode o WHERE o.episode_id = old.episode_id)
            THEN old.episode_id END AS episode_id
FROM grouped g
LEFT JOIN naaccr.person_episode old
  ON old.person_id = g.person_id AND old.episode_key = g.episode_key
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant disease ON disease.constant_name = 'episode_disease'
JOIN etl.concept_constant episode_type
  ON episode_type.constant_name = 'episode_type_registry';

-- Remove owned episode events that are no longer staged for their kept episode.
DELETE FROM omop.episode_event
WHERE episode_id IN (SELECT episode_id FROM naaccr.person_episode)
  AND NOT EXISTS (
    SELECT 1 FROM temp.bridge_episode b
    JOIN temp.bridge_episode_event e
      ON e.person_id = b.person_id AND e.episode_key = b.episode_key
    WHERE b.episode_id = omop.episode_event.episode_id
      AND e.event_id = omop.episode_event.event_id
      AND e.field_concept_id = omop.episode_event.episode_event_field_concept_id
);

DELETE FROM omop.episode
WHERE episode_id IN (
    SELECT l.episode_id FROM naaccr.person_episode l
    WHERE NOT EXISTS (SELECT 1 FROM temp.bridge_episode b WHERE b.episode_id = l.episode_id)
);

DELETE FROM naaccr.person_episode
WHERE NOT EXISTS (
    SELECT 1 FROM temp.bridge_episode b
    WHERE b.episode_id = naaccr.person_episode.episode_id
      AND b.person_id = naaccr.person_episode.person_id
      AND b.episode_key = naaccr.person_episode.episode_key
);

UPDATE omop.episode AS o
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
FROM temp.bridge_episode b
WHERE o.episode_id = b.episode_id AND (
    o.person_id IS NOT b.person_id
    OR o.episode_concept_id IS NOT b.concept_id
    OR o.episode_start_date IS NOT b.start_date
    OR o.episode_start_datetime IS NOT NULL
    OR o.episode_end_date IS NOT NULL
    OR o.episode_end_datetime IS NOT NULL
    OR o.episode_parent_id IS NOT NULL
    OR o.episode_number IS NOT NULL
    OR o.episode_object_concept_id IS NOT b.object_concept_id
    OR o.episode_type_concept_id IS NOT b.type_concept_id
    OR o.episode_source_value IS NOT NULL
    OR o.episode_source_concept_id IS NOT b.source_concept_id
);

DROP TABLE IF EXISTS temp.bridge_new_episode;

CREATE TEMP TABLE bridge_new_episode AS
SELECT person_id, episode_key,
       MAX((SELECT COALESCE(MAX(episode_id), 0) FROM omop.episode),
           COALESCE((SELECT seq FROM omop.sqlite_sequence WHERE name = 'episode'), 0))
           + ROW_NUMBER() OVER (ORDER BY person_id, episode_key) AS episode_id
FROM temp.bridge_episode WHERE episode_id IS NULL;

UPDATE temp.bridge_episode
SET episode_id = (
    SELECT n.episode_id FROM temp.bridge_new_episode n
    WHERE n.person_id = temp.bridge_episode.person_id
      AND n.episode_key = temp.bridge_episode.episode_key)
WHERE episode_id IS NULL;

INSERT INTO omop.episode (episode_id, person_id, episode_concept_id, episode_start_date,
    episode_start_datetime, episode_end_date, episode_end_datetime, episode_parent_id,
    episode_number, episode_object_concept_id, episode_type_concept_id, episode_source_value,
    episode_source_concept_id)
SELECT b.episode_id, b.person_id, b.concept_id, b.start_date, NULL, NULL, NULL, NULL, NULL,
    b.object_concept_id, b.type_concept_id, NULL, b.source_concept_id
FROM temp.bridge_episode b
JOIN temp.bridge_new_episode n
  ON n.person_id = b.person_id AND n.episode_key = b.episode_key
ORDER BY b.episode_id;

INSERT INTO naaccr.person_episode (episode_id, person_id, episode_key)
SELECT b.episode_id, b.person_id, b.episode_key
FROM temp.bridge_episode b
JOIN temp.bridge_new_episode n
  ON n.person_id = b.person_id AND n.episode_key = b.episode_key
ORDER BY b.episode_id;

INSERT INTO omop.episode_event (episode_id, event_id, episode_event_field_concept_id)
SELECT b.episode_id, e.event_id, e.field_concept_id
FROM temp.bridge_episode_event e
JOIN temp.bridge_episode b ON b.person_id = e.person_id AND b.episode_key = e.episode_key
WHERE NOT EXISTS (
    SELECT 1 FROM omop.episode_event x
    WHERE x.episode_id = b.episode_id AND x.event_id = e.event_id
      AND x.episode_event_field_concept_id = e.field_concept_id
)
ORDER BY b.episode_id, e.field_concept_id, e.event_id;
