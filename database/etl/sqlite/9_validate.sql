/*
  Validation script 9 (SQLite): checks the bridge's OMOP output against its
  sources. Only `sdc-cdm validate` runs this file. It reads; it never writes.

  Contract: every statement returns rows (check_name, category, actual), where
  actual counts the offending rows, or the reported quantity. The SQL Server
  script emits the same check names. Python judges each row by its category:

    structural      orphan rows and event links, and each concept slot against
                    its OMOP contract; must be 0
    provenance      bridge-owned rows that cannot reach an intake.inbound_message;
                    must be 0
    reconciliation  selected, historical, and excluded inputs against the
                    OMOP rows they produce or explain; must be 0
    coverage        unmapped inputs; must not exceed validate_thresholds.csv
    report          printed, never fails

  Bridge-owned rows are the ones its link tables name: persons with an
  intake.patient row, periods with an etl.observation_period_derivation row,
  notes in sdc.note_report, clinical rows in naaccr.value_event, conditions in
  naaccr.group_condition, episodes in naaccr.person_episode, and every
  episode_event of an owned episode. Other OMOP rows are reported as unowned,
  never failed, but the orphan checks cover every row of the bridge-written
  tables. Constants come from etl.concept_constant by name.
*/

-- structural: rows whose person or episode is missing.
SELECT 'observation_period_orphan_person' AS check_name, 'structural' AS category,
       COUNT(*) AS actual
FROM omop.observation_period x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'note_orphan_person', 'structural', COUNT(*)
FROM omop.note x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'measurement_orphan_person', 'structural', COUNT(*)
FROM omop.measurement x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'observation_orphan_person', 'structural', COUNT(*)
FROM omop.observation x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'condition_orphan_person', 'structural', COUNT(*)
FROM omop.condition_occurrence x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'episode_orphan_person', 'structural', COUNT(*)
FROM omop.episode x
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = x.person_id)
UNION ALL
SELECT 'episode_event_orphan_episode', 'structural', COUNT(*)
FROM omop.episode_event x
WHERE NOT EXISTS (SELECT 1 FROM omop.episode e WHERE e.episode_id = x.episode_id);

-- structural: a non-NULL concept slot that names no omop.concept row.
SELECT 'person_unknown_concept' AS check_name, 'structural' AS category, COUNT(*) AS actual
FROM omop.person x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.gender_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.race_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.ethnicity_concept_id)
   OR (x.gender_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.gender_source_concept_id))
   OR (x.race_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.race_source_concept_id))
   OR (x.ethnicity_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.ethnicity_source_concept_id))
UNION ALL
SELECT 'observation_period_unknown_concept', 'structural', COUNT(*)
FROM omop.observation_period x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.period_type_concept_id)
UNION ALL
SELECT 'note_unknown_concept', 'structural', COUNT(*)
FROM omop.note x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.note_type_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.note_class_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.encoding_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.language_concept_id)
   OR (x.note_event_field_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.note_event_field_concept_id))
UNION ALL
SELECT 'measurement_unknown_concept', 'structural', COUNT(*)
FROM omop.measurement x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.measurement_concept_id)
   OR NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.measurement_type_concept_id)
   OR (x.operator_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.operator_concept_id))
   OR (x.value_as_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.value_as_concept_id))
   OR (x.unit_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.unit_concept_id))
   OR (x.measurement_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.measurement_source_concept_id))
   OR (x.unit_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.unit_source_concept_id))
   OR (x.meas_event_field_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.meas_event_field_concept_id))
UNION ALL
SELECT 'observation_unknown_concept', 'structural', COUNT(*)
FROM omop.observation x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.observation_concept_id)
   OR NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.observation_type_concept_id)
   OR (x.value_as_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.value_as_concept_id))
   OR (x.qualifier_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.qualifier_concept_id))
   OR (x.unit_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.unit_concept_id))
   OR (x.observation_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.observation_source_concept_id))
   OR (x.obs_event_field_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.obs_event_field_concept_id))
UNION ALL
SELECT 'condition_unknown_concept', 'structural', COUNT(*)
FROM omop.condition_occurrence x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.condition_concept_id)
   OR NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.condition_type_concept_id)
   OR (x.condition_status_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.condition_status_concept_id))
   OR (x.condition_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.condition_source_concept_id))
UNION ALL
SELECT 'episode_unknown_concept', 'structural', COUNT(*)
FROM omop.episode x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.episode_concept_id)
   OR NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.episode_object_concept_id)
   OR NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.episode_type_concept_id)
   OR (x.episode_source_concept_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM omop.concept c WHERE c.concept_id = x.episode_source_concept_id))
UNION ALL
SELECT 'episode_event_unknown_concept', 'structural', COUNT(*)
FROM omop.episode_event x
WHERE NOT EXISTS (
    SELECT 1 FROM omop.concept c WHERE c.concept_id = x.episode_event_field_concept_id)
UNION ALL
SELECT 'cdm_source_unknown_concept', 'structural', COUNT(*)
FROM omop.cdm_source x
WHERE NOT EXISTS (SELECT 1 FROM omop.concept c WHERE c.concept_id = x.cdm_version_concept_id);

-- structural: event links. A note-field event must name a note, and an
-- episode_event with a bridge field constant must name a row of that table.
WITH k AS (
    SELECT
        MAX(CASE WHEN constant_name = 'field_note_note_id' THEN concept_id END) AS note_field,
        MAX(CASE WHEN constant_name = 'field_measurement_measurement_id'
                 THEN concept_id END) AS measurement_field,
        MAX(CASE WHEN constant_name = 'field_observation_observation_id'
                 THEN concept_id END) AS observation_field,
        MAX(CASE WHEN constant_name = 'field_condition_occurrence_id'
                 THEN concept_id END) AS condition_field
    FROM etl.concept_constant
)
SELECT 'measurement_orphan_note_event' AS check_name, 'structural' AS category,
       COUNT(*) AS actual
FROM omop.measurement x CROSS JOIN k
WHERE (x.measurement_event_id IS NULL AND x.meas_event_field_concept_id IS NOT NULL)
   OR (x.measurement_event_id IS NOT NULL AND x.meas_event_field_concept_id IS NULL)
   OR (x.meas_event_field_concept_id = k.note_field AND NOT EXISTS (
       SELECT 1 FROM omop.note n WHERE n.note_id = x.measurement_event_id))
UNION ALL
SELECT 'observation_orphan_note_event', 'structural', COUNT(*)
FROM omop.observation x CROSS JOIN k
WHERE (x.observation_event_id IS NULL AND x.obs_event_field_concept_id IS NOT NULL)
   OR (x.observation_event_id IS NOT NULL AND x.obs_event_field_concept_id IS NULL)
   OR (x.obs_event_field_concept_id = k.note_field AND NOT EXISTS (
       SELECT 1 FROM omop.note n WHERE n.note_id = x.observation_event_id))
UNION ALL
SELECT 'episode_event_orphan_event', 'structural', COUNT(*)
FROM omop.episode_event x CROSS JOIN k
WHERE (x.episode_event_field_concept_id = k.measurement_field AND NOT EXISTS (
          SELECT 1 FROM omop.measurement o WHERE o.measurement_id = x.event_id))
   OR (x.episode_event_field_concept_id = k.observation_field AND NOT EXISTS (
          SELECT 1 FROM omop.observation o WHERE o.observation_id = x.event_id))
   OR (x.episode_event_field_concept_id = k.condition_field AND NOT EXISTS (
          SELECT 1 FROM omop.condition_occurrence o
          WHERE o.condition_occurrence_id = x.event_id));

-- structural: bridge link rows whose OMOP row or source row is missing.
SELECT 'note_report_orphan_link' AS check_name, 'structural' AS category, COUNT(*) AS actual
FROM sdc.note_report l
WHERE NOT EXISTS (SELECT 1 FROM omop.note n WHERE n.note_id = l.note_id)
   OR NOT EXISTS (
       SELECT 1 FROM naaccr.report_group g WHERE g.report_group_id = l.report_group_id)
   OR NOT EXISTS (
       SELECT 1 FROM naaccr.report_version rv
       WHERE rv.sdc_report_id = l.sdc_report_id AND rv.report_group_id = l.report_group_id)
UNION ALL
-- One group and exactly one anchor per linked note.
SELECT 'note_report_inconsistent', 'structural', COUNT(*)
FROM (
    SELECT note_id
    FROM sdc.note_report
    GROUP BY note_id
    HAVING COUNT(DISTINCT report_group_id) <> 1
       OR SUM(CASE WHEN is_anchor = 1 THEN 1 ELSE 0 END) <> 1
) x
UNION ALL
SELECT 'value_event_orphan_link', 'structural', COUNT(*)
FROM naaccr.value_event l
WHERE NOT EXISTS (
          SELECT 1 FROM naaccr.naaccr_value v WHERE v.naaccr_value_id = l.naaccr_value_id)
   OR (l.event_table = 'measurement' AND NOT EXISTS (
          SELECT 1 FROM omop.measurement o WHERE o.measurement_id = l.event_id))
   OR (l.event_table = 'observation' AND NOT EXISTS (
          SELECT 1 FROM omop.observation o WHERE o.observation_id = l.event_id))
UNION ALL
SELECT 'group_condition_orphan_link', 'structural', COUNT(*)
FROM naaccr.group_condition l
WHERE NOT EXISTS (
          SELECT 1 FROM omop.condition_occurrence o
          WHERE o.condition_occurrence_id = l.condition_occurrence_id)
   OR NOT EXISTS (
          SELECT 1 FROM naaccr.naaccr_value v WHERE v.naaccr_value_id = l.naaccr_value_id)
   OR NOT EXISTS (
          SELECT 1 FROM naaccr.report_group g WHERE g.report_group_id = l.report_group_id)
UNION ALL
SELECT 'person_episode_orphan_link', 'structural', COUNT(*)
FROM naaccr.person_episode l
WHERE NOT EXISTS (
    SELECT 1 FROM omop.episode e
    WHERE e.episode_id = l.episode_id AND e.person_id = l.person_id)
UNION ALL
SELECT 'period_derivation_orphan_link', 'structural', COUNT(*)
FROM etl.observation_period_derivation d
WHERE NOT EXISTS (
    SELECT 1 FROM omop.observation_period o
    WHERE o.observation_period_id = d.observation_period_id AND o.person_id = d.person_id);

-- structural: type, field, and constant slots of bridge-owned rows hold their
-- resolved constants, and slots the bridge leaves empty are NULL.
WITH k AS (
    SELECT
        MAX(CASE WHEN constant_name = 'unmapped' THEN concept_id END) AS unmapped,
        MAX(CASE WHEN constant_name = 'gender_male' THEN concept_id END) AS gender_male,
        MAX(CASE WHEN constant_name = 'gender_female' THEN concept_id END) AS gender_female,
        MAX(CASE WHEN constant_name = 'period_type_registry'
                 THEN concept_id END) AS period_type,
        MAX(CASE WHEN constant_name = 'note_type_ehr' THEN concept_id END) AS note_type,
        MAX(CASE WHEN constant_name = 'measurement_type_registry'
                 THEN concept_id END) AS measurement_type,
        MAX(CASE WHEN constant_name = 'observation_type_registry'
                 THEN concept_id END) AS observation_type,
        MAX(CASE WHEN constant_name = 'condition_type_registry'
                 THEN concept_id END) AS condition_type,
        MAX(CASE WHEN constant_name = 'episode_type_registry'
                 THEN concept_id END) AS episode_type,
        MAX(CASE WHEN constant_name = 'episode_disease' THEN concept_id END) AS episode_disease,
        MAX(CASE WHEN constant_name = 'field_note_note_id' THEN concept_id END) AS note_field,
        MAX(CASE WHEN constant_name = 'field_measurement_measurement_id'
                 THEN concept_id END) AS measurement_field,
        MAX(CASE WHEN constant_name = 'field_observation_observation_id'
                 THEN concept_id END) AS observation_field,
        MAX(CASE WHEN constant_name = 'field_condition_occurrence_id'
                 THEN concept_id END) AS condition_field,
        MAX(CASE WHEN constant_name = 'cdm_version' THEN concept_id END) AS cdm_version
    FROM etl.concept_constant
)
SELECT 'person_constant_slots' AS check_name, 'structural' AS category, COUNT(*) AS actual
FROM omop.person x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM intake.patient i WHERE i.patient_id = x.person_id)
  AND (x.gender_concept_id <> CASE UPPER(TRIM(x.gender_source_value))
                                   WHEN 'M' THEN k.gender_male
                                   WHEN 'F' THEN k.gender_female
                                   ELSE k.unmapped END
       OR x.race_concept_id <> k.unmapped
       OR x.ethnicity_concept_id <> k.unmapped
       OR x.gender_source_concept_id IS NULL
       OR x.gender_source_concept_id <> k.unmapped)
UNION ALL
SELECT 'observation_period_constant_slots', 'structural', COUNT(*)
FROM omop.observation_period x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM etl.observation_period_derivation d
              WHERE d.observation_period_id = x.observation_period_id)
  AND x.period_type_concept_id <> k.period_type
UNION ALL
SELECT 'note_constant_slots', 'structural', COUNT(*)
FROM omop.note x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM sdc.note_report l WHERE l.note_id = x.note_id)
  AND (x.note_type_concept_id <> k.note_type
       OR x.note_class_concept_id <> k.unmapped
       OR x.encoding_concept_id <> k.unmapped
       OR x.language_concept_id <> k.unmapped
       OR x.note_event_id IS NOT NULL
       OR x.note_event_field_concept_id IS NOT NULL)
UNION ALL
SELECT 'measurement_constant_slots', 'structural', COUNT(*)
FROM omop.measurement x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
              WHERE l.event_table = 'measurement' AND l.event_id = x.measurement_id)
  AND (x.measurement_type_concept_id <> k.measurement_type
       OR x.meas_event_field_concept_id IS NULL
       OR x.meas_event_field_concept_id <> k.note_field
       OR x.operator_concept_id IS NOT NULL
       OR x.unit_concept_id IS NOT NULL
       OR x.unit_source_concept_id IS NOT NULL)
UNION ALL
SELECT 'observation_constant_slots', 'structural', COUNT(*)
FROM omop.observation x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
              WHERE l.event_table = 'observation' AND l.event_id = x.observation_id)
  AND (x.observation_type_concept_id <> k.observation_type
       OR x.obs_event_field_concept_id IS NULL
       OR x.obs_event_field_concept_id <> k.note_field
       OR x.qualifier_concept_id IS NOT NULL
       OR x.unit_concept_id IS NOT NULL)
UNION ALL
SELECT 'condition_constant_slots', 'structural', COUNT(*)
FROM omop.condition_occurrence x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM naaccr.group_condition l
              WHERE l.condition_occurrence_id = x.condition_occurrence_id)
  AND (x.condition_type_concept_id <> k.condition_type
       OR x.condition_status_concept_id IS NOT NULL)
UNION ALL
SELECT 'episode_constant_slots', 'structural', COUNT(*)
FROM omop.episode x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM naaccr.person_episode l WHERE l.episode_id = x.episode_id)
  AND (x.episode_concept_id <> k.episode_disease
       OR x.episode_type_concept_id <> k.episode_type
       OR x.episode_source_concept_id IS NULL
       OR x.episode_source_concept_id <> k.unmapped)
UNION ALL
SELECT 'episode_event_constant_slots', 'structural', COUNT(*)
FROM omop.episode_event x CROSS JOIN k
WHERE EXISTS (SELECT 1 FROM naaccr.person_episode l WHERE l.episode_id = x.episode_id)
  AND x.episode_event_field_concept_id NOT IN (
      k.measurement_field, k.observation_field, k.condition_field)
UNION ALL
SELECT 'cdm_source_constant_slots', 'structural', COUNT(*)
FROM omop.cdm_source x CROSS JOIN k
WHERE x.cdm_version_concept_id <> k.cdm_version;

-- structural: a nonzero standard-target slot of a bridge-owned row holds a
-- valid standard concept, in the routed domain where the slot has one.
SELECT 'measurement_target_not_standard' AS check_name, 'structural' AS category,
       COUNT(*) AS actual
FROM omop.measurement x
WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
              WHERE l.event_table = 'measurement' AND l.event_id = x.measurement_id)
  AND x.measurement_concept_id <> 0
  AND NOT EXISTS (
      SELECT 1 FROM omop.concept c
      WHERE c.concept_id = x.measurement_concept_id AND c.standard_concept = 'S'
        AND c.invalid_reason IS NULL AND c.domain_id = 'Measurement')
UNION ALL
SELECT 'observation_target_not_standard', 'structural', COUNT(*)
FROM omop.observation x
WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
              WHERE l.event_table = 'observation' AND l.event_id = x.observation_id)
  AND x.observation_concept_id <> 0
  AND NOT EXISTS (
      SELECT 1 FROM omop.concept c
      WHERE c.concept_id = x.observation_concept_id AND c.standard_concept = 'S'
        AND c.invalid_reason IS NULL AND c.domain_id = 'Observation')
UNION ALL
SELECT 'value_target_not_standard', 'structural',
       (SELECT COUNT(*) FROM omop.measurement x
        WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
                      WHERE l.event_table = 'measurement' AND l.event_id = x.measurement_id)
          AND x.value_as_concept_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM omop.concept c
              WHERE c.concept_id = x.value_as_concept_id AND c.standard_concept = 'S'
                AND c.invalid_reason IS NULL))
       + (SELECT COUNT(*) FROM omop.observation x
          WHERE EXISTS (SELECT 1 FROM naaccr.value_event l
                        WHERE l.event_table = 'observation' AND l.event_id = x.observation_id)
            AND x.value_as_concept_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM omop.concept c
                WHERE c.concept_id = x.value_as_concept_id AND c.standard_concept = 'S'
                  AND c.invalid_reason IS NULL))
UNION ALL
SELECT 'condition_target_not_standard', 'structural', COUNT(*)
FROM omop.condition_occurrence x
WHERE EXISTS (SELECT 1 FROM naaccr.group_condition l
              WHERE l.condition_occurrence_id = x.condition_occurrence_id)
  AND x.condition_concept_id <> 0
  AND NOT EXISTS (
      SELECT 1 FROM omop.concept c
      WHERE c.concept_id = x.condition_concept_id AND c.standard_concept = 'S'
        AND c.invalid_reason IS NULL AND c.domain_id = 'Condition')
UNION ALL
SELECT 'episode_object_not_standard', 'structural', COUNT(*)
FROM omop.episode x
WHERE EXISTS (SELECT 1 FROM naaccr.person_episode l WHERE l.episode_id = x.episode_id)
  AND x.episode_object_concept_id <> 0
  AND NOT EXISTS (
      SELECT 1 FROM omop.concept c
      WHERE c.concept_id = x.episode_object_concept_id AND c.standard_concept = 'S'
        AND c.invalid_reason IS NULL AND c.domain_id = 'Condition');

-- structural: each owned row's route, value target, and slots are the ones the
-- current maps give it, recomputed as scripts 3 and 4 do. A target_domain row
-- carries its item map's target in the table of that target's domain; every
-- other row carries 0 and sits in the table its value shape picks. A value
-- target is 'mapped' only for a nonzero, non-collision (#100) value map target,
-- which is then value_as_concept_id; nothing else carries one. Source slots are
-- the map's source concept, else 0. ecp_code rows never take a map row by
-- numeric prefix, so they route only to default_ecp_code with 0 in both slots.
-- Rerun `bridge` after `maps build`, or these checks report the stale rows.
WITH k AS (
    SELECT concept_id AS unmapped FROM etl.concept_constant WHERE constant_name = 'unmapped'
),
collision AS (
    SELECT DISTINCT item_num, code FROM naaccr.value_code_collision
),
owned AS (
    SELECT l.event_table, l.route, l.value_target, x.measurement_concept_id AS concept_id,
           x.measurement_source_concept_id AS source_concept_id, x.value_as_concept_id,
           v.item_num, v.value_code, v.value_text
    FROM naaccr.value_event l
    JOIN omop.measurement x ON x.measurement_id = l.event_id
    JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
    WHERE l.event_table = 'measurement'
    UNION ALL
    SELECT l.event_table, l.route, l.value_target, x.observation_concept_id,
           x.observation_source_concept_id, x.value_as_concept_id, v.item_num,
           v.value_code, v.value_text
    FROM naaccr.value_event l
    JOIN omop.observation x ON x.observation_id = l.event_id
    JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
    WHERE l.event_table = 'observation'
),
expected AS (
    SELECT o.event_table, o.route, o.value_target, o.concept_id, o.source_concept_id,
           o.value_as_concept_id,
           CASE WHEN o.item_num IS NULL THEN 'default_ecp_code'
                WHEN m.item_num IS NULL THEN 'default_no_map'
                WHEN m.concept_id = 0 THEN 'default_no_target'
                WHEN m.target_domain_id IN ('Measurement', 'Observation') THEN 'target_domain'
                ELSE 'default_other_domain' END AS expected_route,
           CASE WHEN m.concept_id <> 0 AND m.target_domain_id = 'Measurement'
                    THEN 'measurement'
                WHEN m.concept_id <> 0 AND m.target_domain_id = 'Observation'
                    THEN 'observation'
                WHEN NULLIF(TRIM(o.value_text), '') IS NOT NULL THEN 'observation'
                ELSE 'measurement' END AS expected_table,
           CASE WHEN o.value_code IS NULL THEN 'none'
                WHEN c.item_num IS NOT NULL THEN 'collision_suppressed'
                WHEN vm.concept_id <> 0 THEN 'mapped'
                ELSE 'unmapped' END AS expected_value_target,
           m.concept_id AS map_concept_id, m.source_concept_id AS map_source_concept_id,
           vm.concept_id AS value_map_concept_id
    FROM owned o
    LEFT JOIN naaccr.naaccr_concept_map m ON m.item_num = o.item_num
    LEFT JOIN naaccr.naaccr_value_concept_map vm
      ON vm.item_num = o.item_num AND vm.code = o.value_code
    LEFT JOIN collision c ON c.item_num = o.item_num AND c.code = o.value_code
),
mismatched AS (
    SELECT e.event_table
    FROM expected e
    CROSS JOIN k
    WHERE e.route <> e.expected_route
       OR e.event_table <> e.expected_table
       OR e.value_target <> e.expected_value_target
       OR e.concept_id <> CASE WHEN e.expected_route = 'target_domain'
                               THEN e.map_concept_id ELSE k.unmapped END
       OR e.source_concept_id IS NULL
       OR e.source_concept_id <> COALESCE(e.map_source_concept_id, k.unmapped)
       OR (e.expected_value_target = 'mapped'
           AND (e.value_as_concept_id IS NULL
                OR e.value_as_concept_id <> e.value_map_concept_id))
       OR (e.expected_value_target <> 'mapped' AND e.value_as_concept_id IS NOT NULL)
),
site AS (
    SELECT l.condition_target, x.condition_concept_id, x.condition_source_concept_id,
           v.item_num,
           CASE WHEN c.item_num IS NOT NULL THEN 'collision_suppressed'
                WHEN vm.item_num IS NULL THEN 'no_map'
                WHEN vm.concept_id = 0 THEN 'no_target'
                WHEN vm.target_domain_id = 'Condition' THEN 'mapped'
                ELSE 'other_domain' END AS expected_target,
           vm.concept_id AS map_concept_id, vm.source_concept_id AS map_source_concept_id
    FROM naaccr.group_condition l
    JOIN omop.condition_occurrence x
      ON x.condition_occurrence_id = l.condition_occurrence_id
    JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
    LEFT JOIN naaccr.naaccr_value_concept_map vm
      ON vm.item_num = 400 AND vm.code = v.value_code
    LEFT JOIN collision c ON c.item_num = 400 AND c.code = v.value_code
)
SELECT 'measurement_route_mismatch' AS check_name, 'structural' AS category,
       COUNT(*) AS actual
FROM mismatched WHERE event_table = 'measurement'
UNION ALL
SELECT 'observation_route_mismatch', 'structural', COUNT(*)
FROM mismatched WHERE event_table = 'observation'
UNION ALL
SELECT 'condition_target_mismatch', 'structural', COUNT(*)
FROM site s
CROSS JOIN k
WHERE s.item_num IS NULL OR s.item_num <> 400
   OR s.condition_target <> s.expected_target
   OR s.condition_concept_id <> CASE WHEN s.expected_target = 'mapped'
                                     THEN s.map_concept_id ELSE k.unmapped END
   OR s.condition_source_concept_id IS NULL
   OR s.condition_source_concept_id <> COALESCE(s.map_source_concept_id, k.unmapped);

-- provenance: every bridge-owned row reaches an intake.inbound_message.
SELECT 'person_without_message' AS check_name, 'provenance' AS category, COUNT(*) AS actual
FROM omop.person x
JOIN intake.patient i ON i.patient_id = x.person_id
WHERE NOT EXISTS (
    SELECT 1 FROM intake.inbound_message m
    WHERE m.inbound_message_id = i.first_seen_inbound_message_id)
UNION ALL
SELECT 'observation_period_without_source', 'provenance', COUNT(*)
FROM etl.observation_period_derivation d
WHERE (d.start_naaccr_value_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM naaccr.naaccr_value v
          JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
          JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
          WHERE v.naaccr_value_id = d.start_naaccr_value_id AND v.person_id = d.person_id))
   OR (d.end_naaccr_value_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM naaccr.naaccr_value v
          JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
          JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
          WHERE v.naaccr_value_id = d.end_naaccr_value_id AND v.person_id = d.person_id))
   OR (d.start_inbound_envelope_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM intake.inbound_envelope e
          JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
          WHERE e.inbound_envelope_id = d.start_inbound_envelope_id))
   OR (d.end_inbound_envelope_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM intake.inbound_envelope e
          JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
          WHERE e.inbound_envelope_id = d.end_inbound_envelope_id))
UNION ALL
SELECT 'note_report_without_message', 'provenance', COUNT(*)
FROM sdc.note_report l
WHERE NOT EXISTS (
    SELECT 1 FROM sdc.sdc_report r
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id
    JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    WHERE r.sdc_report_id = l.sdc_report_id)
UNION ALL
-- The value reaches its message, and its report is linked to the event's note.
SELECT 'measurement_without_message', 'provenance', COUNT(*)
FROM naaccr.value_event l
JOIN omop.measurement x ON x.measurement_id = l.event_id
WHERE l.event_table = 'measurement' AND NOT EXISTS (
    SELECT 1 FROM naaccr.naaccr_value v
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
    JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    JOIN sdc.note_report n
      ON n.sdc_report_id = v.sdc_report_id AND n.note_id = x.measurement_event_id
    WHERE v.naaccr_value_id = l.naaccr_value_id)
UNION ALL
SELECT 'observation_without_message', 'provenance', COUNT(*)
FROM naaccr.value_event l
JOIN omop.observation x ON x.observation_id = l.event_id
WHERE l.event_table = 'observation' AND NOT EXISTS (
    SELECT 1 FROM naaccr.naaccr_value v
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
    JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    JOIN sdc.note_report n
      ON n.sdc_report_id = v.sdc_report_id AND n.note_id = x.observation_event_id
    WHERE v.naaccr_value_id = l.naaccr_value_id)
UNION ALL
SELECT 'owned_row_person_mismatch', 'provenance',
       (SELECT COUNT(*) FROM naaccr.value_event l
        JOIN omop.measurement x ON x.measurement_id = l.event_id
        WHERE l.event_table = 'measurement' AND NOT EXISTS (
            SELECT 1 FROM omop.note n
            WHERE n.note_id = x.measurement_event_id AND n.person_id = x.person_id))
       + (SELECT COUNT(*) FROM naaccr.value_event l
          JOIN omop.observation x ON x.observation_id = l.event_id
          WHERE l.event_table = 'observation' AND NOT EXISTS (
              SELECT 1 FROM omop.note n
              WHERE n.note_id = x.observation_event_id AND n.person_id = x.person_id))
       + (SELECT COUNT(*) FROM naaccr.group_condition l
          JOIN omop.condition_occurrence x
            ON x.condition_occurrence_id = l.condition_occurrence_id
          JOIN naaccr.report_group g ON g.report_group_id = l.report_group_id
          WHERE x.person_id <> g.person_id)
UNION ALL
SELECT 'condition_without_message', 'provenance', COUNT(*)
FROM naaccr.group_condition l
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.naaccr_value v
    JOIN naaccr.report_version rv
      ON rv.sdc_report_id = v.sdc_report_id AND rv.report_group_id = l.report_group_id
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
    JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    WHERE v.naaccr_value_id = l.naaccr_value_id)
UNION ALL
SELECT 'episode_without_message', 'provenance', COUNT(*)
FROM naaccr.person_episode l
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.naaccr_value v
    JOIN naaccr.value_event ve ON ve.naaccr_value_id = v.naaccr_value_id
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
    JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    WHERE v.person_id = l.person_id AND v.episode_key = l.episode_key);

-- provenance: every episode_event of an owned episode names an owned row of
-- the same (person, episode_key), and that OMOP row belongs to the same person.
WITH k AS (
    SELECT
        MAX(CASE WHEN constant_name = 'field_measurement_measurement_id'
                 THEN concept_id END) AS measurement_field,
        MAX(CASE WHEN constant_name = 'field_observation_observation_id'
                 THEN concept_id END) AS observation_field,
        MAX(CASE WHEN constant_name = 'field_condition_occurrence_id'
                 THEN concept_id END) AS condition_field
    FROM etl.concept_constant
)
SELECT 'episode_event_target_not_owned' AS check_name, 'provenance' AS category,
       COUNT(*) AS actual
FROM omop.episode_event x
JOIN naaccr.person_episode pe ON pe.episode_id = x.episode_id
CROSS JOIN k
WHERE NOT (
    (x.episode_event_field_concept_id = k.measurement_field AND EXISTS (
        SELECT 1 FROM naaccr.value_event l
        JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
        JOIN omop.measurement o ON o.measurement_id = l.event_id AND o.person_id = pe.person_id
        WHERE l.event_table = 'measurement' AND l.event_id = x.event_id
          AND v.person_id = pe.person_id AND v.episode_key = pe.episode_key))
    OR (x.episode_event_field_concept_id = k.observation_field AND EXISTS (
        SELECT 1 FROM naaccr.value_event l
        JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
        JOIN omop.observation o ON o.observation_id = l.event_id AND o.person_id = pe.person_id
        WHERE l.event_table = 'observation' AND l.event_id = x.event_id
          AND v.person_id = pe.person_id AND v.episode_key = pe.episode_key))
    OR (x.episode_event_field_concept_id = k.condition_field AND EXISTS (
        SELECT 1 FROM naaccr.group_condition l
        JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
        JOIN omop.condition_occurrence o
          ON o.condition_occurrence_id = l.condition_occurrence_id
         AND o.person_id = pe.person_id
        WHERE l.condition_occurrence_id = x.event_id
          AND v.person_id = pe.person_id AND v.episode_key = pe.episode_key))
);

-- reconciliation: reports, notes, and the selection between them.
SELECT 'accessioned_report_without_version' AS check_name, 'reconciliation' AS category,
       COUNT(*) AS actual
FROM sdc.sdc_report r
WHERE r.report_accession IS NOT NULL AND r.report_accession <> ''
  AND NOT EXISTS (
      SELECT 1 FROM naaccr.report_version rv WHERE rv.sdc_report_id = r.sdc_report_id)
UNION ALL
SELECT 'selected_report_without_note', 'reconciliation', COUNT(*)
FROM naaccr.report_version rv
WHERE rv.is_selected = 1
  AND NOT EXISTS (SELECT 1 FROM sdc.note_report l WHERE l.sdc_report_id = rv.sdc_report_id)
UNION ALL
SELECT 'note_link_to_unselected_report', 'reconciliation', COUNT(*)
FROM sdc.note_report l
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.report_version rv
    WHERE rv.sdc_report_id = l.sdc_report_id AND rv.is_selected = 1)
UNION ALL
SELECT 'selected_group_note_count', 'reconciliation', COUNT(*)
FROM naaccr.report_group g
WHERE EXISTS (
          SELECT 1 FROM naaccr.report_version rv
          WHERE rv.report_group_id = g.report_group_id AND rv.is_selected = 1)
  AND (SELECT COUNT(DISTINCT l.note_id) FROM sdc.note_report l
       WHERE l.report_group_id = g.report_group_id) <> 1
UNION ALL
SELECT 'patient_without_person', 'reconciliation', COUNT(*)
FROM intake.patient i
WHERE NOT EXISTS (SELECT 1 FROM omop.person p WHERE p.person_id = i.patient_id)
UNION ALL
SELECT 'person_period_count', 'reconciliation', COUNT(*)
FROM intake.patient i
WHERE (SELECT COUNT(*) FROM etl.observation_period_derivation d
       WHERE d.person_id = i.patient_id) <> 1
UNION ALL
SELECT 'cdm_source_row_count', 'reconciliation', ABS(COUNT(*) - 1)
FROM omop.cdm_source;

-- reconciliation: values and the clinical rows, conditions, and episodes they explain.
WITH k AS (
    SELECT
        MAX(CASE WHEN constant_name = 'field_measurement_measurement_id'
                 THEN concept_id END) AS measurement_field,
        MAX(CASE WHEN constant_name = 'field_observation_observation_id'
                 THEN concept_id END) AS observation_field,
        MAX(CASE WHEN constant_name = 'field_condition_occurrence_id'
                 THEN concept_id END) AS condition_field
    FROM etl.concept_constant
),
site_group AS (
    SELECT DISTINCT l.report_group_id
    FROM naaccr.naaccr_value v
    JOIN naaccr.value_event ve ON ve.naaccr_value_id = v.naaccr_value_id
    JOIN sdc.note_report l ON l.sdc_report_id = v.sdc_report_id
    WHERE v.item_num = 400
      AND (NULLIF(TRIM(v.value_code), '') IS NOT NULL
           OR NULLIF(TRIM(v.value_text), '') IS NOT NULL)
)
SELECT 'selected_value_without_event' AS check_name, 'reconciliation' AS category,
       COUNT(*) AS actual
FROM naaccr.naaccr_value v
WHERE EXISTS (
          SELECT 1 FROM naaccr.report_version rv
          WHERE rv.sdc_report_id = v.sdc_report_id AND rv.is_selected = 1)
  AND NOT EXISTS (
          SELECT 1 FROM naaccr.value_event l WHERE l.naaccr_value_id = v.naaccr_value_id)
UNION ALL
-- Historical (unselected) and excluded (accession-less) values never bridge.
SELECT 'event_for_unselected_value', 'reconciliation', COUNT(*)
FROM naaccr.value_event l
JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.report_version rv
    WHERE rv.sdc_report_id = v.sdc_report_id AND rv.is_selected = 1)
UNION ALL
SELECT 'site_group_without_condition', 'reconciliation', COUNT(*)
FROM site_group s
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.group_condition l WHERE l.report_group_id = s.report_group_id)
UNION ALL
SELECT 'condition_without_site_group', 'reconciliation', COUNT(*)
FROM naaccr.group_condition l
WHERE NOT EXISTS (SELECT 1 FROM site_group s WHERE s.report_group_id = l.report_group_id)
UNION ALL
SELECT 'episode_key_without_episode', 'reconciliation', COUNT(*)
FROM (
    SELECT DISTINCT v.person_id, v.episode_key
    FROM naaccr.value_event l
    JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
) x
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.person_episode pe
    WHERE pe.person_id = x.person_id AND pe.episode_key = x.episode_key)
UNION ALL
SELECT 'clinical_row_without_episode_event', 'reconciliation',
       (SELECT COUNT(*) FROM naaccr.value_event l CROSS JOIN k
        WHERE NOT EXISTS (
            SELECT 1 FROM omop.episode_event x
            JOIN naaccr.person_episode pe ON pe.episode_id = x.episode_id
            WHERE x.event_id = l.event_id
              AND x.episode_event_field_concept_id = CASE l.event_table
                  WHEN 'measurement' THEN k.measurement_field
                  ELSE k.observation_field END))
       + (SELECT COUNT(*) FROM naaccr.group_condition l CROSS JOIN k
          WHERE NOT EXISTS (
              SELECT 1 FROM omop.episode_event x
              JOIN naaccr.person_episode pe ON pe.episode_id = x.episode_id
              WHERE x.event_id = l.condition_occurrence_id
                AND x.episode_event_field_concept_id = k.condition_field));

-- coverage: unmapped inputs, each compared with its validate_thresholds.csv row.
SELECT 'unmapped_ckey_values' AS check_name, 'coverage' AS category, COUNT(*) AS actual
FROM naaccr.value_event WHERE route = 'default_ecp_code'
UNION ALL
SELECT 'unmapped_item_values', 'coverage', COUNT(*)
FROM naaccr.value_event WHERE route IN ('default_no_map', 'default_no_target')
UNION ALL
SELECT 'other_domain_item_values', 'coverage', COUNT(*)
FROM naaccr.value_event WHERE route = 'default_other_domain'
UNION ALL
-- Coded item_num values without a value target; CKey codes count above.
SELECT 'unmapped_value_codes', 'coverage', COUNT(*)
FROM naaccr.value_event
WHERE value_target = 'unmapped' AND route <> 'default_ecp_code'
UNION ALL
SELECT 'unmapped_conditions', 'coverage', COUNT(*)
FROM naaccr.group_condition WHERE condition_target IN ('no_map', 'no_target', 'other_domain')
UNION ALL
-- NAACCR-05: an item number absent from the dictionary version it was coded against.
SELECT 'item_numbers_not_in_dictionary', 'coverage', COUNT(*)
FROM naaccr.naaccr_value v
WHERE v.item_num IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM naaccr.naaccr_item i
      WHERE i.dd_version_id = v.dd_version_id AND i.item_num = v.item_num);

-- report: counts printed for review, never failed.
SELECT 'reports_selected' AS check_name, 'report' AS category, COUNT(*) AS actual
FROM naaccr.report_version WHERE is_selected = 1
UNION ALL
SELECT 'reports_historical', 'report', COUNT(*)
FROM naaccr.report_version WHERE is_selected = 0
UNION ALL
-- OMOP-06b: accession-less reports form no group, get no version, and never bridge.
SELECT 'reports_excluded_accessionless', 'report', COUNT(*)
FROM sdc.sdc_report WHERE report_accession IS NULL OR report_accession = ''
UNION ALL
SELECT 'values_historical', 'report', COUNT(*)
FROM naaccr.naaccr_value v
JOIN naaccr.report_version rv ON rv.sdc_report_id = v.sdc_report_id
WHERE rv.is_selected = 0
UNION ALL
SELECT 'values_excluded', 'report', COUNT(*)
FROM naaccr.naaccr_value v
WHERE NOT EXISTS (
    SELECT 1 FROM naaccr.report_version rv WHERE rv.sdc_report_id = v.sdc_report_id)
UNION ALL
SELECT 'content_duplicate_messages', 'report', COUNT(*)
FROM intake.inbound_message WHERE is_content_duplicate = 1
UNION ALL
SELECT 'one_day_observation_periods', 'report', COUNT(*)
FROM omop.observation_period o
WHERE o.observation_period_start_date = o.observation_period_end_date
  AND EXISTS (SELECT 1 FROM etl.observation_period_derivation d
              WHERE d.observation_period_id = o.observation_period_id)
UNION ALL
-- #100: coded values and site codes whose target was withheld.
SELECT 'collision_suppressed_values', 'report',
       (SELECT COUNT(*) FROM naaccr.value_event WHERE value_target = 'collision_suppressed')
       + (SELECT COUNT(*) FROM naaccr.group_condition
          WHERE condition_target = 'collision_suppressed')
UNION ALL
SELECT 'truncated_values', 'report', COUNT(*)
FROM naaccr.value_event WHERE is_truncated = 1
UNION ALL
-- Rows in bridge-written tables that no bridge link names; the bridge keeps them.
SELECT 'unowned_omop_rows', 'report',
       (SELECT COUNT(*) FROM omop.person x
        WHERE NOT EXISTS (SELECT 1 FROM intake.patient i WHERE i.patient_id = x.person_id))
       + (SELECT COUNT(*) FROM omop.observation_period x
          WHERE NOT EXISTS (SELECT 1 FROM etl.observation_period_derivation d
                            WHERE d.observation_period_id = x.observation_period_id))
       + (SELECT COUNT(*) FROM omop.note x
          WHERE NOT EXISTS (SELECT 1 FROM sdc.note_report l WHERE l.note_id = x.note_id))
       + (SELECT COUNT(*) FROM omop.measurement x
          WHERE NOT EXISTS (SELECT 1 FROM naaccr.value_event l
                            WHERE l.event_table = 'measurement'
                              AND l.event_id = x.measurement_id))
       + (SELECT COUNT(*) FROM omop.observation x
          WHERE NOT EXISTS (SELECT 1 FROM naaccr.value_event l
                            WHERE l.event_table = 'observation'
                              AND l.event_id = x.observation_id))
       + (SELECT COUNT(*) FROM omop.condition_occurrence x
          WHERE NOT EXISTS (SELECT 1 FROM naaccr.group_condition l
                            WHERE l.condition_occurrence_id = x.condition_occurrence_id))
       + (SELECT COUNT(*) FROM omop.episode x
          WHERE NOT EXISTS (SELECT 1 FROM naaccr.person_episode l
                            WHERE l.episode_id = x.episode_id))
       + (SELECT COUNT(*) FROM omop.episode_event x
          WHERE NOT EXISTS (SELECT 1 FROM naaccr.person_episode l
                            WHERE l.episode_id = x.episode_id));
