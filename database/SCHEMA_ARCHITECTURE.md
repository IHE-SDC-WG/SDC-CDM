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

`value_event` links each bridged `naaccr_value` (its primary key, an enforced FK) to the one
`omop.measurement` or `omop.observation` row it produced: `event_table` names the table and
`event_id` is a logical reference to its ID, unique per table. It also records how the row was
routed (`route`), how its coded value was typed (`value_target`), and whether any text was cut
(`is_truncated`), so unmapped, #100-suppressed, and truncated values are countable without
reading OMOP. Clinical rows with no link belong to other writers.

`group_condition` links each selected `report_group` (its primary key, an enforced FK) to the
one thin `omop.condition_occurrence` it produced (unique, a logical reference) and to the chosen
primary-site `naaccr_value` (an enforced FK). `condition_target` records why
`condition_concept_id` is or is not a standard target. `person_episode` links each
`omop.episode` ID to its unique `(person_id, episode_key)`; the hashed key does not fit, and is
not, an OMOP source value. The bridge owns only the conditions and episodes named here, plus
every `omop.episode_event` row of an owned episode.

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
  date from a report with no values or with an undated value) that set each of its start and
  end dates. It keeps
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
   |                                   + omop.measurement + omop.observation
   |                                   + naaccr.value_event (one link per value)
   |                                   + omop.condition_occurrence
   |                                   + naaccr.group_condition (one per group with a site)
   |                                   + omop.episode + omop.episode_event
   |                                   + naaccr.person_episode (one per person and tumor)
   |                                   + etl.observation_period_derivation
   |
   +--> sdc.template_* + sdc.sdc_form_answer    (SDC XML path)

database/manifest.json --> etl.schema_migration + etl.run
```

The bridge is a separate transform, `sdc-cdm bridge`, that runs the manifest's ordered `bridge`
entries in one transaction. It reads `intake`, `naaccr`, and `sdc`, writes only standard OMOP
columns plus its own `etl`, `sdc.note_report`, `naaccr.value_event`, `naaccr.group_condition`,
and `naaccr.person_episode` provenance, and does not run as part of `build`.

## Back-reference without a crosswalk

`omop.note.note_source_value` stores the accession, but is not a unique group identity.
`sdc.note_report` is the authoritative note-to-report link. It identifies every selected
contributor, including reports loaded in different messages, and marks the anchor. Group
identity includes patient and sending facility, so matching an accession alone is insufficient.

The bridge chooses an anchor in synoptic / other non-narrative / narrative order, breaking ties
by report ID. Text prefers the first non-empty selected narrative, then anchor text, then a
report-kind placeholder. The date is the anchor's earliest value observation day, then its
envelope report day. Missing dates and accessions longer than 50 characters fail the run.
SQL Server also rejects encoded accessions over 50 bytes before narrowing to `varchar(50)`.
Its reconciliation compares stored text bytes to preserve case and trailing spaces.
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

### Measurements and observations

Each `naaccr_value` of a selected report (one with a `note_report` link) becomes exactly one
clinical row, including a value with no answer. Maps join on `item_num` only; an `ecp_code` is
never parsed for an item number. The row's table and concept slots follow its route:

| Route (`value_event.route`) | Case | Table | `*_concept_id` | `*_source_concept_id` |
|---|---|---|---|---|
| `target_domain` | map target in the `Measurement` or `Observation` domain | that domain's table | map `concept_id` | map `source_concept_id` |
| `default_other_domain` | map target in any other domain | by value shape | `0` | map `source_concept_id` |
| `default_no_target` | map row with `concept_id = 0` (local mint) | by value shape | `0` | map `source_concept_id` |
| `default_no_map` | `item_num` with no map row | by value shape | `0` | `0` |
| `default_ecp_code` | `ecp_code` only | by value shape | `0` | `0` |

"By value shape" means `observation` when the value carries non-blank `value_text`, otherwise
`measurement`. Every `0` comes from the `unmapped` constant. `*_source_value` is the `ecp_code`
or the item number. `*_event_id` is the group's `note_id`, with the event field concept from
`field_note_note_id`. Type concepts come from `measurement_type_registry` and
`observation_type_registry`.

| `naaccr_value` column | OMOP column | Rule |
|---|---|---|
| `value_code` | `value_as_concept_id` | the nonzero `naaccr_value_concept_map` target for `(item_num, value_code)`; NULL when the target is `0` or absent, or when `naaccr.value_code_collision` lists the pair (#100) |
| `value_code`, else `value_text` | `value_source_value` | cut to 50 |
| `value_num` | `value_as_number` | — |
| `value_unit_source` | `unit_source_value` | cut to 50; `unit_concept_id` stays NULL |
| `value_text` | `observation.value_as_string` | cut to 60; `measurement` has no string column |
| `observation_date` | `*_date` | else the report's day-precision envelope date; neither fails the run |

By value shape, a CAP or NAACCR answer lands in these OMOP columns:

| Source value | `measurement` | `observation` |
|---|---|---|
| numeric (`value_num`) | `value_as_number` + `unit_source_value` | `value_as_number` + `unit_source_value` |
| coded (`value_code`) | `value_as_concept_id` when mapped; the code in `value_source_value` | same |
| text (`value_text`) | `value_source_value` only, when there is no code | `value_as_string`, and `value_source_value` when there is no code |

CAP OBX segments that share an OBX-4 sub-ID are staged as one logical `naaccr_value`. The full
OBX-3.1 question identifier is kept in `ecp_code`, and `item_num` stays NULL unless external
preprocessing supplies a verified NAACCR item number.

`value_event.value_target` is `none` (no code), `mapped`, `unmapped`, or `collision_suppressed`
(which takes precedence over `unmapped`). OMOP has no value-source-concept column, so a coded
value keeps its code in `value_source_value` and the item's source concept in
`*_source_concept_id`. Limits are characters on SQLite and bytes of the stored `varchar`
encoding on SQL Server; a cut never splits a character and sets `is_truncated`. An `ecp_code`
longer than 50 bytes fails the run instead of being cut. Datetime, time, operator, range,
provider, visit, and qualifier columns are NULL.

A rerun deletes owned rows whose value is no longer selected, whose table changed, or whose row
is gone; updates only columns that differ; and inserts the rest. IDs stay stable, a deleted ID
is never reused (SQLite allocates above the table's `sqlite_sequence` value, like SQL Server
identity), repeated identical answers stay separate rows, and an unchanged rerun writes nothing. This query walks
each clinical row back to its exact source bytes:

```sql
SELECT ev.event_table, ev.event_id, ev.note_id, v.naaccr_value_id, v.item_num, v.ecp_code,
       l.route, l.value_target, l.is_truncated, nr.report_group_id,
       v.sdc_report_id, e.inbound_envelope_id, m.inbound_message_id, m.raw_blob
FROM (
    SELECT 'measurement' AS event_table, measurement_id AS event_id,
           measurement_event_id AS note_id
    FROM omop.measurement
    UNION ALL
    SELECT 'observation', observation_id, observation_event_id FROM omop.observation
) ev
JOIN naaccr.value_event l ON l.event_table = ev.event_table AND l.event_id = ev.event_id
JOIN naaccr.naaccr_value v ON v.naaccr_value_id = l.naaccr_value_id
JOIN sdc.note_report nr ON nr.sdc_report_id = v.sdc_report_id
JOIN intake.inbound_envelope e ON e.inbound_envelope_id = v.inbound_envelope_id
JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id;
```

### Conditions and episodes

Each selected report group with a primary-site value (item 400) gets one thin
`condition_occurrence`. The chosen value is the group's lowest `naaccr_value_id` with item 400
and a non-blank `value_code` or `value_text`; its script-3 row supplies
`condition_start_date` and the cut `condition_source_value`, so no date or length rule is
repeated. Groups without one get no condition. No histology or ICD-O-3 combination logic runs.

| `group_condition.condition_target` | Case | `condition_concept_id` | `condition_source_concept_id` |
|---|---|---|---|
| `mapped` | `(400, value_code)` value map target in the `Condition` domain | map `concept_id` | map `source_concept_id` |
| `other_domain` | value map target in another domain | `0` | map `source_concept_id` |
| `no_target` | value map row with `concept_id = 0` | `0` | map `source_concept_id` |
| `no_map` | no value map row (including text-only values) | `0` | `0` |
| `collision_suppressed` | `naaccr.value_code_collision` lists the pair (#100); takes precedence | `0` | map `source_concept_id`, else `0` |

The type concept is `condition_type_registry`; every other column is NULL.

Each `(report_group.person_id, naaccr_value.episode_key)` gets one `episode`. The key is the
envelope's source tumor identity when it carries one, else its accession hash, so the same
accession under two patients is two episodes and one tumor identity across accessions is one.
`episode_concept_id` is `episode_disease` (Disease Episode), `episode_type_concept_id` is
`episode_type_registry`, `episode_start_date` is the earliest linked event date, and
`episode_end_date` is NULL. `episode_object_concept_id` is the nonzero `condition_concept_id` of
the episode's lowest-`report_group_id` condition with one, else `0`.
`episode_source_concept_id` is `0` and `episode_source_value`, parent, and number are NULL.
`episode_event` links every measurement, observation, and condition of that tumor, with the
`field_measurement_measurement_id`, `field_observation_observation_id`, or
`field_condition_occurrence_id` event field concept.

Reconciliation follows the clinical rows: owned rows that are no longer staged are deleted,
changed rows are updated, and new rows are inserted. Condition IDs stay stable per group and
episode IDs per `(person_id, episode_key)`; deleted IDs are never reused, and an unchanged rerun
writes nothing.

### Validation

`sdc-cdm validate` runs the manifest's `validate` entries (`9_validate.sql` per dialect) in one
transaction and writes nothing but its `etl.run` row. Each statement returns
`(check_name, category, actual)` rows, and both dialects emit the same check names. Python judges
the counts:

| Category | Covers | Passes when |
|---|---|---|
| `structural` | orphan `person_id`, episode, note-event, and `episode_event` targets on every row of the bridge-written tables; unknown concepts; orphan `note_report`, `value_event`, `group_condition`, `person_episode`, and period-derivation links; type, field, and constant slots of owned rows; standard, valid, routed-domain targets; route, table, value target, and both concept slots recomputed from the current maps and the #100 collision view, as scripts 3 and 4 derive them | `0` |
| `provenance` | owned rows that cannot reach an `intake.inbound_message` (patient first message, period boundaries, note links, values, condition values, episode keys), owned rows whose person differs from their note's or group's, and owned episode events that name an unowned row or another person's row | `0` |
| `reconciliation` | unversioned accessioned reports; selected reports without a note link, links to unselected reports, selected groups without exactly one note; patients without a person or period; selected values without a clinical row and rows for unselected values; site groups versus conditions; episode keys without an episode; owned rows without an episode event; `cdm_source` row count | `0` |
| `coverage` | unmapped CKey values, unmapped and other-domain item values, coded item values without a value target, conditions without a Condition target, item numbers absent from their dictionary version | at most the `validate_thresholds.csv` row |
| `report` | selected, historical, and accession-less reports; historical and excluded values; content-duplicate messages; one-day periods; #100 suppressions; truncated values; unowned OMOP rows | never fails |

The bridge owns the rows that its links name. These are persons with an `intake.patient` row,
periods with a derivation row, notes in `sdc.note_report`, clinical rows in
`naaccr.value_event`, conditions in `naaccr.group_condition`, episodes in
`naaccr.person_episode`, and every `episode_event` of an owned episode. Other OMOP rows are
reported but never failed, because the bridge leaves them in place. The orphan checks still cover
every row. Slot checks compare against the current concept maps, so rerun `bridge` after any `maps build`
before running `validate`. On SQL Server, validation runs at `SERIALIZABLE` so all units read one
database state; concurrent writers wait until it ends, and the session's previous isolation level
is then restored.

### Export bundle

`sdc-cdm export` reads `omop` only, in one consistent snapshot, and writes a new directory:

```text
OUTPUT_DIR/
  manifest.json            bundle_format, tool, cdm_version, exported_at, source_database,
                           etl_run_id, bridge_run_id, vocabulary, concept_map_coverage, csv, tables
  PERSON.csv  OBSERVATION_PERIOD.csv  NOTE.csv  MEASUREMENT.csv  OBSERVATION.csv
  CONDITION_OCCURRENCE.csv  EPISODE.csv  EPISODE_EVENT.csv  CDM_SOURCE.csv
  DOMAIN.csv  VOCABULARY.csv  CONCEPT_CLASS.csv  RELATIONSHIP.csv  CONCEPT.csv
  CONCEPT_RELATIONSHIP.csv  CONCEPT_SYNONYM.csv  CONCEPT_ANCESTOR.csv  DRUG_STRENGTH.csv
                           (vocabulary files only with --include-vocabulary)
```

Clinical files are listed in foreign-key load order. Headers are the upper-case CDM 5.4 columns of
`sdc_cdm.cdm.tables`, the same metadata the Athena loader reads, so the vocabulary files load back
with `vocab load --vocab-dir OUTPUT_DIR --delimiter comma`. `manifest.json` gives each file's row count and sha256.
Concept IDs in the bundle are this database's, including locally minted `NAACCR_LOCAL` IDs, so
bundles from different databases are not concept-comparable. No `intake`, `sdc`, `naaccr`, or
`etl` table is read for a CSV. The bundle still carries the MRN, accession, and narrative held in
`omop`.

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
