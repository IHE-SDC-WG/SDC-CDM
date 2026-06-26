# SDC-CDM

This repository models CAP eCP / NAACCR data with a three-schema architecture:

- `naaccr` stores NAACCR dictionary metadata and raw captured values.
- `sdc` stores SDC form and report structure.
- `omop` stores unmodified OMOP CDM 5.4 rows.

The active database guidance is in [database/SCHEMA_ARCHITECTURE.md](database/SCHEMA_ARCHITECTURE.md). Generated or historical artifacts from the old combined OMOP-SDC model live in [archive/old-omop-extension-model](archive/old-omop-extension-model).

## Quick Checks

SQLite DDL can be smoke-tested with attached databases:

```bash
sqlite3 /tmp/sdc-cdm-control.db
```

Then attach `omop`, `naaccr`, and `sdc` databases and run the DDL under `database/schemas/**/ddl/sqlite/`.

The .NET SQLite implementation builds the same attached schema layout from embedded DDL resources.
