# NAACCR → OMOP 5.4 (SQL Server) Runbook

This folder contains SQL Server scripts to seed a local NAACCR 2026 vocabulary and scaffold a SQL-only ETL into OMOP 5.4, anchored by Oncology Episodes.

## Prerequisites
- OMOP CDM v5.4 tables deployed in schema `dbo` (or replace `@cdmDatabaseSchema` in scripts).
- NAACCR 3NF metadata tables in schema `cap` (`cap.NAACCR_ITEM`, `cap.SCHEMA_ITEM_CODE`, `cap.REGISTRY`).
- No standard OMOP vocabularies are required initially; scripts seed local placeholder concepts.

## Scripts
- `naaccr_omop_vocab.sql`
  - Seeds vocabulary `NAACCR2026`, concept classes (Items, Values, Registry, Episode Type, Field, Type Concept).
  - Assigns persistent concept_ids for NAACCR items and values into `cap.NAACCR_CONCEPT_MAP` and `cap.NAACCR_VALUE_CONCEPT_MAP`.
  - Inserts concepts, item↔value relationships, and `source_to_concept_map` entries.
  - Seeds Episode type (`NAACCR_CANCER_EPISODE`) and field concepts for episode_event (`FIELD_OBSERVATION_ID`, `FIELD_MEASUREMENT_ID`).
  - Seeds a local type concept `TYPE_NAACCR_DERIVED` used for `observation_type_concept_id` and `measurement_type_concept_id`.

- `naaccr_to_omop_etl.sql`
  - Expects a staging `#naaccr_source` temp table with: `person_id`, `episode_key`, `schema_id_number`, `item_num`, `value_code`, `value_num`, `value_unit_source`, `observation_date`.
  - Creates/Upserts Episodes per `(person_id, episode_key)` using `NAACCR_CANCER_EPISODE`.
  - Loads:
    - Categorical items → `observation` (value_as_concept_id from NAACCR Value concepts).
    - Numeric items → `measurement` (value_as_number; carries `unit_source_value`).
  - Links Observations and Measurements to Episodes via `episode_event` using the field concepts.

- `../../naaccr_omop/naaccr_omop_extension_mapping_spec.json`
  - JSON mapping specification generated from the NAACCR extension-table workbooks in `NAACRToOMOPmaps/`.
  - Captures concept-class extension tables, table grain, foreign-key expectations, item-level storage targets, and the `NAACCR_PERSON` proposal.
  - This is the neutral JSON input consumed by the in-repo `phenoml-workflows/` package without adding a PhenoML dependency to the SQL Server ETL scripts.

- `report_naaccr_omop_vocab_ingestion.sql`
  - Generates a comprehensive report of NAACCR → OMOP vocabulary ingestion with no patient data required.
  - Summarizes: vocabulary presence, concept classes/domains, NAACCR Item/Value mappings (`cap.NAACCR_CONCEPT_MAP`, `cap.NAACCR_VALUE_CONCEPT_MAP`), OMOP concept counts and ranges, item↔value relationships (`Has value` / `Value of`), `source_to_concept_map` entries, special seed concepts (Episode Type, Field, Type), and integrity checks for missing concepts/relationships.
  - Useful for leadership review to verify that seeding and mappings are complete before any ETL runs.

## Run Order
1. Deploy OMOP CDM v5.4 (SQL Server) and create `cap` schema with NAACCR 3NF metadata.
2. Execute `naaccr_omop_vocab.sql`.
3. (Optional, no patient data needed) Execute `report_naaccr_omop_vocab_ingestion.sql` to verify vocabulary ingestion and mappings.
3. Prepare case-level data into `#naaccr_source` (or adapt the script to a real staging table).
4. Execute `naaccr_to_omop_etl.sql`.

## Notes
- Concept IDs use the local range `2,500,000,000+` and are persisted to ensure repeatable runs.
- Units: `unit_concept_id` is left `NULL` initially; `unit_source_value` is stored. When standard vocabularies are available, map units accordingly.
- Sequences/IDs: If your OMOP tables use identity columns rather than sequences, remove explicit `NEXT VALUE FOR seq_*` and rely on identity assignments.
- Episode key: Provide a stable tumor/episode identifier in `#naaccr_source.episode_key`. If none exists, derive one consistently (e.g., site + histology + diagnosis date).

## Contact
For questions on item classification (Observation vs Measurement) or enriching Episodes (e.g., SNOMED disease concepts), please ask and we can extend the scripts accordingly.
