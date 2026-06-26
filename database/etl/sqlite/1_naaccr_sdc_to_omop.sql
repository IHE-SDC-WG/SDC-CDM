PRAGMA foreign_keys = ON;

INSERT INTO omop.note (
    person_id, note_date, note_datetime, note_type_concept_id, note_class_concept_id,
    note_title, note_text, encoding_concept_id, language_concept_id,
    provider_id, visit_occurrence_id, note_source_value, note_event_id, note_event_field_concept_id
)
SELECT
    sr.person_id,
    COALESCE(MIN(nv.observation_date), DATE('now')),
    COALESCE(MIN(nv.observation_date), DATE('now')),
    32817,
    0,
    'Synoptic Report',
    COALESCE(sr.report_text, 'Synoptic report'),
    0,
    0,
    sr.provider_id,
    sr.visit_occurrence_id,
    sr.report_accession,
    NULL,
    NULL
FROM sdc.sdc_report sr
LEFT JOIN naaccr.naaccr_value nv
    ON nv.report_accession = sr.report_accession
WHERE sr.report_accession IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM omop.note n
      WHERE n.person_id = sr.person_id
        AND n.note_source_value = sr.report_accession
  )
GROUP BY
    sr.sdc_report_id, sr.person_id, sr.report_text, sr.provider_id,
    sr.visit_occurrence_id, sr.report_accession;

INSERT INTO omop.measurement (
    person_id, measurement_concept_id, measurement_date, measurement_datetime,
    measurement_type_concept_id, operator_concept_id, value_as_number, value_as_concept_id,
    unit_concept_id, range_low, range_high, provider_id, visit_occurrence_id, visit_detail_id,
    measurement_source_value, measurement_source_concept_id, unit_source_value,
    unit_source_concept_id, value_source_value, measurement_event_id, meas_event_field_concept_id
)
SELECT
    nv.person_id,
    COALESCE(ncm.concept_id, 0),
    COALESCE(nv.observation_date, DATE('now')),
    COALESCE(nv.observation_date, DATE('now')),
    0,
    NULL,
    nv.value_num,
    nvcm.concept_id,
    NULL,
    NULL,
    NULL,
    sr.provider_id,
    sr.visit_occurrence_id,
    NULL,
    CAST(nv.item_num AS TEXT),
    ncm.concept_id,
    nv.value_unit_source,
    NULL,
    nv.value_code,
    n.note_id,
    1147289
FROM naaccr.naaccr_value nv
JOIN sdc.sdc_report sr
    ON sr.report_accession = nv.report_accession
JOIN omop.note n
    ON n.person_id = nv.person_id
   AND n.note_source_value = nv.report_accession
LEFT JOIN naaccr.naaccr_concept_map ncm
    ON ncm.item_num = nv.item_num
LEFT JOIN naaccr.naaccr_value_concept_map nvcm
    ON nvcm.item_num = nv.item_num
   AND nvcm.code = COALESCE(nv.value_code, '');
