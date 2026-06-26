IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'sdc') EXEC('CREATE SCHEMA sdc');
GO

IF OBJECT_ID('sdc.sdc_report', 'U') IS NULL
BEGIN
  CREATE TABLE sdc.sdc_report (
    sdc_report_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    template_instance_id INT NULL,
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
    first_seen_report_id INT NULL,
    created_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_datetime DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );

  CREATE INDEX IX_sdc_report_accession ON sdc.sdc_report(report_accession);
END
GO
