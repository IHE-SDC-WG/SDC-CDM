/*
  Bridge script 1 (SQLite): omop.person, omop.observation_period, omop.cdm_source

  Only `sdc-cdm bridge` runs this file, inside its data transaction, after it has
  checked the constants, seed, vocabulary version, and concept map this script
  reads and staged the seed row in etl.cdm_source_seed. A statement that
  returns rows is a required-data check: each row names one offending source
  row, and any row fails and rolls back the run.

  person: one row per intake.patient, with person_id = patient_id. Birth month
  and day stay NULL when the source omits them. Source gender M or F resolves
  through etl.concept_constant; any other value gets the unmapped concept.

  observation_period: one unpadded period per person, built from the person's
  selected report versions only. When those reports carry a day-precision
  NAACCR item 390 (date of diagnosis) and item 1750 (date of last contact), the
  period runs from the earliest 390 to the latest 1750. Otherwise it spans the
  earliest and latest day-precision naaccr_value.observation_date. Partial
  dates never set a boundary, and no date is ever inferred or taken from
  today. etl.observation_period_derivation records the rule and the
  naaccr_value rows that set each boundary.

  Every write updates changed rows or inserts missing ones, so an unchanged
  rerun writes nothing.
*/

DROP TABLE IF EXISTS temp.bridge_person;

CREATE TEMP TABLE bridge_person AS
SELECT
    p.patient_id AS person_id,
    CASE UPPER(TRIM(p.gender_source_value))
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
FROM intake.patient p
JOIN etl.concept_constant male ON male.constant_name = 'gender_male'
JOIN etl.concept_constant female ON female.constant_name = 'gender_female'
JOIN etl.concept_constant unmapped ON unmapped.constant_name = 'unmapped';

DROP TABLE IF EXISTS temp.bridge_period;

CREATE TEMP TABLE bridge_period AS
WITH selected_value AS (
    SELECT
        v.naaccr_value_id,
        v.person_id,
        v.item_num,
        v.observation_date,
        TRIM(COALESCE(NULLIF(TRIM(v.value_code), ''), v.value_text)) AS item_value
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
        substr(item_value, 1, 4) || '-' || substr(item_value, 5, 2) || '-'
            || substr(item_value, 7, 2) AS day
    FROM selected_value
    WHERE item_num IN (390, 1750)
      AND length(item_value) = 8
      AND item_value NOT GLOB '*[^0-9]*'
),
diagnosis AS (
    SELECT person_id, day, naaccr_value_id,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY day, naaccr_value_id) AS n
    FROM naaccr_day
    WHERE item_num = 390 AND date(day) = day
),
last_contact AS (
    SELECT person_id, day, naaccr_value_id,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY day DESC, naaccr_value_id) AS n
    FROM naaccr_day
    WHERE item_num = 1750 AND date(day) = day
),
first_clinical AS (
    SELECT person_id, observation_date AS day, naaccr_value_id,
           ROW_NUMBER() OVER (
               PARTITION BY person_id ORDER BY observation_date, naaccr_value_id
           ) AS n
    FROM selected_value
    WHERE date(observation_date) = observation_date
),
last_clinical AS (
    SELECT person_id, observation_date AS day, naaccr_value_id,
           ROW_NUMBER() OVER (
               PARTITION BY person_id ORDER BY observation_date DESC, naaccr_value_id
           ) AS n
    FROM selected_value
    WHERE date(observation_date) = observation_date
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
        THEN lc.day ELSE lcl.day END AS end_date,
    CASE WHEN dx.person_id IS NOT NULL AND lc.person_id IS NOT NULL
        THEN lc.naaccr_value_id ELSE lcl.naaccr_value_id END AS end_naaccr_value_id
FROM intake.patient p
LEFT JOIN diagnosis dx ON dx.person_id = p.patient_id AND dx.n = 1
LEFT JOIN last_contact lc ON lc.person_id = p.patient_id AND lc.n = 1
LEFT JOIN first_clinical fc ON fc.person_id = p.patient_id AND fc.n = 1
LEFT JOIN last_clinical lcl ON lcl.person_id = p.patient_id AND lcl.n = 1;

-- Required-data check: every row fails the run before any OMOP write.
SELECT message
FROM (
    SELECT patient_id AS person_id, 1 AS rule_order,
           'intake.patient ' || patient_id || ': birth year is missing' AS message
    FROM intake.patient
    WHERE birth_year IS NULL
    UNION ALL
    SELECT patient_id, 2,
           'intake.patient ' || patient_id
               || ': person_source_value is longer than the 50 characters omop.person allows'
    FROM intake.patient
    WHERE length(person_source_value) > 50
    UNION ALL
    SELECT person_id, 3,
           'intake.patient ' || person_id
               || ': no selected report has a day-precision clinical date'
    FROM temp.bridge_period
    WHERE derivation IS NULL
    UNION ALL
    SELECT person_id, 4,
           'intake.patient ' || person_id || ': date of last contact ' || end_date
               || ' (naaccr_value ' || end_naaccr_value_id
               || ') precedes date of diagnosis ' || start_date
               || ' (naaccr_value ' || start_naaccr_value_id || ')'
    FROM temp.bridge_period
    WHERE end_date < start_date
)
ORDER BY person_id, rule_order;

UPDATE omop.person AS o
SET gender_concept_id = b.gender_concept_id,
    year_of_birth = b.year_of_birth,
    month_of_birth = b.month_of_birth,
    day_of_birth = b.day_of_birth,
    race_concept_id = b.unmapped_concept_id,
    ethnicity_concept_id = b.unmapped_concept_id,
    person_source_value = b.person_source_value,
    gender_source_value = b.gender_source_value,
    gender_source_concept_id = b.unmapped_concept_id
FROM temp.bridge_person b
WHERE o.person_id = b.person_id
  AND (
      o.gender_concept_id IS NOT b.gender_concept_id
      OR o.year_of_birth IS NOT b.year_of_birth
      OR o.month_of_birth IS NOT b.month_of_birth
      OR o.day_of_birth IS NOT b.day_of_birth
      OR o.race_concept_id IS NOT b.unmapped_concept_id
      OR o.ethnicity_concept_id IS NOT b.unmapped_concept_id
      OR o.person_source_value IS NOT b.person_source_value
      OR o.gender_source_value IS NOT b.gender_source_value
      OR o.gender_source_concept_id IS NOT b.unmapped_concept_id
  );

INSERT INTO omop.person (
    person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth,
    race_concept_id, ethnicity_concept_id, person_source_value, gender_source_value,
    gender_source_concept_id
)
SELECT
    b.person_id, b.gender_concept_id, b.year_of_birth, b.month_of_birth, b.day_of_birth,
    b.unmapped_concept_id, b.unmapped_concept_id, b.person_source_value,
    b.gender_source_value, b.unmapped_concept_id
FROM temp.bridge_person b
WHERE NOT EXISTS (SELECT 1 FROM omop.person o WHERE o.person_id = b.person_id)
ORDER BY b.person_id;

UPDATE omop.observation_period AS o
SET observation_period_start_date = b.start_date,
    observation_period_end_date = b.end_date,
    period_type_concept_id = t.concept_id
FROM temp.bridge_period b
JOIN etl.concept_constant t ON t.constant_name = 'period_type_registry'
WHERE o.person_id = b.person_id
  AND (
      o.observation_period_start_date IS NOT b.start_date
      OR o.observation_period_end_date IS NOT b.end_date
      OR o.period_type_concept_id IS NOT t.concept_id
  );

INSERT INTO omop.observation_period (
    person_id, observation_period_start_date, observation_period_end_date,
    period_type_concept_id
)
SELECT b.person_id, b.start_date, b.end_date, t.concept_id
FROM temp.bridge_period b
JOIN etl.concept_constant t ON t.constant_name = 'period_type_registry'
WHERE NOT EXISTS (
    SELECT 1 FROM omop.observation_period o WHERE o.person_id = b.person_id
)
ORDER BY b.person_id;

UPDATE etl.observation_period_derivation AS d
SET person_id = b.person_id,
    derivation = b.derivation,
    start_naaccr_value_id = b.start_naaccr_value_id,
    end_naaccr_value_id = b.end_naaccr_value_id
FROM omop.observation_period o
JOIN temp.bridge_period b ON b.person_id = o.person_id
WHERE d.observation_period_id = o.observation_period_id
  AND (
      d.person_id IS NOT b.person_id
      OR d.derivation IS NOT b.derivation
      OR d.start_naaccr_value_id IS NOT b.start_naaccr_value_id
      OR d.end_naaccr_value_id IS NOT b.end_naaccr_value_id
  );

INSERT INTO etl.observation_period_derivation (
    observation_period_id, person_id, derivation, start_naaccr_value_id, end_naaccr_value_id
)
SELECT o.observation_period_id, b.person_id, b.derivation, b.start_naaccr_value_id,
       b.end_naaccr_value_id
FROM omop.observation_period o
JOIN temp.bridge_period b ON b.person_id = o.person_id
WHERE NOT EXISTS (
    SELECT 1 FROM etl.observation_period_derivation d
    WHERE d.observation_period_id = o.observation_period_id
)
ORDER BY o.observation_period_id;

-- cdm_source: the staged seed plus the loaded vocabulary version and the
-- resolved CDM version concept. The table holds exactly this one row.
DROP TABLE IF EXISTS temp.bridge_cdm_source;

CREATE TEMP TABLE bridge_cdm_source AS
SELECT
    s.cdm_source_name, s.cdm_source_abbreviation, s.cdm_holder, s.source_description,
    s.source_documentation_reference, s.cdm_etl_reference, s.source_release_date,
    s.cdm_release_date, s.cdm_version, c.concept_id AS cdm_version_concept_id,
    v.vocabulary_version
FROM etl.cdm_source_seed s
JOIN etl.concept_constant c ON c.constant_name = 'cdm_version'
JOIN omop.vocabulary v ON v.vocabulary_id = 'None';

DELETE FROM omop.cdm_source AS o
WHERE (SELECT COUNT(*) FROM omop.cdm_source) <> 1
   OR NOT EXISTS (
       SELECT 1 FROM temp.bridge_cdm_source b
       WHERE b.cdm_source_name IS o.cdm_source_name
         AND b.cdm_source_abbreviation IS o.cdm_source_abbreviation
         AND b.cdm_holder IS o.cdm_holder
         AND b.source_description IS o.source_description
         AND b.source_documentation_reference IS o.source_documentation_reference
         AND b.cdm_etl_reference IS o.cdm_etl_reference
         AND b.source_release_date IS o.source_release_date
         AND b.cdm_release_date IS o.cdm_release_date
         AND b.cdm_version IS o.cdm_version
         AND b.cdm_version_concept_id IS o.cdm_version_concept_id
         AND b.vocabulary_version IS o.vocabulary_version
   );

INSERT INTO omop.cdm_source (
    cdm_source_name, cdm_source_abbreviation, cdm_holder, source_description,
    source_documentation_reference, cdm_etl_reference, source_release_date,
    cdm_release_date, cdm_version, cdm_version_concept_id, vocabulary_version
)
SELECT
    cdm_source_name, cdm_source_abbreviation, cdm_holder, source_description,
    source_documentation_reference, cdm_etl_reference, source_release_date,
    cdm_release_date, cdm_version, cdm_version_concept_id, vocabulary_version
FROM temp.bridge_cdm_source
WHERE NOT EXISTS (SELECT 1 FROM omop.cdm_source);

DROP TABLE temp.bridge_cdm_source;
DROP TABLE temp.bridge_period;
DROP TABLE temp.bridge_person;
