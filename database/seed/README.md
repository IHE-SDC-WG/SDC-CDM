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

## NAACCR concept maps

`concept_map_overrides.csv` is the reviewed layer-2 input. A row is active only
when `omop_concept_id` is non-blank; rows with a blank target remain inactive
skeletons. A blank `code` denotes an item-level row. A blank
`omop_source_concept_id` tells the map builder to inherit the layer-1 source
concept, or to create the layer-3 source concept when no source concept exists.

`naaccr_item_exclusions.csv` lists NAACCR items that are excluded from mapping
and local concept creation, together with the recorded reason.
