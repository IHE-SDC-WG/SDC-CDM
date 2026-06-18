-- ECP Data Query Examples
-- eCP synoptic Q&A defaults to MEASUREMENT (qualitatively/quantitatively derived).
-- See ECP_OMOP_MAPPING.md. These examples use the PostgreSQL-style denormalized sdc_*
-- columns on measurement; SQLite links via sdc_form_answer.

-- 1. How many lung cancer patients were diagnosed in California in 2024?
SELECT
    COUNT(DISTINCT m.person_id) as patient_count
FROM measurement m
JOIN person p ON m.person_id = p.person_id
WHERE m.sdc_question_identifier LIKE '%820603%'  -- Procedure field
  AND m.sdc_response_value LIKE '%lung%'
  AND m.measurement_date >= '2024-01-01'
  AND m.measurement_date <= '2024-12-31';

-- 2. Show all ECP data for a specific template version
SELECT
    m.measurement_id,
    m.person_id,
    m.sdc_question_identifier,
    m.sdc_question_text,
    m.sdc_response_value,
    m.sdc_response_type,
    m.sdc_units,
    m.sdc_datatype,
    m.sdc_order,
    m.measurement_date
FROM measurement m
WHERE m.sdc_template_version = '3.007.011.1000043'
ORDER BY m.sdc_order;

-- 3. Find patients with specific tumor characteristics
SELECT
    p.person_id,
    p.person_source_value,
    m_tumor.sdc_response_value as tumor_size,
    m_tumor.sdc_units as tumor_size_units,
    m_grade.sdc_response_value as tumor_grade,
    m_margin.sdc_response_value as margin_status
FROM person p
JOIN measurement m_tumor ON p.person_id = m_tumor.person_id
LEFT JOIN measurement m_grade ON p.person_id = m_grade.person_id
LEFT JOIN measurement m_margin ON p.person_id = m_margin.person_id
WHERE m_tumor.sdc_question_identifier LIKE '%2129%'  -- Tumor Size
  AND m_grade.sdc_question_identifier LIKE '%820395%'  -- Tumor Grade
  AND m_margin.sdc_question_identifier LIKE '%2153%'   -- Margin Status
  AND m_tumor.sdc_template_instance_guid = m_grade.sdc_template_instance_guid
  AND m_tumor.sdc_template_instance_guid = m_margin.sdc_template_instance_guid;

-- 4. Get all template instances for a specific template
SELECT
    ecp.sdc_template_instance_ecp_id,
    ecp.template_name,
    ecp.template_version,
    ecp.template_instance_guid,
    ecp.tumor_site,
    ecp.procedure_type,
    ecp.specimen_laterality,
    ecp.created_datetime,
    COUNT(m.measurement_id) as measurement_count
FROM sdc_template_instance_ecp ecp
LEFT JOIN measurement m ON ecp.template_instance_guid = m.sdc_template_instance_guid
WHERE ecp.template_name LIKE '%ADRENAL%'
GROUP BY ecp.sdc_template_instance_ecp_id
ORDER BY ecp.created_datetime DESC;

-- 5. Query both vanilla OMOP fields and SDC-specific columns
SELECT
    p.person_id,
    p.person_source_value,
    p.year_of_birth,
    p.gender_source_value,
    m.measurement_date,
    m.measurement_source_value,
    m.value_as_number,    -- numeric answers (e.g. tumor size, organ weight)
    m.value_as_concept_id, -- coded answer concept (when vocabulary mapped)
    m.value_source_value,  -- raw / human-readable answer
    m.unit_source_value,
    -- SDC-specific fields
    m.sdc_template_instance_guid,
    m.sdc_question_identifier,
    m.sdc_question_text,
    m.sdc_response_value,
    m.sdc_response_type,
    m.sdc_template_version,
    m.sdc_units,
    m.sdc_datatype
FROM person p
JOIN measurement m ON p.person_id = m.person_id
WHERE m.sdc_template_instance_guid IS NOT NULL
  AND m.measurement_date >= '2024-01-01'
ORDER BY p.person_id, m.sdc_order;

-- 6. Find all measurements for a specific template instance
SELECT
    m.sdc_question_identifier,
    m.sdc_question_text,
    m.sdc_response_value,
    m.sdc_response_type,
    m.sdc_units,
    m.sdc_datatype,
    m.sdc_order,
    m.measurement_date
FROM measurement m
WHERE m.sdc_template_instance_guid = 'your-template-instance-guid-here'
ORDER BY m.sdc_order;

-- 7. Get template metadata for a specific instance
SELECT
    ecp.template_name,
    ecp.template_version,
    ecp.report_template_source,
    ecp.report_template_id,
    ecp.report_template_version_id,
    ecp.report_accession,
    ecp.report_loinc,
    ecp.tumor_site,
    ecp.procedure_type,
    ecp.specimen_laterality,
    ecp.created_datetime
FROM sdc_template_instance_ecp ecp
WHERE ecp.template_instance_guid = 'your-template-instance-guid-here';

-- 8. Count measurements by response type
SELECT
    m.sdc_response_type,
    COUNT(*) as count
FROM measurement m
WHERE m.sdc_template_instance_guid IS NOT NULL
GROUP BY m.sdc_response_type
ORDER BY count DESC;

-- 9. Find patients with adrenal gland procedures
SELECT
    p.person_id,
    p.person_source_value,
    ecp.template_name,
    ecp.procedure_type,
    ecp.tumor_site,
    ecp.specimen_laterality,
    ecp.created_datetime
FROM person p
JOIN sdc_template_instance_ecp ecp ON p.person_id = ecp.person_id
WHERE ecp.template_name LIKE '%ADRENAL%'
  AND ecp.procedure_type IS NOT NULL
ORDER BY ecp.created_datetime DESC;

-- 10. Retrieve a whole synoptic report via its NOTE anchor.
--     Every measurement from a report shares one measurement_event_id = note.note_id.
SELECT
    n.note_id,
    n.note_source_value AS report_accession,
    m.sdc_question_text,
    m.value_as_number,
    m.value_as_concept_id,
    m.value_source_value,
    m.sdc_order
FROM note n
JOIN measurement m
  ON m.measurement_event_id = n.note_id
 AND m.meas_event_field_concept_id = 1147289   -- note.note_id field concept
ORDER BY n.note_id, m.sdc_order;

-- 11. Flagged duplicate synoptic reports (same OBR accession re-imported).
--     Re-imports are never deduped; they are inserted and flagged.
SELECT
    ecp.sdc_template_instance_ecp_id,
    ecp.report_accession,
    ecp.first_seen_ecp_id,
    ecp.created_datetime
FROM sdc_template_instance_ecp ecp
WHERE ecp.is_duplicate_accession = 1
ORDER BY ecp.report_accession, ecp.created_datetime;
