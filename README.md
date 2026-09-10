# SDC-CDM

SDC-CDM models CAP eCP and NAACCR data in one physical database with five logical schemas:

- `etl` records schema migrations and pipeline runs.
- `intake` stores source identity, exact inbound payloads, and canonical envelopes.
- `omop` contains unmodified OMOP CDM 5.4 tables.
- `naaccr` contains the NAACCR dictionary, captured values, and concept maps.
- `sdc` contains SDC templates, form answers, and report metadata.

The active design is documented in
[database/SCHEMA_ARCHITECTURE.md](database/SCHEMA_ARCHITECTURE.md). The diagrams directory is
still named [`three-schema/`](diagrams/three-schema/) for continuity, but its overview covers
all five current schemas.

## Database build

Python 3.11 or later is required. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"

python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm build --dialect sqlite --db out/demo.db --list
```

The SQLite build creates `out/demo.db` as the control database and five sibling files named
`demo.etl.db`, `demo.intake.db`, `demo.omop.db`, `demo.naaccr.db`, and `demo.sdc.db`. The second
build reads `etl.schema_migration` and skips every unchanged file.

SQL Server uses the same ordered [`database/manifest.json`](database/manifest.json). Install
the optional driver and provide a complete ODBC connection string:

```bash
python -m pip install -e ".[sqlserver]"
export SDC_CDM_SQLSERVER_CONNECTION_STRING='DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=sdc_cdm;UID=user;PWD=password;Encrypt=yes;TrustServerCertificate=yes'
python -m sdc_cdm build --dialect sqlserver
```

Only SQLite and SQL Server are supported executable dialects. The manifest explicitly declares
all retained, unexecuted upstream reference files as excluded.

## NAACCR dictionary

The item dictionary and SSDI staging metadata come from SEER\*API. The Python fetch commands write
one shared, deterministic CSV generation under gitignored repository-root `out-egs/`; load uses one
transaction and the same files for SQLite or SQL Server. Verify compares counts with the committed
NAACCR 25 expectations.

```bash
export SEER_API_KEY='your key'
python -m sdc_cdm dict fetch --dialect sqlite --version 25
python -m sdc_cdm ssdi fetch --dialect sqlite --naaccr-version 25
python -m sdc_cdm dict load --dialect sqlite --db out/demo.db
python -m sdc_cdm dict verify --dialect sqlite --db out/demo.db \
  --expect expectations/naaccr-25.json
```

Both fetch commands inherit `--dialect` for a uniform command shape but do not connect to a
database. The API sequence, flag mapping, 12-file SSDI contract, SQL Server commands, and rebuild
guidance are in
[`database/schemas/naaccr/DICTIONARY_LOAD.md`](database/schemas/naaccr/DICTIONARY_LOAD.md).

## Tool support

| Tool | SQLite | SQL Server |
| --- | --- | --- |
| Python `sdc_cdm build` | Supported | Supported |
| Python `sdc_cdm dict load` / `dict verify` | Supported | Supported |
| Python `sdc_cdm dict fetch` | Network-only; target ignored | Network-only; target ignored |
| Python `sdc_cdm ssdi fetch` | Network-only; target ignored | Network-only; target ignored |
| C# SDC XML importer | Supported | Not supported |

The C# project is deliberately limited to SDC XML template and response persistence. It uses
an isolated SQLite store and does not build or run the broader database pipeline.

## Vocabulary data

The OMOP DDL creates empty vocabulary tables. Download an OHDSI Athena extract, place its nine
files under [`database/vocab/`](database/vocab/README.md), and follow that directory's licensing,
validation, and load instructions. Athena files are not covered by this repository's license and
must not be committed or redistributed through this repository.

## Tests

```bash
python -m pytest -ra
dotnet test src/csharp/SdcCdm.Sdc.Tests
```

The Python suite covers the manifest, migration ledger, schema contracts, NAACCR dictionary client
and transaction behavior, parser utilities, and the SQLite bridge rerun regression. SQL Server runs
the same suite for pull requests and pushes to `main` when database, Python, or tool paths change.
The C# suite covers only the SDC XML library.

Historical artifacts from the retired combined OMOP-SDC model are available in Git at commit
[`6304b3e`](https://github.com/IHE-SDC-WG/SDC-CDM/tree/6304b3e).
