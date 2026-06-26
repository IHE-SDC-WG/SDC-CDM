-- OMOP CDM v5.4 - SQL Server
-- Table: concept

IF OBJECT_ID('dbo.concept', 'U') IS NOT NULL DROP TABLE dbo.concept;
GO

CREATE TABLE dbo.concept (
  concept_id          INT           NOT NULL,
  concept_name        VARCHAR(255)  NOT NULL,
  domain_id           VARCHAR(20)   NOT NULL,
  vocabulary_id       VARCHAR(20)   NOT NULL,
  concept_class_id    VARCHAR(20)   NOT NULL,
  standard_concept    CHAR(1)       NULL,
  concept_code        VARCHAR(50)   NOT NULL,
  valid_start_date    DATE          NOT NULL,
  valid_end_date      DATE          NOT NULL,
  invalid_reason      CHAR(1)       NULL,
  CONSTRAINT pk_concept PRIMARY KEY (concept_id),
  CONSTRAINT fk_concept_domain        FOREIGN KEY (domain_id)        REFERENCES dbo.domain (domain_id),
  CONSTRAINT fk_concept_vocabulary    FOREIGN KEY (vocabulary_id)    REFERENCES dbo.vocabulary (vocabulary_id),
  CONSTRAINT fk_concept_concept_class FOREIGN KEY (concept_class_id) REFERENCES dbo.concept_class (concept_class_id)
);

-- Recommended indexes
CREATE INDEX idx_concept_code_vocab   ON dbo.concept (concept_code, vocabulary_id);
CREATE INDEX idx_concept_vocab_class  ON dbo.concept (vocabulary_id, concept_class_id);
CREATE INDEX idx_concept_domain       ON dbo.concept (domain_id);
