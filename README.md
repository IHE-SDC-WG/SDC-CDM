# SDC-CDM

This repository models CAP eCP / NAACCR data with a three-schema architecture:

- `naaccr` stores NAACCR dictionary metadata and raw captured values.
- `sdc` stores SDC form and report structure.
- `omop` stores unmodified OMOP CDM 5.4 rows.

The active database guidance is in [database/SCHEMA_ARCHITECTURE.md](database/SCHEMA_ARCHITECTURE.md), with entity-relationship diagrams in [diagrams/](diagrams/) — start with [`three-schema-overview.mmd`](diagrams/three-schema/three-schema-overview.mmd). Historical artifacts from the retired combined OMOP-SDC model are available in Git at commit [`6304b3e`](https://github.com/IHE-SDC-WG/SDC-CDM/tree/6304b3e).

## OMOP Vocabularies

Create the three database schemas, then load an OHDSI Athena vocabulary extract
before importing clinical data. Downloaded vocabulary files belong in
[`database/vocab/`](database/vocab/README.md), where they are ignored by Git.
That README explains how to request a bundle from Athena, comply with the
individual vocabulary licenses, validate the extract, and run the loader for
SQLite, PostgreSQL, or SQL Server.

For example, validate an extracted bundle without connecting to a database:

```bash
python3 tools/load_athena_vocab.py \
  --vocab-dir database/vocab \
  --check-only
```

The Athena files are not covered by this repository's license and must not be
committed or redistributed through this repository.

## Quick Checks

SQLite DDL can be smoke-tested with attached databases:

```bash
sqlite3 /tmp/sdc-cdm-control.db
```

Then attach `omop`, `naaccr`, and `sdc` databases and run the DDL under `database/schemas/**/ddl/sqlite/`.

The .NET SQLite implementation builds the same attached schema layout from embedded DDL resources.

## End-to-end quickstart

1. Build the three schemas for your database dialect. The DDL is under
   `database/schemas/{omop,naaccr,sdc}/ddl/<dialect>/`. PostgreSQL and SQL Server use real
   schemas. SQLite attaches separate `omop`, `naaccr`, and `sdc` database files; `BuildSchema()`
   loads the SQLite DDL resources and performs those attachments.
2. Load the Athena vocabulary files by following
   [`database/vocab/README.md`](database/vocab/README.md). Apply any repo-specific NAACCR
   vocabulary additions after the standard Athena load.
3. Import an HL7 V2 / NAACCR message. The importer writes raw answers to
   `naaccr.naaccr_value` and the report header to `sdc.sdc_report`.
4. Run `database/etl/<dialect>/1_naaccr_sdc_to_omop.sql` to create the report note and its
   measurements. For SQLite, `BridgeNaaccrSdcToOmop()` runs the embedded bridge script.

The compact code sample below uses the built-in SQLite bridge seed concepts. A
complete OMOP deployment should perform step 2 before running the import and
bridge.

```csharp
using System.IO;
using SdcCdm;
using SdcCdmInSqlite;

var store = new SdcCdmInSqlite("quickstart.db", overwrite: true);
store.BuildSchema();

var message = File.ReadAllText("sample_data/naaccr_v2/obx-Adrenal.hl7");
NAACCRVolVImporter.ImportNaaccrVolV(store, message);
store.BridgeNaaccrSdcToOmop();
```

5. Inspect the bridged rows with the standard OMOP note anchor. More examples are in
   `database/SCHEMA_ARCHITECTURE.md` and `sample_data/ecp_query_examples.sql`.

```sql
SELECT m.measurement_id,
       n.note_source_value AS report_accession,
       m.measurement_source_value AS item_num,
       m.value_as_number,
       m.value_as_concept_id,
       m.value_source_value
FROM omop.measurement m
JOIN omop.note n ON n.note_id = m.measurement_event_id
WHERE m.meas_event_field_concept_id = 1147289
ORDER BY m.measurement_id;
```

6. For SQL Server, optionally run
   `database/etl/sqlserver/validate_naaccr_sdc_to_omop.sql` after the bridge.
