/*
  Bridge script 3: one omop.measurement or omop.observation row per
  naaccr.naaccr_value of a selected report (a report with an sdc.note_report
  link), with naaccr.value_event provenance. Only clinical rows named by this
  link table belong to this bridge; each source occurrence has its own link, so
  repeated identical answers stay separate rows and an unchanged rerun is a no-op.

  Routing (route): an item_num map row whose standard target is in the
  Measurement or Observation domain goes to that table (target_domain). Every
  other row keeps 0 in *_concept_id and goes to observation when it carries
  non-blank value_text, otherwise to measurement: ecp_code only
  (default_ecp_code), item_num with no map row (default_no_map), a map row with
  no standard target (default_no_target), or a target in another domain
  (default_other_domain). Maps join on item_num only; ecp_code is never parsed.

  Values: value_num -> value_as_number; value_unit_source -> unit_source_value
  (unit_concept_id NULL); value_text -> observation.value_as_string;
  value_code, else value_text -> value_source_value. value_as_concept_id is the
  nonzero (item_num, value_code) target unless naaccr.value_code_collision lists
  the pair (#100). Text is cut to the OMOP limits (60 for value_as_string, 50
  for value_source_value and unit_source_value) and the link is flagged.

  Date: the value's own day-precision date, else its report's day-precision
  envelope date. Never infer a date. A missing date names the value and aborts
  the entire run. Updates occur only when state differs; event IDs stay stable.
*/

DROP TABLE IF EXISTS temp.bridge_collision;

CREATE TEMP TABLE bridge_collision AS
SELECT DISTINCT item_num, code FROM naaccr.value_code_collision;

DROP TABLE IF EXISTS temp.bridge_event;

CREATE TEMP TABLE bridge_event AS
WITH report_day AS (
    SELECT link.sdc_report_id, printf('%04d-%02d-%02d',
               json_extract(e.envelope_json, '$.report.observation_date.y'),
               json_extract(e.envelope_json, '$.report.observation_date.m'),
               json_extract(e.envelope_json, '$.report.observation_date.d')) AS day
    FROM sdc.note_report link
    JOIN sdc.sdc_report r ON r.sdc_report_id = link.sdc_report_id
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id
    WHERE json_extract(e.envelope_json, '$.report.observation_date.d') IS NOT NULL
),
routed AS (
    SELECT v.naaccr_value_id, v.sdc_report_id, link.note_id, g.person_id,
           v.item_num, v.ecp_code, v.value_code, v.value_num, v.value_text,
           v.value_unit_source,
           COALESCE(
               CASE WHEN date(v.observation_date) = v.observation_date THEN v.observation_date END,
               CASE WHEN date(rd.day) = rd.day THEN rd.day END) AS event_date,
           CASE WHEN v.item_num IS NULL THEN 'default_ecp_code'
                WHEN m.item_num IS NULL THEN 'default_no_map'
                WHEN m.concept_id = 0 THEN 'default_no_target'
                WHEN m.target_domain_id IN ('Measurement', 'Observation') THEN 'target_domain'
                ELSE 'default_other_domain' END AS route,
           m.concept_id AS map_concept_id, m.source_concept_id AS map_source_concept_id,
           m.target_domain_id, vm.concept_id AS value_concept_id,
           CASE WHEN c.item_num IS NOT NULL THEN 1 ELSE 0 END AS is_collision
    FROM naaccr.naaccr_value v
    JOIN sdc.note_report link ON link.sdc_report_id = v.sdc_report_id
    JOIN naaccr.report_group g ON g.report_group_id = link.report_group_id
    LEFT JOIN report_day rd ON rd.sdc_report_id = v.sdc_report_id
    LEFT JOIN naaccr.naaccr_concept_map m ON m.item_num = v.item_num
    LEFT JOIN naaccr.naaccr_value_concept_map vm
      ON vm.item_num = v.item_num AND vm.code = v.value_code
    LEFT JOIN temp.bridge_collision c ON c.item_num = v.item_num AND c.code = v.value_code
),
shaped AS (
    SELECT r.*,
           CASE WHEN r.route = 'target_domain' AND r.target_domain_id = 'Measurement'
                    THEN 'measurement'
                WHEN r.route = 'target_domain' THEN 'observation'
                WHEN NULLIF(TRIM(r.value_text), '') IS NOT NULL THEN 'observation'
                ELSE 'measurement' END AS event_table,
           COALESCE(r.value_code, r.value_text) AS value_source
    FROM routed r
)
SELECT s.naaccr_value_id, s.sdc_report_id, s.note_id, s.person_id, s.event_table, s.route,
       CASE WHEN s.value_code IS NULL THEN 'none'
            WHEN s.is_collision = 1 THEN 'collision_suppressed'
            WHEN s.value_concept_id <> 0 THEN 'mapped'
            ELSE 'unmapped' END AS value_target,
       CASE WHEN s.route = 'target_domain' THEN s.map_concept_id
            ELSE unmapped.concept_id END AS concept_id,
       COALESCE(s.map_source_concept_id, unmapped.concept_id) AS source_concept_id,
       COALESCE(s.ecp_code, CAST(s.item_num AS TEXT)) AS source_value,
       s.event_date,
       CASE WHEN s.event_table = 'measurement' THEN measurement_type.concept_id
            ELSE observation_type.concept_id END AS type_concept_id,
       s.value_num AS value_as_number,
       CASE WHEN s.value_code IS NOT NULL AND s.is_collision = 0 AND s.value_concept_id <> 0
            THEN s.value_concept_id END AS value_as_concept_id,
       CASE WHEN s.event_table = 'observation' THEN substr(s.value_text, 1, 60)
            END AS value_as_string,
       substr(s.value_source, 1, 50) AS value_source_value,
       substr(s.value_unit_source, 1, 50) AS unit_source_value,
       CASE WHEN (s.event_table = 'observation' AND length(s.value_text) > 60)
                 OR length(s.value_source) > 50 OR length(s.value_unit_source) > 50
            THEN 1 ELSE 0 END AS is_truncated,
       field.concept_id AS field_concept_id,
       -- Keep an owned row only while its value still routes to the same table.
       CASE WHEN old.event_table = s.event_table AND (
                (old.event_table = 'measurement' AND EXISTS (
                    SELECT 1 FROM omop.measurement o WHERE o.measurement_id = old.event_id))
                OR (old.event_table = 'observation' AND EXISTS (
                    SELECT 1 FROM omop.observation o WHERE o.observation_id = old.event_id)))
            THEN old.event_id END AS event_id
FROM shaped s
LEFT JOIN naaccr.value_event old ON old.naaccr_value_id = s.naaccr_value_id
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant measurement_type
  ON measurement_type.constant_name = 'measurement_type_registry'
JOIN etl.concept_constant observation_type
  ON observation_type.constant_name = 'observation_type_registry'
JOIN etl.concept_constant field ON field.constant_name = 'field_note_note_id';

SELECT 'naaccr.naaccr_value ' || naaccr_value_id || ' (sdc_report ' || sdc_report_id
       || '): no day-precision clinical date' AS message
FROM temp.bridge_event
WHERE event_date IS NULL
ORDER BY naaccr_value_id;

-- Remove owned rows whose value is unselected, re-routed, or whose row is gone.
DELETE FROM omop.measurement
WHERE measurement_id IN (
    SELECT l.event_id FROM naaccr.value_event l
    WHERE l.event_table = 'measurement' AND NOT EXISTS (
        SELECT 1 FROM temp.bridge_event b
        WHERE b.naaccr_value_id = l.naaccr_value_id
          AND b.event_table = l.event_table AND b.event_id = l.event_id
    )
);

DELETE FROM omop.observation
WHERE observation_id IN (
    SELECT l.event_id FROM naaccr.value_event l
    WHERE l.event_table = 'observation' AND NOT EXISTS (
        SELECT 1 FROM temp.bridge_event b
        WHERE b.naaccr_value_id = l.naaccr_value_id
          AND b.event_table = l.event_table AND b.event_id = l.event_id
    )
);

DELETE FROM naaccr.value_event
WHERE NOT EXISTS (
    SELECT 1 FROM temp.bridge_event b
    WHERE b.naaccr_value_id = naaccr.value_event.naaccr_value_id
      AND b.event_table = naaccr.value_event.event_table
      AND b.event_id = naaccr.value_event.event_id
);

UPDATE omop.measurement AS o
SET person_id = b.person_id,
    measurement_concept_id = b.concept_id,
    measurement_date = b.event_date,
    measurement_datetime = NULL,
    measurement_time = NULL,
    measurement_type_concept_id = b.type_concept_id,
    operator_concept_id = NULL,
    value_as_number = b.value_as_number,
    value_as_concept_id = b.value_as_concept_id,
    unit_concept_id = NULL,
    range_low = NULL,
    range_high = NULL,
    provider_id = NULL,
    visit_occurrence_id = NULL,
    visit_detail_id = NULL,
    measurement_source_value = b.source_value,
    measurement_source_concept_id = b.source_concept_id,
    unit_source_value = b.unit_source_value,
    unit_source_concept_id = NULL,
    value_source_value = b.value_source_value,
    measurement_event_id = b.note_id,
    meas_event_field_concept_id = b.field_concept_id
FROM temp.bridge_event b
WHERE b.event_table = 'measurement' AND o.measurement_id = b.event_id AND (
    o.person_id IS NOT b.person_id
    OR o.measurement_concept_id IS NOT b.concept_id
    OR o.measurement_date IS NOT b.event_date
    OR o.measurement_datetime IS NOT NULL
    OR o.measurement_time IS NOT NULL
    OR o.measurement_type_concept_id IS NOT b.type_concept_id
    OR o.operator_concept_id IS NOT NULL
    OR o.value_as_number IS NOT b.value_as_number
    OR o.value_as_concept_id IS NOT b.value_as_concept_id
    OR o.unit_concept_id IS NOT NULL
    OR o.range_low IS NOT NULL
    OR o.range_high IS NOT NULL
    OR o.provider_id IS NOT NULL
    OR o.visit_occurrence_id IS NOT NULL
    OR o.visit_detail_id IS NOT NULL
    OR o.measurement_source_value IS NOT b.source_value
    OR o.measurement_source_concept_id IS NOT b.source_concept_id
    OR o.unit_source_value IS NOT b.unit_source_value
    OR o.unit_source_concept_id IS NOT NULL
    OR o.value_source_value IS NOT b.value_source_value
    OR o.measurement_event_id IS NOT b.note_id
    OR o.meas_event_field_concept_id IS NOT b.field_concept_id
);

UPDATE omop.observation AS o
SET person_id = b.person_id,
    observation_concept_id = b.concept_id,
    observation_date = b.event_date,
    observation_datetime = NULL,
    observation_type_concept_id = b.type_concept_id,
    value_as_number = b.value_as_number,
    value_as_string = b.value_as_string,
    value_as_concept_id = b.value_as_concept_id,
    qualifier_concept_id = NULL,
    unit_concept_id = NULL,
    provider_id = NULL,
    visit_occurrence_id = NULL,
    visit_detail_id = NULL,
    observation_source_value = b.source_value,
    observation_source_concept_id = b.source_concept_id,
    unit_source_value = b.unit_source_value,
    qualifier_source_value = NULL,
    value_source_value = b.value_source_value,
    observation_event_id = b.note_id,
    obs_event_field_concept_id = b.field_concept_id
FROM temp.bridge_event b
WHERE b.event_table = 'observation' AND o.observation_id = b.event_id AND (
    o.person_id IS NOT b.person_id
    OR o.observation_concept_id IS NOT b.concept_id
    OR o.observation_date IS NOT b.event_date
    OR o.observation_datetime IS NOT NULL
    OR o.observation_type_concept_id IS NOT b.type_concept_id
    OR o.value_as_number IS NOT b.value_as_number
    OR o.value_as_string IS NOT b.value_as_string
    OR o.value_as_concept_id IS NOT b.value_as_concept_id
    OR o.qualifier_concept_id IS NOT NULL
    OR o.unit_concept_id IS NOT NULL
    OR o.provider_id IS NOT NULL
    OR o.visit_occurrence_id IS NOT NULL
    OR o.visit_detail_id IS NOT NULL
    OR o.observation_source_value IS NOT b.source_value
    OR o.observation_source_concept_id IS NOT b.source_concept_id
    OR o.unit_source_value IS NOT b.unit_source_value
    OR o.qualifier_source_value IS NOT NULL
    OR o.value_source_value IS NOT b.value_source_value
    OR o.observation_event_id IS NOT b.note_id
    OR o.obs_event_field_concept_id IS NOT b.field_concept_id
);

UPDATE naaccr.value_event AS l
SET route = b.route, value_target = b.value_target, is_truncated = b.is_truncated
FROM temp.bridge_event b
WHERE b.naaccr_value_id = l.naaccr_value_id AND (
    l.route IS NOT b.route
    OR l.value_target IS NOT b.value_target
    OR l.is_truncated IS NOT b.is_truncated
);

DROP TABLE IF EXISTS temp.bridge_new_event;

-- Stage explicit IDs: RETURNING would be treated as a required-data failure.
CREATE TEMP TABLE bridge_new_event AS
SELECT naaccr_value_id,
       CASE WHEN event_table = 'measurement'
            THEN (SELECT COALESCE(MAX(measurement_id), 0) FROM omop.measurement)
            ELSE (SELECT COALESCE(MAX(observation_id), 0) FROM omop.observation) END
           + ROW_NUMBER() OVER (PARTITION BY event_table ORDER BY naaccr_value_id) AS event_id
FROM temp.bridge_event WHERE event_id IS NULL;

UPDATE temp.bridge_event
SET event_id = (SELECT n.event_id FROM temp.bridge_new_event n
                WHERE n.naaccr_value_id = temp.bridge_event.naaccr_value_id)
WHERE event_id IS NULL;

INSERT INTO omop.measurement (measurement_id, person_id, measurement_concept_id,
    measurement_date, measurement_datetime, measurement_time, measurement_type_concept_id,
    operator_concept_id, value_as_number, value_as_concept_id, unit_concept_id, range_low,
    range_high, provider_id, visit_occurrence_id, visit_detail_id, measurement_source_value,
    measurement_source_concept_id, unit_source_value, unit_source_concept_id,
    value_source_value, measurement_event_id, meas_event_field_concept_id)
SELECT b.event_id, b.person_id, b.concept_id, b.event_date, NULL, NULL, b.type_concept_id,
    NULL, b.value_as_number, b.value_as_concept_id, NULL, NULL, NULL, NULL, NULL, NULL,
    b.source_value, b.source_concept_id, b.unit_source_value, NULL, b.value_source_value,
    b.note_id, b.field_concept_id
FROM temp.bridge_event b
JOIN temp.bridge_new_event n ON n.naaccr_value_id = b.naaccr_value_id
WHERE b.event_table = 'measurement'
ORDER BY b.naaccr_value_id;

INSERT INTO omop.observation (observation_id, person_id, observation_concept_id,
    observation_date, observation_datetime, observation_type_concept_id, value_as_number,
    value_as_string, value_as_concept_id, qualifier_concept_id, unit_concept_id, provider_id,
    visit_occurrence_id, visit_detail_id, observation_source_value,
    observation_source_concept_id, unit_source_value, qualifier_source_value,
    value_source_value, observation_event_id, obs_event_field_concept_id)
SELECT b.event_id, b.person_id, b.concept_id, b.event_date, NULL, b.type_concept_id,
    b.value_as_number, b.value_as_string, b.value_as_concept_id, NULL, NULL, NULL, NULL, NULL,
    b.source_value, b.source_concept_id, b.unit_source_value, NULL, b.value_source_value,
    b.note_id, b.field_concept_id
FROM temp.bridge_event b
JOIN temp.bridge_new_event n ON n.naaccr_value_id = b.naaccr_value_id
WHERE b.event_table = 'observation'
ORDER BY b.naaccr_value_id;

INSERT INTO naaccr.value_event (naaccr_value_id, event_table, event_id, route, value_target,
    is_truncated)
SELECT b.naaccr_value_id, b.event_table, b.event_id, b.route, b.value_target, b.is_truncated
FROM temp.bridge_event b
JOIN temp.bridge_new_event n ON n.naaccr_value_id = b.naaccr_value_id
ORDER BY b.naaccr_value_id;
