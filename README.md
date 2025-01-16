# SDC-CDM
A Common Data Model (CDM) for the Structured Data Capture (SDC) IG

## Notebook

### Dotnet

The notebook showcases one way to use the CDM schema within a .NET application

Open `notebooks/try_sdc_cdm_dotnet.dib` using VS Code with the Polyglot Notebooks extension installed

The notebook will walk through how to:

- Create a Sqlite database loaded with the CDM schema
- Import SDC templates, SDC forms, and NAACCR V2 messages
- Export CDM data into FHIR CPDS bundles

## Library

We maintain a dotnet library at `SdcCdmLib/` that can perform some common SDC CDM operations

Example usage is in the Polyglot Notebook

## Standalone Database

The CDM schema is maintained under `database/`. The following Docker instructions will start a Postgres database and load in the schema on first run.

### Setup

Copy `.env.example` to `.env`. The default values will work

`docker compose up` starts a Postgres database with the OMOP CDM loaded in

To reset the database, run `docker compose down -v` to remove the db volume before running `docker compose up` again
