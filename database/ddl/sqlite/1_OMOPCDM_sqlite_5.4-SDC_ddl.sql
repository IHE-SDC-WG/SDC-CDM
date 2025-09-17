-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

--sqlite CDM DDL Specification for OMOP Common Data Model 5.4-SDC
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.person (
			person_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			gender_concept_id integer NOT NULL REFERENCES concept(concept_id),
			year_of_birth integer NOT NULL,
			month_of_birth integer NULL,
			day_of_birth integer NULL,
			birth_datetime REAL NULL,
			race_concept_id integer NOT NULL REFERENCES concept(concept_id),
			ethnicity_concept_id integer NOT NULL REFERENCES concept(concept_id),
			location_id integer NULL,
			provider_id integer NULL,
			care_site_id integer NULL,
			person_source_value TEXT NULL,
			gender_source_value TEXT NULL,
			gender_source_concept_id integer NULL,
			race_source_value TEXT NULL,
			race_source_concept_id integer NULL,
			ethnicity_source_value TEXT NULL,
			ethnicity_source_concept_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.observation_period (
			observation_period_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			observation_period_start_date date NOT NULL,
			observation_period_end_date date NOT NULL,
			period_type_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.visit_occurrence (
			visit_occurrence_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			visit_concept_id integer NOT NULL REFERENCES concept(concept_id),
			visit_start_date date NOT NULL,
			visit_start_datetime REAL NULL,
			visit_end_date date NOT NULL,
			visit_end_datetime REAL NULL,
			visit_type_concept_id Integer NOT NULL REFERENCES concept(concept_id),
			provider_id integer NULL,
			care_site_id integer NULL,
			visit_source_value TEXT NULL,
			visit_source_concept_id integer NULL,
			admitted_from_concept_id integer NULL,
			admitted_from_source_value TEXT NULL,
			discharged_to_concept_id integer NULL,
			discharged_to_source_value TEXT NULL,
			preceding_visit_occurrence_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.visit_detail (
			visit_detail_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			visit_detail_concept_id integer NOT NULL REFERENCES concept(concept_id),
			visit_detail_start_date date NOT NULL,
			visit_detail_start_datetime REAL NULL,
			visit_detail_end_date date NOT NULL,
			visit_detail_end_datetime REAL NULL,
			visit_detail_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			provider_id integer NULL,
			care_site_id integer NULL,
			visit_detail_source_value TEXT NULL,
			visit_detail_source_concept_id Integer NULL,
			admitted_from_concept_id Integer NULL,
			admitted_from_source_value TEXT NULL,
			discharged_to_source_value TEXT NULL,
			discharged_to_concept_id integer NULL,
			preceding_visit_detail_id integer NULL,
			parent_visit_detail_id integer NULL,
			visit_occurrence_id integer NOT NULL REFERENCES visit_occurrence(visit_occurrence_id) );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.condition_occurrence (
			condition_occurrence_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			condition_concept_id integer NOT NULL REFERENCES concept(concept_id),
			condition_start_date date NOT NULL,
			condition_start_datetime REAL NULL,
			condition_end_date date NULL,
			condition_end_datetime REAL NULL,
			condition_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			condition_status_concept_id integer NULL,
			stop_reason TEXT NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			condition_source_value TEXT NULL,
			condition_source_concept_id integer NULL,
			condition_status_source_value TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.drug_exposure (
			drug_exposure_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			drug_concept_id integer NOT NULL REFERENCES concept(concept_id),
			drug_exposure_start_date date NOT NULL,
			drug_exposure_start_datetime REAL NULL,
			drug_exposure_end_date date NOT NULL,
			drug_exposure_end_datetime REAL NULL,
			verbatim_end_date date NULL,
			drug_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			stop_reason TEXT NULL,
			refills integer NULL,
			quantity REAL NULL,
			days_supply integer NULL,
			sig TEXT NULL,
			route_concept_id integer NULL,
			lot_number TEXT NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			drug_source_value TEXT NULL,
			drug_source_concept_id integer NULL,
			route_source_value TEXT NULL,
			dose_unit_source_value TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.procedure_occurrence (
			procedure_occurrence_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			procedure_concept_id integer NOT NULL REFERENCES concept(concept_id),
			procedure_date date NOT NULL,
			procedure_datetime REAL NULL,
			procedure_end_date date NULL,
			procedure_end_datetime REAL NULL,
			procedure_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			modifier_concept_id integer NULL,
			quantity integer NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			procedure_source_value TEXT NULL,
			procedure_source_concept_id integer NULL,
			modifier_source_value TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.device_exposure (
			device_exposure_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			device_concept_id integer NOT NULL REFERENCES concept(concept_id),
			device_exposure_start_date date NOT NULL,
			device_exposure_start_datetime REAL NULL,
			device_exposure_end_date date NULL,
			device_exposure_end_datetime REAL NULL,
			device_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			unique_device_id TEXT NULL,
			production_id TEXT NULL,
			quantity integer NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			device_source_value TEXT NULL,
			device_source_concept_id integer NULL,
			unit_concept_id integer NULL,
			unit_source_value TEXT NULL,
			unit_source_concept_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.measurement (
			measurement_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			measurement_concept_id integer NOT NULL REFERENCES concept(concept_id),
			measurement_date date NOT NULL,
			measurement_datetime REAL NULL,
			measurement_time TEXT NULL,
			measurement_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			operator_concept_id integer NULL,
			value_as_number REAL NULL,
			value_as_concept_id integer NULL,
			unit_concept_id integer NULL,
			range_low REAL NULL,
			range_high REAL NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			measurement_source_value TEXT NULL,
			measurement_source_concept_id integer NULL,
			unit_source_value TEXT NULL,
			unit_source_concept_id integer NULL,
			value_source_value TEXT NULL,
			measurement_event_id integer NULL,
			meas_event_field_concept_id integer NULL
			-- SDC linkage to ancillary SDC tables (extras as FK refs only)
			-- sdc_form_answer_id will be added after SDC tables are created to satisfy FK ordering
			-- see ALTER TABLE at end of script
			);
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.observation (
			observation_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			observation_concept_id integer NOT NULL REFERENCES concept(concept_id),
			observation_date date NOT NULL,
			observation_datetime REAL NULL,
			observation_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			value_as_number REAL NULL,
			value_as_string TEXT NULL,
			value_as_concept_id Integer NULL,
			qualifier_concept_id integer NULL,
			unit_concept_id integer NULL,
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			observation_source_value TEXT NULL,
			observation_source_concept_id integer NULL,
			unit_source_value TEXT NULL,
			qualifier_source_value TEXT NULL,
			value_source_value TEXT NULL,
			observation_event_id integer NULL,
			obs_event_field_concept_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.death (
			person_id integer NOT NULL REFERENCES person(person_id),
			death_date date NOT NULL,
			death_datetime REAL NULL,
			death_type_concept_id integer NULL,
			cause_concept_id integer NULL,
			cause_source_value TEXT NULL,
			cause_source_concept_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.note (
			note_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			note_date date NOT NULL,
			note_datetime REAL NULL,
			note_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			note_class_concept_id integer NOT NULL REFERENCES concept(concept_id),
			note_title TEXT NULL,
			note_text TEXT NOT NULL,
			encoding_concept_id integer NOT NULL REFERENCES concept(concept_id),
			language_concept_id integer NOT NULL REFERENCES concept(concept_id),
			provider_id integer NULL,
			visit_occurrence_id integer NULL,
			visit_detail_id integer NULL,
			note_source_value TEXT NULL,
			note_event_id integer NULL,
			note_event_field_concept_id integer NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.note_nlp (
			note_nlp_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			note_id integer NOT NULL,
			section_concept_id integer NULL,
			snippet TEXT NULL,
			"offset" TEXT NULL,
			lexical_variant TEXT NOT NULL,
			note_nlp_concept_id integer NULL,
			note_nlp_source_concept_id integer NULL,
			nlp_system TEXT NULL,
			nlp_date date NOT NULL,
			nlp_datetime REAL NULL,
			term_exists TEXT NULL,
			term_temporal TEXT NULL,
			term_modifiers TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.specimen (
			specimen_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			specimen_concept_id integer NOT NULL REFERENCES concept(concept_id),
			specimen_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			specimen_date date NOT NULL,
			specimen_datetime REAL NULL,
			quantity REAL NULL,
			unit_concept_id integer NULL,
			anatomic_site_concept_id integer NULL,
			disease_status_concept_id integer NULL,
			specimen_source_id TEXT NULL,
			specimen_source_value TEXT NULL,
			unit_source_value TEXT NULL,
			anatomic_site_source_value TEXT NULL,
			disease_status_source_value TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.fact_relationship (
			domain_concept_id_1 integer NOT NULL REFERENCES concept(concept_id),
			fact_id_1 integer NOT NULL,
			domain_concept_id_2 integer NOT NULL REFERENCES concept(concept_id),
			fact_id_2 integer NOT NULL,
			relationship_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.location (
			location_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			address_1 TEXT NULL,
			address_2 TEXT NULL,
			city TEXT NULL,
			state TEXT NULL,
			zip TEXT NULL,
			county TEXT NULL,
			location_source_value TEXT NULL,
			country_concept_id integer NULL,
			country_source_value TEXT NULL,
			latitude REAL NULL,
			longitude REAL NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.care_site (
			care_site_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			care_site_name TEXT NULL,
			place_of_service_concept_id integer NULL,
			location_id integer NULL,
			care_site_source_value TEXT NULL,
			place_of_service_source_value TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.provider (
			provider_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			provider_name TEXT NULL,
			npi TEXT NULL,
			dea TEXT NULL,
			specialty_concept_id integer NULL,
			care_site_id integer NULL,
			year_of_birth integer NULL,
			gender_concept_id integer NULL,
			provider_source_value TEXT NULL,
			specialty_source_value TEXT NULL,
			specialty_source_concept_id integer NULL,
			gender_source_value TEXT NULL,
			gender_source_concept_id integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.payer_plan_period (
			payer_plan_period_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			payer_plan_period_start_date date NOT NULL,
			payer_plan_period_end_date date NOT NULL,
			payer_concept_id integer NULL,
			payer_source_value TEXT NULL,
			payer_source_concept_id integer NULL,
			plan_concept_id integer NULL,
			plan_source_value TEXT NULL,
			plan_source_concept_id integer NULL,
			sponsor_concept_id integer NULL,
			sponsor_source_value TEXT NULL,
			sponsor_source_concept_id integer NULL,
			family_source_value TEXT NULL,
			stop_reason_concept_id integer NULL,
			stop_reason_source_value TEXT NULL,
			stop_reason_source_concept_id integer NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.cost (
			cost_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			cost_event_id integer NOT NULL,
			cost_domain_id TEXT NOT NULL,
			cost_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			currency_concept_id integer NULL,
			total_charge REAL NULL,
			total_cost REAL NULL,
			total_paid REAL NULL,
			paid_by_payer REAL NULL,
			paid_by_patient REAL NULL,
			paid_patient_copay REAL NULL,
			paid_patient_coinsurance REAL NULL,
			paid_patient_deductible REAL NULL,
			paid_by_primary REAL NULL,
			paid_ingredient_cost REAL NULL,
			paid_dispensing_fee REAL NULL,
			payer_plan_period_id integer NULL,
			amount_allowed REAL NULL,
			revenue_code_concept_id integer NULL,
			revenue_code_source_value TEXT NULL,
			drg_concept_id integer NULL,
			drg_source_value TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.drug_era (
			drug_era_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			drug_concept_id integer NOT NULL REFERENCES concept(concept_id),
			drug_era_start_date date NOT NULL,
			drug_era_end_date date NOT NULL,
			drug_exposure_count integer NULL,
			gap_days integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.dose_era (
			dose_era_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			drug_concept_id integer NOT NULL REFERENCES concept(concept_id),
			unit_concept_id integer NOT NULL REFERENCES concept(concept_id),
			dose_value REAL NOT NULL,
			dose_era_start_date date NOT NULL,
			dose_era_end_date date NOT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.condition_era (
			condition_era_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			condition_concept_id integer NOT NULL REFERENCES concept(concept_id),
			condition_era_start_date date NOT NULL,
			condition_era_end_date date NOT NULL,
			condition_occurrence_count integer NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.episode (
			episode_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			person_id integer NOT NULL REFERENCES person(person_id),
			episode_concept_id integer NOT NULL REFERENCES concept(concept_id),
			episode_start_date date NOT NULL,
			episode_start_datetime REAL NULL,
			episode_end_date date NULL,
			episode_end_datetime REAL NULL,
			episode_parent_id integer NULL,
			episode_number integer NULL,
			episode_object_concept_id integer NOT NULL REFERENCES concept(concept_id),
			episode_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			episode_source_value TEXT NULL,
			episode_source_concept_id integer NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.episode_event (
			episode_id integer NOT NULL REFERENCES episode(episode_id),
			event_id integer NOT NULL,
			episode_event_field_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.metadata (
			metadata_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			metadata_concept_id integer NOT NULL REFERENCES concept(concept_id),
			metadata_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			name TEXT NOT NULL,
			value_as_string TEXT NULL,
			value_as_concept_id integer NULL,
			value_as_number REAL NULL,
			metadata_date date NULL,
			metadata_datetime REAL NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.cdm_source (
			cdm_source_name TEXT NOT NULL,
			cdm_source_abbreviation TEXT NOT NULL,
			cdm_holder TEXT NOT NULL,
			source_description TEXT NULL,
			source_documentation_reference TEXT NULL,
			cdm_etl_reference TEXT NULL,
			source_release_date date NOT NULL,
			cdm_release_date date NOT NULL,
			cdm_version TEXT NULL,
			cdm_version_concept_id integer NOT NULL REFERENCES concept(concept_id),
			vocabulary_version TEXT NOT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.concept (
			concept_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			concept_name TEXT NOT NULL,
			domain_id TEXT NOT NULL,
			vocabulary_id TEXT NOT NULL,
			concept_class_id TEXT NOT NULL,
			standard_concept TEXT NULL,
			concept_code TEXT NOT NULL,
			valid_start_date date NOT NULL,
			valid_end_date date NOT NULL,
			invalid_reason TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.vocabulary (
			vocabulary_id TEXT NOT NULL,
			vocabulary_name TEXT NOT NULL,
			vocabulary_reference TEXT NULL,
			vocabulary_version TEXT NULL,
			vocabulary_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.domain (
			domain_id TEXT NOT NULL,
			domain_name TEXT NOT NULL,
			domain_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.concept_class (
			concept_class_id TEXT NOT NULL,
			concept_class_name TEXT NOT NULL,
			concept_class_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.concept_relationship (
			concept_id_1 integer NOT NULL REFERENCES concept(concept_id),
			concept_id_2 integer NOT NULL REFERENCES concept(concept_id),
			relationship_id TEXT NOT NULL,
			valid_start_date date NOT NULL,
			valid_end_date date NOT NULL,
			invalid_reason TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.relationship (
			relationship_id TEXT NOT NULL,
			relationship_name TEXT NOT NULL,
			is_hierarchical TEXT NOT NULL,
			defines_ancestry TEXT NOT NULL,
			reverse_relationship_id TEXT NOT NULL,
			relationship_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.concept_synonym (
			concept_id integer NOT NULL REFERENCES concept(concept_id),
			concept_synonym_name TEXT NOT NULL,
			language_concept_id integer NOT NULL REFERENCES concept(concept_id) );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.concept_ancestor (
			ancestor_concept_id integer NOT NULL REFERENCES concept(concept_id),
			descendant_concept_id integer NOT NULL REFERENCES concept(concept_id),
			min_levels_of_separation integer NOT NULL,
			max_levels_of_separation integer NOT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.source_to_concept_map (
			source_code TEXT NOT NULL,
			source_concept_id integer NOT NULL REFERENCES concept(concept_id),
			source_vocabulary_id TEXT NOT NULL,
			source_code_description TEXT NULL,
			target_concept_id integer NOT NULL REFERENCES concept(concept_id),
			target_vocabulary_id TEXT NOT NULL,
			valid_start_date date NOT NULL,
			valid_end_date date NOT NULL,
			invalid_reason TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.drug_strength (
			drug_concept_id integer NOT NULL REFERENCES concept(concept_id),
			ingredient_concept_id integer NOT NULL REFERENCES concept(concept_id),
			amount_value REAL NULL,
			amount_unit_concept_id integer NULL,
			numerator_value REAL NULL,
			numerator_unit_concept_id integer NULL,
			denominator_value REAL NULL,
			denominator_unit_concept_id integer NULL,
			box_size integer NULL,
			valid_start_date date NOT NULL,
			valid_end_date date NOT NULL,
			invalid_reason TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.cohort (
			cohort_definition_id integer NOT NULL,
			subject_id integer NOT NULL,
			cohort_start_date date NOT NULL,
			cohort_end_date date NOT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.cohort_definition (
			cohort_definition_id integer NOT NULL,
			cohort_definition_name TEXT NOT NULL,
			cohort_definition_description TEXT NULL,
			definition_type_concept_id integer NOT NULL REFERENCES concept(concept_id),
			cohort_definition_syntax TEXT NULL,
			subject_concept_id integer NOT NULL REFERENCES concept(concept_id),
			cohort_initiation_date date NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.template_sdc (
			template_sdc_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			sdc_form_design_sdcid TEXT NULL,
			base_uri TEXT NULL,
			lineage TEXT NULL,
			version TEXT NULL,
			full_uri TEXT NULL,
			form_title TEXT NULL,
			sdc_xml TEXT NULL,
			doc_type TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.template_item (
			template_item_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_sdc_id integer NOT NULL REFERENCES template_sdc(template_sdc_id),
			parent_template_item_id integer NULL,
			template_item_sdcid TEXT NULL,
			'type' TEXT NULL,
			visible_text TEXT NULL,
			invisible_text TEXT NULL,
			min_cardinality TEXT NULL,
			must_implement TEXT NULL,
			item_order TEXT NULL );
--HINT DISTRIBUTE ON KEY (person_id)
CREATE TABLE main.template_instance (
			template_instance_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_instance_version_guid TEXT NULL,
			template_instance_version_uri TEXT NULL,
			template_sdc_id integer NOT NULL REFERENCES template_sdc(template_sdc_id),
			instance_version_date TEXT NULL,
			diag_report_props TEXT NULL,
			surg_path_sdcid TEXT NULL,
			person_id integer NULL,
			visit_occurrence_id integer NULL,
			provider_id integer NULL,
			report_text TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.sdc_form_answer (
			sdc_form_answer_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_instance_id integer NOT NULL REFERENCES template_instance(template_instance_id),
			parent_form_answer_id integer NULL REFERENCES sdc_form_answer(sdc_form_answer_id),
			-- Question metadata
			section_sdcid TEXT NULL,
			section_guid TEXT NULL,
			question_text TEXT NULL,
			question_instance_guid TEXT NULL,
			question_sdcid TEXT NULL,
			-- Answer context (no raw values stored here)
			list_item_id TEXT NULL,
			list_item_text TEXT NULL,
			list_item_instance_guid TEXT NULL,
			list_item_parent_guid TEXT NULL,
			units_system TEXT NULL,
			datatype TEXT NULL,
			sdc_order TEXT NULL,
			sdc_repeat_level TEXT NULL,
			sdc_comments TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.template_term_map (
			template_term_map_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_map_id TEXT NULL,
			template TEXT NULL,
			template_sdc_id integer NOT NULL REFERENCES template_sdc(template_sdc_id),
			map_xml TEXT NULL,
			code_system_name TEXT NULL,
			code_system_release_date TEXT NULL,
			code_system_version TEXT NULL,
			code_system_oid TEXT NULL,
			code_system_uri TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.template_map_content (
			template_map_content_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_term_map_id integer NOT NULL REFERENCES template_term_map(template_term_map_id),
			target_id TEXT NULL,
			code TEXT NULL,
			code_text TEXT NULL,
			code_match TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.sdc_specimen (
			sdc_specimen_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			parent_specimen_id integer NULL,
			patient_id TEXT NULL,
			visit_occurrence_id integer NULL,
			specimen_type_text TEXT NULL,
			specimen_type_code TEXT NULL,
			source_site_text TEXT NULL,
			source_site_code TEXT NULL,
			collection_method_text TEXT NULL,
			collection_method_code TEXT NULL,
			specimen_count TEXT NULL,
			collection_date TEXT NULL );
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.observation_specimens (
			observation_specimens_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			sdc_form_answer_id integer NOT NULL REFERENCES sdc_form_answer(sdc_form_answer_id),
			sdc_specimen_id integer NOT NULL REFERENCES sdc_specimen(sdc_specimen_id) );

-- SDC Template Instance table for ECP data
--HINT DISTRIBUTE ON RANDOM
CREATE TABLE main.sdc_template_instance_ecp (
			sdc_template_instance_ecp_id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
			template_name TEXT NOT NULL,
			template_version TEXT NOT NULL,
			template_lineage TEXT NULL,
			template_base_uri TEXT NULL,
			template_instance_guid TEXT NOT NULL UNIQUE,
			template_instance_version_guid TEXT NULL,
			template_instance_version_uri TEXT NULL,
			instance_version_date date NULL,
			person_id integer NULL REFERENCES person(person_id),
			visit_occurrence_id integer NULL REFERENCES visit_occurrence(visit_occurrence_id),
			provider_id integer NULL REFERENCES provider(provider_id),
			report_text TEXT NULL,
			-- NAACCR V2 specific fields from first 3 OBX segments
			report_template_source TEXT NULL,
			report_template_id TEXT NULL,
			report_template_version_id TEXT NULL,
			tumor_site TEXT NULL,
			procedure_type TEXT NULL,
			specimen_laterality TEXT NULL,
			-- Metadata fields
			created_datetime REAL DEFAULT (julianday('now')),
			updated_datetime REAL DEFAULT (julianday('now')) );
-- Add SDC linkage FKs to OMOP tables after ancillary SDC table creation
ALTER TABLE main.measurement
	ADD COLUMN sdc_form_answer_id integer NULL REFERENCES sdc_form_answer(sdc_form_answer_id);
CREATE INDEX IF NOT EXISTS idx_measurement_sdc_form_answer_id ON measurement(sdc_form_answer_id);

ALTER TABLE main.observation
	ADD COLUMN sdc_form_answer_id integer NULL REFERENCES sdc_form_answer(sdc_form_answer_id);
CREATE INDEX IF NOT EXISTS idx_observation_sdc_form_answer_id ON observation(sdc_form_answer_id);
COMMIT;
