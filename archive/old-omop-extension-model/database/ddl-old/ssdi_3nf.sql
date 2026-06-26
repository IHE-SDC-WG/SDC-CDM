

IF NOT EXISTS (SELECT *
FROM sys.schemas
WHERE name = 'cap') EXEC('CREATE SCHEMA cap');

CREATE TABLE cap.STAGING_SCHEMA
(
  schema_id_number NVARCHAR(255) PRIMARY KEY,
  schema_id NVARCHAR(255) NOT NULL,
  schema_name NVARCHAR(255)
);

CREATE TABLE cap.SCHEMA_SELECTION_RULE
(
  id BIGINT IDENTITY(1,1) PRIMARY KEY,
  schema_id_number NVARCHAR(255) NOT NULL,
  site NVARCHAR(MAX),
  histology NVARCHAR(MAX),
  behavior NVARCHAR(MAX),
  sex_at_birth NVARCHAR(MAX),
  discriminator_1 NVARCHAR(MAX),
  discriminator_2 NVARCHAR(MAX),
  year_dx NVARCHAR(MAX),
  CONSTRAINT FK_schema_selection_rule_schema FOREIGN KEY (schema_id_number) REFERENCES cap.STAGING_SCHEMA(schema_id_number)
);

CREATE TABLE cap.NAACCR_ITEM
(
  item_num INT PRIMARY KEY,
  name NVARCHAR(255),
  xml_id NVARCHAR(255)
);

CREATE TABLE cap.SCHEMA_ITEM
(
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  used_for_staging BIT NOT NULL DEFAULT 0,
  default_value NVARCHAR(255),
  description NVARCHAR(MAX),
  rationale NVARCHAR(MAX),
  additional_info NVARCHAR(MAX),
  table_notes NVARCHAR(MAX),
  coding_guidelines NVARCHAR(MAX),
  PRIMARY KEY (schema_id_number, item_num),
  CONSTRAINT FK_schema_item_schema FOREIGN KEY (schema_id_number) REFERENCES cap.STAGING_SCHEMA(schema_id_number),
  CONSTRAINT FK_schema_item_naaccr FOREIGN KEY (item_num) REFERENCES cap.NAACCR_ITEM(item_num)
);

CREATE TABLE cap.REGISTRY
(
  id SMALLINT IDENTITY(1,1) PRIMARY KEY,
  code NVARCHAR(50) NOT NULL UNIQUE,
  name NVARCHAR(255) NOT NULL
);

CREATE TABLE cap.SCHEMA_ITEM_REQUIREMENT
(
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  registry_id SMALLINT NOT NULL,
  is_required BIT NOT NULL,
  PRIMARY KEY (schema_id_number, item_num, registry_id),
  CONSTRAINT FK_schema_item_req_registry FOREIGN KEY (registry_id) REFERENCES cap.REGISTRY(id),
  CONSTRAINT FK_schema_item_req_item FOREIGN KEY (schema_id_number, item_num) REFERENCES cap.SCHEMA_ITEM(schema_id_number, item_num)
);

CREATE TABLE cap.SCHEMA_ITEM_CODE
(
  schema_id_number NVARCHAR(255) NOT NULL,
  item_num INT NOT NULL,
  code NVARCHAR(255) NOT NULL,
  description NVARCHAR(MAX),
  PRIMARY KEY (schema_id_number, item_num, code),
  CONSTRAINT FK_schema_item_code_item FOREIGN KEY (schema_id_number, item_num) REFERENCES cap.SCHEMA_ITEM(schema_id_number, item_num)
);

CREATE INDEX idx_selection_schema ON cap.SCHEMA_SELECTION_RULE(schema_id_number);
CREATE INDEX idx_item_schema ON cap.SCHEMA_ITEM(schema_id_number);
CREATE INDEX idx_req_schema_item ON cap.SCHEMA_ITEM_REQUIREMENT(schema_id_number, item_num);
CREATE INDEX idx_code_schema_item ON cap.SCHEMA_ITEM_CODE(schema_id_number, item_num);
