# SEER SSDI / NAACCR dictionary export (TypeScript)

This script (Node 22+ required) calls the SEER Staging REST API and produces the NAACCR
dictionary data loaded into the `naaccr` schema. It has two output modes.

## Modes

**3NF mode (`SSDI_OUTPUT_3NF=1`) — authoritative for the database.** Emits the normalized CSVs
consumed by `load-3nf-to-sqlserver.ts`:
- `data_dictionary_version.csv` — one row per run: `algorithm, version, naaccr_version, source_api`.
  The loader upserts this first and stamps its `dd_version_id` onto every other table, so multiple
  NAACCR/staging versions can coexist.
- `staging_schema.csv`, `schema_selection_rule.csv`, `registry.csv`, `schema_item_requirement.csv`
- `naaccr_item.csv` — now includes `unit`, `decimal_places` (from the Staging API). The
  `data_type`/`length`/`padding`/`section` columns exist in the DDL but are populated by a later
  NAACCR Data Dictionary API enrichment step (not yet implemented — see
  `database/schemas/naaccr/FUTURE_REFERENCE_TABLES.md`).
- `schema_item.csv` — now includes `item_role` (`input` | `output`); staging **outputs**
  (derived summary stage, T/N/M, etc.) are emitted alongside SSDI inputs.
- `schema_item_code.csv` — allowable codes for both input and output items.
- `staging_table.csv`, `staging_table_column.csv`, `staging_table_row.csv`,
  `schema_involved_table.csv` — the SEER lookup-table catalog (row cells are a JSON array aligned
  to the columns), plus each schema's involved tables.

**Flat mode (default) — export-only compatibility output.** Reproduces the Java `CreateSSDIFile`
files: `schema-file.csv`, `ssdi-list-file.csv`, `ssdi-code-file.csv`. These are **not** loaded into
the database (the 3NF `schema_item` + `schema_item_code` supersede them); they exist only for
consumers that expect SEER's original flat layout.

## Quick start

```bash
# From repo root
cd tools/ssdi-ts
npm install

# 3NF export (what the loader reads)
SEER_API_KEY=your_key_here SSDI_OUTPUT_3NF=1 npm run dev

# Flat compatibility export
SEER_API_KEY=your_key_here npm run dev
```

## Options
- `SEER_API_KEY`: SEER API key (header `X-SEERAPI-Key`).
- `SSDI_ALGORITHM`: defaults to `eod_public`.
- `SSDI_VERSION`: defaults to `3.3`.
- `SSDI_NAACCR_VERSION`: optional NAACCR data-dictionary version label recorded on the
  `data_dictionary_version` row.
- `SSDI_OUTPUT_3NF`: set to `1`/`true` for 3NF mode.
- `SSDI_OUT_DIR`: defaults to `out-egs`.

Outputs are written under the given `SSDI_OUT_DIR` relative to the repository root.
```bash
# Load the 3NF CSVs into SQL Server
MSSQL_SERVER=… MSSQL_DATABASE=… MSSQL_USER=… MSSQL_PASSWORD=… CSV_DIR=out-egs \
  npx tsx src/load-3nf-to-sqlserver.ts
```

The loader replaces all dictionary rows for the resolved algorithm/version inside one
serializable transaction. Repeating a load produces the same rows, and a failed load rolls
back without leaving a partially refreshed version.
