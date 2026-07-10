IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'sdc') EXEC('CREATE SCHEMA sdc');
GO

IF OBJECT_ID('sdc.template_sdc', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.template_sdc (
    template_sdc_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    sdc_form_design_sdcid NVARCHAR(255) NULL,
    base_uri NVARCHAR(2048) NULL,
    lineage NVARCHAR(255) NULL,
    version NVARCHAR(255) NULL,
    full_uri NVARCHAR(2048) NULL,
    form_title NVARCHAR(1000) NULL,
    sdc_xml NVARCHAR(MAX) NULL,
    doc_type NVARCHAR(255) NULL
  );
END
GO

IF OBJECT_ID('sdc.template_item', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.template_item (
    template_item_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_sdc_id INT NOT NULL REFERENCES sdc.template_sdc(template_sdc_id),
    parent_template_item_id INT NULL REFERENCES sdc.template_item(template_item_id),
    template_item_sdcid NVARCHAR(255) NOT NULL,
    type NVARCHAR(255) NULL,
    visible_text NVARCHAR(MAX) NULL,
    invisible_text NVARCHAR(MAX) NULL,
    min_card NVARCHAR(255) NULL,
    must_implement NVARCHAR(255) NULL,
    item_order NVARCHAR(255) NULL
  );
END
GO

IF OBJECT_ID('sdc.template_instance', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.template_instance (
    template_instance_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_instance_version_guid NVARCHAR(255) NULL,
    template_instance_version_uri NVARCHAR(2048) NULL,
    template_sdc_id INT NOT NULL REFERENCES sdc.template_sdc(template_sdc_id),
    instance_version_date NVARCHAR(255) NULL,
    diag_report_props NVARCHAR(MAX) NULL,
    surg_path_sdcid NVARCHAR(255) NULL,
    person_id INT NULL,
    visit_occurrence_id INT NULL,
    provider_id INT NULL,
    report_text NVARCHAR(MAX) NULL
  );
END
GO

IF OBJECT_ID('sdc.sdc_report', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.sdc_report (
    sdc_report_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_instance_id INT NULL REFERENCES sdc.template_instance(template_instance_id),
    template_name NVARCHAR(255) NOT NULL,
    template_version NVARCHAR(255) NOT NULL,
    template_instance_guid NVARCHAR(255) NOT NULL,
    person_id INT NULL,
    visit_occurrence_id INT NULL,
    provider_id INT NULL,
    report_text NVARCHAR(MAX) NULL,
    report_template_source NVARCHAR(255) NULL,
    report_template_id NVARCHAR(255) NULL,
    report_template_version_id NVARCHAR(255) NULL,
    tumor_site NVARCHAR(255) NULL,
    procedure_type NVARCHAR(255) NULL,
    specimen_laterality NVARCHAR(255) NULL,
    report_accession NVARCHAR(100) NULL,
    report_loinc NVARCHAR(50) NULL,
    is_duplicate_accession BIT NOT NULL DEFAULT 0,
    first_seen_report_id INT NULL REFERENCES sdc.sdc_report(sdc_report_id),
    created_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );

  CREATE INDEX IX_sdc_report_accession ON sdc.sdc_report(report_accession);
END
GO

IF OBJECT_ID('sdc.sdc_form_answer', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.sdc_form_answer (
    sdc_form_answer_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_instance_id INT NULL REFERENCES sdc.template_instance(template_instance_id),
    parent_form_answer_id INT NULL REFERENCES sdc.sdc_form_answer(sdc_form_answer_id),
    section_sdcid NVARCHAR(255) NULL,
    section_guid NVARCHAR(255) NULL,
    question_text NVARCHAR(MAX) NULL,
    question_instance_guid NVARCHAR(255) NULL,
    question_sdcid NVARCHAR(255) NULL,
    list_item_id NVARCHAR(255) NULL,
    list_item_text NVARCHAR(MAX) NULL,
    list_item_instance_guid NVARCHAR(255) NULL,
    list_item_parent_guid NVARCHAR(255) NULL,
    units_system NVARCHAR(255) NULL,
    response NVARCHAR(MAX) NULL,
    units NVARCHAR(255) NULL,
    response_int BIGINT NULL,
    response_float FLOAT NULL,
    response_datetime DATETIME2 NULL,
    reponse_string_nvarchar NVARCHAR(MAX) NULL,
    datatype NVARCHAR(255) NULL,
    sdc_order NVARCHAR(255) NULL,
    sdc_repeat_level NVARCHAR(255) NULL,
    sdc_comments NVARCHAR(MAX) NULL
  );

  CREATE INDEX IX_sdc_form_answer_instance_question
    ON sdc.sdc_form_answer(template_instance_id, question_sdcid);
END
GO

IF OBJECT_ID('sdc.template_term_map', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.template_term_map (
    template_term_map_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_sdc_id INT NOT NULL REFERENCES sdc.template_sdc(template_sdc_id),
    template_item_sdcid NVARCHAR(255) NULL,
    code NVARCHAR(255) NULL,
    code_system NVARCHAR(2048) NULL,
    display NVARCHAR(MAX) NULL
  );
END
GO

IF OBJECT_ID('sdc.template_map_content', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.template_map_content (
    template_map_content_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_term_map_id INT NOT NULL REFERENCES sdc.template_term_map(template_term_map_id),
    map_content NVARCHAR(MAX) NULL
  );
END
GO

IF OBJECT_ID('sdc.sdc_specimen', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.sdc_specimen (
    sdc_specimen_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    parent_specimen_id INT NULL REFERENCES sdc.sdc_specimen(sdc_specimen_id),
    visit_occurrence_id INT NULL,
    specimen_identifier NVARCHAR(255) NULL,
    specimen_type NVARCHAR(255) NULL,
    specimen_site NVARCHAR(255) NULL,
    laterality NVARCHAR(255) NULL
  );
END
GO

IF OBJECT_ID('sdc.observation_specimens', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.observation_specimens (
    observation_specimens_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    sdc_form_answer_id INT NOT NULL REFERENCES sdc.sdc_form_answer(sdc_form_answer_id),
    sdc_specimen_id INT NOT NULL REFERENCES sdc.sdc_specimen(sdc_specimen_id)
  );
END
GO
