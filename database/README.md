# Database Layout

The canonical database design is [SCHEMA_ARCHITECTURE.md](SCHEMA_ARCHITECTURE.md).

This repo now uses one physical database with three logical schemas:

- `naaccr`: NAACCR dictionary tables, raw captured values, and NAACCR to OMOP concept maps.
- `sdc`: SDC form, report, question, section, list-item, and specimen structure. It does not store answer values.
- `omop`: stock OMOP CDM 5.4 tables, kept unmodified.

The bridge step reads `naaccr` and `sdc`, then writes standard OMOP rows only. OMOP rows point back to the source through standard fields such as `note_source_value`, `measurement_event_id`, `observation_event_id`, and source value columns.

## Files

```text
database/
  schemas/
    naaccr/ddl/{sqlite,postgresql,sqlserver}/
    sdc/ddl/{sqlite,postgresql,sqlserver}/
    omop/ddl/{sqlite,postgresql,sqlserver}/
  etl/
    sqlite/
    sqlserver/
    postgresql/
```

SQLite uses attached databases named `naaccr`, `sdc`, and `omop`. PostgreSQL and SQL Server use real schemas.

## Archived Model

The previous combined OMOP-SDC model is archived under `archive/old-omop-extension-model/`. It is retained for reference only. Do not regenerate active DDL from the old OMOP-SDC fork.
