# Athena Vocabulary Files

This directory is the local staging location for an OHDSI Athena vocabulary
extract. Downloaded archives and extracted vocabulary data are ignored by Git.
Only this README and the directory's `.gitignore` belong in the repository.

## Licensing

> Athena vocabulary packages are not covered by this repository's license.
> Each included vocabulary remains subject to its own license and permitted-use
> terms. You are responsible for obtaining and complying with every required
> license. Do not commit or redistribute downloaded Athena files through this
> repository.

Athena marks restricted content with **License required**. Complete that process
and provide any requested proof of authorization before including the
vocabulary in a download. Selecting a vocabulary in Athena does not replace or
change its underlying license. CPT4 users must also complete the local name
reconstruction step supplied with the Athena package and comply with the
applicable use agreement.

See the official references:

- [Athena vocabulary downloads](https://athena.ohdsi.org/vocabulary/list)
- [OHDSI guidance for accessing standardized vocabularies](https://ohdsi.github.io/BookOfOhdsi-2ndEdition/representation/vocabularies.html#access-to-the-standardized-vocabularies)
- [OHDSI Athena CSV loader format](https://ohdsi.github.io/ETL-Synthea/reference/LoadVocabFromCsv.html)

## Download from Athena

1. Create or sign into an Athena account.
2. Open **Download** and choose **Download Vocabularies**.
3. Select NAACCR and the standard vocabularies required for your source data
   and mappings. Complete every **License required** step that applies.
4. Name and submit the bundle, then wait for Athena to prepare the ZIP file.
5. Download and extract the ZIP.
6. If the bundle contains the CPT4 reconstruction scripts, follow the
   instructions included by Athena before loading the files.
7. Copy the following extracted files directly into this directory:

```text
CONCEPT.csv
CONCEPT_ANCESTOR.csv
CONCEPT_CLASS.csv
CONCEPT_RELATIONSHIP.csv
CONCEPT_SYNONYM.csv
DOMAIN.csv
DRUG_STRENGTH.csv
RELATIONSHIP.csv
VOCABULARY.csv
```

Athena uses tab-delimited data despite the `.csv` file extension. The loader
expects tabs by default. `SOURCE_TO_CONCEPT_MAP.csv` is not part of this
nine-table load.

## Validate the Extract

From the repository root:

```bash
python -m sdc_cdm vocab check \
  --dialect sqlite \
  --vocab-dir database/vocab
```

The check verifies all required files and headers, parses every row, and reports
the row counts without connecting to a database.

## Load SQLite

Create the database through the manifest first, then pass the same control
database to the vocabulary loader:

```bash
python -m sdc_cdm build --dialect sqlite --db quickstart.db
```

```bash
python -m sdc_cdm vocab load \
  --dialect sqlite \
  --db quickstart.db \
  --vocab-dir database/vocab

python -m sdc_cdm constants resolve \
  --dialect sqlite \
  --db quickstart.db
```

A fresh manifest build leaves the OMOP vocabulary tables empty. The loader
requires all nine target vocabulary tables to be empty and stops if it finds any
existing rows.

## Load SQL Server

Install a system ODBC manager and a Microsoft SQL Server ODBC driver for your
platform first. Then install the optional Python driver and provide a complete
connection string either as an argument or through the shared environment
variable:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install ".[sqlserver]"

export SDC_CDM_SQLSERVER_CONNECTION_STRING='DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=cdm;UID=user;PWD=password;TrustServerCertificate=yes'
python -m sdc_cdm vocab load \
  --dialect sqlserver \
  --vocab-dir database/vocab

python -m sdc_cdm constants resolve \
  --dialect sqlserver
```

Use `--connection-string` on either command to override the environment
variable.

## Safety and Load Order

The loader is for the initial load into a fresh OMOP vocabulary schema. It
stops if any of the nine target vocabulary tables contains existing rows. It
does not silently merge, delete, or refresh an existing vocabulary.

For this repository, use the following order:

1. Build the `etl`, `intake`, `omop`, `naaccr`, and `sdc` schemas from the manifest.
2. Load the Athena vocabulary files with this loader.
3. Resolve the tracked concept pairs with `sdc-cdm constants resolve`.
4. Apply repo-specific NAACCR vocabulary additions where the database path
   requires them.
5. Import the source report data.
6. Run the NAACCR-to-OMOP bridge.

The load runs in a transaction, checks source and database row counts, verifies
the tracked vocabulary/code pairs, checks vocabulary references, and reports
the loaded versions from `VOCABULARY.csv`. Constant resolution fails without
modifying `etl.concept_constant` if any tracked pair is missing or ambiguous.
