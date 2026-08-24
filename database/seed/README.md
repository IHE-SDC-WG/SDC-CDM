# OMOP Concept Constants

`concept_constants.csv` names the OMOP concepts that repository ETL and import
code require. `sdc-cdm constants resolve` finds each concept by its
`vocabulary_id` and `concept_code`, then records the resulting IDs in
`etl.concept_constant`.

The tracked pairs replace historical literals `32817`, `32879`, `1147289`,
`8507`, `8532`, and concept `0`. The `unmapped` pair uses the real OMOP code
`No matching concept`; the former code `0` came only from a repository fixture.

These values are data rather than Python constants because this repository
cannot contain an Athena bundle that verifies them. A load and resolution run
against an authorized Athena extract is the acceptance gate. If a pair changes,
correct its CSV row and rerun both commands.
