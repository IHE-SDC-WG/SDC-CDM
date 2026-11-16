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
  the pair (#100). Text is cut to the OMOP limits (60 bytes for value_as_string,
  50 for value_source_value and unit_source_value, in the stored varchar
  encoding, never splitting a character) and the link is flagged.

  Date: the value's own date, else its report's day-precision envelope date.
  Never infer a date. A missing date names the value and aborts the entire run.
  Updates occur only when state differs; event IDs stay stable.
*/

DROP TABLE IF EXISTS #bridge_collision;
GO

SELECT DISTINCT item_num, code
INTO #bridge_collision
FROM naaccr.value_code_collision;
GO

DROP TABLE IF EXISTS #bridge_length;
GO

-- Prefix lengths 0..60 for cutting text to a byte limit.
SELECT ones.n + 10 * tens.n AS k
INTO #bridge_length
FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) ones (n)
CROSS JOIN (VALUES (0), (1), (2), (3), (4), (5), (6)) tens (n)
WHERE ones.n + 10 * tens.n <= 60;
GO

DROP TABLE IF EXISTS #bridge_event;
GO

WITH report_day AS (
    SELECT link.sdc_report_id, TRY_CONVERT(date, CONCAT(
            RIGHT(CONCAT('000', JSON_VALUE(e.envelope_json, '$.report.observation_date.y')), 4),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.m')), 2),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.d')), 2)
        ), 23) AS day
    FROM sdc.note_report link
    JOIN sdc.sdc_report r ON r.sdc_report_id = link.sdc_report_id
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id
    WHERE JSON_VALUE(e.envelope_json, '$.report.observation_date.d') IS NOT NULL
),
routed AS (
    SELECT v.naaccr_value_id, v.sdc_report_id, link.note_id, g.person_id,
           v.item_num, v.ecp_code, v.value_code, v.value_num, v.value_text,
           v.value_unit_source,
           COALESCE(v.observation_date, rd.day) AS event_date,
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
    -- Codes match exactly, as in SQLite: no case folding or trailing-space padding.
    LEFT JOIN naaccr.naaccr_value_concept_map vm
      ON vm.item_num = v.item_num AND vm.code = v.value_code
     AND CAST(vm.code AS varbinary(510)) = CAST(v.value_code AS varbinary(510))
    LEFT JOIN #bridge_collision c
      ON c.item_num = v.item_num AND c.code = v.value_code
     AND CAST(c.code AS varbinary(510)) = CAST(v.value_code AS varbinary(510))
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
SELECT s.naaccr_value_id, s.sdc_report_id, s.note_id, s.person_id,
       CAST(s.event_table AS varchar(20)) AS event_table,
       CAST(s.route AS varchar(30)) AS route,
       CAST(CASE WHEN s.value_code IS NULL THEN 'none'
                 WHEN s.is_collision = 1 THEN 'collision_suppressed'
                 WHEN s.value_concept_id <> 0 THEN 'mapped'
                 ELSE 'unmapped' END AS varchar(30)) AS value_target,
       CAST(CASE WHEN s.route = 'target_domain' THEN s.map_concept_id
                 ELSE unmapped.concept_id END AS int) AS concept_id,
       CAST(COALESCE(s.map_source_concept_id, unmapped.concept_id) AS int) AS source_concept_id,
       COALESCE(CAST(s.ecp_code AS varchar(MAX)), CAST(s.item_num AS varchar(MAX))) AS source_value,
       s.event_date,
       CASE WHEN s.event_table = 'measurement' THEN measurement_type.concept_id
            ELSE observation_type.concept_id END AS type_concept_id,
       s.value_num AS value_as_number,
       CAST(CASE WHEN s.value_code IS NOT NULL AND s.is_collision = 0
                      AND s.value_concept_id <> 0
                 THEN s.value_concept_id END AS int) AS value_as_concept_id,
       -- The full source text stays here so the cut below can find a character boundary.
       CASE WHEN s.event_table = 'observation' THEN s.value_text END AS string_source,
       s.value_source, s.value_unit_source AS unit_source,
       CASE WHEN s.event_table = 'observation' THEN CAST(s.value_text AS varchar(MAX))
            END AS value_as_string,
       CAST(s.value_source AS varchar(MAX)) AS value_source_value,
       CAST(s.value_unit_source AS varchar(MAX)) AS unit_source_value,
       CASE WHEN (s.event_table = 'observation'
                  AND DATALENGTH(CAST(s.value_text AS varchar(MAX))) > 60)
                 OR DATALENGTH(CAST(s.value_source AS varchar(MAX))) > 50
                 OR DATALENGTH(CAST(s.value_unit_source AS varchar(MAX))) > 50
            THEN 1 ELSE 0 END AS is_truncated,
       field.concept_id AS field_concept_id,
       -- Keep an owned row only while its value still routes to the same table.
       CASE WHEN old.event_table = s.event_table AND (
                (old.event_table = 'measurement' AND EXISTS (
                    SELECT 1 FROM omop.measurement o WHERE o.measurement_id = old.event_id))
                OR (old.event_table = 'observation' AND EXISTS (
                    SELECT 1 FROM omop.observation o WHERE o.observation_id = old.event_id)))
            THEN old.event_id END AS event_id
INTO #bridge_event
FROM shaped s
LEFT JOIN naaccr.value_event old ON old.naaccr_value_id = s.naaccr_value_id
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
JOIN etl.concept_constant measurement_type
  ON measurement_type.constant_name = 'measurement_type_registry'
JOIN etl.concept_constant observation_type
  ON observation_type.constant_name = 'observation_type_registry'
JOIN etl.concept_constant field ON field.constant_name = 'field_note_note_id';
GO

SELECT CONCAT('naaccr.naaccr_value ', naaccr_value_id, ' (sdc_report ', sdc_report_id,
              '): ', defect) AS message
FROM (
    SELECT naaccr_value_id, sdc_report_id, 0 AS rule_order,
           'no day-precision clinical date' AS defect
    FROM #bridge_event WHERE event_date IS NULL
    UNION ALL
    -- An identifier is never cut; ecp_code fits in 50 characters but may not fit in 50 bytes.
    SELECT naaccr_value_id, sdc_report_id, 1,
           'ecp_code exceeds the 50-byte source value limit'
    FROM #bridge_event WHERE DATALENGTH(source_value) > 50
) failures
ORDER BY naaccr_value_id, rule_order;
GO

-- Cut each over-length value to its longest whole-character prefix within the limit.
UPDATE b
SET value_as_string = (
    SELECT TOP (1) CAST(LEFT(b.string_source, n.k) AS varchar(MAX))
    FROM #bridge_length n
    WHERE DATALENGTH(CAST(LEFT(b.string_source, n.k) AS varchar(MAX))) <= 60
    ORDER BY n.k DESC
)
FROM #bridge_event b
WHERE DATALENGTH(b.value_as_string) > 60;
GO

UPDATE b
SET value_source_value = (
    SELECT TOP (1) CAST(LEFT(b.value_source, n.k) AS varchar(MAX))
    FROM #bridge_length n
    WHERE n.k <= 50 AND DATALENGTH(CAST(LEFT(b.value_source, n.k) AS varchar(MAX))) <= 50
    ORDER BY n.k DESC
)
FROM #bridge_event b
WHERE DATALENGTH(b.value_source_value) > 50;
GO

UPDATE b
SET unit_source_value = (
    SELECT TOP (1) CAST(LEFT(b.unit_source, n.k) AS varchar(MAX))
    FROM #bridge_length n
    WHERE n.k <= 50 AND DATALENGTH(CAST(LEFT(b.unit_source, n.k) AS varchar(MAX))) <= 50
    ORDER BY n.k DESC
)
FROM #bridge_event b
WHERE DATALENGTH(b.unit_source_value) > 50;
GO

-- Remove owned rows whose value is unselected, re-routed, or whose row is gone.
DELETE o
FROM omop.measurement o
JOIN naaccr.value_event l ON l.event_table = 'measurement' AND l.event_id = o.measurement_id
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_event b
    WHERE b.naaccr_value_id = l.naaccr_value_id
      AND b.event_table = l.event_table AND b.event_id = l.event_id
);
GO

DELETE o
FROM omop.observation o
JOIN naaccr.value_event l ON l.event_table = 'observation' AND l.event_id = o.observation_id
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_event b
    WHERE b.naaccr_value_id = l.naaccr_value_id
      AND b.event_table = l.event_table AND b.event_id = l.event_id
);
GO

DELETE l
FROM naaccr.value_event l
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_event b
    WHERE b.naaccr_value_id = l.naaccr_value_id
      AND b.event_table = l.event_table AND b.event_id = l.event_id
);
GO

UPDATE o
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
FROM omop.measurement o
JOIN #bridge_event b ON b.event_table = 'measurement' AND b.event_id = o.measurement_id
WHERE EXISTS (
    -- Text collation ignores some case/spacing changes; compare the stored bytes.
    SELECT o.person_id, o.measurement_concept_id, o.measurement_date, o.measurement_datetime,
        CAST(o.measurement_time AS varbinary(MAX)), o.measurement_type_concept_id,
        o.operator_concept_id, o.value_as_number, o.value_as_concept_id, o.unit_concept_id,
        o.range_low, o.range_high, o.provider_id, o.visit_occurrence_id, o.visit_detail_id,
        CAST(o.measurement_source_value AS varbinary(MAX)), o.measurement_source_concept_id,
        CAST(o.unit_source_value AS varbinary(MAX)), o.unit_source_concept_id,
        CAST(o.value_source_value AS varbinary(MAX)), o.measurement_event_id,
        o.meas_event_field_concept_id
    EXCEPT
    SELECT b.person_id, b.concept_id, b.event_date, NULL, NULL, b.type_concept_id, NULL,
        b.value_as_number, b.value_as_concept_id, NULL, NULL, NULL, NULL, NULL, NULL,
        CAST(b.source_value AS varbinary(MAX)), b.source_concept_id,
        CAST(b.unit_source_value AS varbinary(MAX)), NULL,
        CAST(b.value_source_value AS varbinary(MAX)), b.note_id, b.field_concept_id
);
GO

UPDATE o
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
FROM omop.observation o
JOIN #bridge_event b ON b.event_table = 'observation' AND b.event_id = o.observation_id
WHERE EXISTS (
    -- Text collation ignores some case/spacing changes; compare the stored bytes.
    SELECT o.person_id, o.observation_concept_id, o.observation_date, o.observation_datetime,
        o.observation_type_concept_id, o.value_as_number,
        CAST(o.value_as_string AS varbinary(MAX)), o.value_as_concept_id,
        o.qualifier_concept_id, o.unit_concept_id, o.provider_id, o.visit_occurrence_id,
        o.visit_detail_id, CAST(o.observation_source_value AS varbinary(MAX)),
        o.observation_source_concept_id, CAST(o.unit_source_value AS varbinary(MAX)),
        CAST(o.qualifier_source_value AS varbinary(MAX)),
        CAST(o.value_source_value AS varbinary(MAX)), o.observation_event_id,
        o.obs_event_field_concept_id
    EXCEPT
    SELECT b.person_id, b.concept_id, b.event_date, NULL, b.type_concept_id,
        b.value_as_number, CAST(b.value_as_string AS varbinary(MAX)), b.value_as_concept_id,
        NULL, NULL, NULL, NULL, NULL, CAST(b.source_value AS varbinary(MAX)),
        b.source_concept_id, CAST(b.unit_source_value AS varbinary(MAX)), NULL,
        CAST(b.value_source_value AS varbinary(MAX)), b.note_id, b.field_concept_id
);
GO

UPDATE l
SET route = b.route, value_target = b.value_target, is_truncated = b.is_truncated
FROM naaccr.value_event l
JOIN #bridge_event b ON b.naaccr_value_id = l.naaccr_value_id
WHERE EXISTS (
    SELECT CAST(l.route AS varbinary(60)), CAST(l.value_target AS varbinary(60)),
        CAST(l.is_truncated AS int)
    EXCEPT
    SELECT CAST(b.route AS varbinary(60)), CAST(b.value_target AS varbinary(60)),
        b.is_truncated
);
GO

DROP TABLE IF EXISTS #bridge_new_event;
GO

CREATE TABLE #bridge_new_event (naaccr_value_id INT NOT NULL, event_id INT NOT NULL);
GO

-- OUTPUT INTO records value identity without returning a result set to the runner.
MERGE omop.measurement AS target
USING (SELECT * FROM #bridge_event WHERE event_id IS NULL AND event_table = 'measurement') AS b
ON 1 = 0
WHEN NOT MATCHED THEN
    INSERT (person_id, measurement_concept_id, measurement_date, measurement_datetime,
        measurement_time, measurement_type_concept_id, operator_concept_id, value_as_number,
        value_as_concept_id, unit_concept_id, range_low, range_high, provider_id,
        visit_occurrence_id, visit_detail_id, measurement_source_value,
        measurement_source_concept_id, unit_source_value, unit_source_concept_id,
        value_source_value, measurement_event_id, meas_event_field_concept_id)
    VALUES (b.person_id, b.concept_id, b.event_date, NULL, NULL, b.type_concept_id, NULL,
        b.value_as_number, b.value_as_concept_id, NULL, NULL, NULL, NULL, NULL, NULL,
        b.source_value, b.source_concept_id, b.unit_source_value, NULL,
        b.value_source_value, b.note_id, b.field_concept_id)
OUTPUT b.naaccr_value_id, inserted.measurement_id
    INTO #bridge_new_event (naaccr_value_id, event_id);
GO

MERGE omop.observation AS target
USING (SELECT * FROM #bridge_event WHERE event_id IS NULL AND event_table = 'observation') AS b
ON 1 = 0
WHEN NOT MATCHED THEN
    INSERT (person_id, observation_concept_id, observation_date, observation_datetime,
        observation_type_concept_id, value_as_number, value_as_string, value_as_concept_id,
        qualifier_concept_id, unit_concept_id, provider_id, visit_occurrence_id,
        visit_detail_id, observation_source_value, observation_source_concept_id,
        unit_source_value, qualifier_source_value, value_source_value, observation_event_id,
        obs_event_field_concept_id)
    VALUES (b.person_id, b.concept_id, b.event_date, NULL, b.type_concept_id,
        b.value_as_number, b.value_as_string, b.value_as_concept_id, NULL, NULL, NULL, NULL,
        NULL, b.source_value, b.source_concept_id, b.unit_source_value, NULL,
        b.value_source_value, b.note_id, b.field_concept_id)
OUTPUT b.naaccr_value_id, inserted.observation_id
    INTO #bridge_new_event (naaccr_value_id, event_id);
GO

UPDATE #bridge_event
SET event_id = (SELECT n.event_id FROM #bridge_new_event n
                WHERE n.naaccr_value_id = #bridge_event.naaccr_value_id)
WHERE event_id IS NULL;
GO

INSERT INTO naaccr.value_event (naaccr_value_id, event_table, event_id, route, value_target,
    is_truncated)
SELECT b.naaccr_value_id, b.event_table, b.event_id, b.route, b.value_target, b.is_truncated
FROM #bridge_event b
JOIN #bridge_new_event n ON n.naaccr_value_id = b.naaccr_value_id;
GO
