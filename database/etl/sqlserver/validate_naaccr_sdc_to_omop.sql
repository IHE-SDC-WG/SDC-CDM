/*
  Validation: NAACCR + SDC -> stock OMOP bridge outputs
  Purpose: Confirm once-per-accession notes, source-value measurements, and
           standard OMOP note anchors after the bridge runs.
*/

SET NOCOUNT ON;

DECLARE @FIELD_NOTE_ID BIGINT = 1147289;

-----------------------------
-- 1) Notes expected vs actual
-----------------------------
SELECT 'Notes: expected vs actual' AS section,
       (
         SELECT COUNT(*)
         FROM (
           SELECT DISTINCT sr.person_id, sr.report_accession
           FROM sdc.sdc_report sr
           WHERE NULLIF(sr.report_accession, '') IS NOT NULL
             AND sr.person_id IS NOT NULL
             AND sr.is_duplicate_accession = 0
         ) expected
       ) AS expected_notes,
       (SELECT COUNT(*) FROM omop.note) AS actual_notes;

-----------------------------
-- 2) Missing and duplicate notes
-----------------------------
SELECT TOP 20 'Missing notes' AS section,
       sr.person_id,
       sr.report_accession
FROM sdc.sdc_report sr
LEFT JOIN omop.note n
  ON n.person_id = sr.person_id
 AND n.note_source_value = sr.report_accession
WHERE NULLIF(sr.report_accession, '') IS NOT NULL
  AND sr.person_id IS NOT NULL
  AND sr.is_duplicate_accession = 0
  AND n.note_id IS NULL
ORDER BY sr.person_id, sr.report_accession;

SELECT 'Duplicate notes per accession' AS section,
       n.person_id,
       n.note_source_value,
       COUNT(*) AS note_count
FROM omop.note n
WHERE n.note_source_value IS NOT NULL
GROUP BY n.person_id, n.note_source_value
HAVING COUNT(*) > 1
ORDER BY n.person_id, n.note_source_value;

-----------------------------
-- 3) Measurements expected vs actual
-----------------------------
SELECT 'Measurements: expected vs actual' AS section,
       (
         SELECT COUNT(*)
         FROM naaccr.naaccr_value nv
         JOIN sdc.sdc_report sr
           ON sr.sdc_report_id = nv.sdc_report_id
          AND sr.is_duplicate_accession = 0
          AND sr.person_id = nv.person_id
          AND NULLIF(sr.report_accession, '') IS NOT NULL
         JOIN omop.note n
           ON n.person_id = sr.person_id
          AND n.note_source_value = sr.report_accession
       ) AS expected_measurements,
       (
         SELECT COUNT(*)
         FROM omop.measurement m
         WHERE m.meas_event_field_concept_id = @FIELD_NOTE_ID
       ) AS actual_measurements;

-----------------------------
-- 4) Raw rows that cannot bridge
-----------------------------
SELECT TOP 20 'Unbridgeable raw rows' AS section,
       nv.naaccr_value_id,
       nv.person_id,
       nv.report_accession,
       nv.item_num,
       CASE
         WHEN nv.sdc_report_id IS NULL THEN 'no report link'
         WHEN sr.sdc_report_id IS NULL THEN 'orphan report link'
         WHEN sr.is_duplicate_accession = 1 THEN 'duplicate-import row'
         WHEN sr.person_id IS NULL THEN 'report has no person'
         WHEN sr.person_id <> nv.person_id THEN 'person mismatch'
         WHEN NULLIF(sr.report_accession, '') IS NULL THEN 'no accession'
         WHEN n.note_id IS NULL THEN 'no note anchor'
       END AS reason
FROM naaccr.naaccr_value nv
LEFT JOIN sdc.sdc_report sr
  ON sr.sdc_report_id = nv.sdc_report_id
LEFT JOIN omop.note n
  ON n.person_id = sr.person_id
 AND n.note_source_value = sr.report_accession
WHERE nv.sdc_report_id IS NULL
   OR sr.sdc_report_id IS NULL
   OR sr.is_duplicate_accession = 1
   OR sr.person_id IS NULL
   OR sr.person_id <> nv.person_id
   OR NULLIF(sr.report_accession, '') IS NULL
   OR n.note_id IS NULL
ORDER BY nv.naaccr_value_id;

-----------------------------
-- 5) Measurements missing their standard note anchor
-----------------------------
SELECT 'Measurements missing note anchor' AS section,
       COUNT(*) AS missing_note_anchor
FROM omop.measurement m
LEFT JOIN omop.note n
  ON n.note_id = m.measurement_event_id
WHERE m.meas_event_field_concept_id = @FIELD_NOTE_ID
  AND n.note_id IS NULL;

-----------------------------
-- 6) Spot check for units
-----------------------------
SELECT TOP 20 'Measurement units' AS section,
       m.person_id, m.measurement_source_value, m.value_as_number,
       m.unit_source_value, m.measurement_date
FROM omop.measurement m
WHERE NULLIF(m.unit_source_value, '') IS NOT NULL
ORDER BY m.measurement_date DESC;

-- End validation script
