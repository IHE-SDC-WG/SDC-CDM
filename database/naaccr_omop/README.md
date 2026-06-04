# NAACCR to OMOP Extension Mapping Spec

This directory contains the repo-local, vendor-neutral mapping artifact derived
from the NAACCR-to-OMOP extension-table workbooks.

## Files

- `naaccr_omop_extension_mapping_spec.json` is the JSON mapping specification
  generated from the three XLSX workbooks in `NAACRToOMOPmaps/`.
- `../../tools/convert_naaccr_omop_maps.py` is the dependency-free converter
  used to regenerate the JSON spec.

## Pipeline Boundary

The `omop` branch of this SDC-CDM repo currently implements the working-group
SQL Server path:

```text
dbo.naaccr_staging -> EPISODE -> OBSERVATION / MEASUREMENT -> EPISODE_EVENT
```

That path is represented by `database/ddl/sqlserver/naaccr_to_omop_etl.sql`
and the SQL Server runbook. It remains platform-neutral and does not depend on
PhenoML.

The PhenoML Workflows path is different:

```text
NAACCR XML or V2 -> JSON -> PhenoML workflow -> OMOP CDM 5.4 rows
```

PhenoML Workflows should consume JSON only. Any XLSX workbook, NAACCR XML, or
HL7 V2 input must be converted upstream before workflow execution.

The PhenoML-specific implementation is co-located in `phenoml-workflows/`
because PhenoML is acting as the service provider for CAP. Keep that package
separate from the neutral SQL and mapping artifacts, and keep credentials out
of committed files.

## Working-Group Rules Captured

The generated spec encodes the rules confirmed in SDC-CDM discussion #77
from May 27, 2026:

- Pathology and measurement-like NAACCR items, including SSDIs, grades, staging,
  and constrained pick lists, default to `MEASUREMENT`.
- Demographic, registry-management, confidential, and otherwise NAACCR-specific
  data remains in extension tables unless it maps cleanly to OMOP core.
- Foreign keys live on the NAACCR extension-table side and point to OMOP records.
- Do not add non-FK NAACCR fields to OMOP core tables.
- The preferred direction is CAP to NAACCR to MEASUREMENT.

Discussion #78 is dated June 3, 2026 and is a future agenda as of June 1, 2026,
so it is referenced as a planning input rather than as a final decision record.

## Regenerating

Run from the repository root:

```bash
python3 tools/convert_naaccr_omop_maps.py
```

The converter reads:

- `NAACRToOMOPmaps/extension_table_names.xlsx`
- `NAACRToOMOPmaps/NAACCR_OMOP_Extension_Tables_by_ConceptClass.xlsx`
- `NAACRToOMOPmaps/NAACCR_PERSON_proposed.xlsx`

and writes:

- `database/naaccr_omop/naaccr_omop_extension_mapping_spec.json`

Use `--output -` to inspect the JSON on stdout, or `--compact` for a compact
artifact.

Regeneration preserves mapping review metadata already present in
`workflow_input.item_mappings`, matched by `concept_class_id + concept_code`.
The workbook-derived fields are refreshed from the source XLSX files, while the
following review fields remain canonical in the JSON:

- `review_status`
- `reviewer`
- `reviewed_at`
- `review_notes`
- `rationale`
- `target_override_table`
- `target_override_field`
- `needs_wg_decision`

Rows from `NAACCR_PERSON_proposed.xlsx` are matched back into
`workflow_input.item_mappings` by `naaccr_concept_id + field_code` to
`concept_id + concept_code`. When a match exists, the NAACCR_PERSON proposal is
the effective mapping used by the review UI and generated Excel review workbook,
so patient-level fields are not replaced by generic concept-class defaults.

Valid review statuses are `unreviewed`, `needs_review`, `approved`, `rejected`,
and `deferred`. Target override fields are advisory in v1 and do not affect
workflow execution.

## Human Review

The in-repo `phenoml-workflows/` package provides both a web review UI and Excel
export/import helpers. The JSON spec remains canonical; Excel is a generated
review artifact.

The web UI exposes:

- `GET /` for the dashboard.
- `GET /api/mappings` for filtered mapping rows.
- `PATCH /api/mappings/<concept_class_id>/<concept_code>/review` for review
  field edits.
- `GET /excel/export` to download the review workbook.
- `POST /excel/import` to upload an `.xlsx` workbook and stage a diff.
- `POST /excel/apply` to apply the current valid staged diff.
- `GET /excel/diff` to download the staged diff report.

Excel import only accepts review/governance fields. Edits to source mapping
columns are ignored and reported in the import diff.

## PhenoML Package

The in-repo `phenoml-workflows/` package references this JSON spec as an input
and implements:

- a config module containing `instanceUrl`, `clientId`, and `clientSecret`;
- `create_client(config)` using `PhenomlClient` from the official Python
  `phenoml` SDK;
- a workflow runner that loads JSON workflow definitions and this mapping spec;
- a NAACCR XML or V2 to JSON preprocessor;
- sample execution that emits OMOP 5.4-compatible `episode`,
  `episode_event`, `measurement`, `observation`, and extension-table rows.

Credentials must not be committed. The PhenoML package should fail loudly with a
clear "credentials not configured" message when required credentials are absent.

## References

- OHDSI CDM v5.4: https://ohdsi.github.io/CommonDataModel/cdm54.html
- OHDSI CDM wiki page supplied with the prompt:
  https://www.ohdsi.org/web/wiki/doku.php?id=documentation:cdm:common_data_model
- FHIR-to-OMOP IG technical artifacts:
  https://build.fhir.org/ig/HL7/fhir-omop-ig/en/technical_artifacts.html
- PhenoML Workflows docs: https://developer.pheno.ml/docs/workflows
- SDC-CDM discussion #77: https://github.com/IHE-SDC-WG/SDC-CDM/discussions/77
- SDC-CDM discussion #78: https://github.com/IHE-SDC-WG/SDC-CDM/discussions/78
- Local OMOP clinical-event diagram:
  `diagrams/original-omop/by-domain/clinical-events.mmd`
- Local OMOP episode diagram:
  `diagrams/original-omop/by-domain/eras-episodes-cohorts-metadata.mmd`
- Local cancer-case diagram:
  `diagrams/sdc-sdm-modifications/by-domain/CancerCase.mmd`
