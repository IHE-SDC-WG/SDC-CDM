# NAACCR dictionary test excerpt

This fixture is a 12-item excerpt of the NAACCR version 25 data dictionary returned by
SEER\*API. It is committed for automated testing only, not as a distributable NAACCR
dictionary.

`seer_api/` preserves the API layers used by the client:

- `versions.json` is the response from `/rest/naaccr/versions`.
- `index-25.json` is a reduced `/rest/naaccr/25` index. Three retired entries omit `id`, so
  the client must use their `item` number for the detail request.
- `items/*.json` contains one verbatim detail DTO for each index entry.

The selected records cover four sections and the required edge cases: SSDI input and output
items, an allowed-code description containing a newline, a repeated code within one item,
non-ASCII prose, a comma in an item name, five alternate names including a comma, retired
DTOs with six and seven fields, a retired item with `record_types`, and a live item without
`item_data_type`. The excerpt does not represent all 17 NAACCR sections.

`csv/` contains the four files derived from those JSON responses plus a small synthetic SSDI
CSV set used to prove the shared `dd_version_id` and zero-orphan checks. Tests regenerate the
four API-derived CSVs without a key and compare their bytes with the committed files.
`broken_csv/` changes only the staging membership by adding item `999999`; it exercises the
pre-transaction orphan preflight.
