# SDC-CDM

This repository models CAP eCP / NAACCR data with a three-schema architecture:

- `naaccr` stores NAACCR dictionary metadata and raw captured values.
- `sdc` stores SDC form and report structure.
- `omop` stores unmodified OMOP CDM 5.4 rows.

The active database guidance is in [database/SCHEMA_ARCHITECTURE.md](database/SCHEMA_ARCHITECTURE.md). Historical artifacts from the retired combined OMOP-SDC model are available in Git at commit [`6304b3e`](https://github.com/IHE-SDC-WG/SDC-CDM/tree/6304b3e).

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
2. Import an HL7 V2 / NAACCR message. The importer writes raw answers to
   `naaccr.naaccr_value` and the report header to `sdc.sdc_report`.
3. Run `database/etl/<dialect>/1_naaccr_sdc_to_omop.sql` to create the report note and its
   measurements. For SQLite, `BridgeNaaccrSdcToOmop()` runs the embedded bridge script.

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

4. Inspect the bridged rows with the standard OMOP note anchor. More examples are in
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

5. For SQL Server, optionally run
   `database/etl/sqlserver/validate_naaccr_sdc_to_omop.sql` after the bridge.
