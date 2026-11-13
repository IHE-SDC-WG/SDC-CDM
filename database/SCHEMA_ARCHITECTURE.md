# Schema Architecture: intake + NAACCR + SDC + OMOP + ETL

**Status:** implemented for schema construction. One physical database contains five logical
schemas. OMOP remains stock CDM 5.4; source capture, SDC structure, NAACCR data, and execution
records stay outside OMOP core.

## Schemas

### 1. `intake`: immutable source and local identity

`intake` owns data needed before a source message can become clinical rows:

- `inbound_message` stores the exact payload, SHA-256 digest, duplicate chain, source metadata,
  canonical envelope, parser version, and parse status.
- `inbound_message_diagnostic` stores parser information, warnings, and errors.
- `patient` is the local patient registry, keyed by `(assigning_authority,
  person_source_value)`, with partial birth dates represented as separate fields.

`naaccr.naaccr_value.person_id` and `sdc.sdc_report.person_id` refer logically to
`intake.patient.patient_id`, not directly to `omop.person.person_id`. Neither column has a
cross-schema foreign key. `1_person_and_period.sql` owns the 1:1 mapping into OMOP.

### 2. `naaccr`: dictionary and captured values

`naaccr` is authoritative for the NAACCR dictionary and raw captured answers.

- `data_dictionary_version` scopes the dictionary by algorithm and version. A filtered unique index
  permits one `is_current = 1` row per algorithm.
- `naaccr_item` holds SEER\*API item definitions. `naaccr_item_allowed_code` preserves each
  structured code by array ordinal, including repeated codes, and
  `naaccr_item_registry_requirement` stores the four registries' source collection text.
- `staging_schema`, `schema_item`, schema-scoped value-set and requirement tables, `registry`, and
  staging lookup tables hold the site-specific SSDI axis.
- `naaccr_value` stores one row per logical answered item, with either a verified NAACCR
  `item_num` or the full CAP OBX-3.1 `ecp_code`, plus OBX sub-ID,
  coded, numeric, and text values, source units, observation date, dictionary version, and source
  report identifiers.
- `naaccr_concept_map` and `naaccr_value_concept_map` map item and item-value pairs to OMOP
  concepts. They are keyed independently of dictionary version because the bridge joins by item
  number and code. `maps build` gives every eligible key a stable `NAACCR_LOCAL`
  `source_concept_id`; `concept_id` is a valid standard target or zero. A target
  can come from a reviewed override or a valid Athena `Maps to` relationship.
  The append-only allocation ledger preserves local IDs across rebuilds of one
  database. IDs are not promised to match independently built databases. The
  singleton build record ties the map rows to their current dictionary generation.
  The value map is keyed `(item_num, code)` while `schema_item_code` is
  schema-scoped, so `naaccr.value_code_collision` lists current-generation pairs
  whose descriptions differ across schemas (#100); `concept_map_coverage` reports
  coverage by layer for the generation that built the map rows.
- `report_group` is one accession for one intake patient at one sending facility, and
  `report_version` holds one row per loaded, accessioned `sdc_report`, with its envelope, raw
  message, report LOINC (the report type), selection flag, and predecessor. The first version of
  each type is selected; `reports supersede` is the only thing that moves selection. Unique
  indexes allow one selected version per group and type and one successor per predecessor, and a
  composite foreign key keeps each predecessor in its successor's group and type. Missing
  facility or LOINC is stored as `''`. Accession-less reports get no group.

`dict fetch` stamps its CSVs with `data_dictionary_version.csv` and `ssdi fetch` stamps its CSVs with
`ssdi_version.csv`; `dict load` requires the two stamps to agree and injects one `dd_version_id` into
both axes. `dict load` replaces the selected generation in one transaction and
promotes it only after demoting the prior current row for the same algorithm. The canonical current
lookup is:

```sql
SELECT dd_version_id
FROM naaccr.data_dictionary_version
WHERE algorithm = ? AND is_current = 1;
```

Fetch, CSV, load, and verification details are in
[`schemas/naaccr/DICTIONARY_LOAD.md`](schemas/naaccr/DICTIONARY_LOAD.md).

`naaccr_value.sdc_report_id` is a logical pointer to the source `sdc.sdc_report` row.
`report_accession` remains as a denormalized business key, but the bridge joins by report ID so
duplicate-accession and accession-less reports cannot fan out.

### 3. `sdc`: form structure and report metadata

The SDC XML path stores templates, instances, and submitted answers:

- `template_sdc`, `template_item`, `template_instance`, `template_term_map`, and
  `template_map_content`
- `sdc_form_answer`, including section, question, selected list item, typed response, units, and
  parent-answer context
- `sdc_specimen` and `observation_specimens`

The eCP path uses `sdc_report` for report headers and keeps its answer values in
`naaccr.naaccr_value`. `sdc_report` carries accession, report LOINC, template identity, narrative,
and duplicate-report provenance.

`note_report` links each bridge-owned `omop.note` to every selected contributing `sdc_report`.
It records the report group and one `is_anchor = 1` row per group. Its composite primary key
is `(note_id, sdc_report_id)` and each report ID is unique. Note and group IDs are logical
cross-schema references; the report ID has an enforced FK within `sdc`. Supersession replaces
contributors atomically while retaining the note ID. Notes with no link belong to other writers.

### 4. `omop`: stock OMOP CDM 5.4

The executable OMOP DDL is the upstream SQLite or SQL Server CDM 5.4 drop. It has no SDC tables,
no `sdc_*` columns, and no `sdc_form_answer_id` foreign key. Repository-specific provenance uses
standard OMOP event and source-value columns plus links outside OMOP in `sdc` and `etl`.

### 5. `etl`: build and run records

- `schema_migration` stores each applied manifest path and SHA-256 hash.
- `run` records command, dialect, status, timing, and errors.
- `concept_constant` holds the vocabulary constants that `constants resolve` found for
  `database/seed/concept_constants.csv`.
- `observation_period_derivation` records, for each bridge-written `omop.observation_period`, its
  derivation rule and the `naaccr.naaccr_value` row or `intake.inbound_envelope` (for a report
  date from a report with no values) that set each of its start and end dates. It keeps
  that provenance out of the stock OMOP table.
- `cdm_source_seed` holds the current bridge run's `cdm_source.csv` row; Python replaces it inside
  the run's transaction.

The first entry in `database/manifest.json` creates this schema and its ledger. Every later build
decision is recorded against that ledger.

## Data flow

```text
Inbound bytes
   |
   +--> intake.inbound_message + intake.patient
   |          |
   |          +--> canonical envelope and diagnostics
   |
   +--> naaccr.naaccr_value + sdc.sdc_report
   |          |
   |          +--> naaccr.report_group + naaccr.report_version (selection)
   |                      |
   |                      +--> bridge --> omop.person + omop.observation_period
   |                                   + omop.cdm_source + omop.note
   |                                   + sdc.note_report (selected contributors + anchor)
   |                                   + etl.observation_period_derivation
   |
   +--> sdc.template_* + sdc.sdc_form_answer    (SDC XML path)

database/manifest.json --> etl.schema_migration + etl.run
```

The bridge is a separate transform, `sdc-cdm bridge`, that runs the manifest's ordered `bridge`
entries in one transaction. It reads `intake`, `naaccr`, and `sdc`, writes only standard OMOP
columns plus its own `etl` and `sdc.note_report` provenance, and does not run as part of `build`.

## Back-reference without a crosswalk

`omop.note.note_source_value` stores the accession, but is not a unique group identity.
`sdc.note_report` is the authoritative note-to-report link. It identifies every selected
contributor, including reports loaded in different messages, and marks the anchor. Group
identity includes patient and sending facility, so matching an accession alone is insufficient.

The bridge chooses an anchor in synoptic / other non-narrative / narrative order, breaking ties
by report ID. Text prefers the first non-empty selected narrative, then anchor text, then a
report-kind placeholder. The date is the anchor's earliest value observation day, then its
envelope report day. Missing dates and accessions longer than 50 characters fail the run.
An unchanged rerun performs no note or link writes.

This query recovers each note's contributing reports and exact source bytes without adding
columns to OMOP:

```sql
SELECT n.note_id, nr.report_group_id, nr.is_anchor,
       sr.sdc_report_id, sr.report_accession,
       e.inbound_envelope_id, m.inbound_message_id, m.raw_blob
FROM omop.note n
JOIN sdc.note_report nr ON nr.note_id = n.note_id
JOIN sdc.sdc_report sr ON sr.sdc_report_id = nr.sdc_report_id
JOIN intake.inbound_envelope e ON e.inbound_envelope_id = sr.inbound_envelope_id
JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id;
```

A supersession for an already bridged group runs selection and the full bridge in one
transaction, including pending loads and period recalculation. Any failure rolls back both.
An unbridged group only moves selection, with no bridge prerequisites. Its `etl.run` record
is written outside the data transaction so failed outcomes survive rollback.

Measurement and observation event pointers and source-value columns are extended in Phase 4.3.
The excluded pre-rebuild bridge remains under separate regression tests until Phase 4.5;
it must not run alongside the manifest bridge on one database.

## Physical model and build order

- **SQLite:** the control file attaches one sibling database per logical schema. For a control
  file `demo.db`, the files are `demo.etl.db`, `demo.intake.db`, `demo.omop.db`,
  `demo.naaccr.db`, and `demo.sdc.db`.
- **SQL Server:** `etl`, `intake`, `omop`, `naaccr`, and `sdc` are real schemas in one database.

SCHEMA-02 treats these storage differences as equivalent after normalization:

| Logical field | SQLite | SQL Server | Test normalization |
|---|---|---|---|
| `registry.id`, `schema_item_requirement.registry_id` | `INTEGER` | `SMALLINT` | Integer identity/reference |
| Boolean flags | checked `INTEGER` | `BIT` | `0` / `1` |
| Generated identifiers | `AUTOINCREMENT` | `IDENTITY` | Generated integer |
| Variable text and JSON text | `TEXT` | `NVARCHAR(n)` / `NVARCHAR(MAX)` | Unicode string |

`database/manifest.json` is the only complete apply inventory. For both dialects it orders files
by `etl`, `intake`, `omop`, `naaccr`, then `sdc`. Re-running `build` skips unchanged files by
ledger hash. Changed re-applicable schema files run again; changed immutable files require an
explicit hash acceptance after review.

```bash
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm build --dialect sqlite --db out/demo.db --list
```

## Repository layout

```text
database/
  manifest.json
  schemas/
    etl/ddl/{sqlite,sqlserver}/
    intake/ddl/{sqlite,sqlserver}/
    omop/ddl/{sqlite,sqlserver}/
    naaccr/ddl/{sqlite,sqlserver}/
    sdc/ddl/{sqlite,sqlserver}/
  etl/{sqlite,sqlserver}/
diagrams/
  three-schema/              historical directory name; current model diagrams
  original-omop/             upstream OMOP CDM 5.4 reference diagrams
```

The Mermaid sources are hand-maintained and must change with related DDL. Start with
[`three-schema-overview.mmd`](../diagrams/three-schema/three-schema-overview.mmd), then use
[`naaccr.mmd`](../diagrams/three-schema/naaccr.mmd),
[`sdc.mmd`](../diagrams/three-schema/sdc.mmd), and
[`naaccr-sdc-to-omop-bridge.mmd`](../diagrams/three-schema/naaccr-sdc-to-omop-bridge.mmd) for
table and bridge details.

## Fixed decisions

- One physical database, five logical schemas.
- SQLite and SQL Server are the executable dialects.
- The manifest is the schema construction order; the Python driver is its only consumer.
- Captured eCP values use the NAACCR staging shape.
- SDC XML answers stay in `sdc_form_answer`.
- OMOP remains stock CDM 5.4.
- Cross-schema provenance is logical and uses standard source/event fields.
- The bridge is a separate batch transform and must be safe to rerun.
