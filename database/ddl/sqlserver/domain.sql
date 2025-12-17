-- OMOP CDM v5.4 - SQL Server
-- Table: domain

IF OBJECT_ID('dbo.DOMAIN', 'U') IS NOT NULL DROP TABLE dbo.DOMAIN;
GO

CREATE TABLE dbo.DOMAIN
(
  domain_id VARCHAR(20) NOT NULL,
  domain_name VARCHAR(255) NOT NULL,
  domain_concept_id INT NOT NULL,
  CONSTRAINT pk_domain PRIMARY KEY (domain_id)
);

CREATE UNIQUE INDEX ux_domain_concept_id ON dbo.DOMAIN (domain_concept_id);
