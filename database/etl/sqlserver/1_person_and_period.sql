/*
  Bridge script 1 (SQL Server): omop.person, omop.observation_period, omop.cdm_source

  Only `sdc-cdm bridge` runs this file, inside its data transaction, after it has
  checked the constants, seed, vocabulary version, and concept map this script
  reads and staged the seed row in etl.cdm_source_seed. A batch that returns
  rows is a required-data check: each row names one offending source row, and
  any row fails and rolls back the run. Each GO batch holds one statement.

  person: one row per intake.patient, with person_id = patient_id. Birth month
  and day stay NULL when the source omits them. Source gender M or F resolves
  through etl.concept_constant; any other value gets the unmapped concept.

  observation_period: one unpadded period per person, built from the person's
  selected report versions only. When those reports carry a day-precision
  NAACCR item 390 (date of diagnosis) and item 1750 (date of last contact), the
  period runs from the earliest 390 to the latest 1750. Otherwise it spans the
  earliest and latest day-precision clinical date: each
  naaccr_value.observation_date, plus the envelope report.observation_date of
  each selected report that has no naaccr_value rows (narrative reports keep
  their date only there). Partial dates never set a boundary, and no date is
  ever inferred or taken from today. etl.observation_period_derivation records
  the rule and the naaccr_value row or inbound envelope that set each boundary.

  Every write updates changed rows or inserts missing ones, so an unchanged
  rerun writes nothing. EXISTS (... EXCEPT ...) is the NULL-safe "differs" test.
*/

DROP TABLE IF EXISTS #bridge_person;
GO

SELECT
    p.patient_id AS person_id,
    CASE UPPER(LTRIM(RTRIM(p.gender_source_value)))
        WHEN 'M' THEN male.concept_id
        WHEN 'F' THEN female.concept_id
        ELSE unmapped.concept_id
    END AS gender_concept_id,
    p.birth_year AS year_of_birth,
    p.birth_month AS month_of_birth,
    p.birth_day AS day_of_birth,
    unmapped.concept_id AS unmapped_concept_id,
    p.person_source_value,
    p.gender_source_value
INTO #bridge_person
FROM intake.patient p
JOIN etl.concept_constant male ON male.constant_name = 'gender_male'
JOIN etl.concept_constant female ON female.constant_name = 'gender_female'
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped';
GO

DROP TABLE IF EXISTS #bridge_period;
GO

WITH selected_value AS (
    SELECT
        v.naaccr_value_id,
        v.person_id,
        v.item_num,
        v.observation_date,
        LTRIM(RTRIM(COALESCE(NULLIF(LTRIM(RTRIM(v.value_code)), ''), v.value_text)))
            AS item_value
    FROM naaccr.naaccr_value v
    JOIN naaccr.report_version rv
        ON rv.sdc_report_id = v.sdc_report_id
       AND rv.is_selected = 1
),
naaccr_day AS (
    SELECT
        naaccr_value_id,
        person_id,
        item_num,
        TRY_CONVERT(date, item_value, 112) AS day
    FROM selected_value
    WHERE item_num IN (390, 1750)
      AND LEN(item_value) = 8
      AND item_value NOT LIKE '%[^0-9]%'
),
diagnosis AS (
    SELECT person_id, day, naaccr_value_id,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY day, naaccr_value_id) AS n
    FROM naaccr_day
    WHERE item_num = 390 AND day IS NOT NULL
),
last_contact AS (
    SELECT person_id, day, naaccr_value_id,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY day DESC, naaccr_value_id) AS n
    FROM naaccr_day
    WHERE item_num = 1750 AND day IS NOT NULL
),
report_day AS (
    SELECT
        el.person_id,
        e.inbound_envelope_id,
        TRY_CONVERT(date, CONCAT(
            RIGHT(CONCAT('000', JSON_VALUE(e.envelope_json, '$.report.observation_date.y')), 4),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.m')), 2),
            '-',
            RIGHT(CONCAT('0', JSON_VALUE(e.envelope_json, '$.report.observation_date.d')), 2)
        ), 23) AS day
    FROM naaccr.report_version rv
    JOIN intake.envelope_load el ON el.inbound_envelope_id = rv.inbound_envelope_id
    JOIN intake.inbound_envelope e ON e.inbound_envelope_id = rv.inbound_envelope_id
    WHERE rv.is_selected = 1
      AND JSON_VALUE(e.envelope_json, '$.report.observation_date.d') IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM naaccr.naaccr_value v WHERE v.sdc_report_id = rv.sdc_report_id
      )
),
-- A value date sorts before a report date on the same day, so provenance
-- prefers the more specific source.
clinical_day AS (
    SELECT person_id, observation_date AS day, naaccr_value_id,
           CAST(NULL AS BIGINT) AS inbound_envelope_id, 0 AS source_order,
           CAST(naaccr_value_id AS BIGINT) AS source_id
    FROM selected_value
    WHERE observation_date IS NOT NULL
    UNION ALL
    SELECT person_id, day, NULL, inbound_envelope_id, 1, inbound_envelope_id
    FROM report_day
    WHERE day IS NOT NULL
),
first_clinical AS (
    SELECT person_id, day, naaccr_value_id, inbound_envelope_id,
           ROW_NUMBER() OVER (
               PARTITION BY person_id ORDER BY day, source_order, source_id
           ) AS n
    FROM clinical_day
),
last_clinical AS (
    SELECT person_id, day, naaccr_value_id, inbound_envelope_id,
           ROW_NUMBER() OVER (
               PARTITION BY person_id ORDER BY day DESC, source_order, source_id
           ) AS n
    FROM clinical_day
)
SELECT
    p.patient_id AS person_id,
    CASE
        WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
            THEN 'naaccr_diagnosis_to_last_contact'
        WHEN fc.person_id IS NOT NULL THEN 'clinical_date_span'
    END AS derivation,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN dx.day ELSE fc.day END AS start_date,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN dx.naaccr_value_id ELSE fc.naaccr_value_id END AS start_naaccr_value_id,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN NULL ELSE fc.inbound_envelope_id END AS start_inbound_envelope_id,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN lc.day ELSE lcl.day END AS end_date,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN lc.naaccr_value_id ELSE lcl.naaccr_value_id END AS end_naaccr_value_id,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN NULL ELSE lcl.inbound_envelope_id END AS end_inbound_envelope_id
INTO #bridge_period
FROM intake.patient p
LEFT JOIN diagnosis dx ON dx.person_id = p.patient_id AND dx.n = 1
LEFT JOIN last_contact lc ON lc.person_id = p.patient_id AND lc.n = 1
LEFT JOIN first_clinical fc ON fc.person_id = p.patient_id AND fc.n = 1
LEFT JOIN last_clinical lcl ON lcl.person_id = p.patient_id AND lcl.n = 1;
GO

-- Required-data check: every row fails the run before any OMOP write.
SELECT message
FROM (
    SELECT patient_id AS person_id, 1 AS rule_order,
           CONCAT('intake.patient ', patient_id, ': birth year is missing') AS message
    FROM intake.patient
    WHERE birth_year IS NULL
    UNION ALL
    SELECT patient_id, 2,
           CONCAT('intake.patient ', patient_id,
                  ': person_source_value is longer than the 50 characters omop.person allows')
    FROM intake.patient
    WHERE LEN(person_source_value) > 50
    UNION ALL
    SELECT person_id, 3,
           CONCAT('intake.patient ', person_id,
                  ': no selected report has a day-precision clinical date')
    FROM #bridge_period
    WHERE derivation IS NULL
    UNION ALL
    SELECT person_id, 4,
           CONCAT('intake.patient ', person_id, ': date of last contact ',
                  CONVERT(char(10), end_date, 23), ' (naaccr_value ', end_naaccr_value_id,
                  ') precedes date of diagnosis ', CONVERT(char(10), start_date, 23),
                  ' (naaccr_value ', start_naaccr_value_id, ')')
    FROM #bridge_period
    WHERE end_date < start_date
) AS problem
ORDER BY person_id, rule_order;
GO

UPDATE o
SET gender_concept_id = b.gender_concept_id,
    year_of_birth = b.year_of_birth,
    month_of_birth = b.month_of_birth,
    day_of_birth = b.day_of_birth,
    race_concept_id = b.unmapped_concept_id,
    ethnicity_concept_id = b.unmapped_concept_id,
    person_source_value = b.person_source_value,
    gender_source_value = b.gender_source_value,
    gender_source_concept_id = b.unmapped_concept_id
FROM omop.person o
JOIN #bridge_person b ON b.person_id = o.person_id
WHERE EXISTS (
    SELECT o.gender_concept_id, o.year_of_birth, o.month_of_birth, o.day_of_birth,
           o.race_concept_id, o.ethnicity_concept_id, o.person_source_value,
           o.gender_source_value, o.gender_source_concept_id
    EXCEPT
    SELECT b.gender_concept_id, b.year_of_birth, b.month_of_birth, b.day_of_birth,
           b.unmapped_concept_id, b.unmapped_concept_id, b.person_source_value,
           b.gender_source_value, b.unmapped_concept_id
);
GO

INSERT INTO omop.person (
    person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth,
    race_concept_id, ethnicity_concept_id, person_source_value, gender_source_value,
    gender_source_concept_id
)
SELECT
    b.person_id, b.gender_concept_id, b.year_of_birth, b.month_of_birth, b.day_of_birth,
    b.unmapped_concept_id, b.unmapped_concept_id, b.person_source_value,
    b.gender_source_value, b.unmapped_concept_id
FROM #bridge_person b
WHERE NOT EXISTS (SELECT 1 FROM omop.person o WHERE o.person_id = b.person_id)
ORDER BY b.person_id;
GO

UPDATE o
SET observation_period_start_date = b.start_date,
    observation_period_end_date = b.end_date,
    period_type_concept_id = t.concept_id
FROM omop.observation_period o
JOIN #bridge_period b ON b.person_id = o.person_id
JOIN etl.concept_constant t ON t.constant_name = 'period_type_registry'
WHERE EXISTS (
    SELECT o.observation_period_start_date, o.observation_period_end_date,
           o.period_type_concept_id
    EXCEPT
    SELECT b.start_date, b.end_date, t.concept_id
);
GO

INSERT INTO omop.observation_period (
    person_id, observation_period_start_date, observation_period_end_date,
    period_type_concept_id
)
SELECT b.person_id, b.start_date, b.end_date, t.concept_id
FROM #bridge_period b
JOIN etl.concept_constant t ON t.constant_name = 'period_type_registry'
WHERE NOT EXISTS (
    SELECT 1 FROM omop.observation_period o WHERE o.person_id = b.person_id
)
ORDER BY b.person_id;
GO

UPDATE d
SET person_id = b.person_id,
    derivation = b.derivation,
    start_naaccr_value_id = b.start_naaccr_value_id,
    start_inbound_envelope_id = b.start_inbound_envelope_id,
    end_naaccr_value_id = b.end_naaccr_value_id,
    end_inbound_envelope_id = b.end_inbound_envelope_id
FROM etl.observation_period_derivation d
JOIN omop.observation_period o ON o.observation_period_id = d.observation_period_id
JOIN #bridge_period b ON b.person_id = o.person_id
WHERE EXISTS (
    SELECT d.person_id, d.derivation, d.start_naaccr_value_id, d.start_inbound_envelope_id,
           d.end_naaccr_value_id, d.end_inbound_envelope_id
    EXCEPT
    SELECT b.person_id, b.derivation, b.start_naaccr_value_id, b.start_inbound_envelope_id,
           b.end_naaccr_value_id, b.end_inbound_envelope_id
);
GO

INSERT INTO etl.observation_period_derivation (
    observation_period_id, person_id, derivation, start_naaccr_value_id,
    start_inbound_envelope_id, end_naaccr_value_id, end_inbound_envelope_id
)
SELECT o.observation_period_id, b.person_id, b.derivation, b.start_naaccr_value_id,
       b.start_inbound_envelope_id, b.end_naaccr_value_id, b.end_inbound_envelope_id
FROM omop.observation_period o
JOIN #bridge_period b ON b.person_id = o.person_id
WHERE NOT EXISTS (
    SELECT 1 FROM etl.observation_period_derivation d
    WHERE d.observation_period_id = o.observation_period_id
)
ORDER BY o.observation_period_id;
GO

-- cdm_source: the staged seed plus the loaded vocabulary version and the
-- resolved CDM version concept. The table holds exactly this one row.
DROP TABLE IF EXISTS #bridge_cdm_source;
GO

SELECT
    s.cdm_source_name, s.cdm_source_abbreviation, s.cdm_holder, s.source_description,
    s.source_documentation_reference, s.cdm_etl_reference, s.source_release_date,
    s.cdm_release_date, s.cdm_version, c.concept_id AS cdm_version_concept_id,
    v.vocabulary_version
INTO #bridge_cdm_source
FROM etl.cdm_source_seed s
JOIN etl.concept_constant c ON c.constant_name = 'cdm_version'
JOIN omop.vocabulary v ON v.vocabulary_id = 'None';
GO

DELETE o
FROM omop.cdm_source o
WHERE (SELECT COUNT(*) FROM omop.cdm_source) <> 1
   OR NOT EXISTS (
       SELECT b.cdm_source_name, b.cdm_source_abbreviation, b.cdm_holder,
              b.source_description, b.source_documentation_reference, b.cdm_etl_reference,
              b.source_release_date, b.cdm_release_date, b.cdm_version,
              b.cdm_version_concept_id, b.vocabulary_version
       FROM #bridge_cdm_source b
       INTERSECT
       SELECT o.cdm_source_name, o.cdm_source_abbreviation, o.cdm_holder,
              o.source_description, o.source_documentation_reference, o.cdm_etl_reference,
              o.source_release_date, o.cdm_release_date, o.cdm_version,
              o.cdm_version_concept_id, o.vocabulary_version
   );
GO

INSERT INTO omop.cdm_source (
    cdm_source_name, cdm_source_abbreviation, cdm_holder, source_description,
    source_documentation_reference, cdm_etl_reference, source_release_date,
    cdm_release_date, cdm_version, cdm_version_concept_id, vocabulary_version
)
SELECT
    cdm_source_name, cdm_source_abbreviation, cdm_holder, source_description,
    source_documentation_reference, cdm_etl_reference, source_release_date,
    cdm_release_date, cdm_version, cdm_version_concept_id, vocabulary_version
FROM #bridge_cdm_source
WHERE NOT EXISTS (SELECT 1 FROM omop.cdm_source);
GO

DROP TABLE #bridge_cdm_source;
GO

DROP TABLE #bridge_period;
GO

DROP TABLE #bridge_person;
GO
