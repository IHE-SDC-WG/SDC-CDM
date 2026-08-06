# OMOP CDM DDL provenance

The SQL Server and retained reference DDL are OHDSI Common Data Model 5.4 artifacts. Their upstream
revision is unknown. The repository first records these files in the squashed import at `c29d01d`,
which contains no upstream commit or release archive checksum.

To recover provenance during the Phase 6 re-vendor:

1. Obtain the tagged CDM 5.4 SQL Server and PostgreSQL artifacts from `OHDSI/CommonDataModel`.
2. Compare each file after normalizing line endings only.
3. Record the exact upstream commit, release tag, and source-file checksums here.
4. Review every remaining difference as a local modification before replacing a file.

## Dialect status

- SQL Server is a supported build dialect.
- The retained PostgreSQL files are reference copies only. They are excluded from
  `database/manifest.json` and are not an executable project path.
- SQLite is not an upstream OHDSI dialect. The SQLite files are hand-adapted for attached databases
  and should not be described as vendored upstream artifacts.

## Local modifications

- SQLite table names are qualified with the attached `omop` database and its surrogate-key columns
  use `PRIMARY KEY AUTOINCREMENT`.
- The `5.4-SDC` header suffix is a stale remnant of the retired combined model. No current OMOP table
  or column differs from stock CDM 5.4 because of that suffix.
