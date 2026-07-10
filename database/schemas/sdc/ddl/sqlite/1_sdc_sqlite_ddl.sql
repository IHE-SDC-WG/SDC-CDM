PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS sdc.template_sdc (
    template_sdc_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    sdc_form_design_sdcid TEXT NULL,
    base_uri TEXT NULL,
    lineage TEXT NULL,
    version TEXT NULL,
    full_uri TEXT NULL,
    form_title TEXT NULL,
    sdc_xml TEXT NULL,
    doc_type TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.template_item (
    template_item_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_sdc_id INTEGER NOT NULL REFERENCES template_sdc(template_sdc_id),
    parent_template_item_id INTEGER NULL REFERENCES template_item(template_item_id),
    template_item_sdcid TEXT NOT NULL,
    type TEXT NULL,
    visible_text TEXT NULL,
    invisible_text TEXT NULL,
    min_card TEXT NULL,
    must_implement TEXT NULL,
    item_order TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.template_instance (
    template_instance_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_instance_version_guid TEXT NULL,
    template_instance_version_uri TEXT NULL,
    template_sdc_id INTEGER NOT NULL REFERENCES template_sdc(template_sdc_id),
    instance_version_date TEXT NULL,
    diag_report_props TEXT NULL,
    surg_path_sdcid TEXT NULL,
    person_id INTEGER NULL,
    visit_occurrence_id INTEGER NULL,
    provider_id INTEGER NULL,
    report_text TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.sdc_report (
    sdc_report_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_instance_id INTEGER NULL REFERENCES template_instance(template_instance_id),
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_instance_guid TEXT NOT NULL,
    person_id INTEGER NULL,
    visit_occurrence_id INTEGER NULL,
    provider_id INTEGER NULL,
    report_text TEXT NULL,
    report_template_source TEXT NULL,
    report_template_id TEXT NULL,
    report_template_version_id TEXT NULL,
    tumor_site TEXT NULL,
    procedure_type TEXT NULL,
    specimen_laterality TEXT NULL,
    report_accession TEXT NULL,
    report_loinc TEXT NULL,
    is_duplicate_accession INTEGER NOT NULL DEFAULT 0,
    first_seen_report_id INTEGER NULL REFERENCES sdc_report(sdc_report_id),
    created_datetime TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_datetime TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sdc.sdc_form_answer (
    sdc_form_answer_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_instance_id INTEGER NULL REFERENCES template_instance(template_instance_id),
    parent_form_answer_id INTEGER NULL REFERENCES sdc_form_answer(sdc_form_answer_id),
    section_sdcid TEXT NULL,
    section_guid TEXT NULL,
    question_text TEXT NULL,
    question_instance_guid TEXT NULL,
    question_sdcid TEXT NULL,
    list_item_id TEXT NULL,
    list_item_text TEXT NULL,
    list_item_instance_guid TEXT NULL,
    list_item_parent_guid TEXT NULL,
    units_system TEXT NULL,
    response TEXT NULL,
    units TEXT NULL,
    response_int INTEGER NULL,
    response_float REAL NULL,
    response_datetime TEXT NULL,
    reponse_string_nvarchar TEXT NULL,
    datatype TEXT NULL,
    sdc_order TEXT NULL,
    sdc_repeat_level TEXT NULL,
    sdc_comments TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.template_term_map (
    template_term_map_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_sdc_id INTEGER NOT NULL REFERENCES template_sdc(template_sdc_id),
    template_item_sdcid TEXT NULL,
    code TEXT NULL,
    code_system TEXT NULL,
    display TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.template_map_content (
    template_map_content_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    template_term_map_id INTEGER NOT NULL REFERENCES template_term_map(template_term_map_id),
    map_content TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.sdc_specimen (
    sdc_specimen_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    parent_specimen_id INTEGER NULL REFERENCES sdc_specimen(sdc_specimen_id),
    visit_occurrence_id INTEGER NULL,
    specimen_identifier TEXT NULL,
    specimen_type TEXT NULL,
    specimen_site TEXT NULL,
    laterality TEXT NULL
);

CREATE TABLE IF NOT EXISTS sdc.observation_specimens (
    observation_specimens_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    sdc_form_answer_id INTEGER NOT NULL REFERENCES sdc_form_answer(sdc_form_answer_id),
    sdc_specimen_id INTEGER NOT NULL REFERENCES sdc_specimen(sdc_specimen_id)
);

CREATE INDEX IF NOT EXISTS sdc.idx_sdc_report_accession
    ON sdc_report (report_accession);
CREATE INDEX IF NOT EXISTS sdc.idx_sdc_form_answer_instance_question
    ON sdc_form_answer (template_instance_id, question_sdcid);

COMMIT;
