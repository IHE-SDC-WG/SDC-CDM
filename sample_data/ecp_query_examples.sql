-- ECP Data Query Examples
-- This file contains example SQL queries for the OMOP SDC MVP ECP data

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
    m.value_as_number,
    m.value_as_string,
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

-- 10. Get all template instances with their measurement counts
SELECT 
    ecp.template_name,
    ecp.template_version,
    COUNT(DISTINCT ecp.sdc_template_instance_ecp_id) as instance_count,
    COUNT(m.measurement_id) as total_measurements,
    AVG(measurement_count) as avg_measurements_per_instance
FROM sdc_template_instance_ecp ecp
LEFT JOIN (
    SELECT sdc_template_instance_guid, COUNT(*) as measurement_count
    FROM measurement 
    WHERE sdc_template_instance_guid IS NOT NULL
    GROUP BY sdc_template_instance_guid
) m ON ecp.template_instance_guid = m.sdc_template_instance_guid
GROUP BY ecp.template_name, ecp.template_version
ORDER BY instance_count DESC;
