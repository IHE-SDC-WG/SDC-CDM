# eCP to OMOP Mapping

**Status:** updated for the three-schema architecture.

CAP eCP / NAACCR answers are ingested in two steps:

1. The importer parses the message once and writes source data to:
   - `sdc.sdc_report` and `sdc.sdc_form_answer` for report and form structure.
   - `naaccr.naaccr_value` for raw answer values.
2. The bridge reads `sdc` plus `naaccr` and writes only stock OMOP rows.

## OMOP Target

eCP synoptic Q&A defaults to OMOP `measurement`. Each item is a qualitative or quantitative result from a standardized pathology activity. Once concept mappings are complete, routing can use the mapped concept `domain_id`; until then, the bridge writes measurement rows by default.

Value handling:

| Source value | OMOP column |
|---|---|
| numeric | `measurement.value_as_number` plus `unit_source_value` |
| coded | `measurement.value_as_concept_id` when mapped, with raw code in `value_source_value` |
| text | `measurement.value_source_value` |

## Report Back-Reference

Each report creates one OMOP `note` row. The note stores the accession in `note.note_source_value`.

Measurements point to that note through standard OMOP fields:

- `measurement.measurement_event_id = note.note_id`
- `measurement.meas_event_field_concept_id = CDM field concept for note.note_id`

There is no `sdc_form_answer_id` column on OMOP tables. SDC context is recovered with a key join:

```sql
SELECT
  m.measurement_id,
  n.note_source_value AS report_accession,
  sfa.question_text,
  nv.value_code,
  nv.value_num
FROM omop.measurement m
JOIN omop.note n
  ON n.note_id = m.measurement_event_id
JOIN sdc.sdc_report sr
  ON sr.report_accession = n.note_source_value
JOIN sdc.sdc_form_answer sfa
  ON sfa.report_id = sr.sdc_report_id
JOIN naaccr.naaccr_value nv
  ON nv.report_accession = sr.report_accession
 AND CAST(nv.item_num AS TEXT) = substr(sfa.question_sdcid, 1, instr(sfa.question_sdcid || '.', '.') - 1);
```

## Importer Boundary

`ImportNaaccrVolV.cs` writes `sdc` and `naaccr` only. It does not write OMOP rows directly.

The SQLite implementation exposes `BridgeNaaccrSdcToOmop()` for the bridge step. Other dialects should follow the same boundary.
