IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'etl') EXEC('CREATE SCHEMA etl');
GO

IF OBJECT_ID('etl.concept_constant', 'U') IS NULL
BEGIN
    CREATE TABLE etl.concept_constant (
        constant_name NVARCHAR(255) NOT NULL PRIMARY KEY,
        concept_id INT NOT NULL,
        vocabulary_id NVARCHAR(20) NOT NULL,
        concept_code NVARCHAR(255) NOT NULL,
        resolved_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO

IF OBJECT_ID('etl.run', 'U') IS NULL
BEGIN
    CREATE TABLE etl.run (
        run_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        command NVARCHAR(100) NOT NULL,
        dialect NVARCHAR(20) NOT NULL CHECK (dialect IN ('sqlite', 'sqlserver')),
        status NVARCHAR(20) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
        started_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        completed_at DATETIME2(3) NULL,
        error_message NVARCHAR(MAX) NULL
    );
    CREATE INDEX IX_etl_run_status ON etl.run(status, started_at);
END
GO

IF OBJECT_ID('etl.schema_migration', 'U') IS NULL
BEGIN
    CREATE TABLE etl.schema_migration (
        migration_path NVARCHAR(450) NOT NULL PRIMARY KEY,
        file_sha256 CHAR(64) NOT NULL,
        previous_sha256 CHAR(64) NULL,
        applied_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        last_run_id BIGINT NULL REFERENCES etl.run(run_id),
        CHECK (LEN(file_sha256) = 64),
        CHECK (previous_sha256 IS NULL OR LEN(previous_sha256) = 64)
    );
END
GO

-- How the bridge derived each omop.observation_period row, keyed by its
-- observation_period_id, and the naaccr.naaccr_value rows that set its start
-- and end dates. Logical references to omop and naaccr; not enforced FKs.
IF OBJECT_ID('etl.observation_period_derivation', 'U') IS NULL
BEGIN
    CREATE TABLE etl.observation_period_derivation (
        observation_period_id INT NOT NULL PRIMARY KEY,
        person_id INT NOT NULL UNIQUE,
        derivation NVARCHAR(40) NOT NULL
            CHECK (derivation IN ('naaccr_diagnosis_to_last_contact', 'clinical_date_span')),
        start_naaccr_value_id INT NOT NULL,
        end_naaccr_value_id INT NOT NULL
    );
END
GO

-- The cdm_source seed row of the current bridge run. Python replaces it inside
-- the run's data transaction; the bridge adds the vocabulary version and the
-- CDM version concept when it writes omop.cdm_source.
IF OBJECT_ID('etl.cdm_source_seed', 'U') IS NULL
BEGIN
    CREATE TABLE etl.cdm_source_seed (
        cdm_source_name NVARCHAR(255) NOT NULL,
        cdm_source_abbreviation NVARCHAR(25) NOT NULL,
        cdm_holder NVARCHAR(255) NOT NULL,
        source_description NVARCHAR(MAX) NULL,
        source_documentation_reference NVARCHAR(255) NULL,
        cdm_etl_reference NVARCHAR(255) NULL,
        source_release_date DATE NOT NULL,
        cdm_release_date DATE NOT NULL,
        cdm_version NVARCHAR(10) NOT NULL
    );
END
GO
