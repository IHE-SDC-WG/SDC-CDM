IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'naaccr')
    EXEC('CREATE SCHEMA naaccr');
GO

IF OBJECT_ID('naaccr.DATA_DICTIONARY_VERSION', 'U') IS NULL
BEGIN
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
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.DATA_DICTIONARY_VERSION')
      AND name = 'idx_dd_version_current_algorithm'
)
BEGIN
    ;WITH ranked_current AS
    (
        SELECT is_current,
               ROW_NUMBER() OVER (
                   PARTITION BY algorithm ORDER BY dd_version_id DESC
               ) AS current_rank
        FROM naaccr.DATA_DICTIONARY_VERSION
        WHERE is_current = 1
    )
    UPDATE ranked_current SET is_current = 0 WHERE current_rank > 1;

    CREATE UNIQUE INDEX idx_dd_version_current_algorithm
        ON naaccr.DATA_DICTIONARY_VERSION(algorithm)
        WHERE is_current = 1;
END
GO

IF OBJECT_ID('naaccr.STAGING_SCHEMA', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.STAGING_SCHEMA
    (
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        schema_id NVARCHAR(255) NOT NULL,
        schema_name NVARCHAR(255),
        PRIMARY KEY (dd_version_id, schema_id_number),
        CONSTRAINT FK_staging_schema_version FOREIGN KEY (dd_version_id)
            REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
    );
END
GO

IF OBJECT_ID('naaccr.SCHEMA_SELECTION_RULE', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.SCHEMA_SELECTION_RULE
    (
        schema_selection_rule_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        site NVARCHAR(MAX),
        histology NVARCHAR(MAX),
        behavior NVARCHAR(MAX),
        sex_at_birth NVARCHAR(MAX),
        discriminator_1 NVARCHAR(MAX),
        discriminator_2 NVARCHAR(MAX),
        year_dx NVARCHAR(MAX),
        CONSTRAINT FK_schema_selection_rule_schema FOREIGN KEY
            (dd_version_id, schema_id_number)
            REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number)
    );
END
GO

IF COL_LENGTH('naaccr.SCHEMA_SELECTION_RULE', 'schema_selection_rule_id') IS NULL
   AND COL_LENGTH('naaccr.SCHEMA_SELECTION_RULE', 'id') IS NOT NULL
BEGIN
    EXEC sp_rename
        'naaccr.SCHEMA_SELECTION_RULE.id',
        'schema_selection_rule_id',
        'COLUMN';
END
GO

IF OBJECT_ID('naaccr.NAACCR_ITEM', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.NAACCR_ITEM
    (
        dd_version_id INT NOT NULL,
        item_num INT NOT NULL,
        name NVARCHAR(255),
        xml_id NVARCHAR(255),
        unit NVARCHAR(50),
        decimal_places INT,
        data_type NVARCHAR(50),
        [length] INT,
        -- No NAACCR-published source supplies padding, alignment, or trim. These
        -- fields existed only in the fixed-column layouts retired after v18.
        padding NVARCHAR(50),
        alignment NVARCHAR(50),
        trim NVARCHAR(50),
        section NVARCHAR(255),
        parent_xml_element NVARCHAR(255),
        record_types NVARCHAR(MAX),
        alternate_names NVARCHAR(MAX),
        source_of_standard NVARCHAR(255),
        allowable_values NVARCHAR(MAX),
        code_description NVARCHAR(MAX),
        code_note NVARCHAR(MAX),
        item_format NVARCHAR(MAX),
        description NVARCHAR(MAX),
        rationale NVARCHAR(MAX),
        general_notes NVARCHAR(MAX),
        clarification NVARCHAR(MAX),
        version_implemented NVARCHAR(50),
        year_implemented INT,
        version_retired NVARCHAR(50),
        year_retired INT,
        date_created NVARCHAR(64),
        date_modified NVARCHAR(64),
        PRIMARY KEY (dd_version_id, item_num),
        CONSTRAINT FK_naaccr_item_version FOREIGN KEY (dd_version_id)
            REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
    );
END
GO

IF COL_LENGTH('naaccr.NAACCR_ITEM', 'record_types') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD record_types NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'alternate_names') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD alternate_names NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'source_of_standard') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD source_of_standard NVARCHAR(255) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'allowable_values') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD allowable_values NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'code_description') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD code_description NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'code_note') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD code_note NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'item_format') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD item_format NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'description') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD description NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'rationale') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD rationale NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'general_notes') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD general_notes NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'clarification') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD clarification NVARCHAR(MAX) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'version_implemented') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD version_implemented NVARCHAR(50) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'year_implemented') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD year_implemented INT NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'version_retired') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD version_retired NVARCHAR(50) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'year_retired') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD year_retired INT NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'date_created') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD date_created NVARCHAR(64) NULL;
IF COL_LENGTH('naaccr.NAACCR_ITEM', 'date_modified') IS NULL
    ALTER TABLE naaccr.NAACCR_ITEM ADD date_modified NVARCHAR(64) NULL;
GO

IF OBJECT_ID('naaccr.NAACCR_ITEM_ALLOWED_CODE', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.NAACCR_ITEM_ALLOWED_CODE
    (
        dd_version_id INT NOT NULL,
        item_num INT NOT NULL,
        code_seq INT NOT NULL,
        code NVARCHAR(255) NOT NULL,
        description NVARCHAR(MAX),
        PRIMARY KEY (dd_version_id, item_num, code_seq),
        CONSTRAINT FK_naaccr_item_allowed_code_item FOREIGN KEY
            (dd_version_id, item_num)
            REFERENCES naaccr.NAACCR_ITEM(dd_version_id, item_num)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.NAACCR_ITEM_ALLOWED_CODE')
      AND name = 'idx_naaccr_item_allowed_code_lookup'
)
BEGIN
    CREATE INDEX idx_naaccr_item_allowed_code_lookup
        ON naaccr.NAACCR_ITEM_ALLOWED_CODE(dd_version_id, item_num, code);
END
GO

IF OBJECT_ID('naaccr.NAACCR_ITEM_REGISTRY_REQUIREMENT', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.NAACCR_ITEM_REGISTRY_REQUIREMENT
    (
        dd_version_id INT NOT NULL,
        item_num INT NOT NULL,
        registry_code NVARCHAR(50) NOT NULL,
        collect_status NVARCHAR(255) NOT NULL,
        PRIMARY KEY (dd_version_id, item_num, registry_code),
        CONSTRAINT FK_naaccr_item_registry_requirement_item FOREIGN KEY
            (dd_version_id, item_num)
            REFERENCES naaccr.NAACCR_ITEM(dd_version_id, item_num)
    );
END
GO

IF OBJECT_ID('naaccr.SCHEMA_ITEM', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.SCHEMA_ITEM
    (
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        item_num INT NOT NULL,
        item_role NVARCHAR(20) NOT NULL DEFAULT 'input',
        used_for_staging BIT NOT NULL DEFAULT 0,
        default_value NVARCHAR(255),
        description NVARCHAR(MAX),
        rationale NVARCHAR(MAX),
        additional_info NVARCHAR(MAX),
        table_notes NVARCHAR(MAX),
        coding_guidelines NVARCHAR(MAX),
        PRIMARY KEY (dd_version_id, schema_id_number, item_num),
        CONSTRAINT FK_schema_item_schema FOREIGN KEY
            (dd_version_id, schema_id_number)
            REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number),
        CONSTRAINT FK_schema_item_naaccr FOREIGN KEY (dd_version_id, item_num)
            REFERENCES naaccr.NAACCR_ITEM(dd_version_id, item_num)
    );
END
GO

IF OBJECT_ID('naaccr.REGISTRY', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.REGISTRY
    (
        id SMALLINT IDENTITY(1,1) PRIMARY KEY,
        code NVARCHAR(50) NOT NULL UNIQUE,
        name NVARCHAR(255) NOT NULL
    );
END
GO

IF OBJECT_ID('naaccr.SCHEMA_ITEM_REQUIREMENT', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.SCHEMA_ITEM_REQUIREMENT
    (
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        item_num INT NOT NULL,
        registry_id SMALLINT NOT NULL,
        is_required BIT NOT NULL,
        PRIMARY KEY (dd_version_id, schema_id_number, item_num, registry_id),
        CONSTRAINT FK_schema_item_req_registry FOREIGN KEY (registry_id)
            REFERENCES naaccr.REGISTRY(id),
        CONSTRAINT FK_schema_item_req_item FOREIGN KEY
            (dd_version_id, schema_id_number, item_num)
            REFERENCES naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number, item_num)
    );
END
GO

IF OBJECT_ID('naaccr.SCHEMA_ITEM_CODE', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.SCHEMA_ITEM_CODE
    (
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        item_num INT NOT NULL,
        code NVARCHAR(255) NOT NULL,
        description NVARCHAR(MAX),
        PRIMARY KEY (dd_version_id, schema_id_number, item_num, code),
        CONSTRAINT FK_schema_item_code_item FOREIGN KEY
            (dd_version_id, schema_id_number, item_num)
            REFERENCES naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number, item_num)
    );
END
GO

IF OBJECT_ID('naaccr.STAGING_TABLE', 'U') IS NULL
BEGIN
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
        CONSTRAINT FK_staging_table_version FOREIGN KEY (dd_version_id)
            REFERENCES naaccr.DATA_DICTIONARY_VERSION(dd_version_id)
    );
END
GO

IF OBJECT_ID('naaccr.STAGING_TABLE_COLUMN', 'U') IS NULL
BEGIN
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
        CONSTRAINT FK_staging_table_column_table FOREIGN KEY
            (dd_version_id, table_key)
            REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
    );
END
GO

IF OBJECT_ID('naaccr.STAGING_TABLE_ROW', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.STAGING_TABLE_ROW
    (
        dd_version_id INT NOT NULL,
        table_key NVARCHAR(255) NOT NULL,
        row_index INT NOT NULL,
        cells NVARCHAR(MAX),
        PRIMARY KEY (dd_version_id, table_key, row_index),
        CONSTRAINT FK_staging_table_row_table FOREIGN KEY
            (dd_version_id, table_key)
            REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
    );
END
GO

IF OBJECT_ID('naaccr.SCHEMA_INVOLVED_TABLE', 'U') IS NULL
BEGIN
    CREATE TABLE naaccr.SCHEMA_INVOLVED_TABLE
    (
        dd_version_id INT NOT NULL,
        schema_id_number NVARCHAR(255) NOT NULL,
        table_key NVARCHAR(255) NOT NULL,
        PRIMARY KEY (dd_version_id, schema_id_number, table_key),
        CONSTRAINT FK_involved_table_schema FOREIGN KEY
            (dd_version_id, schema_id_number)
            REFERENCES naaccr.STAGING_SCHEMA(dd_version_id, schema_id_number),
        CONSTRAINT FK_involved_table_table FOREIGN KEY
            (dd_version_id, table_key)
            REFERENCES naaccr.STAGING_TABLE(dd_version_id, table_key)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.SCHEMA_SELECTION_RULE')
      AND name = 'idx_selection_schema'
)
    CREATE INDEX idx_selection_schema
        ON naaccr.SCHEMA_SELECTION_RULE(dd_version_id, schema_id_number);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.SCHEMA_ITEM')
      AND name = 'idx_item_schema'
)
    CREATE INDEX idx_item_schema
        ON naaccr.SCHEMA_ITEM(dd_version_id, schema_id_number);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.SCHEMA_ITEM_REQUIREMENT')
      AND name = 'idx_req_schema_item'
)
    CREATE INDEX idx_req_schema_item
        ON naaccr.SCHEMA_ITEM_REQUIREMENT(dd_version_id, schema_id_number, item_num);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.SCHEMA_ITEM_CODE')
      AND name = 'idx_code_schema_item'
)
    CREATE INDEX idx_code_schema_item
        ON naaccr.SCHEMA_ITEM_CODE(dd_version_id, schema_id_number, item_num);
GO
