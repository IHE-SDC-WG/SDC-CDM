# NAACCR dictionary and SSDI fetch, load, and verification

The Python `dict` and `ssdi` commands fetch two parts of one versioned NAACCR data set from
SEER\*API. Both producers write deterministic CSVs, each with its own generation stamp, for the same
Python loader. The API key is used only by the two fetch commands; builds, loads, verification, and
tests remain offline.

## Fetch commands and flags

Both fetch commands inherit required `--dialect` for a uniform CLI shape but never open a database.
They require `SEER_API_KEY` and exit 2 before any request when it is missing.

| Command | NAACCR flag | Algorithm | Staging version | Output directory |
| --- | --- | --- | --- | --- |
| `dict fetch` | `--version`, default `25` | `--algorithm`, default `eod_public` | `--staging-version`, default `3.3` | `--csv-dir`, default repository-root `out-egs/` |
| `ssdi fetch` | required `--naaccr-version` | `--algorithm`, default `eod_public` | `--staging-version`, default `3.3` | `--csv-dir`, default repository-root `out-egs/` |

`SSDI_ALGORITHM` and `SSDI_VERSION` are not read. Pass non-default values as flags to both commands.
`dict fetch` records its generation in `data_dictionary_version.csv` and `ssdi fetch` records its
generation in `ssdi_version.csv`; `dict load` refuses a directory whose two stamps disagree on
algorithm, staging version, or NAACCR version. `SEER_API_KEY` is the only fetch credential.

```bash
export SEER_API_KEY='your key'

python -m sdc_cdm dict fetch --dialect sqlite --version 26
python -m sdc_cdm ssdi fetch --dialect sqlite --naaccr-version 26
```

The same commands can target an explicit directory from any working directory:

```bash
python -m sdc_cdm dict fetch --dialect sqlite --version 26 --csv-dir /tmp/naaccr-26
python -m sdc_cdm ssdi fetch --dialect sqlite --naaccr-version 26 \
  --csv-dir /tmp/naaccr-26
```

## Endpoint order and request bounds

`dict fetch` calls:

1. `GET /rest/naaccr/versions`
2. `GET /rest/naaccr/{version}`
3. `GET /rest/naaccr/{version}/{key}` once per index entry

The detail key is `entry.get("id") or entry["item"]` because retired index entries can omit `id`.

`ssdi fetch` calls:

1. `GET /rest/naaccr/versions` and validates `--naaccr-version`
2. `GET /rest/staging/{algorithm}/{staging-version}/schemas`
3. `GET /rest/staging/{algorithm}/{staging-version}/schema/{id}` once per unique projection ID
4. `GET /rest/staging/{algorithm}/{staging-version}/table/{id}` once per unique involved table

NAACCR validation finishes before any staging request. Schema and table details use eight concurrent
requests by default, capped at 16. Dictionary items use the same bound. The shared transport retries
HTTP 429, 500, 502, 503, and 504 responses, URL errors, and timeouts up to four times. It honours
`Retry-After`; authentication and not-found errors are not retried.

Schemas are emitted in numeric `naaccr_schema_id` order. A schema without that output ID is fetched
once and omitted. Involved tables include each retained schema's selection table plus every input
and output table. Table catalog and link order first preserves the former producer order: selection
table, SSDI inputs by item number, then API-order numeric NAACCR outputs. Tables on non-NAACCR
outputs follow that prefix. Non-SSDI input tables are appended in sorted-schema and API-input order.
Shared table IDs are fetched and emitted once.

## CSV contract

All CSVs use UTF-8 without a BOM, LF endings, always-quoted fields, empty cells for null scalar
values, and atomic replacement. Embedded newlines and quotes are retained. Table row cells use
compact JSON arrays, including `null` positions.

`dict fetch` writes three dictionary files plus the dictionary generation row that it alone owns:

| File | Contents |
| --- | --- |
| `naaccr_item_dictionary.csv` | One scalar item row, with compact JSON `record_types` and `alternate_names` cells |
| `naaccr_item_allowed_code.csv` | Ordered allowed codes; zero-based `code_seq` preserves duplicates |
| `naaccr_item_registry_requirement.csv` | Present SEER, NPCR, COC, and CCCR collection text |
| `data_dictionary_version.csv` | One algorithm, staging version, NAACCR version, and source API row |

`ssdi fetch` writes these twelve files:

| File | Contents |
| --- | --- |
| `ssdi_version.csv` | One-row SSDI generation stamp with the same four columns; must match `data_dictionary_version.csv` |
| `staging_schema.csv` | Numeric schema ID, API schema ID, and name |
| `schema_selection_rule.csv` | Site, histology, behavior, sex, discriminators, and diagnosis-year ranges |
| `naaccr_item.csv` | SSDI input and NAACCR output items with unit and decimal metadata |
| `schema_item.csv` | SSDI inputs and numeric NAACCR outputs; input wins on collisions |
| `registry.csv` | Static SEER, NPCR, COC, and CCCR rows |
| `schema_item_requirement.csv` | Four lowercase-Boolean registry rows per SSDI input |
| `schema_item_code.csv` | First-column codes and case-insensitive description-column text |
| `staging_table.csv` | Ordered, unique involved-table catalog |
| `staging_table_column.csv` | Ordered column definitions per table |
| `staging_table_row.csv` | Ordered rows as compact JSON cell arrays |
| `schema_involved_table.csv` | Ordered schema-to-table links, including non-SSDI inputs |

Only inputs carrying `metadata.name == "SSDI"` become `schema_item` input rows. All numeric NAACCR
outputs are included unless the same schema and item already appeared as an input. Non-NAACCR
outputs do not become item rows, but their tables remain involved. No flat compatibility files or
`--flat` mode are provided.

Each producer removes its own stamp before rewriting its data files and writes the stamp last, so an
interrupted refresh leaves a set that `dict load` rejects as incomplete rather than a mixed
generation.

The complete fetched output stays in gitignored `out-egs/`. The repository contains only small,
independently synthetic test fixtures under `sample_data/test-fixtures/ssdi/` and a reduced
NAACCR dictionary excerpt under `sample_data/test-fixtures/naaccr-dict/`.

## SQLite workflow

```bash
export SEER_API_KEY='your key'
python -m sdc_cdm dict fetch --dialect sqlite --version 25
python -m sdc_cdm ssdi fetch --dialect sqlite --naaccr-version 25
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm dict load --dialect sqlite --db out/demo.db
python -m sdc_cdm dict verify --dialect sqlite --db out/demo.db \
  --expect expectations/naaccr-25.json
```

Use an expectation file matching the fetched NAACCR version. The committed acceptance file is for
version 25.

SQLite cannot conditionally add columns. If a database was built with the older `naaccr_item`
shape, `dict load` fails before opening its transaction with a rebuild message. Delete the control
database and its sibling schema database files, rebuild, and load again.

## SQL Server workflow

Install the optional dependency and supply a complete connection string. There are no server,
database, user, password, port, or certificate defaults.

```bash
python -m pip install -e '.[sqlserver]'
export SDC_CDM_SQLSERVER_CONNECTION_STRING='DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=sdc_cdm;UID=user;PWD=password;Encrypt=yes;TrustServerCertificate=yes'

python -m sdc_cdm dict fetch --dialect sqlserver --version 25
python -m sdc_cdm ssdi fetch --dialect sqlserver --naaccr-version 25
python -m sdc_cdm build --dialect sqlserver
python -m sdc_cdm dict load --dialect sqlserver
python -m sdc_cdm dict verify --dialect sqlserver \
  --expect expectations/naaccr-25.json
```

The SQL Server dictionary DDL is guarded and re-applicable, so an existing built database gains the
new columns and tables when `build` runs again.

## Transaction and current-version rules

If any SSDI CSV is present, `dict load` requires the complete 12-file SSDI set, including
`ssdi_version.csv`, in addition to `data_dictionary_version.csv`. A dictionary-only load is valid
when none is present. The loader validates CSV headers, target columns, agreement between the two
generation stamps, and every `schema_item.item_num` before opening its transaction.

Within one transaction it resolves the version row, demotes the previous current row for that
algorithm, clears the selected generation child-first, loads item definitions before staging
membership, and checks foreign keys before commit. Repeating the same load replaces that generation
with identical counts. A failure restores the prior generation and its `is_current` value.

Consumers select a current version by algorithm:

```sql
SELECT dd_version_id
FROM naaccr.data_dictionary_version
WHERE algorithm = ? AND is_current = 1;
```

## NAACCR 25 acceptance anchor

`expectations/naaccr-25.json` contains counts and section labels only. The live anchor is 946 items:
780 non-retired and 166 retired, 17 populated sections for every non-retired item, 3,900
allowed-code rows, 3,122 registry-requirement rows, and zero staging-item orphans.

TODO(phase-6): define an owned credential-rotation and refresh policy before adding any scheduled,
key-gated dictionary check. Do not add a disabled workflow or a schedule tied to a personal key.
