IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'naaccr') EXEC('CREATE SCHEMA naaccr');
GO

-- One accession for one intake patient at one sending facility. Versions of
-- every report type in the group hang off this row.
IF OBJECT_ID('naaccr.report_group', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.report_group (
    report_group_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_report_group PRIMARY KEY,
    -- logical reference to intake.patient.patient_id; not an enforced FK (cross-schema/attached-DB)
    person_id INT NOT NULL,
    -- '' when the message names no sending facility
    sending_facility NVARCHAR(255) NOT NULL,
    report_accession NVARCHAR(100) NOT NULL,
    created_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_report_group_key UNIQUE (person_id, sending_facility, report_accession),
    CONSTRAINT CK_report_group_accession CHECK (DATALENGTH(report_accession) > 0)
  );
END
GO

-- One row per loaded, accessioned sdc_report. The first version of each type is
-- selected; only an explicit supersession moves selection, and the successor
-- records its predecessor in the same group and type.
IF OBJECT_ID('naaccr.report_version', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.report_version (
    report_version_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_report_version PRIMARY KEY,
    report_group_id INT NOT NULL
      CONSTRAINT FK_report_version_group REFERENCES naaccr.report_group(report_group_id),
    -- the report type; '' when the OBR carries no report LOINC
    report_loinc NVARCHAR(50) NOT NULL,
    -- logical references to sdc.sdc_report, intake.inbound_envelope and
    -- intake.inbound_message; not enforced FKs (cross-schema/attached-DB)
    sdc_report_id INT NOT NULL CONSTRAINT UQ_report_version_report UNIQUE,
    inbound_envelope_id BIGINT NOT NULL,
    inbound_message_id BIGINT NOT NULL,
    is_selected BIT NOT NULL,
    predecessor_sdc_report_id INT NULL,
    created_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_report_version_type_report UNIQUE (report_group_id, report_loinc, sdc_report_id),
    CONSTRAINT CK_report_version_predecessor
      CHECK (predecessor_sdc_report_id IS NULL OR predecessor_sdc_report_id <> sdc_report_id)
  );

  ALTER TABLE naaccr.report_version ADD CONSTRAINT FK_report_version_predecessor
    FOREIGN KEY (report_group_id, report_loinc, predecessor_sdc_report_id)
    REFERENCES naaccr.report_version (report_group_id, report_loinc, sdc_report_id);

  CREATE UNIQUE INDEX UX_report_version_selected
    ON naaccr.report_version (report_group_id, report_loinc) WHERE is_selected = 1;
  CREATE UNIQUE INDEX UX_report_version_predecessor
    ON naaccr.report_version (predecessor_sdc_report_id) WHERE predecessor_sdc_report_id IS NOT NULL;
END
GO
