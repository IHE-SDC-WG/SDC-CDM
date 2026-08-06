# NAACCR to OMOP Mapping Spec

This directory contains the canonical review artifact generated from the NAACCR to OMOP workbooks.

## Files

- `naaccr_omop_extension_mapping_spec.json` is the JSON mapping specification generated from the three XLSX workbooks in `NAACRToOMOPmaps/`.
- `../../tools/convert_naaccr_omop_maps.py` regenerates the JSON spec.

## Architecture Boundary

The active database architecture uses five schemas. This mapping artifact concerns the three
clinical schemas in the center of the flow:

```text
naaccr.naaccr_value + naaccr concept maps
sdc.sdc_report
        -> bridge
omop.note + omop.measurement
```

`intake` owns source payloads and patient identity; `etl` owns build and run records.

`sdc.sdc_form_answer` is reserved for SDC XML form intake and is not part of the eCP bridge.

The mapping spec remains canonical for review metadata and item-level storage decisions. In the new layout, workbook storage concepts should be read as NAACCR-side guidance, not as instructions to add fields to OMOP core tables.

## Rules Captured

- eCP synoptic Q&A defaults to OMOP `measurement`.
- NAACCR-specific fields that do not map cleanly to OMOP core remain in the `naaccr` schema.
- Do not add non-FK NAACCR or SDC fields to OMOP core tables.
- Excel is a generated review artifact. The JSON remains the source of truth.

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

Regeneration preserves review fields already present in `workflow_input.item_mappings`.

## Human Review

The `phenoml-workflows/` package provides the web review UI and Excel import/export helpers. Review edits must flow back into the JSON spec through the app import/apply path.
