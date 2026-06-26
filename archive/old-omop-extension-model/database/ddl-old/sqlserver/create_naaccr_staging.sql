/*
  Create NAACCR staging table for ETL
  Purpose: Provide a permanent source for the ETL to populate #naaccr_source
*/

IF OBJECT_ID('dbo.naaccr_staging') IS NULL
BEGIN
  CREATE TABLE dbo.naaccr_staging
  (
    person_id INT NOT NULL,
    episode_key NVARCHAR(100) NOT NULL,
    schema_id_number NVARCHAR(255) NULL,
    item_num INT NOT NULL,
    value_code NVARCHAR(255) NULL,
    value_num FLOAT NULL,
    value_unit_source NVARCHAR(50) NULL,
    observation_date DATE NULL
  );

  -- Helpful indexes for ETL joins & grouping
  CREATE INDEX IX_naaccr_staging_person_episode
    ON dbo.naaccr_staging (person_id, episode_key);

  CREATE INDEX IX_naaccr_staging_item_code
    ON dbo.naaccr_staging (item_num, value_code);

  CREATE INDEX IX_naaccr_staging_obs_date
    ON dbo.naaccr_staging (observation_date);
END
GO

-- Example: verify empty table
SELECT TOP 1
  *
FROM dbo.naaccr_staging;
