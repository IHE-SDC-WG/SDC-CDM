# C# SDC XML library

The C# surface is limited to SDC template and form-response persistence in SQLite:

- `SdcCdm.Sdc` contains `TemplateImporter`, `TemplateRowDataImporter`, `XmlFormImporter`, the
  trimmed `ISdcCdm` contract, and `SdcSqliteStore`.
- `SdcCdm.Sdc.Tests` verifies template metadata, instance linkage, selected list items, nested
  questions, typed string/integer/int/decimal responses, and unanswered-value handling.

It does not contain an HL7 importer, FHIR importer/exporter, OMOP bridge, pipeline CLI, full
database builder, or SQL Server store. Those retired paths must not be reintroduced as hidden C#
dependencies; Python owns the database pipeline.

## Requirements

- .NET 10.x SDK

## Build and test

From the repository root:

```bash
dotnet build src/csharp/SdcCdm.sln
dotnet test src/csharp/SdcCdm.Sdc.Tests
```

`SdcSqliteStore.BuildSchema()` attaches only an `sdc` SQLite database and applies the embedded
`database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql` resource. It does not read
`database/manifest.json` and does not require Python. The Python build likewise does not require
.NET.

The complete database build instructions are in the repository
[`README.md`](../../README.md) and [`database/README.md`](../../database/README.md).
