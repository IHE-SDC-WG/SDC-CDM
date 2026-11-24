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
Registry (32879) is `OMOP4976952`. `period_type_registry` and
`observation_type_registry` therefore share `measurement_type_registry`'s pair.
`cdm_version` is `CDM` / `CDM v5.4.0` (756265). The `Gender` pairs and
`unmapped` match the extract as well. `field_note_note_id` is `CDM` / `CDM212`
(1147156, the v5 `note.note_id` field concept). The extract has no `CDM`
concept with code `note.note_id`, and the historical literal 1147289 is
`dose_era.person_id`. The pre-rebuild bridge that carried that literal was
retired in Phase 4.5; no bridge or validation script embeds a concept ID.

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

## Validation thresholds

`validate_thresholds.csv` caps each `coverage` check of `sdc-cdm validate`:
unmapped CKey values, unmapped and other-domain item values, coded values
without a value target, primary sites without a Condition target, and item
numbers absent from the loaded dictionary. Each row is
`check_name,max_count,reason`; a check passes when its count is at most
`max_count`. Structural, provenance, and reconciliation checks never read this
file; they must be zero.

The tracked rows are the **fixture-corpus baseline**: the counts that
`sample_data/naaccr_v2/*.hl7` produce after intake and `bridge` (OMOP-08). Every
fixture OBX carries a CAP CKey, so only `unmapped_ckey_values` is nonzero. These
limits fit no real deployment. A deployment keeps its own reviewed copy and
passes `--seed-dir` to `validate`, so raising a limit is a reviewed CSV change.

`validate` rejects a missing file, a changed header, a repeated or blank
`check_name`, a `max_count` that is not a non-negative integer, and a blank
`reason`. It also fails, naming the check, when a coverage check has no row or a
row names no coverage check. `bridge` does not read this file.

## NAACCR concept maps

`concept_map_overrides.csv` is the reviewed layer-2 input. A row is active only
when `omop_concept_id` is non-blank; rows with a blank target remain inactive
skeletons. A blank `code` denotes an item-level row. A blank
`omop_concept_id` is not a target. Source concepts always come from the local
allocation ledger, even when Athena provides a standard target.

`naaccr_item_exclusions.csv` lists NAACCR items that are excluded from mapping
and local concept creation, together with the recorded reason.
