# Database Layout

The canonical database design is [SCHEMA_ARCHITECTURE.md](SCHEMA_ARCHITECTURE.md).

This repo now uses one physical database with five logical schemas:

- `intake`: exact inbound bytes, canonical envelopes, diagnostics, and local patient identity.
- `naaccr`: NAACCR dictionary tables, raw captured values, and NAACCR to OMOP concept maps.
- `sdc`: SDC form, report, question, section, list-item, and specimen structure. The SDC XML path stores submitted answers in `sdc_form_answer`; the eCP/HL7 path stores answers in `naaccr_value`.
- `omop`: stock OMOP CDM 5.4 tables, kept unmodified.
- `etl`: run history, applied migrations, and resolved concept constants.

The bridge reads `intake`, `naaccr`, and `sdc`, and writes stock OMOP columns plus provenance
in `etl`, `sdc.note_report`, `naaccr.value_event`, `naaccr.group_condition`, and
`naaccr.person_episode`. `sdc.note_report` connects each `omop.note`
to its selected reports and marks its anchor. `note_source_value` stores the accession for
display; it is not a group key. `naaccr.value_event` connects each bridged `naaccr_value` to its
`omop.measurement` or `omop.observation` row. `naaccr.group_condition` connects each selected
report group to its `omop.condition_occurrence` and chosen primary-site value, and
`naaccr.person_episode` connects each `omop.episode` to its `(person_id, episode_key)`.
Following a link to `inbound_envelope_id` reaches the exact raw message bytes.

## Files

```text
database/
  manifest.json
  vocab/
    README.md
  schemas/
    intake/ddl/{sqlite,sqlserver}/
    etl/ddl/{sqlite,sqlserver}/
    naaccr/ddl/{sqlite,sqlserver}/
    sdc/ddl/{sqlite,sqlserver}/
    omop/ddl/{sqlite,sqlserver}/
  etl/
    sqlite/
    sqlserver/
```

SQLite uses attached databases named `etl`, `intake`, `omop`, `naaccr`, and `sdc`. SQL Server uses
real schemas. The repository provides schema builds and bridge ETL for SQLite and SQL Server.

`etl/<dialect>/` holds the bridge scripts and `9_validate.sql`. `sdc-cdm bridge` runs the
manifest's ordered `bridge` entries and nothing else; `sdc-cdm validate` runs its `validate`
entries. Each entry names the constants, seed files, and tables it uses. The manifest test fails if
a SQL file in that directory is neither listed nor excluded.

`1_person_and_period.sql` writes people, periods, and source metadata. `2_note.sql` writes one
note per selected report group, anchored in synoptic / other non-narrative / narrative order,
with the lowest report ID breaking ties. It prefers the first non-empty selected narrative,
then the anchor comment, then a report-kind placeholder. Its date is the anchor's earliest
value observation day, then its envelope report day. Missing dates and accessions over 50
characters fail the run. SQL Server also checks the untruncated encoded accession against the
50-byte `varchar(50)` limit. Text comparisons use stored bytes so case and trailing spaces
are preserved. Each selected report gets an `sdc.note_report` link; superseded and
accession-less reports do not.

`3_measurement_observation.sql` writes one `measurement` or `observation` per value of a
selected report. A map target in the `Measurement` or `Observation` domain picks that table;
every other value keeps concept `0` and goes to `observation` when it has non-blank text,
otherwise to `measurement`. Coded values get the value map's nonzero target unless
`naaccr.value_code_collision` lists the pair (#100). Over-length text is cut to the OMOP
column limit and flagged. A value with no day-precision date of its own or on its report
fails the run. `naaccr.value_event` records each row's route, value typing, and truncation.

`4_condition_and_episode.sql` writes one thin `condition_occurrence` per selected group with a
primary-site (item 400) value, taking the group's lowest non-blank one and its script-3 date and
source value. `condition_concept_id` is the value map's target only for a standard,
non-collision `Condition` concept, else `0`; `naaccr.group_condition.condition_target` records
which. It writes one disease `episode` per `(person_id, episode_key)` and an `episode_event` for
every measurement, observation, and condition of that tumor. All four scripts reconcile changed
state and keep existing IDs.

`reports supersede` refreshes the full bridge when the group already has a note, in the same
transaction as selection. Pending loads are also bridged and periods recalculated. A failure
rolls back selection and all derived changes. Unbridged groups require no bridge prerequisites.
The command accepts `--seed-dir` and logs its outcome outside the data transaction.

`9_validate.sql` only reads. Each statement returns `(check_name, category, actual)` rows, and
both dialects emit the same check names. Python judges them: `structural`, `provenance`, and
`reconciliation` counts must be zero; `coverage` counts must not exceed
[`seed/validate_thresholds.csv`](seed/validate_thresholds.csv); `report` counts are printed only.
Bridge-written OMOP rows that no bridge link names are reported, never failed, because the bridge
leaves unrelated OMOP rows in place.

`sdc-cdm export --dialect <dialect> (--db | --connection-string) OUTPUT_DIR [--include-vocabulary]`
writes the nine bridge-populated OMOP tables, and optionally the nine vocabulary tables, as one CSV
each plus `manifest.json`. Column lists come from `src/python/sdc_cdm/cdm/tables.py`. It reads
only `omop` in one consistent snapshot and needs exactly one `omop.cdm_source` row. Raw bytes and
intake PID fields cannot reach the bundle, but the bundle is not de-identified: it carries the MRN
(`person_source_value`), the accession (`note_source_value`), and the narrative (`note_text`).

## Build

The manifest is the only complete schema apply order. The first entry creates the `etl` ledger;
subsequent runs compare each file's SHA-256 hash with `etl.schema_migration` and skip unchanged
files.

From the repository root:

```bash
python -m pip install -e .
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm build --dialect sqlite --db out/demo.db --list
```

The control file is `out/demo.db`; attached schema files are written beside it as
`demo.<schema>.db`. For SQL Server, install the `sqlserver` optional dependency and pass either
`--connection-string` or `SDC_CDM_SQLSERVER_CONNECTION_STRING`.

Only SQLite and SQL Server are executable dialects. Files listed under the manifest's `excluded`
array are references or later-phase inputs and are never applied by `build`.

### Upgrading the eCP identifier columns

`naaccr.naaccr_value` now stores either a full CAP `ecp_code` or a verified NAACCR
`item_num`. A build replaces an empty legacy value table with the new schema. If the
legacy table has rows, build and dry run stop and report the ambiguous row count.
The old importer discarded the suffix of OBX-3.1, so those rows cannot be
converted from `item_num` alone. Preserve the database and original messages,
recover the complete CAP codes, and reload the values into the new schema.
Clearing or replacing legacy rows is an operator step; `build` does not delete them.
`--accept-changed-hashes` does not bypass this check.

## NAACCR Dictionary Data

`dict fetch` obtains the full item dictionary from SEER\*API and `ssdi fetch` obtains the
site-specific staging metadata. Both write deterministic CSVs to repository-root `out-egs/`, each
with its own generation stamp. `dict load` requires the two stamps to agree, resolves the dictionary
version, loads item definitions before SSDI schema membership, validates constraints, and commits
the generation as one unit. `dict verify` checks counts and the section distribution without making
network requests.

```bash
export SEER_API_KEY='your key'
python -m sdc_cdm dict fetch --dialect sqlite --version 25
python -m sdc_cdm ssdi fetch --dialect sqlite --naaccr-version 25
python -m sdc_cdm dict load --dialect sqlite --db out/demo.db
python -m sdc_cdm dict verify --dialect sqlite --db out/demo.db \
  --expect expectations/naaccr-25.json
```

Both fetch commands require `SEER_API_KEY`; load and verify are offline. See
[`schemas/naaccr/DICTIONARY_LOAD.md`](schemas/naaccr/DICTIONARY_LOAD.md) for the API call order,
CSV fields, SSDI producer order, generation stamps, SQL Server invocation, and current-version query.

## OMOP Vocabulary Data

The OMOP DDL creates empty vocabulary tables. Download an OHDSI Athena bundle,
extract its nine vocabulary files under [`vocab/`](vocab/README.md), then run
`sdc-cdm vocab load` and `sdc-cdm constants resolve` before importing clinical
data. The downloaded files are ignored by Git and remain subject to the
licenses of their individual vocabularies.

## Historical Model

The previous combined OMOP-SDC model is available in Git at commit
[`6304b3e`](https://github.com/IHE-SDC-WG/SDC-CDM/tree/6304b3e). It is retained
in repository history for reference only. Do not regenerate active DDL from the
old OMOP-SDC fork.
