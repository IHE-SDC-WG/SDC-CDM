# eCP to OMOP Mapping

**Status:** updated for the five-schema architecture.

CAP eCP / NAACCR answers are ingested in two steps:

1. The planned Python importer parses the message once and writes source data to:
   - `intake.inbound_message` for exact payload and envelope provenance.
   - `intake.patient` for local patient identity.
   - `sdc.sdc_report` for report metadata.
   - `naaccr.naaccr_value` for raw answer values.
2. The bridge reads `sdc` plus `naaccr` and writes only stock OMOP rows.

## OMOP Target

eCP synoptic Q&A defaults to OMOP `measurement`. Each item is a qualitative or quantitative result from a standardized pathology activity. Once concept mappings are complete, routing can use the mapped concept `domain_id`; until then, the bridge writes measurement rows by default.

Value handling:

| Source value | OMOP column |
|---|---|
| numeric | `measurement.value_as_number` plus `unit_source_value` |
| coded | `measurement.value_as_concept_id` when mapped; raw code is used in `value_source_value` when no companion text is present |
| text | `measurement.value_source_value`; companion text takes precedence over the raw code |

CAP OBX segments sharing an OBX-4 sub-ID are staged as one logical `naaccr_value`.
The coded component populates `value_code`, the numeric component populates `value_num`,
and a nonnumeric ST companion populates `value_text`.

## Report Back-Reference

Each report creates one OMOP `note` row. The note stores the accession in `note.note_source_value`.

Measurements point to that note through standard OMOP fields:

- `measurement.measurement_event_id = note.note_id`
- `measurement.meas_event_field_concept_id = CDM field concept for note.note_id`

There is no `sdc_form_answer_id` column on OMOP tables. Report and item context is recovered
with a key join:

```sql
SELECT
  m.measurement_id,
  n.note_source_value AS report_accession,
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

## Importer boundary

Phase 0 has no active HL7 importer. The retired C# importer's expected output is frozen under
`contracts/golden/` for the Python port. The new importer will write `intake`, `sdc.sdc_report`,
and `naaccr.naaccr_value`; it will not write SDC XML form tables or OMOP rows directly.

Each `naaccr_value` row records its source `sdc_report_id`, and a missing OBR-3 accession is
stored as NULL rather than an empty string. Only non-duplicate, accessioned reports bridge to
OMOP, so re-imports and accession-less reports never produce extra notes or measurements.

The SQLite and SQL Server bridge scripts follow the same boundary. Phase 0 tests execute them
through the Python SQL splitter; a public `bridge` command is assigned to Phase 4.
