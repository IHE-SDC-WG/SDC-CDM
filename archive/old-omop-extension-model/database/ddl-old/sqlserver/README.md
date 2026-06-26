# OMOP CDM v5.4 DDL (SQL Server)

This folder contains SQL Server DDL scripts for core tables needed by the `concept` table foreign keys.

## Files
- `domain.sql`
- `vocabulary.sql`
- `concept_class.sql`
- `concept.sql`

## Order of execution
Run in this order to satisfy foreign keys:

```sql
:r domain.sql
:r vocabulary.sql
:r concept_class.sql
:r concept.sql
```

Or from any client, simply execute the file contents in that order.

## Quick checks
Confirm SQL Server and version:
```sql
SELECT @@VERSION;
SELECT SERVERPROPERTY('ProductVersion') AS ProductVersion,
       SERVERPROPERTY('Edition')        AS Edition;
```
