# Tracked Seed Data

These CSV files are tracked data because CI has no private Athena bundle from
which to derive or verify the required concept identifiers. Changes are
reviewed through git history.

## OMOP concept constants

`concept_constants.csv` names the OMOP concepts that repository ETL and import
code require. `sdc-cdm constants resolve` finds each concept by its
`vocabulary_id` and `concept_code`, then records the resulting IDs in
`etl.concept_constant`.

The tracked pairs replace historical literals `32817`, `32879`, `1147289`,
`8507`, `8532`, and concept `0`. The `unmapped` pair uses the real OMOP code
`No matching concept`; the former code `0` came only from a repository fixture.

These values are data rather than Python constants. A load and resolution run
against an authorized Athena extract is the acceptance gate. If a pair changes,
correct its CSV row and rerun both commands.

Several pairs have been checked against an Athena extract (vocabulary
`v5.0 27-FEB-26`). In the `Type Concept` vocabulary, concept codes are
`OMOP…` identifiers, not concept names: EHR (32817) is `OMOP4976890` and
Registry (32879) is `OMOP4976952`. `period_type_registry` therefore shares
`measurement_type_registry`'s pair. `cdm_version` is `CDM` / `CDM v5.4.0`
(756265). The `Gender` pairs and `unmapped` match the extract as well.
`field_note_note_id` does not: that extract has no `CDM` concept with code
`note.note_id`, and the historical literal 1147289 is `dose_era.person_id`.
Correct that pair before loading a real extract: `vocab load` and
`constants resolve` both fail until every tracked pair is present.

## OMOP CDM source

`cdm_source.csv` holds the one `omop.cdm_source` row that `sdc-cdm bridge`
writes, except for `vocabulary_version` and `cdm_version_concept_id`. The bridge
takes those from the loaded vocabulary's `None` row and the `cdm_version`
constant. The tracked row describes a **synthetic test source** with fixed
release dates. A real deployment replaces it with its own source name, holder,
documentation, and release dates, or passes `--seed-dir` to `bridge`. The bridge
rejects a missing file, a changed header, any number of data rows other than
one, a blank required field, a value longer than its SQL Server CDM column, a
date that is not `YYYY-MM-DD`, and a `cdm_version` other than `5.4` (the shipped
OMOP schema, which the bridge pairs with the `CDM v5.4.0` concept).

## NAACCR concept maps

`concept_map_overrides.csv` is the reviewed layer-2 input. A row is active only
when `omop_concept_id` is non-blank; rows with a blank target remain inactive
skeletons. A blank `code` denotes an item-level row. A blank
`omop_concept_id` is not a target. Source concepts always come from the local
allocation ledger, even when Athena provides a standard target.

`naaccr_item_exclusions.csv` lists NAACCR items that are excluded from mapping
and local concept creation, together with the recorded reason.
