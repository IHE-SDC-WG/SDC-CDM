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
