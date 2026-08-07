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
cross-schema foreign key. The later person transform owns the 1:1 mapping into OMOP; current bridge
regression fixtures seed the matching OMOP person explicitly.

### 2. `naaccr`: dictionary and captured values

`naaccr` is authoritative for the NAACCR dictionary and raw captured answers.

- `data_dictionary_version` scopes the dictionary by algorithm and version.
- `naaccr_item`, `staging_schema`, `schema_item`, value-set, requirement, registry, and staging
  lookup tables hold dictionary metadata.
- `naaccr_value` stores one row per logical answered item, including `item_num`, OBX sub-ID,
  coded, numeric, and text values, source units, observation date, dictionary version, and source
  report identifiers.
- `naaccr_concept_map` and `naaccr_value_concept_map` map item and item-value pairs to OMOP
  concepts. They are keyed independently of dictionary version because the bridge joins by item
  number and code.

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

### 4. `omop`: stock OMOP CDM 5.4

The executable OMOP DDL is the upstream SQLite or SQL Server CDM 5.4 drop. It has no SDC tables,
no `sdc_*` columns, and no `sdc_form_answer_id` foreign key. Repository-specific provenance uses
standard OMOP event and source-value columns.

### 5. `etl`: build and run records

- `schema_migration` stores each applied manifest path and SHA-256 hash.
- `run` records command, dialect, status, timing, and errors.
- `concept_constant` is reserved for resolved vocabulary constants in the later mapping phase.

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
   |          +--> bridge --> omop.note + omop.measurement
   |
   +--> sdc.template_* + sdc.sdc_form_answer    (SDC XML path)

database/manifest.json --> etl.schema_migration + etl.run
```

The bridge is a separate transform. It reads `naaccr` and `sdc`, writes only standard OMOP
columns, and does not run as part of `build`.

## Back-reference without a crosswalk

OMOP rows point back to source records using standard columns:

- `omop.note.note_source_value` stores the report accession.
- `omop.measurement.measurement_source_value` stores the NAACCR item number.
- `omop.measurement.measurement_event_id` points to `omop.note.note_id` when
  `meas_event_field_concept_id = 1147289` (`note.note_id`).
- Numeric answers use `value_as_number`; coded answers use `value_as_concept_id`; companion text
  or an unmapped raw code uses `value_source_value`.

The following SQLite query walks from a measurement back to report and dictionary metadata by
key joins rather than a stored crosswalk:

```sql
SELECT m.measurement_id,
       m.value_as_number,
       m.value_source_value,
       sr.report_accession,
       ni.name AS naaccr_item_name
FROM omop.measurement m
JOIN omop.note n
  ON n.note_id = m.measurement_event_id
JOIN sdc.sdc_report sr
  ON sr.report_accession = n.note_source_value
 AND sr.person_id = n.person_id
 AND sr.is_duplicate_accession = 0
JOIN naaccr.naaccr_item ni
  ON CAST(ni.item_num AS TEXT) = m.measurement_source_value
 AND ni.dd_version_id = (
       SELECT MAX(dd_version_id)
       FROM naaccr.data_dictionary_version
       WHERE is_current = 1
     )
WHERE m.meas_event_field_concept_id = 1147289;
```

## Physical model and build order

- **SQLite:** the control file attaches one sibling database per logical schema. For a control
  file `demo.db`, the files are `demo.etl.db`, `demo.intake.db`, `demo.omop.db`,
  `demo.naaccr.db`, and `demo.sdc.db`.
- **SQL Server:** `etl`, `intake`, `omop`, `naaccr`, and `sdc` are real schemas in one database.

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
