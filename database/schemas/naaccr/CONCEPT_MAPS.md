# NAACCR concept maps

`maps build` assigns a `NAACCR_LOCAL` source concept to each current, non-retired,
non-excluded NAACCR item and distinct allowed value. Map rows use that ID in
`source_concept_id`. `concept_id` holds a valid standard OMOP target or zero.
The map tables have no dictionary version, so each build replaces their rows
for the selected current algorithm.

Run these commands against the same database, after `sdc-cdm build`:

```bash
sdc-cdm vocab load --dialect sqlite --db .context/cdm.db --vocab-dir database/vocab
sdc-cdm dict load --dialect sqlite --db .context/cdm.db --csv-dir .context/naaccr-25
sdc-cdm constants resolve --dialect sqlite --db .context/cdm.db
sdc-cdm maps build --dialect sqlite --db .context/cdm.db --algorithm eod_public
sdc-cdm maps coverage --dialect sqlite --db .context/cdm.db --algorithm eod_public
```

Use `--dialect sqlserver` and the configured connection string for SQL Server.
`maps build` takes `--seed-dir` and `maps coverage` takes `--seed-dir` and
`--expect`; both default to the tracked `database/seed` directory. When exactly
one dictionary algorithm is current, `--algorithm` can be omitted.

The tracked override CSV has item number, optional value code, target concept
ID, optional target domain, and review fields. Blank targets are inactive.
An explicit zero target is active. Any nonzero target must be a current valid
standard concept. An active override for an unknown current item or value
fails with its CSV line. The exclusions CSV removes the named item and all
its allowed values from local minting and the map tables.

Local IDs are allocated from 2,100,000,000 through 2,147,483,647, within SQL
Server's `INT` range and apart from the SQL Server-only `NAACCR2026` supplement.
The append-only `local_concept_allocation` table records vocabulary, class,
item, and value keys. A second build reuses their IDs, even if a map row was
deleted. Stability is within one database; independently built databases can
assign different IDs. Full value codes remain in the ledger and map key.
The local OMOP `concept_code` uses a SHA-256-derived bounded value to fit the
50-character OMOP column, independent of Athena's coding convention.

An Athena extract that contains `NAACCR` can supply standard targets through
valid `Maps to` relationships. The current value lookup uses `item@code` only
as a provisional matcher for synthetic tests. Before treating real Athena
value coverage as accepted, record counts by `concept_class_id`, ten
`concept_code` samples per class, outbound relationship IDs, and final
`maps coverage` output from an authorized NAACCR-containing bundle. Confirm
the value code format and revisit issue #100 if it is schema-specific.
Zero `athena_standard` rows are expected when the available extract lacks
`NAACCR`; all eligible rows must still have stable local source IDs.

Coverage groups item and value counts by section and layer. It also prints
exclusion, schema-specific value-code collision, and captured foreign-item
counts. An expectation JSON can pin aggregate `checks` for a measured run:

```json
{"algorithm":"eod_public","checks":{"item_total":780,"item_athena_standard":0}}
```

The tracked NAACCR 25 expectation was measured from the current SEER dictionary
with a synthetic OMOP vocabulary fixture that deliberately lacks `NAACCR`.
Replace its layer counts after a real NAACCR-containing bundle is measured.
Keep Athena downloads, fetched SEER rows, credentials,
and record-level reports in gitignored local storage.
