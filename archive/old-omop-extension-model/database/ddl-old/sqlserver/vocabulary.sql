-- OMOP CDM v5.4 - SQL Server
-- Table: vocabulary

IF OBJECT_ID('dbo.VOCABULARY', 'U') IS NOT NULL DROP TABLE dbo.VOCABULARY;
GO

CREATE TABLE dbo.VOCABULARY
(
  vocabulary_id VARCHAR(20) NOT NULL,
  vocabulary_name VARCHAR(255) NOT NULL,
  vocabulary_reference VARCHAR(255) NULL,
  vocabulary_version VARCHAR(255) NULL,
  vocabulary_concept_id INT NOT NULL,
  CONSTRAINT pk_vocabulary PRIMARY KEY (vocabulary_id)
);

CREATE UNIQUE INDEX ux_vocabulary_concept_id ON dbo.VOCABULARY (vocabulary_concept_id);
