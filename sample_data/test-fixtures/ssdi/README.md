# Synthetic SSDI staging fixture

This fixture is independently synthetic. It does not contain SEER staging content or clinical,
facility, or patient data.

`seer_api.json` maps the exact test request paths to small response payloads. It covers duplicate
and unsorted schema projections, a schema without `naaccr_schema_id`, shared tables, non-SSDI input
tables, an input/output item collision, a non-NAACCR output, mixed-case description columns, quotes,
newlines, non-ASCII text, and null positions in table row arrays.

`csv/` contains all 12 deterministic files produced from those payloads, including the
`ssdi_version.csv` generation stamp. `data_dictionary_version.csv` is absent because `dict fetch`
alone owns that row. The automated test fetches through an injected offline transport, asserts that
NAACCR validation occurs first, checks one call per unique schema and table endpoint, and compares
every output byte-for-byte.
