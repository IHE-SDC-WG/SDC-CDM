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
    item_num INT NULL,
    ecp_code NVARCHAR(50) NULL,
    obx_sub_id NVARCHAR(255) NULL,
    value_code NVARCHAR(255) NULL,
    value_num FLOAT NULL,
    value_text NVARCHAR(MAX) NULL,
    value_unit_source NVARCHAR(50) NULL,
    observation_date DATE NULL,
    -- Gap #1: the dictionary version this answer was coded against. Nullable so existing
    -- import paths that do not yet supply it keep working; populate going forward.
    dd_version_id INT NULL,
    -- logical reference to intake.inbound_envelope.inbound_envelope_id; not an enforced FK (cross-schema/attached-DB)
    inbound_envelope_id BIGINT NULL,
    CONSTRAINT CK_naaccr_value_identifier CHECK (
      (item_num IS NOT NULL AND ecp_code IS NULL)
      OR (item_num IS NULL AND ecp_code IS NOT NULL AND LEN(ecp_code) > 0)
    )
  );

  CREATE INDEX IX_naaccr_value_person_episode
    ON naaccr.naaccr_value (person_id, episode_key);
  CREATE INDEX IX_naaccr_value_report_item
    ON naaccr.naaccr_value (report_accession, item_num);
  CREATE INDEX IX_naaccr_value_item_code
    ON naaccr.naaccr_value (item_num, value_code);
  CREATE INDEX IX_naaccr_value_report_ecp
    ON naaccr.naaccr_value (report_accession, ecp_code);
  CREATE INDEX IX_naaccr_value_sdc_report
    ON naaccr.naaccr_value (sdc_report_id);
END
GO

IF COL_LENGTH('naaccr.naaccr_value', 'inbound_envelope_id') IS NULL
    ALTER TABLE naaccr.naaccr_value ADD inbound_envelope_id BIGINT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('naaccr.naaccr_value') AND name = 'IX_naaccr_value_inbound_envelope'
)
    CREATE INDEX IX_naaccr_value_inbound_envelope ON naaccr.naaccr_value (inbound_envelope_id);
GO

-- Bridge script 3 provenance: one link per naaccr_value bridged into omop.measurement or
-- omop.observation. event_id is a logical reference into the table named by event_table
-- (OMOP holds no crosswalk). The bridge owns only clinical rows named here. route,
-- value_target, and is_truncated record how the row was routed and typed, so unmapped,
-- collision-suppressed, and truncated values stay reportable.
IF OBJECT_ID('naaccr.value_event', 'U') IS NULL
BEGIN
  CREATE TABLE naaccr.value_event (
    naaccr_value_id INT NOT NULL,
    event_table VARCHAR(20) NOT NULL,
    event_id INT NOT NULL,
    route VARCHAR(30) NOT NULL,
    value_target VARCHAR(30) NOT NULL,
    is_truncated BIT NOT NULL,
    CONSTRAINT PK_value_event PRIMARY KEY (naaccr_value_id),
    CONSTRAINT FK_value_event_naaccr_value FOREIGN KEY (naaccr_value_id)
      REFERENCES naaccr.naaccr_value (naaccr_value_id),
    CONSTRAINT UQ_value_event_event UNIQUE (event_table, event_id),
    CONSTRAINT CK_value_event_table CHECK (event_table IN ('measurement', 'observation')),
    CONSTRAINT CK_value_event_route CHECK (route IN (
      'target_domain', 'default_ecp_code', 'default_no_map',
      'default_no_target', 'default_other_domain'
    )),
    CONSTRAINT CK_value_event_value_target CHECK (value_target IN (
      'none', 'mapped', 'unmapped', 'collision_suppressed'
    ))
  );
END
GO
