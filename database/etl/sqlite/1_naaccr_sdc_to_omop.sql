PRAGMA foreign_keys = ON;

/*
  NAACCR + SDC -> stock OMOP bridge (SQLite)

  Values bridge only through their originating non-duplicate report, linked by
  naaccr.naaccr_value.sdc_report_id -> sdc.sdc_report.sdc_report_id. Because each
  imported message writes its own report row and stamps its value rows with that
  report id, a re-imported message's values point at a duplicate-flagged report and
  never bridge -- so duplicate imports cannot double-count regardless of when the
  bridge runs. Reports with a NULL/empty accession, and value rows whose
  sdc_report_id is NULL, never bridge.

  Measurement de-duplication is occurrence-aware: for each report/item/value
  tuple, the bridge inserts only source occurrences beyond the number already
  present in OMOP. This preserves legitimate identical values, keeps re-runs
  idempotent, and repairs partial loads.
*/

WITH report_dates AS (
    SELECT sdc_report_id, MIN(observation_date) AS observation_date
    FROM naaccr.naaccr_value
    GROUP BY sdc_report_id
)
INSERT INTO omop.note (
    person_id, note_date, note_datetime, note_type_concept_id, note_class_concept_id,
    note_title, note_text, encoding_concept_id, language_concept_id,
    provider_id, visit_occurrence_id, note_source_value, note_event_id, note_event_field_concept_id
)
SELECT
    sr.person_id,
    COALESCE(rd.observation_date, DATE('now')),
    COALESCE(rd.observation_date, DATE('now')),
    32817,
    0,
    'Synoptic Report',
    COALESCE(NULLIF(TRIM(sr.report_text), ''), 'Synoptic report'),
    0,
    0,
    sr.provider_id,
    sr.visit_occurrence_id,
    sr.report_accession,
    NULL,
    NULL
FROM sdc.sdc_report sr
LEFT JOIN report_dates rd
    ON rd.sdc_report_id = sr.sdc_report_id
WHERE NULLIF(sr.report_accession, '') IS NOT NULL
  AND sr.is_duplicate_accession = 0
  AND sr.person_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM omop.note n
      WHERE n.person_id = sr.person_id
        AND n.note_source_value = sr.report_accession
  );

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
    32879, -- Registry OMOP Type Concept; seed the Type Concept vocabulary before bridging.
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
    COALESCE(NULLIF(nv.value_text, ''), nv.value_code),
    n.note_id,
    1147289
FROM (
    SELECT
        nv.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                nv.sdc_report_id, nv.item_num, nv.value_code, nv.value_num,
                nv.value_text, nv.value_unit_source
            ORDER BY nv.naaccr_value_id
        ) AS occurrence_n
    FROM naaccr.naaccr_value nv
) nv
JOIN sdc.sdc_report sr
    ON sr.sdc_report_id = nv.sdc_report_id
   AND sr.is_duplicate_accession = 0
   AND sr.person_id = nv.person_id
   AND NULLIF(sr.report_accession, '') IS NOT NULL
JOIN omop.note n
    ON n.person_id = sr.person_id
   AND n.note_source_value = sr.report_accession
LEFT JOIN naaccr.naaccr_concept_map ncm
    ON ncm.item_num = nv.item_num
LEFT JOIN naaccr.naaccr_value_concept_map nvcm
    ON nvcm.item_num = nv.item_num
   AND nvcm.code = COALESCE(nv.value_code, '')
WHERE nv.occurrence_n > (
    SELECT COUNT(*)
    FROM omop.measurement m
    WHERE m.measurement_event_id = n.note_id
      AND m.meas_event_field_concept_id = 1147289
      AND m.measurement_source_value = CAST(nv.item_num AS TEXT)
      AND m.value_as_concept_id IS nvcm.concept_id
      AND m.value_as_number IS nv.value_num
      AND m.value_source_value IS COALESCE(NULLIF(nv.value_text, ''), nv.value_code)
      AND m.unit_source_value IS nv.value_unit_source
);
