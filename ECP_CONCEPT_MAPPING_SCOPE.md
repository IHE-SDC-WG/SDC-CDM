# Scope: eCP → Standard OMOP Concept Mapping (enables domain-driven routing)

**Status:** scoping (not yet implemented). **Why:** the decision in `ECP_OMOP_MAPPING.md` is
*domain-driven, Measurement-default*. True domain-driven routing — and populating
`measurement_concept_id` / `value_as_concept_id` — requires mapping eCP items and their coded
answers to **standard OMOP concepts** and reading each concept's `domain_id`. That mapping does
not exist in the repo yet; today we default everything to `measurement` with `concept_id = 0`.

## The gap (what's missing today)

- The mapping spec's `concept_id` values (e.g. `442`) are **NAACCR row ids, not standard OMOP
  concept_ids**; `concept_code` is the NAACCR field name; the field labeled `domain_id` actually
  holds the **NAACCR data type** (`DIGITS`/`TEXT`/`DATE`…), not the OMOP domain.
- The C# importer / PhenoML mapper write `measurement_concept_id = 0` and `value_as_concept_id =
  null` (TODO markers in code).
- The SQL Server ETL already *assumes* `naaccr.NAACCR_CONCEPT_MAP` (item→concept) and
  `naaccr.NAACCR_VALUE_CONCEPT_MAP` (answer code→value concept) exist — those maps are the shape we need
  everywhere.

## Deliverables

1. **Item → standard concept map**: `(CAP eCC code | NAACCR item_num) → standard concept_id +
   domain_id + standard_concept`. Sourced from the OHDSI NAACCR vocabulary (Athena) and CAP eCC ↔
   LOINC/SNOMED crosswalks. Mirrors `naaccr.NAACCR_CONCEPT_MAP`.
2. **Answer-value → concept map**: `(item, answer code) → value concept_id`. Mirrors
   `naaccr.NAACCR_VALUE_CONCEPT_MAP`. Drives `value_as_concept_id` for coded answers.
3. **Real OMOP domain in the spec**: add an `omop_domain_id` field (distinct from the NAACCR data
   type) to `naaccr_omop_extension_mapping_spec.json` via `convert_naaccr_omop_maps.py`; consider
   renaming the existing `domain_id` field to `naaccr_data_type` to end the confusion.
4. **Wire routing + concept population** into all paths:
   - importer/mapper/ETL look up the item concept + `domain_id`; route by domain (Measurement
     default; Observation-domain minority → observation); populate
     `measurement_concept_id`/`observation_concept_id` and `value_as_concept_id`.
   - unmapped items keep the default (Measurement, `concept_id = 0`) and are reported, not dropped.

## Sources / dependencies
- OHDSI **NAACCR vocabulary** (Athena) — NAACCR variable + value concepts, with domains.
- CAP **eCC**/eCP code system ↔ LOINC/SNOMED crosswalk (CAP-provided where available).
- Existing SQL Server `naaccr.NAACCR_CONCEPT_MAP` / `naaccr.NAACCR_VALUE_CONCEPT_MAP` table shapes and
  `ssdi_3nf.sql` dictionary as the data model to reuse.

## Phasing
1. Load/stage the NAACCR standard-concept vocabulary; build the item concept map for the eCP
   templates in scope first (Adrenal, then Breast/Appendix).
2. Build the value-set (answer) concept maps for those templates.
3. Add `omop_domain_id` to the spec + converter; regenerate.
4. Flip importer/mapper/ETL from blanket-Measurement to domain-driven; populate concept ids.
5. Backfill / re-import; validate counts by domain.

## Open questions
- Vocabulary source + licensing, and refresh cadence (NAACCR releases).
- Which eCP templates to map first, and coverage target before flipping to domain-driven.
- Handling of items with no standard concept (stay Measurement `concept_id = 0`, flagged).
- Confirm whether the 3-schema architecture (`database/SCHEMA_ARCHITECTURE.md`) lands before or
  after this — the concept maps belong in the `naaccr` schema under that design.

## Effort (rough)
Vocabulary load + item/value maps for one template: small–medium. Spec/converter `omop_domain_id`:
small. Wiring all four paths to domain-driven + concept population: medium. Full template coverage:
ongoing, data-entry-bound.
