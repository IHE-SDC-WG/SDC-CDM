# NAACCR dictionary fetch, load, and verification

The Python `dict` commands construct the NAACCR dictionary from SEER\*API and load the same
CSV files into SQLite or SQL Server. The API key is used only by `dict fetch`; builds, loads,
verification, and tests remain offline.

## How the API dictionary is constructed

SEER\*API uses the `X-SEERAPI-Key` header for all `/rest/*` requests. The dictionary client
calls the endpoints in this order:

1. `GET /rest/naaccr/versions` discovers the available NAACCR versions.
2. `GET /rest/naaccr/{version}` returns a thin item index containing `id`, `item`, and `name`.
3. `GET /rest/naaccr/{version}/{key}` returns one full item DTO for each index entry.

The index does not contain the detail fields, so a complete version requires one index request
plus one detail request per item. For retired items, the index omits `id`; the request key is
therefore `entry.get("id") or entry["item"]`. Retired detail DTOs are also sparse. Only the item
number, item name, creation and modification dates, and retirement year and version are
guaranteed.

The client uses eight concurrent detail requests, caps a configured value at 16, and restores
deterministic numeric item order before writing. It retries up to four times for HTTP 429, 500,
502, 503, and 504 responses, URL errors, and timeouts. It honours `Retry-After`; authentication
and not-found errors are not retried. An API error envelope's `message` is reported directly.

The item DTO is split into three relational shapes:

- Scalar fields and compact JSON arrays (`record_types`, `alternate_names`) become one
  `naaccr_item_dictionary.csv` row per item.
- Each `allowed_codes` array entry becomes a `naaccr_item_allowed_code.csv` row. Its zero-based
  `code_seq` preserves repeated codes in one item.
- Each present `seer_collect`, `npcr_collect`, `coc_collect`, or `cccr_collect` value becomes a
  `naaccr_item_registry_requirement.csv` row. Collection status remains source text.

`allowable_values` is retained separately from `allowed_codes`: it can refer to an external
coding system even when the DTO has no enumerated code list.

There is no cheap date-based incremental fetch. The index has no `date_modified`, so `--since`
would still require every detail request. The API's `version_implemented=V` query is useful only
for finding items added in a particular version.

## CSV contract

All files are written under repository-root `out-egs/`, regardless of the shell's current
directory. CSVs use UTF-8 without a BOM, LF endings, an always-quoted field format, doubled
quotes, empty strings for nulls, and raw embedded newlines inside quoted fields. Array values
use compact JSON. The reader trims every field to match the existing SSDI export contract.

The dictionary producer writes:

- `naaccr_item_dictionary.csv`
- `naaccr_item_allowed_code.csv`
- `naaccr_item_registry_requirement.csv`
- `data_dictionary_version.csv`

The first file stays separate from the SSDI producer's `naaccr_item.csv`. The dictionary owns
item definitions; the SSDI file supplies only `unit` and `decimal_places`. Both producers share
the single one-row `data_dictionary_version.csv`, and the loader injects its resolved
`dd_version_id` into every versioned row. With non-default staging settings, pass matching
`--algorithm` and `--staging-version` values to `dict fetch` and matching environment values to
the SSDI exporter.

If any SSDI CSV is present, `dict load` requires the complete SSDI CSV set. A dictionary-only
load is valid when none is present. The loader always seeds the four registry codes.

## SQLite workflow

```bash
export SEER_API_KEY='your key'

# If site-specific staging rows are needed, produce them first. This command remains
# the SSDI producer until its Python port lands.
cd tools/ssdi-ts
SSDI_OUTPUT_3NF=1 SSDI_NAACCR_VERSION=25 npm run dev
cd ../..

# --dialect is inherited for a uniform CLI and is ignored by this network-only verb.
python -m sdc_cdm dict fetch --dialect sqlite --version 25
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm dict load --dialect sqlite --db out/demo.db
python -m sdc_cdm dict verify --dialect sqlite --db out/demo.db \
  --expect expectations/naaccr-25.json
```

SQLite cannot conditionally add columns. If a database was built with the older
`naaccr_item` shape, `dict load` fails before opening its transaction with a rebuild message.
Delete the control database and its sibling schema database files, rebuild, and load again.

## SQL Server workflow

Install the optional dependency and supply a complete connection string. There are no server,
database, user, password, port, or certificate defaults.

```bash
python -m pip install -e '.[sqlserver]'
export SDC_CDM_SQLSERVER_CONNECTION_STRING='DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=sdc_cdm;UID=user;PWD=password;Encrypt=yes;TrustServerCertificate=yes'

python -m sdc_cdm build --dialect sqlserver
python -m sdc_cdm dict load --dialect sqlserver
python -m sdc_cdm dict verify --dialect sqlserver \
  --expect expectations/naaccr-25.json
```

The SQL Server dictionary DDL is guarded and re-applicable, so an existing built database gains
the new columns and tables when `build` runs again.

## Transaction and current-version rules

`dict load` validates the CSV headers, target columns, and every `schema_item.item_num` before
opening the load transaction. Within one transaction it resolves the version row, demotes the
previous current row for that algorithm, clears the selected generation child-first, loads item
definitions before staging membership, and checks foreign keys before commit. Repeating the same
load replaces that generation with identical counts. A failure restores the previous generation
and its `is_current` value.

Consumers select a current version by algorithm, never by an unqualified maximum ID:

```sql
SELECT dd_version_id
FROM naaccr.data_dictionary_version
WHERE algorithm = ? AND is_current = 1;
```

The filtered unique index permits one current row per algorithm.

## NAACCR 25 acceptance anchor

`expectations/naaccr-25.json` contains counts and section labels only. The live anchor is 946
items: 780 non-retired and 166 retired, 17 populated sections for every non-retired item, 3,900
allowed-code rows, 3,122 registry-requirement rows, and zero staging-item orphans. It also pins
the 17-section distribution. The repository commits only a 12-item automated-test excerpt; the
complete fetched dictionary remains in gitignored `out-egs/`.

TODO(phase-6): define an owned credential-rotation and refresh policy before adding any scheduled,
key-gated dictionary check. Do not add a disabled workflow or a schedule tied to a personal key.
