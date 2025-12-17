-- OMOP CDM v5.4 - SQL Server
-- Table: concept_class

IF OBJECT_ID('dbo.CONCEPT_CLASS', 'U') IS NOT NULL DROP TABLE dbo.CONCEPT_CLASS;
GO

CREATE TABLE dbo.CONCEPT_CLASS
(
  concept_class_id VARCHAR(20) NOT NULL,
  concept_class_name VARCHAR(255) NOT NULL,
  concept_class_concept_id INT NOT NULL,
  CONSTRAINT pk_concept_class PRIMARY KEY (concept_class_id)
);

CREATE UNIQUE INDEX ux_concept_class_concept_id ON dbo.CONCEPT_CLASS (concept_class_concept_id);
