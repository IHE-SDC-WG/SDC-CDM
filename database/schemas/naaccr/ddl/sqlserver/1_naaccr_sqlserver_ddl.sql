IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'naaccr') EXEC('CREATE SCHEMA naaccr');
GO

IF OBJECT_ID('naaccr.naaccr_value', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.naaccr_value (
    naaccr_value_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    person_id INT NOT NULL,
    episode_key NVARCHAR(100) NOT NULL,
    -- logical reference to sdc.sdc_report.sdc_report_id; not an enforced FK (cross-schema/attached-DB)
    sdc_report_id INT NULL,
    report_accession NVARCHAR(100) NULL,
    schema_id_number NVARCHAR(255) NULL,
    item_num INT NOT NULL,
    value_code NVARCHAR(255) NULL,
    value_num FLOAT NULL,
    value_unit_source NVARCHAR(50) NULL,
    observation_date DATE NULL
  );

  CREATE INDEX IX_naaccr_value_person_episode
    ON naaccr.naaccr_value (person_id, episode_key);
  CREATE INDEX IX_naaccr_value_report_item
    ON naaccr.naaccr_value (report_accession, item_num);
  CREATE INDEX IX_naaccr_value_item_code
    ON naaccr.naaccr_value (item_num, value_code);
  CREATE INDEX IX_naaccr_value_sdc_report
    ON naaccr.naaccr_value (sdc_report_id);
END
GO
