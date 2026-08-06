/*
  eCP query examples for the clinical schemas in the five-schema architecture.

  SQLite examples use attached databases named omop, sdc, and naaccr.
  SQL Server uses the same schema-qualified table shape.
*/

-- 1. Reports imported from SDC.
SELECT
  sr.sdc_report_id,
  sr.report_accession,
  sr.report_loinc,
  sr.template_name,
  sr.template_version,
  sr.is_duplicate_accession
FROM sdc.sdc_report sr
ORDER BY sr.created_datetime DESC;

-- 2. Raw NAACCR answers for a report.
SELECT
  nv.report_accession,
  nv.item_num,
  ni.name AS item_name,
  nv.obx_sub_id,
  nv.value_code,
  nv.value_num,
  nv.value_text,
  nv.value_unit_source
FROM naaccr.naaccr_value nv
LEFT JOIN naaccr.naaccr_item ni
  ON ni.item_num = nv.item_num
 AND ni.dd_version_id = COALESCE(
       nv.dd_version_id,
       (SELECT MAX(dd_version_id)
        FROM naaccr.data_dictionary_version
        WHERE is_current = 1)
     )
WHERE nv.report_accession = 'your-accession-here'
ORDER BY nv.naaccr_value_id;

-- 3. OMOP measurements with report accession.
SELECT
  m.measurement_id,
  n.note_source_value AS report_accession,
  m.measurement_source_value AS item_num,
  m.value_as_number,
  m.value_as_concept_id,
  m.value_source_value,
  m.unit_source_value
FROM omop.measurement m
JOIN omop.note n
  ON n.note_id = m.measurement_event_id
ORDER BY m.measurement_id;

-- 4. OMOP measurement back to report metadata and raw NAACCR value.
SELECT
  m.measurement_id,
  n.note_source_value AS report_accession,
  ni.name AS item_name,
  nv.obx_sub_id,
  nv.value_code,
  nv.value_num,
  nv.value_text,
  nv.value_unit_source
FROM omop.measurement m
JOIN omop.note n
  ON n.note_id = m.measurement_event_id
JOIN sdc.sdc_report sr
  ON sr.report_accession = n.note_source_value
 AND sr.person_id = n.person_id
 AND sr.is_duplicate_accession = 0
JOIN naaccr.naaccr_value nv
  ON nv.sdc_report_id = sr.sdc_report_id
 AND CAST(nv.item_num AS TEXT) = m.measurement_source_value
LEFT JOIN naaccr.naaccr_item ni
  ON ni.item_num = nv.item_num
 AND ni.dd_version_id = COALESCE(
       nv.dd_version_id,
       (SELECT MAX(dd_version_id)
        FROM naaccr.data_dictionary_version
        WHERE is_current = 1)
     )
ORDER BY m.measurement_id;

-- 5. Check OMOP remains free of direct SDC linkage columns.
PRAGMA omop.table_info(measurement);
PRAGMA omop.table_info(observation);
