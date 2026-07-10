# Schema Architecture: NAACCR + SDC + OMOP (separation of concerns)

**Status:** implemented. **Goal:** keep SDC/NAACCR extensions out of
OMOP core. Instead, one physical database with **separate schemas per concern**, an unmodified
OMOP CDM, and a transform that bridges them. This honors the policy already in
`naaccr_omop/README.md`: *FKs live on the NAACCR side; do not add non-FK fields to OMOP core.*

## Schemas (one database, extensible)

Start with three schemas; add more later (e.g. `vocab`, `fhir`, `audit`, `etl`) without disturbing
these. Cross-schema references use schema-qualified names within the one database.

### 1. `naaccr` — NAACCR-native dictionary + captured values
Authoritative for the NAACCR data dictionary **and** the raw captured answers.

- **Dictionary / metadata** (today's `cap.*`):
  `naaccr_item` (item_num, name, xml_id), `staging_schema`, `schema_selection_rule`,
  `schema_item`, `schema_item_code` (value sets), `schema_item_requirement`, `registry`.
- **Captured values — staging shape** (per the chosen model, like today's `dbo.naaccr_staging`):
  `naaccr_value` with `person_id, episode_key, sdc_report_id, report_accession, schema_id_number,
  item_num, value_code, value_num, value_unit_source, observation_date`. One row per answered item.
  `sdc_report_id` is a logical (non-FK) pointer to the originating `sdc.sdc_report`;
  `report_accession` is retained as the denormalized business key (OBR accession).
- **Concept maps**: `naaccr_concept_map` (item_num → OMOP concept), `naaccr_value_concept_map`
  (item code → value concept).

### 2. `sdc` — Structured Data Capture and report metadata
The IHE-SDC XML-form layer stores form structure and submitted answer values. The eCP/HL7
path uses `sdc_report` for report metadata and keeps its raw answers in `naaccr_value`.

- `template_sdc`, `template_item`, `template_instance`, `template_term_map`, `template_map_content`
- `sdc_form_answer` (question/section/list-item context and value for SDC XML intake), `sdc_specimen`,
  `observation_specimens`
- `sdc_report` (renamed `sdc_template_instance_ecp`): the synoptic-report header — `report_accession`,
  `report_loinc` (60568-3), template name/version, narrative, `is_duplicate_accession`,
  `first_seen_report_id`.

`naaccr_value` relates to `sdc_report` by the `naaccr_value.sdc_report_id` provenance pointer
(the originating report), with `report_accession` kept as a denormalized business key. The bridge
joins on `sdc_report_id` so re-imported (duplicate-flagged) reports and accession-less reports
never fan out. No hard cross-schema FK is required.
`sdc_form_answer` belongs to the separate SDC XML form path and is keyed to `template_instance`.

### 3. `omop` — vanilla OMOP CDM 5.4 (UNMODIFIED)
Stock OHDSI DDL, dropped in unchanged. **No `sdc_*` columns, no SDC tables, no `sdc_form_answer_id`
FK.** Upgradable by swapping the upstream DDL; ATLAS/Achilles/DQD work out of the box.

## Back-reference WITHOUT a crosswalk (loose coupling)

OMOP rows point back to the source using **only standard OMOP columns**:

- `omop.measurement.measurement_source_value` = the NAACCR item number
- `omop.measurement.measurement_source_concept_id` = mapped concept
- `omop.measurement.measurement_event_id` = `omop.note.note_id`; `omop.note.note_source_value`
  = the report accession
- numeric → `value_as_number` (+ `unit_source_value`); coded → `value_as_concept_id`; text →
  `value_source_value`

Going from an OMOP measurement back to its report and NAACCR item metadata is a **key join**,
not a stored FK:

```sql
SELECT m.measurement_id, m.value_as_number, m.value_source_value,
       sr.report_accession, ni.name AS naaccr_item_name
FROM omop.measurement m
JOIN omop.note n       ON n.note_id = m.measurement_event_id
JOIN sdc.sdc_report sr ON sr.report_accession = n.note_source_value
                      AND sr.person_id = n.person_id
                      AND sr.is_duplicate_accession = 0
JOIN naaccr.naaccr_item ni
  ON CAST(ni.item_num AS TEXT) = m.measurement_source_value
WHERE m.meas_event_field_concept_id = 1147289;
```

## Data flow

```
HL7 V2 / NAACCR XML
   │  (importer: parse once)
   ├─► naaccr.naaccr_value         (raw answers, staging shape)
   ├─► naaccr.* dictionary         (seeded/reference)
   └─► sdc.sdc_report               (report header)
            │
            ▼  (bridge / transform — reads naaccr+sdc, writes standard OMOP only)
   omop.note (1 per accession) + omop.measurement (measurement_event_id→note)

SDC XML form submission
   └─► sdc.template_* + sdc.sdc_form_answer   (form structure + answer values)
```

Two steps: (1) ingest to `naaccr`+`sdc`; (2) transform to `omop`. The transform is the only place
that knows both sides, and it writes vanilla OMOP.

## Physical model per dialect (decide at implementation)

- **PostgreSQL / SQL Server**: real `CREATE SCHEMA naaccr|sdc|omop`; schema-qualified joins are free.
  (SQL Server already does `cap` + `dbo`.)
- **SQLite**: no native schemas — emulate with **`ATTACH DATABASE 'naaccr.db' AS naaccr`** (one file
  per schema, schema-qualified names + cross-schema joins work), or a single file with `naaccr_` /
  `sdc_` / `omop_` table-name prefixes. ATTACH is the closer analog and keeps the qualified-name model.

## Repo layout

```
database/
  schemas/
    naaccr/ddl/{sqlite,postgresql,sqlserver}/   + seed/   (dictionary, concept maps)
    sdc/ddl/{sqlite,postgresql,sqlserver}/
    omop/ddl/{sqlite,postgresql,sqlserver}/      (vendored upstream OHDSI CDM 5.4, unmodified)
  etl/                                           (naaccr+sdc -> omop transform, dialect-aware)
  build.sh                                       (create schemas in order; load seeds; run etl)
```

## Migration from today

- **Delete from OMOP core**: the 14 `sdc_*` columns on `observation` (PG), the `sdc_form_answer_id`
  ALTERs/indexes (SQLite), and any SDC tables currently created inside the OMOP DDL.
- **Move to `sdc`**: `template_*`, `sdc_form_answer`, `sdc_specimen`, `observation_specimens`,
  `sdc_template_instance_ecp`→`sdc_report`. Drop the duplicate `sdc_observation` answer store.
- **Move to `naaccr`**: `cap.*` dictionary + a `naaccr_value` (staging-shape) answer table + concept maps.
- **Keep as-is (already OMOP-native, survives untouched)**: the `note` per report and
  `observation_event_id` linkage we just built; `observation_source_value`/`_concept_id`.
- **C# importer**: split writes — populate `naaccr`/`sdc`, then run the bridge to emit `omop`.
  `ISdcCdm` gains `naaccr`/`sdc` writers; the OMOP writers target vanilla columns only.
- **Queries**: `ecp_query_examples.sql` denormalized `sdc_*` selects become key joins (example above).

## Decisions locked in
- One database, three schemas (`naaccr`, `sdc`, `omop`), extensible to more.
- Captured values stored in NAACCR staging shape.
- OMOP back-reference via `observation_source_value` + `observation_event_id` only — no crosswalk table.
- Dialects chosen at implementation time.

## Open questions for implementation
- SQLite: ATTACH-per-schema vs name-prefix (affects build scripts and how the C# connection attaches).
- Whether the importer writes `omop` inline (single pass) or the bridge is a separate batch step.

## Resolved
- **`naaccr_value` → report key.** Resolved: the row-to-report link is `naaccr_value.sdc_report_id`
  (a logical pointer to the originating `sdc.sdc_report`), not `report_accession`. `report_accession`
  can be absent (stored NULL) and is not unique across re-imports, so the bridge keys on
  `sdc_report_id`; `episode_key` remains the intra-report grouping key.
