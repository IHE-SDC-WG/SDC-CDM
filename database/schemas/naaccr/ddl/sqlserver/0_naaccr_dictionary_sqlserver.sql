

IF NOT EXISTS (SELECT *
FROM sys.schemas
WHERE name = 'naaccr') EXEC('CREATE SCHEMA naaccr');

-- Gap #1: algorithm + version as a first-class dimension. Every dictionary row is
-- scoped to a (algorithm, version) generation so multiple NAACCR/staging versions
-- can coexist and captured answers can record the version they were coded against.
CREATE TABLE naaccr.DATA_DICTIONARY_VERSION
(
  dd_version_id INT IDENTITY(1,1) PRIMARY KEY,
  algorithm NVARCHAR(255) NOT NULL,
  version NVARCHAR(255) NOT NULL,
  naaccr_version NVARCHAR(255),
  valid_start_date DATE,
  valid_end_date DATE,
  is_current BIT NOT NULL DEFAULT 1,
  source_api NVARCHAR(512),
  loaded_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
  CONSTRAINT UQ_dd_version UNIQUE (algorithm, version)
);

CREATE TABLE naaccr.STAGING_SCHEMA
(
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  schema_id NVARCHAR(255) NOT NULL,
  schema_name NVARCHAR(255),
  PRIMARY KEY (dd_version_id, schema_id_number),
  CONSTRAINT FK_staging_schema_version FOREIGN KEY (dd_version_id) REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
);

CREATE TABLE naaccr.SCHEMA_SELECTION_RULE
(
  id BIGINT IDENTITY(1,1) PRIMARY KEY,
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  site NVARCHAR(MAX),
  histology NVARCHAR(MAX),
  behavior NVARCHAR(MAX),
  sex_at_birth NVARCHAR(MAX),
  discriminator_1 NVARCHAR(MAX),
  discriminator_2 NVARCHAR(MAX),
  year_dx NVARCHAR(MAX),
  CONSTRAINT FK_schema_selection_rule_schema FOREIGN KEY (dd_version_id, schema_id_number) REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number)
);

CREATE TABLE naaccr.NAACCR_ITEM
(
  dd_version_id INT NOT NULL,
  item_num INT NOT NULL,
  name NVARCHAR(255),
  xml_id NVARCHAR(255),
  -- Gap #2a: field metadata available from the SEER Staging API (per-input unit/decimals).
  unit NVARCHAR(50),
  decimal_places INT,
  -- Gap #2b: field metadata from the NAACCR Data Dictionary API / imsweb layout.
  -- Nullable so the staging-only load works before the DD-API enrichment runs.
  data_type NVARCHAR(50),
  [length] INT,
  padding NVARCHAR(50),
  alignment NVARCHAR(50),
  trim NVARCHAR(50),
  section NVARCHAR(255),
  parent_xml_element NVARCHAR(255),
  PRIMARY KEY (dd_version_id, item_num),
  CONSTRAINT FK_naaccr_item_version FOREIGN KEY (dd_version_id) REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
);

CREATE TABLE naaccr.SCHEMA_ITEM
(
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  -- Gap #4: distinguish captured inputs from derived staging outputs.
  item_role NVARCHAR(20) NOT NULL DEFAULT 'input',
  used_for_staging BIT NOT NULL DEFAULT 0,
  default_value NVARCHAR(255),
  description NVARCHAR(MAX),
  rationale NVARCHAR(MAX),
  additional_info NVARCHAR(MAX),
  table_notes NVARCHAR(MAX),
  coding_guidelines NVARCHAR(MAX),
  PRIMARY KEY (dd_version_id, schema_id_number, item_num),
  CONSTRAINT FK_schema_item_schema FOREIGN KEY (dd_version_id, schema_id_number) REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number),
  CONSTRAINT FK_schema_item_naaccr FOREIGN KEY (dd_version_id, item_num) REFERENCES naaccr.NAACCR_ITEM(dd_version_id, item_num)
);

CREATE TABLE naaccr.REGISTRY
(
  id SMALLINT IDENTITY(1,1) PRIMARY KEY,
  code NVARCHAR(50) NOT NULL UNIQUE,
  name NVARCHAR(255) NOT NULL
);

CREATE TABLE naaccr.SCHEMA_ITEM_REQUIREMENT
(
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  registry_id SMALLINT NOT NULL,
  is_required BIT NOT NULL,
  PRIMARY KEY (dd_version_id, schema_id_number, item_num, registry_id),
  CONSTRAINT FK_schema_item_req_registry FOREIGN KEY (registry_id) REFERENCES naaccr.REGISTRY(id),
  CONSTRAINT FK_schema_item_req_item FOREIGN KEY (dd_version_id, schema_id_number, item_num) REFERENCES naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number, item_num)
);

CREATE TABLE naaccr.SCHEMA_ITEM_CODE
(
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  code NVARCHAR(255) NOT NULL,
  description NVARCHAR(MAX),
  PRIMARY KEY (dd_version_id, schema_id_number, item_num, code),
  CONSTRAINT FK_schema_item_code_item FOREIGN KEY (dd_version_id, schema_id_number, item_num) REFERENCES naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number, item_num)
);

-- Gap #3: persist the SEER staging lookup tables (the value-validation / staging
-- building blocks). Natural-keyed on (dd_version_id, table_key). Row cells are stored
-- as a JSON array of strings so the shape is portable across both supported dialects.
CREATE TABLE naaccr.STAGING_TABLE
(
  dd_version_id INT NOT NULL,
  table_key NVARCHAR(255) NOT NULL,
  name NVARCHAR(255),
  title NVARCHAR(MAX),
  subtitle NVARCHAR(MAX),
  description NVARCHAR(MAX),
  notes NVARCHAR(MAX),
  coding_guidelines NVARCHAR(MAX),
  PRIMARY KEY (dd_version_id, table_key),
  CONSTRAINT FK_staging_table_version FOREIGN KEY (dd_version_id) REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
);

CREATE TABLE naaccr.STAGING_TABLE_COLUMN
(
  dd_version_id INT NOT NULL,
  table_key NVARCHAR(255) NOT NULL,
  col_index INT NOT NULL,
  col_key NVARCHAR(255),
  col_name NVARCHAR(255),
  col_type NVARCHAR(50),
  col_source NVARCHAR(255),
  PRIMARY KEY (dd_version_id, table_key, col_index),
  CONSTRAINT FK_staging_table_column_table FOREIGN KEY (dd_version_id, table_key) REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
);

CREATE TABLE naaccr.STAGING_TABLE_ROW
(
  dd_version_id INT NOT NULL,
  table_key NVARCHAR(255) NOT NULL,
  row_index INT NOT NULL,
  cells NVARCHAR(MAX), -- JSON array of cell values, ordered by col_index
  PRIMARY KEY (dd_version_id, table_key, row_index),
  CONSTRAINT FK_staging_table_row_table FOREIGN KEY (dd_version_id, table_key) REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
);

CREATE TABLE naaccr.SCHEMA_INVOLVED_TABLE
(
  dd_version_id INT NOT NULL,
  schema_id_number NVARCHAR(255) NOT NULL,
  table_key NVARCHAR(255) NOT NULL,
  PRIMARY KEY (dd_version_id, schema_id_number, table_key),
  CONSTRAINT FK_involved_table_schema FOREIGN KEY (dd_version_id, schema_id_number) REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number),
  CONSTRAINT FK_involved_table_table FOREIGN KEY (dd_version_id, table_key) REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
);

CREATE INDEX idx_selection_schema ON naaccr.SCHEMA_SELECTION_RULE(dd_version_id, schema_id_number);
CREATE INDEX idx_item_schema ON naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number);
CREATE INDEX idx_req_schema_item ON naaccr.SCHEMA_ITEM_REQUIREMENT(dd_version_id, schema_id_number, item_num);
CREATE INDEX idx_code_schema_item ON naaccr.SCHEMA_ITEM_CODE(dd_version_id, schema_id_number, item_num);
