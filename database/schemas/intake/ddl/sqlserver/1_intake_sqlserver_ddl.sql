IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'intake') EXEC('CREATE SCHEMA intake');
GO

IF OBJECT_ID('intake.inbound_message', 'U') IS NULL
BEGIN
    CREATE TABLE intake.inbound_message (
        inbound_message_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        source_format NVARCHAR(50) NOT NULL,
        media_type NVARCHAR(255) NOT NULL,
        raw_blob VARBINARY(MAX) NOT NULL,
        raw_sha256 CHAR(64) NOT NULL,
        byte_length BIGINT NOT NULL CHECK (byte_length >= 0),
        is_content_duplicate BIT NOT NULL DEFAULT 0,
        first_seen_inbound_message_id BIGINT NULL
            REFERENCES intake.inbound_message(inbound_message_id),
        received_datetime DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        received_by NVARCHAR(255) NULL,
        message_control_id NVARCHAR(255) NULL,
        sending_facility NVARCHAR(255) NULL,
        message_profile NVARCHAR(255) NULL,
        envelope_json NVARCHAR(MAX) NULL,
        envelope_version NVARCHAR(20) NULL,
        parser_name NVARCHAR(255) NULL,
        parser_version NVARCHAR(100) NULL,
        parse_status NVARCHAR(20) NOT NULL DEFAULT 'pending'
            CHECK (parse_status IN ('pending', 'parsed', 'failed', 'quarantined')),
        parse_error NVARCHAR(MAX) NULL,
        CHECK (LEN(raw_sha256) = 64),
        CHECK (
            (is_content_duplicate = 0 AND first_seen_inbound_message_id IS NULL)
            OR (is_content_duplicate = 1 AND first_seen_inbound_message_id IS NOT NULL)
        )
    );
    CREATE INDEX IX_inbound_message_sha256
        ON intake.inbound_message(raw_sha256);
    CREATE INDEX IX_inbound_message_control_id
        ON intake.inbound_message(message_control_id);
END
GO

IF OBJECT_ID('intake.inbound_message_diagnostic', 'U') IS NULL
BEGIN
    CREATE TABLE intake.inbound_message_diagnostic (
        inbound_message_diagnostic_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        inbound_message_id BIGINT NOT NULL REFERENCES intake.inbound_message(inbound_message_id),
        severity NVARCHAR(20) NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
        code NVARCHAR(100) NOT NULL,
        detail NVARCHAR(MAX) NOT NULL,
        created_datetime DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_inbound_message_diagnostic_message
        ON intake.inbound_message_diagnostic(inbound_message_id);
END
GO

IF OBJECT_ID('intake.patient', 'U') IS NULL
BEGIN
    CREATE TABLE intake.patient (
        patient_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        person_source_value NVARCHAR(255) NOT NULL,
        assigning_authority NVARCHAR(100) NOT NULL DEFAULT '',
        birth_year INT NULL,
        birth_month INT NULL,
        birth_day INT NULL,
        gender_source_value NVARCHAR(50) NULL,
        first_seen_inbound_message_id BIGINT NULL
            REFERENCES intake.inbound_message(inbound_message_id),
        created_datetime DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        UNIQUE (assigning_authority, person_source_value),
        CHECK (birth_year IS NULL OR birth_year BETWEEN 1 AND 9999),
        CHECK (birth_month IS NULL OR birth_month BETWEEN 1 AND 12),
        CHECK (birth_day IS NULL OR birth_day BETWEEN 1 AND 31),
        CHECK (birth_year IS NOT NULL OR birth_month IS NULL),
        CHECK (birth_month IS NOT NULL OR birth_day IS NULL)
    );
END
GO
