/*
  Bridge script 2: one omop.note per selected naaccr.report_group, with
  sdc.note_report provenance for every selected contributor. Only notes named
  by this link table belong to this bridge; accession is never an identity key.

  Anchor order: synoptic, other non-narrative, narrative; lowest report ID wins
  ties. Text: first non-empty selected narrative, then anchor text, then a
  report-kind placeholder. Date: earliest day-precision anchor value date,
  then its envelope report date. Never infer a date or use today's date.
  Required-data rows name the group and anchor and abort the entire run.
  Updates and link writes occur only when state differs; note IDs stay stable.
*/

DROP TABLE IF EXISTS #bridge_contributor;
GO

SELECT rv.report_group_id, r.sdc_report_id, r.report_loinc,
       r.report_text, r.inbound_envelope_id,
       ROW_NUMBER() OVER (
           PARTITION BY rv.report_group_id ORDER BY
               CASE WHEN r.report_loinc IN ('60568-3', '60569-1', '60571-7') THEN 0
                    WHEN r.report_loinc IN ('33716-2', '33717-0', '35265-8') THEN 2
                    ELSE 1 END,
               r.sdc_report_id
       ) AS anchor_rank
INTO #bridge_contributor
FROM naaccr.report_version rv
JOIN sdc.sdc_report r ON r.sdc_report_id = rv.sdc_report_id
WHERE rv.is_selected = 1;
GO

DROP TABLE IF EXISTS #bridge_note;
GO

WITH narrative AS (
    SELECT report_group_id, report_text,
           ROW_NUMBER() OVER (PARTITION BY report_group_id ORDER BY sdc_report_id) AS n
    FROM #bridge_contributor
    WHERE report_loinc IN ('33716-2', '33717-0', '35265-8')
      AND NULLIF(TRIM(report_text), '') IS NOT NULL
),
value_day AS (
    SELECT v.sdc_report_id, MIN(v.observation_date) AS day
    FROM naaccr.naaccr_value v
    WHERE v.observation_date IS NOT NULL
    GROUP BY v.sdc_report_id
),
report_day AS (
    SELECT a.sdc_report_id, TRY_CONVERT(date, CONCAT(
            RIGHT(CONCAT('000', JSON_VALUE(e.envelope_json, '$.report.observation_date.y')), 4),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.m')), 2),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.d')), 2)
        ), 23) AS day
    FROM #bridge_contributor a
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = a.inbound_envelope_id
    WHERE a.anchor_rank = 1
      AND JSON_VALUE(e.envelope_json, '$.report.observation_date.d') IS NOT NULL
)
SELECT g.report_group_id, g.person_id, a.sdc_report_id AS anchor_id,
       old.note_id,
       COALESCE(vd.day, CASE WHEN rd.day IS NOT NULL THEN rd.day END) AS note_date,
       CAST(COALESCE(n.report_text,
           CASE WHEN NULLIF(TRIM(a.report_text), '') IS NOT NULL THEN a.report_text END,
           CASE WHEN a.report_loinc IN ('33716-2', '33717-0', '35265-8')
                THEN 'Narrative report' ELSE 'Synoptic report' END) AS varchar(MAX)) AS note_text,
       CAST(g.report_accession AS varchar(50)) AS note_source_value,
       LEN(g.report_accession + N'#') - 1 AS accession_length,
       ehr.concept_id AS note_type_concept_id, unmapped.concept_id AS unmapped_concept_id
INTO #bridge_note
FROM #bridge_contributor a
JOIN naaccr.report_group g ON g.report_group_id = a.report_group_id
LEFT JOIN narrative n ON n.report_group_id = g.report_group_id AND n.n = 1
LEFT JOIN value_day vd ON vd.sdc_report_id = a.sdc_report_id
LEFT JOIN report_day rd ON rd.sdc_report_id = a.sdc_report_id
LEFT JOIN sdc.note_report old ON old.report_group_id = g.report_group_id AND old.is_anchor = 1
JOIN etl.concept_constant ehr ON ehr.constant_name = 'note_type_ehr'
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped'
WHERE a.anchor_rank = 1;
GO

SELECT CONCAT('naaccr.report_group ', report_group_id,
              ' (anchor sdc_report ', anchor_id, '): ', defect) AS message
FROM (
    SELECT report_group_id, anchor_id, 0 AS rule_order,
           'no day-precision note date' AS defect
    FROM #bridge_note WHERE note_date IS NULL
    UNION ALL
    SELECT report_group_id, anchor_id, 1,
           'accession is longer than 50 characters'
    FROM #bridge_note WHERE accession_length > 50
) failures
ORDER BY report_group_id, anchor_id, rule_order;
GO

UPDATE o
SET person_id = b.person_id,
    note_date = b.note_date,
    note_datetime = NULL,
    note_type_concept_id = b.note_type_concept_id,
    note_class_concept_id = b.unmapped_concept_id,
    note_title = NULL,
    note_text = b.note_text,
    encoding_concept_id = b.unmapped_concept_id,
    language_concept_id = b.unmapped_concept_id,
    provider_id = NULL,
    visit_occurrence_id = NULL,
    visit_detail_id = NULL,
    note_source_value = b.note_source_value,
    note_event_id = NULL,
    note_event_field_concept_id = NULL
FROM omop.note o
JOIN #bridge_note b ON b.note_id = o.note_id
WHERE EXISTS (
    SELECT o.person_id, o.note_date, o.note_datetime, o.note_type_concept_id,
        o.note_class_concept_id, o.note_title, o.note_text, o.encoding_concept_id,
        o.language_concept_id, o.provider_id, o.visit_occurrence_id, o.visit_detail_id,
        o.note_source_value, o.note_event_id, o.note_event_field_concept_id
    EXCEPT
    SELECT b.person_id, b.note_date, NULL, b.note_type_concept_id, b.unmapped_concept_id, NULL,
        b.note_text, b.unmapped_concept_id, b.unmapped_concept_id, NULL, NULL, NULL,
        b.note_source_value, NULL, NULL
);
GO

DROP TABLE IF EXISTS #bridge_new_note;
GO

CREATE TABLE #bridge_new_note (note_id INT NOT NULL, report_group_id INT NOT NULL);
GO

-- OUTPUT INTO records group identity without returning a result set to the runner.
MERGE omop.note AS target
USING (SELECT * FROM #bridge_note WHERE note_id IS NULL) AS b
ON 1 = 0
WHEN NOT MATCHED THEN
    INSERT (person_id, note_date, note_datetime, note_type_concept_id, note_class_concept_id,
        note_title, note_text, encoding_concept_id, language_concept_id, provider_id,
        visit_occurrence_id, visit_detail_id, note_source_value, note_event_id,
        note_event_field_concept_id)
    VALUES (b.person_id, b.note_date, NULL, b.note_type_concept_id, b.unmapped_concept_id, NULL,
        b.note_text, b.unmapped_concept_id, b.unmapped_concept_id, NULL, NULL, NULL,
        b.note_source_value, NULL, NULL)
OUTPUT inserted.note_id, b.report_group_id INTO #bridge_new_note (note_id, report_group_id);
GO

UPDATE #bridge_note
SET note_id = (SELECT n.note_id FROM #bridge_new_note n
               WHERE n.report_group_id = #bridge_note.report_group_id)
WHERE note_id IS NULL;
GO

DELETE FROM sdc.note_report
WHERE NOT EXISTS (
    SELECT 1 FROM #bridge_contributor c
    WHERE c.report_group_id = sdc.note_report.report_group_id
      AND c.sdc_report_id = sdc.note_report.sdc_report_id
);
GO

-- Clear before setting: SQLite checks the filtered unique index row by row.
UPDATE sdc.note_report SET is_anchor = 0
WHERE is_anchor = 1 AND EXISTS (
    SELECT 1 FROM #bridge_note b
    WHERE b.report_group_id = sdc.note_report.report_group_id
      AND b.anchor_id <> sdc.note_report.sdc_report_id
);
GO

UPDATE sdc.note_report SET is_anchor = 1
WHERE is_anchor = 0 AND EXISTS (
    SELECT 1 FROM #bridge_note b
    WHERE b.report_group_id = sdc.note_report.report_group_id
      AND b.anchor_id = sdc.note_report.sdc_report_id
);
GO

INSERT INTO sdc.note_report (note_id, report_group_id, sdc_report_id, is_anchor)
SELECT b.note_id, b.report_group_id, c.sdc_report_id,
       CASE WHEN c.sdc_report_id = b.anchor_id THEN 1 ELSE 0 END
FROM #bridge_note b
JOIN #bridge_contributor c ON c.report_group_id = b.report_group_id
WHERE NOT EXISTS (
    SELECT 1 FROM sdc.note_report link WHERE link.sdc_report_id = c.sdc_report_id
);
GO
