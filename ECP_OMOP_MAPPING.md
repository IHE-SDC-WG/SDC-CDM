# eCP → OMOP Mapping

**Status:** implemented. **Scope:** how CAP Electronic Cancer Protocol (eCP) synoptic
report questions and answers are mapped into OMOP CDM v5.4.

## Decision

**eCP synoptic Q&A defaults to the OMOP `measurement` table.** Each synoptic item is a
**qualitative or quantitative result of a standardized pathology activity** (the pathologic
examination) — which is the OMOP definition of a Measurement:

> *"Measurements differ from Observations in that they require a standardized test or some other
> activity to generate a quantitative or qualitative result."* — OMOP CDM 5.4

This also matches the established OHDSI NAACCR vocabulary, where NAACCR items are predominantly
**Measurement-domain** concepts with the coded answer carried in `value_as_concept_id`.

### The rule is domain-driven (Measurement is the default)

The authoritative determinant is the **`domain_id` of the mapped standard concept**, not the
answer's datatype. Practically:

- **Result-bearing synoptic items** (tumor size, grade, stage, margins, LVI, node status,
  histologic type…) → **`measurement`**. This is the bulk of a report and the default.
- A **minority of contextual items** whose mapped concept is Observation-domain → `observation`.
- Some items legitimately map elsewhere (e.g. Procedure, Specimen) — out of scope here.

Until eCP items are mapped to standard concepts (see the scope doc below), we **default
everything to `measurement`**; domain-driven splitting is the follow-up once `domain_id` is readable.

## Value-column mapping (measurement has no `value_as_string`)

| HL7 OBX-2 | OMOP measurement column | sample |
|---|---|---|
| `CWE` (coded) | `value_as_concept_id` (TODO until vocab) + human text in `value_source_value` | `2122…Adrenalectomy, total` |
| `NM` (numeric) | `value_as_number` + `unit_source_value` / `unit_concept_id` | `10 cm`, `156 g` |
| `ST` (text) | `value_source_value` | "specify" text |

The question maps to `measurement_concept_id` (TODO until vocab), with the raw item in
`measurement_source_value`. The report narrative/comment goes to the NOTE (below).

## Single-report reference (OMOP-native)

Each synoptic report (the HL7 `OBR` segment, LOINC `60568-3`, accession e.g. `15SL-2`) becomes:

- one row in **`sdc_template_instance_ecp`** carrying the OBR `report_accession`/`report_loinc`; and
- one OMOP **`note`** row holding the report narrative.

Every measurement from the report sets **`measurement_event_id = note.note_id`** and
**`meas_event_field_concept_id`** = the CDM field concept for `note.note_id`. The
`measurement → sdc_form_answer → template_instance → sdc_template_instance_ecp` FK chain remains as
the repo-native reference. Within a report, a question's sub-answers (unit + value, coded pick +
"specify" text — grouped by HL7 OBX-4) link via `sdc_form_answer.parent_form_answer_id`.

### Re-import / duplicates
Re-importing the same report is **never deduped** — rows are always inserted, and collisions are
**flagged**: `sdc_template_instance_ecp.is_duplicate_accession = 1` with `first_seen_ecp_id`
pointing to the earliest row with that accession.

## What this means in each path

| Area | Behavior |
|---|---|
| C# importer (`ImportNaaccrVolV.cs`) | all answers → `WriteMeasurementLinkedToFormAnswer`; one NOTE per report; OBX-4 grouping; duplicate flagging |
| `measurement` (SQLite FK / PostgreSQL `sdc_*` columns) | carries the SDC linkage; `observation` keeps the linkage too for the future domain-driven minority |
| SQL Server ETL | all staged items → `measurement` (`value_as_concept_id`/`value_as_number`/`value_source_value`), `measurement_event_id` → NOTE, episode_event link |
| PhenoML mapper | measurement-default; Observation-domain items → observation; both anchor to the NOTE |
| Mapping spec | `omop_table` reflects the workbook (mostly MEASUREMENT); domain accuracy comes from the concept-mapping work |

## Follow-ups
- **Concept mapping** (scoped in `ECP_CONCEPT_MAPPING_SCOPE.md`): map eCP items + coded answers to
  standard OMOP concepts so `domain_id` can drive routing and `measurement_concept_id` /
  `value_as_concept_id` get populated.
- Confirm the `note.note_id` field concept_id (used `1147289`) and a synoptic-report
  `note_class_concept_id` against the loaded vocabulary.
- Resolve the `MEASUREMENT + CONDITION_OCCURRENCE` combo rows in the spec with the working group.

## Verification
After importing `sample_data/naaccr_v2/obx-Adrenal.hl7`: eCP items land in `measurement` (the 2 NM
items carry `value_as_number`; coded items carry `value_source_value`), 1 `note` whose
`note_source_value` is the OBR accession, and all measurements share that one `measurement_event_id`.
