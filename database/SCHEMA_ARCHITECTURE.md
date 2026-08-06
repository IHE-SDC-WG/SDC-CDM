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

- **Version dimension**: `data_dictionary_version` (`algorithm`, `version`, `naaccr_version`,
  `source_api`, `is_current`) is the parent of the dictionary. Every dictionary row is scoped to a
  `dd_version_id`, so multiple SEER algorithm/version generations (e.g. `eod_public`/`3.3`) coexist
  and a captured answer records the version it was coded against.
- **Dictionary / metadata**: `naaccr_item` (item_num, name, xml_id, plus field metadata:
  `unit`, `decimal_places`, and — populated later from the NAACCR Data Dictionary API —
  `data_type`, `length`, `padding`, `alignment`, `trim`, `section`, `parent_xml_element`),
  `staging_schema`, `schema_selection_rule`, `schema_item` (with `item_role` = `input` | `output`,
  so derived staging outputs are first-class), `schema_item_code` (value sets),
  `schema_item_requirement`, `registry`. All are keyed by `dd_version_id`.
- **Staging lookup-table catalog** (the SEER value-validation / staging building blocks):
  `staging_table`, `staging_table_column`, `staging_table_row` (row `cells` stored as a JSON array
  aligned to the columns), and `schema_involved_table` linking each schema to its tables. Enables
  value validation and future offline stage derivation.
- **Captured values — staging shape**:
  `naaccr_value` with `person_id, episode_key, sdc_report_id, report_accession, schema_id_number,
  item_num, obx_sub_id, value_code, value_num, value_text, value_unit_source, observation_date,
  dd_version_id`. One row per logical answered item. CWE and numeric/text OBX components sharing
  an OBX-4 sub-ID are combined in that row. `dd_version_id` is a nullable stamp of the dictionary version the answer was coded
  against. `sdc_report_id` is a logical (non-FK) pointer to the originating `sdc.sdc_report`;
  `report_accession` is retained as the denormalized business key (OBR accession).
- **Concept maps**: `naaccr_concept_map` (item_num → OMOP concept), `naaccr_value_concept_map`
  (item code → value concept). These are **version-independent** (a NAACCR item/code maps to the
  same OMOP concept across dictionary versions) so they are keyed on `item_num` / `(item_num, code)`
  only and reference `naaccr_item` logically, matching how the ETL bridge joins.

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
 AND ni.dd_version_id = (
       SELECT MAX(dd_version_id)
       FROM naaccr.data_dictionary_version
       WHERE is_current = 1
     )
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

Diagrams of the above live in [`../diagrams/three-schema/`](../diagrams/three-schema/):
[`three-schema-overview.mmd`](../diagrams/three-schema/three-schema-overview.mmd) for both intake
paths at a glance, [`naaccr.mmd`](../diagrams/three-schema/naaccr.mmd) and
[`sdc.mmd`](../diagrams/three-schema/sdc.mmd) for the full per-schema detail, and
[`naaccr-sdc-to-omop-bridge.mmd`](../diagrams/three-schema/naaccr-sdc-to-omop-bridge.mmd) for the
transform itself (columns read/written, hardcoded concept ids, and the guards that stop a row
bridging). They are hand-maintained — update them alongside the DDL.

## Physical model per dialect

- **SQL Server**: real `CREATE SCHEMA etl|intake|omop|naaccr|sdc`; schema-qualified joins are direct.
- **SQLite**: no native schemas, so the build driver attaches one database file per logical schema.
  Schema-qualified names and cross-database joins retain the same SQL shape.

## Repo layout

```
database/
  manifest.json                                  (single ordered build inventory)
  schemas/
    intake/ddl/{sqlite,sqlserver}/
    etl/ddl/{sqlite,sqlserver}/
    naaccr/ddl/{sqlite,sqlserver}/              + seed/   (dictionary, concept maps)
    sdc/ddl/{sqlite,sqlserver}/
    omop/ddl/{sqlite,sqlserver}/                 (OHDSI CDM 5.4)
  etl/                                           (naaccr+sdc -> omop transform, dialect-aware)
diagrams/
  three-schema/                                  (ERDs for naaccr, sdc, and the bridge)
  original-omop/                                 (upstream OMOP CDM 5.4 reference ERDs)
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
- The `naaccr` dictionary is a versioned 3NF projection of the SEER Staging API (keyed by
  `data_dictionary_version`). Additional SEER\*API reference sources (full NAACCR DD catalog, site
  recodes, MPH, Disease DB, Rx/NDC/HCPCS, glossary) are deferred — see
  `schemas/naaccr/FUTURE_REFERENCE_TABLES.md`.

## Open questions for implementation
- SQLite: ATTACH-per-schema vs name-prefix (affects build scripts and how the C# connection attaches).
- Whether the importer writes `omop` inline (single pass) or the bridge is a separate batch step.

## Resolved
- **`naaccr_value` → report key.** Resolved: the row-to-report link is `naaccr_value.sdc_report_id`
  (a logical pointer to the originating `sdc.sdc_report`), not `report_accession`. `report_accession`
  can be absent (stored NULL) and is not unique across re-imports, so the bridge keys on
  `sdc_report_id`; `episode_key` remains the intra-report grouping key.
