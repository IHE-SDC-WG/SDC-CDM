# Database Layout

The canonical database design is [SCHEMA_ARCHITECTURE.md](SCHEMA_ARCHITECTURE.md).

This repo now uses one physical database with three logical schemas:

- `naaccr`: NAACCR dictionary tables, raw captured values, and NAACCR to OMOP concept maps.
- `sdc`: SDC form, report, question, section, list-item, and specimen structure. The SDC XML path stores submitted answers in `sdc_form_answer`; the eCP/HL7 path stores answers in `naaccr_value`.
- `omop`: stock OMOP CDM 5.4 tables, kept unmodified.

The bridge step reads `naaccr` and `sdc`, then writes standard OMOP rows only. OMOP rows point back to the source through standard fields such as `note_source_value`, `measurement_event_id`, `observation_event_id`, and source value columns.

## Files

```text
database/
  vocab/
    README.md
  schemas/
    naaccr/ddl/{sqlite,postgresql,sqlserver}/
    sdc/ddl/{sqlite,postgresql,sqlserver}/
    omop/ddl/{sqlite,postgresql,sqlserver}/
  etl/
    sqlite/
    sqlserver/
```

SQLite uses attached databases named `naaccr`, `sdc`, and `omop`. PostgreSQL and SQL Server use real schemas.
The repository currently provides bridge ETL for SQLite and SQL Server. PostgreSQL schema
initialization is complete, but PostgreSQL bridge ETL is deferred.

## OMOP Vocabulary Data

The OMOP DDL creates empty vocabulary tables. Download an OHDSI Athena bundle,
extract its nine vocabulary files under [`vocab/`](vocab/README.md), and run
`tools/load_athena_vocab.py` before importing clinical data. The downloaded
files are ignored by Git and remain subject to the licenses of their individual
vocabularies.

## Historical Model

The previous combined OMOP-SDC model is available in Git at commit
[`6304b3e`](https://github.com/IHE-SDC-WG/SDC-CDM/tree/6304b3e). It is retained
in repository history for reference only. Do not regenerate active DDL from the
old OMOP-SDC fork.
