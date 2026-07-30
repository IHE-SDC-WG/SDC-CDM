# Rebuild SDC-CDM around a canonical intake envelope

**Status:** proposed. **Scope:** six phases, one PR each.

This is the controlling design document for the rebuild. Each phase PR should link to its section
here, and reviewers should check that phase's acceptance criteria rather than re-deriving intent.
Amend this file in the same PR whenever a decision in it changes — this repo has already been bitten
by docs that contradict the code, and that list is in the Doc drift section below.

Supersedes the `three-schema-repo-reorg` branch, closed unmerged as a learning exercise. Nothing here
depends on that PR landing, but the rebuild does start from its tip — see **Starting point** below.

## Context

The three-schema design (`naaccr` / `sdc` / `omop`) is sound and should survive. What doesn't work
is everything around it:

- The raw HL7 v2 message is discarded at parse time — no provenance, no replay, warnings go to
  `Console.WriteLine` and vanish.
- The C# importer (`ImportNaaccrVolV.cs`) and its Python port
  (`import_vol_v_message_sqlite.py`) reimplement the same 600 lines of parsing with no automated
  parity test. A third variant (`ccr_labreport_to_naaccr.py`) reimplements the OBX-4 grouping again
  for JSON input.
- `naaccr_concept_map` / `naaccr_value_concept_map` are joined by the bridge but populated only by
  a SQL-Server-only script, so every SQLite measurement lands at `measurement_concept_id = 0`.
- The bridge writes only `note` + `measurement`. `observation_period`, `cdm_source`,
  `condition_occurrence`, `episode`/`episode_event` are never written — and a *second*,
  database-less mapper (`phenoml_workflows/mapper.py`) implements exactly those, divergently.
- Concept IDs `32817` / `32879` / `1147289` are hardcoded in SQL.
- There is no export. `omop` is populated in place with no way to hand it to anyone.

**The organizing idea of this rebuild:** insert a **canonical intake envelope** (versioned JSON)
between parsers and the database. Parsers become the *only* language-specific code; everything
downstream — load, map, bridge, validate, export — is SQL that both a C# CLI, a Python CLI, and a
DBA with `sqlite3`/`sqlcmd` can drive identically. Parity stops being a code-review problem and
becomes a golden-file assertion.

### Decisions locked in

| Decision | Choice |
|---|---|
| Transform ownership | **SQL owns transforms.** C#/Python are thin drivers; only the HL7 parser is duplicated. |
| C# vs Python | **Either/or, not both.** A deployment picks one. Neither test suite may require the other toolchain to be installed. Interoperability comes from the envelope contract, not from lockstep implementations. |
| Person identity | **`intake.patient` is the local registry.** `naaccr_value.person_id` / `sdc_report.person_id` hold an `intake.patient_id`; the bridge maps it 1:1 to `omop.person`. Matching is on `(assigning_authority, person_source_value)`; no cross-authority linkage. |
| Dates in the envelope | **Structured, never strings** — `{y, m, d, precision}`, so partial HL7 dates survive into OMOP's separate year/month/day columns. |
| Decimals in the envelope | **JSON strings, not numbers**, carrying the exact source lexeme so two languages cannot disagree via IEEE-754. |
| Units | **`unit_source_value` only.** `unit_concept_id` stays `NULL`; no UCUM mapping table is built. Roadmap. |
| SDC reference leg | **Not wired.** The eCP path stays NAACCR-dictionary-driven; `sdc.template_*` is intake-only for the SDC XML path, and this gets documented as intentional rather than implied-but-missing. |
| Concept mapping | **Layered**: Athena standard NAACCR vocabulary → curated overrides → locally minted 2B-range concepts, with a `mapping_layer` provenance column. |
| Concept slots | **Two-slot contract**: `*_source_concept_id` = the NAACCR source concept, `*_concept_id` = the standard concept reached via `concept_relationship` `'Maps to'`. Never the same value in both. |
| `NAACCR2026` minting script | **Kept, SQL-Server-only, as a supplement.** Concept identity legitimately differs by dialect; this is documented, not treated as drift. |
| `condition_occurrence` | **Thin version**: one row per report from the primary-site item alone, `concept_id = 0` where unmapped. ICD-O-3 combination-concept derivation goes to the roadmap. |
| Duplicate inbound bytes | **Store, flag, don't re-load.** Mirrors the existing insert-and-flag accession behaviour. |
| Export format | **CSV per OMOP table**, canonical OHDSI layout, with `manifest.json` and a `CDM_SOURCE` row. |
| Dialects | **SQLite + SQL Server.** PostgreSQL DDL stays vendored and schema-smoke-tested; no load/bridge/export until a later phase. |
| FHIR | Roadmap only. |

---

## Starting point: branch from the three-schema tip, not from `omop`

**`origin/omop` is 20 commits behind `three-schema-repo-reorg`, and the merge base is `origin/omop`
itself** (`git rev-list --left-right --count origin/omop...three-schema-repo-reorg` → `0 20`).
`origin/omop` *is* the pre-three-schema state, commit `6304b3e`.

So branching the rebuild from `origin/omop` does not give a clean slate — it gives a slate that is
missing everything this plan builds on:

| Missing on `origin/omop` | Why it matters here |
|---|---|
| `database/schemas/naaccr/` | The entire versioned 3NF dictionary design this plan extends |
| `database/schemas/sdc/` | The SDC form/report schema |
| `database/etl/` | The occurrence-aware bridge whose idempotency pattern Phase 4 preserves |
| `tools/load_athena_vocab.py` | 1024 lines, three backends, tested — and Phase 5 reuses its `TABLE_SPECS` as the CDM column source of truth |
| `tools/ccr_labreport_to_naaccr.py` | The CCR JSON intake path that becomes an envelope parser |

Recommended: **create the new branch at the `three-schema-repo-reorg` tip** and execute the phases
as stacked PRs from there. If `omop` must be the merge base, land the three-schema foundation into
`omop` first — this plan treats it as the starting point, not as work to redo.

### Assets to preserve through the restructure

The rebuild is a **restructure, not a rewrite**. Use `git mv` for layout moves so rename detection
and `git blame` survive — the blame trail is how anyone will ever find out *why* an identifier like
`2118.1000043` is in the code.

| Asset | Why it cannot be cheaply recreated |
|---|---|
| `tools/ssdi-ts/` | Working SEER Staging REST API client + 3NF export. API-specific knowledge, weeks of work. |
| `tools/load_athena_vocab.py` | Three DB backends, freshness guards, CDM 5.4 column metadata, 8 tests. |
| `database/schemas/naaccr/ddl/` | The `data_dictionary_version` dimension, staging-table catalog, `item_role` — real modelling. |
| `.../sqlserver/2_naaccr_omop_vocab_sqlserver.sql` | 665 lines, and we have decided to **keep** it. |
| OBX identifier constants in `ImportNaaccrVolV.cs` | `60573-3`, `60572-5`, `60574-1`, `2118.1000043`, `2168.1000043`, `52756.1000043`, `820603.1000043` — hard-won domain knowledge; the code structure changes, these do not. |
| The OBX-4 grouping rule | Re-derived three times already in this repo. Port it to the parsers verbatim. |
| Occurrence-aware idempotency SQL | The one genuinely well-built part of the current bridge. |
| `sample_data/` | Real HL7 messages, SDC templates, FHIR bundles. |
| `SdcImporterTests.cs:41-154` | The behavioural contract: 19 values → 19 measurements, items 2129 and 820404. Must keep passing. |
| `TEST_PLAN.md` | ~85 catalogued test IDs. Retarget, don't discard. |
| Git history | Why `sdc_report_id` and not accession; why SQLitePCLRaw is pinned; the 17 review findings. |

Deliberately discarded: the importer's *structure* (not its constants), the standalone Python port,
the three-way DDL wiring, `phenoml_workflows/mapper.py` as a mapper, hardcoded concept IDs, and the
empty `database/etl/postgresql/` directory.

---

## Target architecture

### Five schemas

`SCHEMA_ARCHITECTURE.md` already anticipated growth ("add more later — `vocab`, `fhir`, `audit`,
`etl`"). Two get added, each with a one-line charter:

| Schema | Charter |
|---|---|
| `intake` | **New.** Raw inbound bytes + the canonical envelope + parse diagnostics. Holds PHI; isolated so it can carry its own access control and is structurally excluded from exports. |
| `naaccr` | NAACCR dictionary (versioned) + captured values + concept maps. Unchanged in shape. |
| `sdc` | SDC form structure and SDC-XML answers + the eCP report header. Unchanged. |
| `omop` | Vanilla OHDSI CDM 5.4, re-vendored from upstream with the commit recorded. Never modified. |
| `etl` | **New.** Resolved concept constants, run log, applied-migration ledger. No clinical data. |

### The envelope contract

`contracts/envelope.schema.json` — a versioned JSON Schema, the single boundary between parsing and
persistence:

```json
{
  "envelope_version": "1",
  "source":  { "format": "hl7v2", "message_control_id": "…", "sending_facility": "…",
               "message_profile": "…" },
  "raw":     { "sha256": "…", "media_type": "application/hl7-v2+er7", "byte_length": 12345 },
  "patient": { "person_source_value": "…", "assigning_authority": "…",
               "birth_date": { "y": 1957, "m": 3, "d": 4, "precision": "day" },
               "gender": "M" },
  "report":  { "accession": "24-11-000312-2", "report_loinc": "60568-3",
               "template_source": "…", "template_id": "…", "template_version": "…",
               "observation_date": { "y": 2024, "m": 11, "d": 8, "precision": "day" },
               "narrative": "…",
               "tumor_site": "…", "procedure": "…", "laterality": "…" },
  "values":  [ { "item_num": 2129, "obx_sub_id": "2131", "value_code": "…",
                 "value_num": "10.0", "value_text": null,
                 "unit_source": "cm",
                 "observation_date": { "y": 2024, "m": 11, "d": 8, "precision": "day" } } ],
  "diagnostics": [ { "severity": "warning", "code": "NON_INTEGER_ITEM", "detail": "…" } ]
}
```

Three things fall out of this:

1. **Parity is a file diff.** `contracts/golden/<fixture>.envelope.json` is the oracle. Each parser
   must reproduce it byte-identically under the serialization profile below. This is a far stronger
   check than today's manual row-count comparison, and it catches drift before the database is
   involved.
2. **The three existing intake shapes converge.** HL7 v2 ER7 text, the CCR JSON OBX payload that
   `ccr_labreport_to_naaccr.py` handles, and (later) NAACCR XML all become *parsers emitting the
   same envelope*. The OBX-4 grouping rule is implemented once per language, not three times.
3. **Everything after the envelope is SQL.** `database/load/<dialect>/1_load_envelope.sql` shreds
   the JSON with `json_each` (SQLite) / `OPENJSON` (SQL Server) into `naaccr.naaccr_value` +
   `sdc.sdc_report`. The dialect difference is confined to that one file.

No patient *name* enters the envelope — PID-5 is read for nothing today and should stay out, since
the envelope is stored in the database. The raw blob already carries it.

#### Partial dates

HL7 dates are routinely partial: `1957`, `195703`, `19570304`, and OBX-14 may carry time. The current
code silently drops anything under 8 digits (`ImportNaaccrVolV.cs:207` requires `Length >= 8`,
`ParseHl7Date` requires ≥8 digits), which throws away a usable birth year. OMOP `person` has separate
`year_of_birth` / `month_of_birth` / `day_of_birth` columns precisely for this case, so the envelope
must not flatten it.

Every date in the envelope is an object, never a string:

```json
{ "y": 1957, "m": 3, "d": null, "precision": "month" }
```

- `precision` ∈ `year` | `month` | `day` | `second`. Components below the stated precision are
  `null`, never zero and never absent.
- `second` precision adds `"hh"`, `"mi"`, `"ss"` and an optional `"tz"` offset in `±HH:MM`. HL7
  timezone offsets are preserved verbatim, not normalized to UTC — normalizing loses the sending
  facility's local reading, which matters for a date-only observation.
- The loader materializes SQL dates from these: `person` gets its three columns filled to the
  available precision; date columns take the first day of the known period with the precision
  recorded alongside, so a `year`-precision diagnosis does not masquerade as January 1st without
  a flag.
- A date that cannot be parsed at all becomes `null` plus a `diagnostics` entry — not a silent
  fallback to today's date, which is what `ImportNaaccrVolV.cs:197` currently does.

#### Canonical serialization profile

The parity assertion is byte-identity, so serialization must be pinned or C# and Python will differ
on day one over float formatting, key order, and unicode escaping. `contracts/envelope.schema.json`
is accompanied by a written profile, and both parsers have a shared `serialize_envelope` routine
whose only job is to obey it:

| Rule | Value |
|---|---|
| Encoding | UTF-8, no BOM |
| Key order | lexicographic at every level |
| Indentation | 2 spaces, `\n` line endings, single trailing newline |
| Separators | `": "` and `","` — no trailing whitespace |
| Unicode | emitted literally, not `\uXXXX`-escaped; NFC-normalized |
| Absent vs null | optional fields are **omitted** when absent; `null` means "present and empty" |
| Empty containers | `[]` and `{}` are omitted, never emitted empty |
| Booleans/ints | JSON native |
| **Decimals** | **JSON strings**, not numbers — see below |

`value_num` being a *string* is the load-bearing decision. NAACCR items carry a `decimal_places`
field, and IEEE-754 round-tripping through two languages will not preserve `10.0` versus `10`
versus `10.00`. Carrying the decimal as its exact source lexeme (`"10.0"`) keeps the parser honest,
makes the golden file readable, and lets the loader `CAST` to the target column with the dictionary's
declared precision. The raw source text is what the registry actually sent; preserving it is the
point of the whole intake layer.

A conformance test in each language round-trips every golden envelope through
`serialize_envelope(parse(serialize_envelope(x)))` and asserts a fixed point.

### Raw message storage (`intake`)

`intake.inbound_message`:

| Column | Purpose |
|---|---|
| `inbound_message_id` | PK |
| `source_format`, `media_type` | `hl7v2` / `ccr_json` / `naaccr_xml` / `sdc_xml` |
| `raw_blob` | **The exact bytes, unaltered.** `BLOB` / `VARBINARY(MAX)` |
| `raw_sha256`, `byte_length` | content hash; non-unique index for duplicate detection |
| `is_content_duplicate`, `first_seen_inbound_message_id` | set when `raw_sha256` already exists; self-FK to the original |
| `received_datetime`, `received_by` | who/what submitted it |
| `message_control_id`, `sending_facility`, `message_profile` | MSH-10 / MSH-4 / MSH-21, denormalized for triage |
| `envelope_json`, `envelope_version` | the canonical parse result |
| `parser_name`, `parser_version` | **which implementation parsed it** — the forensic key when C# and Python disagree in the field |
| `parse_status`, `parse_error` | `parsed` / `failed` / `quarantined` |

`intake.inbound_message_diagnostic` — one row per warning, FK to the message. This replaces the
`Console.WriteLine` warnings at `ImportNaaccrVolV.cs:541` (non-integer item number) and `:571`
(repeated OBX-4 component), which are currently unrecoverable after the run.

`naaccr.naaccr_value` and `sdc.sdc_report` each gain `inbound_message_id`. The full provenance walk
becomes: `omop.measurement` → `omop.note` → `sdc.sdc_report` → `intake.inbound_message.raw_blob`.
A failed parse still lands a row, so nothing is lost silently — quarantine is queryable.

#### `intake.patient` — the local person registry

The bridge, not the importer, writes `omop.person` (that is what makes the "importer writes no OMOP"
boundary real). But `naaccr.naaccr_value.person_id` is `NOT NULL`
(`1_naaccr_sqlite_ddl.sql:185`) and the bridge joins on it, so ingest cannot simply defer person
creation — there would be no ID to write. `intake.patient` breaks that cycle.

| Column | Purpose |
|---|---|
| `patient_id` | PK — **this is what `naaccr_value.person_id` and `sdc_report.person_id` now hold** |
| `person_source_value`, `assigning_authority` | the PID-3 identifier and its namespace |
| `birth_year`, `birth_month`, `birth_day` | to the precision the message gave |
| `gender_source_value` | PID-8 verbatim |
| `first_seen_inbound_message_id` | provenance |

Ingest resolves or creates an `intake.patient` row; the bridge maps `intake.patient` → `omop.person`
1:1 and writes the OMOP row. The `person_id` columns keep their names and `NOT NULL` constraints, so
`naaccr` and `sdc` DDL are untouched — only the *referent* changes, from "an `omop.person_id`" to
"an `intake.patient_id`". Document that plainly, since the column name no longer says which.

**Person matching policy** — this table is where it finally has a home. Today
`FindPersonByIdentifier` matches on the raw PID-3 string, which conflates identifiers from different
assigning authorities. The rule becomes: match on `(assigning_authority, person_source_value)`, with
a blank authority treated as its own namespace rather than a wildcard. Cross-authority linkage is
explicitly **out of scope** — no probabilistic matching, no merging. If two authorities send the same
human, you get two persons, and that is the honest answer until someone specifies a linkage policy.

Deferring person creation to the bridge has a second benefit: gender resolves through
`etl.concept_constant` at bridge time against the loaded vocabulary, instead of the importer
hardcoding `8507`/`8532` as it does at `ImportNaaccrVolV.cs:236-239`.

**Duplicate-bytes policy.** On a `raw_sha256` collision the message is still stored (the audit trail
must be complete), flagged `is_content_duplicate` with `first_seen_inbound_message_id` pointing at
the original, and **`load_envelope` skips it** — no `naaccr_value` or `sdc_report` rows are written
from it. This deliberately mirrors the existing accession behaviour
(`sdc_report.is_duplicate_accession` / `first_seen_report_id`, set at
`ImportNaaccrVolV.cs:391-402`), so the two duplicate concepts are structurally parallel and both
queryable. Note the two are independent: identical bytes are a resend, whereas a repeated accession
with different bytes is a corrected report — the second must still load.

### Three ways to drive it, one set of stages

Every stage is idempotent and separately invocable. `database/manifest.json` lists the SQL files in
apply order — read by all three drivers, replacing the fragile alphabetical resource glob in
`BuildSchema()` (`SdcCdmInSqlite.cs:127-135`).

| Stage | What it does | Language-specific? |
|---|---|---|
| `build` | apply `database/schemas/*/ddl/<dialect>/` per manifest | no |
| `vocab load` | Athena bundle → `omop.concept` et al. | driver code (CSV streaming) |
| `constants resolve` | populate `etl.concept_constant` by `(vocabulary_id, concept_code)` lookup | no |
| `dict load` | SEER 3NF CSVs → `naaccr.*` dictionary | driver code (CSV streaming) |
| `maps build` | layered concept-map build | no |
| `ingest` | HL7 → `intake` (blob + envelope) → `naaccr` + `sdc` | **parser only** |
| `bridge` | `naaccr` + `sdc` → `omop` | no |
| `validate` | DQ assertions | no |
| `export` | `omop` → CSV bundle + manifest | driver code (CSV writing) |

The only genuinely language-bound work is HL7 parsing and CSV streaming. A DBA can run every other
stage from `sqlite3` / `sqlcmd` given a staged envelope — document that explicitly as the third
supported path.

**The toolchains are alternatives, not layers.** A deployment picks C# *or* Python and never needs
both. That is a deliberate simplification and it shapes the testing story below: the two
implementations do not have to produce identical databases, they have to independently satisfy the
same envelope contract. Interoperability is guaranteed by the envelope and the schema, not by
lockstep code.

**Toolchain × dialect support matrix** — publish this in the README and keep it honest. Today none
of these three are peers: `BuildSchema()` is SQLite-only, Python has no schema builder at all (just
duplicated glob/`executescript` code in a notebook and a test helper), and the pure-SQL path is
Postgres-only via the Dockerfile.

| | SQLite | SQL Server | PostgreSQL |
|---|---|---|---|
| C# CLI (`SdcCdm.Cli`) | full | full | schema only |
| Python CLI (`sdc_cdm`) | full | full | schema only |
| Pure SQL (`sqlite3` / `sqlcmd` / `psql`) | full except parse + CSV | full except parse + CSV | schema only |

The DDL is currently wired three separate ways — a csproj embedded-resource glob
(`SdcCdmInSqlite.csproj:11-13`), a Python runtime glob, and per-file `COPY` in the Dockerfile — so
any DDL add or rename silently breaks one of them. `database/manifest.json` becomes the single
ordering contract all three read.

#### Test topology: independent jobs, one shared contract

Because the toolchains are either/or, tests split into jobs that never depend on each other. Nobody
has to install .NET to work on the Python side, and PR feedback stays fast.

| CI job | Runs | When |
|---|---|---|
| `python-sqlite` | pytest: golden-envelope conformance, full pipeline, export round-trip | every push |
| `csharp-sqlite` | `dotnet test`: same golden envelopes, full pipeline, export round-trip | every push |
| `sql-only` | build + bridge + validate driven from `sqlite3` against a staged envelope | every push |
| `python-sqlserver` | same suite, `mcr.microsoft.com/mssql/server` service container | nightly + on `database/**` changes |
| `csharp-sqlserver` | ditto | nightly + on `database/**` changes |
| `cross-impl-diff` | both CLIs → two SQLite databases → table diff on natural keys | nightly, non-blocking |

The shared contract is `contracts/golden/*.envelope.json`: **each language asserts against the golden
files independently**, so neither test suite needs the other language present. That is what makes
either/or safe — a Python-built database is continuable by C# tooling because both agree with the
contract, not because they agree with each other.

`cross-impl-diff` drops to a nightly, non-blocking job. Under an either/or model its value is
regression signal for maintainers, not a correctness gate, and it was the most expensive and
brittlest check on offer (deterministic surrogate IDs, timestamp exclusion). Keeping SQL Server off
the PR path likewise removes the container cost from ordinary review.

### Repo layout

```
contracts/
  envelope.schema.json                    the shared contract
  golden/                                 golden envelopes per fixture (parity oracle)
database/
  manifest.json                           canonical file order for all three drivers
  schemas/{intake,naaccr,sdc,omop,etl}/ddl/{sqlite,sqlserver}/
  schemas/omop/VENDORED.md                upstream OHDSI commit + re-vendor procedure
  load/{sqlite,sqlserver}/1_load_envelope.sql
  maps/{sqlite,sqlserver}/1_build_concept_maps.sql
  etl/{sqlite,sqlserver}/1_person_and_period.sql
                         2_note.sql
                         3_measurement_observation.sql
                         4_condition_and_episode.sql
                         9_validate.sql
  seed/concept_map_overrides.csv           curated layer-2 map
      cdm_source.csv
src/csharp/{SdcCdm,SdcCdm.Sqlite,SdcCdm.SqlServer,SdcCdm.Cli,SdcCdm.Tests}/
src/python/sdc_cdm/{envelope,hl7v2,cli,db,vocab,export}/  + tests/
tools/ssdi-ts/                             SEER dictionary export (unchanged)
notebooks/                                 recreated from scratch (see below)
sample_data/                               single source of fixtures
docs/{REBUILD_PLAN,SCHEMA_ARCHITECTURE,ROADMAP,TEST_PLAN}.md
```

Both CLIs expose the identical verb set above.

**Deleted outright:** `phenoml-workflows/` (mapping absorbed into Phase 4 SQL, review role replaced
by the tracked overrides CSV), `NAACRToOMOPmaps/*.xlsx` and `tools/convert_naaccr_omop_maps.py`
(after the one-time seed conversion), `database/etl/postgresql/` (empty), and the root-level stray
build artifacts (`test_import*.db`, `etl_test_output.json`).

**`notebooks/` is recreated from scratch, not ported.** The existing notebooks carry their own copy
of the import logic (`notebooks/python_cdm_utils/` — a full 422-line parallel implementation of the
HL7 importer plus a 343-line DAL), which is exactly the duplication this rebuild exists to remove.
The replacements are thin: import `sdc_cdm`, call the CLI verbs, and show results. Target three
notebooks, each earning its place:

1. **Quickstart** — build → vocab → dict → maps → ingest → bridge → export against SQLite, ending in
   the standard back-reference join.
2. **Provenance walk** — from one `omop.measurement` back through note → report → `inbound_message`,
   rendering the raw HL7 blob and the parse diagnostics. This is the notebook that demonstrates the
   new intake layer and has no equivalent today.
3. **Concept-map coverage** — `naaccr.concept_map_coverage` by layer, and what remains unmapped.

`notebooks/serve_db.py` and the Datasette-Lite wiring are worth keeping; the `python_cdm_utils/`
package is deleted with the old notebooks.

---

## Closing the gaps

### Concept maps, layered with provenance

`naaccr.naaccr_concept_map` and `naaccr_value_concept_map` gain `mapping_layer`
(`athena_standard` | `curated_override` | `local_mint`), `source_concept_id`, `target_domain_id`,
and `created_at`. They stay version-independent (keyed on `item_num` / `(item_num, code)`) — the
existing rationale in `SCHEMA_ARCHITECTURE.md:37-40` holds.

`database/maps/<dialect>/1_build_concept_maps.sql` runs three layers in order:

1. **Athena standard.** Join `naaccr.naaccr_item.item_num` → `omop.concept.concept_code` where
   `vocabulary_id = 'NAACCR'`, then follow `concept_relationship` `'Maps to'` to the standard
   concept. Value codes match the `item#code` concept-code pattern. This is the interoperable
   layer and should cover the bulk of registry items.
2. **Curated overrides** from `database/seed/concept_map_overrides.csv`, upserted over layer 1 only
   where explicitly marked as an override. This is where reviewed human decisions land.
3. **Local mint** for items still unmapped and flagged mappable: allocate a stable ID in the
   2,000,000,000+ range into a `NAACCR_LOCAL` vocabulary, recording the allocation in
   `naaccr.local_concept_allocation` so IDs survive rebuilds. Generalize the allocation logic
   already in `database/schemas/naaccr/ddl/sqlserver/2_naaccr_omop_vocab_sqlserver.sql:237-268`
   to both dialects.

`naaccr.concept_map_coverage` view emits items total / mapped per layer / unmapped, so coverage is
a number CI can assert on and regressions are visible.

#### The two-slot contract (fixes a live bug)

The current bridge writes **the same value** into both concept slots — `measurement_concept_id` gets
`COALESCE(ncm.concept_id, 0)` (`1_naaccr_sdc_to_omop.sql:67`) and `measurement_source_concept_id`
gets `ncm.concept_id` (`:81`), differing only by the `COALESCE`. That is only correct when the mapped
concept happens to be standard, and it is invisible until a DQD run flags non-standard concepts in a
standard slot.

The maps therefore carry both IDs explicitly, and the ETL uses them in the right slots:

| OMOP column | Value | Source |
|---|---|---|
| `*_source_concept_id` | the NAACCR **source** concept | `naaccr_concept_map.source_concept_id` |
| `*_concept_id` | the **standard** concept | `naaccr_concept_map.concept_id`, resolved through `concept_relationship` `'Maps to'` at map-build time |
| `*_source_value` | the raw NAACCR item number / code | unchanged |

The same contract applies to `value_as_concept_id` vs the value map's source concept, and to
`condition_concept_id` / `condition_source_concept_id`.

**Unmapped policy and its DQD consequence.** Items that reach layer 3 get a real (local, non-standard)
concept in `*_source_concept_id` and — having no standard target — `0` in `*_concept_id`. Items
flagged not mappable stay `0` in both. This is the deliberate trade: DQD will report unmapped-concept
counts rather than silently accepting local IDs in standard slots, which is the correct failure mode.
`concept_map_coverage` makes the number explicit rather than something a reviewer discovers.

#### Fate of the SQL Server minting script

`2_naaccr_omop_vocab_sqlserver.sql` is **kept as a SQL-Server-only supplement**, not retired and not
ported. It continues to seed its `NAACCR2026` vocabulary, `omop.concept`, and
`omop.source_to_concept_map`, and it continues to populate both maps on that dialect.

The consequence must be stated plainly in `SCHEMA_ARCHITECTURE.md` rather than discovered later:
**concept identity legitimately differs by dialect.** A SQL Server deployment may resolve a given
NAACCR item to a `NAACCR2026` concept where a SQLite deployment resolves it to an Athena `NAACCR`
concept or a `NAACCR_LOCAL` mint. Therefore:

- The `mapping_layer` column is what makes this auditable — you can always see which layer produced
  a given row on a given deployment.
- **Cross-dialect concept equality is explicitly not a test assertion.** The nightly
  cross-implementation diff compares C# against Python *within* one dialect, never SQLite against
  SQL Server on concept IDs.
- Exports carry the resolving vocabulary in `manifest.json` so a recipient knows which concept
  universe they received.

#### Layer 2 without a review UI

`phenoml-workflows/` is **retired**, so layer 2 has no web front-end. It doesn't need one: the
override set becomes a tracked CSV and **git is the review trail.** A mapping decision arrives as a
PR that edits `database/seed/concept_map_overrides.csv`, gets reviewed like any other change, and
carries its rationale in the commit message. That is a better audit trail than a `review_status`
column that has sat at `unreviewed` for all 780 rows.

`database/seed/concept_map_overrides.csv` columns: `item_num`, `code` (blank for item-level),
`omop_concept_id`, `omop_source_concept_id`, `target_domain_id`, `rationale`, `reviewer`,
`reviewed_at`.

**One-time conversion, then retire the artifacts.** `naaccr_omop_extension_mapping_spec.json` holds
780 item rows whose *inventory* is worth keeping even though the mappings are not — concept class,
proposed OMOP table, grain, and the `is_mappable` flag. Convert it once into two tracked seeds:

- `database/seed/concept_map_overrides.csv` — skeleton rows with `omop_concept_id` blank where
  unreviewed (which is all 780 today), so the file starts as an honest to-do list rather than a
  pretend mapping.
- `database/seed/naaccr_item_exclusions.csv` — the 74 items explicitly flagged `is_mappable: false`.

Then drop the JSON, `tools/convert_naaccr_omop_maps.py`, and the `NAACRToOMOPmaps/*.xlsx` workbooks,
recording their provenance in the conversion commit message. If the working group later delivers
another spreadsheet, converting it is a one-off script run, not a permanent tool in the tree.

Note the field-name trap when writing that converter: the spec's `concept_id` field holds a NAACCR
**item number** (e.g. `442` / `ambiguousTerminologyDx`), and its `domain_id` holds an invented value
(`DIGITS`, `TEXT`) that is not an OMOP domain. Map them to `item_num` and drop the fake domain.

**Layer-3 gating.** Mint a local concept for any item that has captured values and no layer-1 or
layer-2 map, **except** those in `naaccr_item_exclusions.csv`. Do not gate on the spec's
`is_mappable` flag directly — it is `None` for 478 of 780 rows, so gating on it would suppress
minting for most of the dictionary.

### OMOP breadth, domain-routed

Split the monolithic bridge into ordered scripts. The `phenoml_workflows/mapper.py` logic
(episode / episode_event / observation routing, currently JSON-only with no database) is **absorbed
here, and `phenoml-workflows/` is deleted from the tree** — its two roles (mapping, and review UI)
are replaced by these SQL scripts and by the tracked overrides CSV respectively. Read it once for
its episode-grain and domain-routing decisions before deleting it; those are the parts worth
carrying over.

1. `1_person_and_period.sql` — `omop.person` from `intake.patient` 1:1, with gender resolved through
   `etl.concept_constant`; `observation_period`; `cdm_source` from seed. This is the honest fix for
   the doc drift: after this, the importer really does write no OMOP.
   **`observation_period` source order**: NAACCR date-of-diagnosis → date-of-last-contact when those
   items are present, else the MIN/MAX span of the person's observation dates. A single synoptic
   report yields a one-day period; that is legal OMOP but nearly useless for cohort logic, so record
   the derivation source per row and surface the one-day count in `validate`. Do not silently pad.
2. `2_note.sql` — one note per non-duplicate accessioned report, as today, with resolved concepts.
3. `3_measurement_observation.sql` — **route on the mapped concept's `domain_id`**: `Measurement` →
   `measurement`, `Observation` → `observation` with `value_as_string`.
   **Units: `unit_source_value` only.** `unit_concept_id` is left `NULL` and no UCUM mapping table is
   built. NAACCR sends `cm`, `mm`, `%` and similar; `unit_source_value` preserves them losslessly,
   and a populated `unit_concept_id` is not worth a hand-curated mapping table at this stage. UCUM
   resolution is on the roadmap and can be applied later as a pure update over existing rows,
   because the source text is retained.
4. `4_condition_and_episode.sql` —
   - **`condition_occurrence`, thin version**: one row per report, derived from the **primary-site
     item alone**, with `condition_concept_id = 0` where the map has no standard target and the
     NAACCR source concept in `condition_source_concept_id`. `condition_start_date` = the report
     observation date; `condition_type_concept_id` from `etl.concept_constant`. No histology
     combination logic. Full ICD-O-3 primary-site + histology combination-concept derivation is
     **roadmap** — it needs the ICDO3 vocabulary loaded and is a phase of its own.
   - **`episode` / `episode_event`**: one `episode` per tumor/accession group, with `episode_event`
     rows linking its measurements and the condition. The Episode Type and
     `episode_event_field_concept_id` field concepts are already pre-seeded by the SQL Server vocab
     script — reuse those definitions rather than re-inventing them, resolving the IDs through
     `etl.concept_constant` so the SQLite path gets the same names from Athena.
5. `9_validate.sql` — generalize `database/etl/sqlserver/validate_naaccr_sdc_to_omop.sql` and
   extend: no orphan FKs, note/measurement counts reconcile against `naaccr_value`, every OMOP row
   traceable to an `inbound_message`, count of one-day observation periods, and the unmapped-concept
   count checked against a threshold declared in `database/seed/validate_thresholds.csv` — a tracked
   file, so raising a threshold is a reviewed PR rather than an argument.

Occurrence-aware idempotency (the `ROW_NUMBER()` + correlated `COUNT(*)` pattern at
`1_naaccr_sdc_to_omop.sql:87-121`) is preserved in each script — it's the one piece of the current
bridge that is genuinely well-built.

`omop` stays vanilla. No crosswalk table. Back-references remain `note_source_value` /
`measurement_event_id` / `measurement_source_value`.

### Export: CSV per OMOP table

`export` writes a directory of `PERSON.csv`, `OBSERVATION_PERIOD.csv`, `NOTE.csv`,
`MEASUREMENT.csv`, `OBSERVATION.csv`, `CONDITION_OCCURRENCE.csv`, `EPISODE.csv`,
`EPISODE_EVENT.csv`, `CDM_SOURCE.csv`, with `--include-vocabulary` for the concept tables.

- Header order and column lists come from the **same CDM 5.4 table metadata that drives the Athena
  loader** (`tools/load_athena_vocab.py:38-175` `TABLE_SPECS`) — promote it to a shared module so
  there is one source of truth for CDM column definitions in both directions.
- `manifest.json`: CDM version, export timestamp, source database identity, per-table row count and
  sha256, the `etl.run` id that produced it, concept-map coverage summary, tool name + version.
- **The export reads `omop.*` only**, so `intake.inbound_message.raw_blob` cannot leak into a
  deliverable by construction. State this as an invariant and test it.
- Round-trip test: export → load into a fresh empty OMOP schema → row-for-row equality.

### No hardcoded concept IDs

`etl.concept_constant (constant_name PK, concept_id, vocabulary_id, concept_code, resolved_at)`.
A `constants resolve` stage looks each one up by `(vocabulary_id, concept_code)` in the loaded
vocabulary and **fails loudly if absent** rather than letting the ETL write a wrong ID:

| Constant | Resolved from |
|---|---|
| `note_type_ehr` | `Type Concept` / `EHR` (today's literal `32817`) |
| `measurement_type_registry` | `Type Concept` / `Registry` (`32879`) |
| `field_note_note_id` | `CDM` / `note.note_id` (`1147289`) |
| `unmapped` | `None` / `0` |
| `gender_male`, `gender_female` | `Gender` / `M`, `F` (`8507`, `8532`) |

The ETL scripts join `etl.concept_constant` instead of embedding literals. This also removes the
`// TODO: confirm the exact field concept_id` at `SdcCdmInSqlite.cs:1228` and makes
`InsertEssentialConcepts()`'s hardcoded 8-concept seed unnecessary — vocabulary load becomes a real
prerequisite rather than something the SQLite path fakes.

### Python bridge runner

Falls out of the architecture for free: `python -m sdc_cdm bridge` executes the same
`database/etl/sqlite/*.sql` files the C# driver does, via the shared manifest. The one-off
`.context/verify_e2e_bridge.py` becomes a real test.

### Doc drift

- **Delete `ECP_OMOP_MAPPING.md`.** Its central claim at line 64 ("the importer does not write OMOP
  rows directly") is false today, and its premise — "eCP synoptic Q&A defaults to `measurement`"
  (line 14) — is superseded by domain routing. The only content worth keeping is its
  numeric/coded/text → OMOP column table, which moves into `SCHEMA_ARCHITECTURE.md` beside the
  two-slot contract. One fewer document to drift is worth more than the file.
- `TEST_PLAN.md` EXP-01 asserts a `NULL AS response` bug that is **already fixed** at
  `SdcCdmInSqlite.cs:589` — delete the stale claim; retarget test IDs at the new stage boundaries.
- `SCHEMA_ARCHITECTURE.md` — five schemas, envelope contract, layered maps, per-dialect status
  table, the two-slot concept contract, the note that `person_id` columns now hold
  `intake.patient_id`, and an explicit statement that the SDC reference is intake-only for the XML
  path.
- `docs/ROADMAP.md` (new) — ICD-O-3 combination-concept `condition_occurrence` derivation, UCUM
  `unit_concept_id` resolution, FHIR intake/export, NAACCR XML, CCDA, PostgreSQL
  load/bridge/export, `PV1` → `visit_occurrence`, `SPM` → `specimen`, SDC template-driven answer
  validation, cross-authority person linkage.
- **Delete the empty `database/etl/postgresql/` directory** (the new `database/load/`, `maps/`,
  `etl/` layout replaces it) and fix the `TEST_PLAN.md:20` glob that implies a PostgreSQL bridge
  file exists. The dialect matrix above is the honest replacement.

---

## Correctness fixes to fold in

These are cheap now and expensive later:

- **OBX classification by identifier, not position.** `ImportNaaccrVolV.cs:440` starts the clinical
  loop at `i = 3`, hard-assuming the first three OBX segments are metadata. Classify each OBX by
  its LOINC (`60573-3`, `60572-5`, `60574-1`) / item number instead. A message that orders its
  metadata differently currently loses real answers or ingests metadata as data.
- **MSH-21 profile validation** (commented out at `:153-156`) returns as a recorded *diagnostic*,
  not a hard failure — the fixtures don't all conform.
- **Vendored-DDL idempotency.** `4_OMOPCDM_sqlite_5.4_indices.sql:7+` uses `CREATE INDEX` with no
  `IF NOT EXISTS`, so `build` fails on a second run. Fix via an `etl.schema_migration` ledger that
  skips already-applied files — this keeps the OMOP DDL pristinely vendored instead of patching it.
- **SQL Server `naaccr` DDL asymmetry.** `1_naaccr_sqlserver_ddl.sql` creates only `naaccr_value`;
  the dictionary lives in `0_…dictionary…` and the concept maps are created *inside the vocabulary
  seeding script*. Renumber so DDL creates **all** tables and loaders only `INSERT`, add the missing
  `naaccr_value.dd_version_id` FK that SQLite and Postgres already enforce, and normalize the
  UPPERCASE table names to lowercase.
- **Rename `sdc_form_answer.reponse_string_nvarchar` → `response_string`.** The typo is baked into
  all three dialect DDLs and the `ISdcCdm` API. A fresh PR is the moment.
- **Implement `FindTemplateItem`** (`SdcCdmInSqlite.cs:647-650` throws `NotImplementedException`),
  so `ImportTemplateRowData` can dedupe across runs.
- **Re-vendor the OMOP DDL** from upstream OHDSI and record the commit in `VENDORED.md`. Drops the
  stale `"5.4-SDC"` header comments without hand-editing vendored files.
- **CI** (`.github/workflows/`): `dotnet test`, `pytest`, a full SQLite pipeline run, the
  cross-implementation parity diff, and the concept-map coverage assertion. `TEST_PLAN.md` CLEAN-03
  has been open the whole time.

---

## Phasing

Order matters — vocabulary before mapping before ingest, so nothing needs re-ingesting.

Each phase is one PR. Acceptance criteria are what the PR must demonstrate, not aspirations.

**Phase 0 — skeleton and contracts.** Repo layout, `contracts/envelope.schema.json`, `intake` + `etl`
DDL, `database/manifest.json`, migration ledger, CI. **Commit this plan as `docs/REBUILD_PLAN.md`**
so each subsequent phase PR can link to its section and reviewers can see the whole arc.
*Accept when:* `build` runs twice against the same database with no error and no duplicate objects
(the current `IF NOT EXISTS` regression); all three toolchains build a SQLite database from the same
manifest, and the SQL Server jobs do the same on their own schedule; the six CI jobs exist and the
three per-push jobs are green; **each language's test suite passes with the other language's
toolchain absent** — no pytest run may require .NET and no `dotnet test` may require Python; the
promoted end-to-end no-double-count test (from the untracked `.context/verify_e2e_bridge.py`) passes
as a tracked test.

**Phase 1 — vocabulary and constants.** Athena loader promoted out of `tools/`; `etl.concept_constant`
resolver; SEER dictionary loader for **both** dialects.
*Accept when:* every constant resolves from a loaded Athena bundle; deleting one required concept
makes `constants resolve` exit non-zero with the missing `(vocabulary_id, concept_code)` named; the
NAACCR dictionary loads into SQLite from the same 3NF CSVs SQL Server uses, with matching row counts.

**Phase 2 — concept maps.** Layered build, coverage view, one-time seed conversion from the mapping
spec, then delete the spec/workbooks/converter.
*Accept when:* `naaccr.concept_map_coverage` reports a nonzero layer-1 count on a real Athena bundle;
every map row has a `mapping_layer` and a `source_concept_id`; layer-3 mints are stable across two
consecutive rebuilds (same IDs); hand-editing one row of `concept_map_overrides.csv` and rebuilding
makes layer 2 win over layer 1 for that item; no OMOP row carries a non-standard concept in a
`*_concept_id` slot.

**Phase 3 — intake.** Blob + envelope + `intake.patient` + both parsers + `load_envelope.sql` +
golden-envelope conformance in each language.
*Accept when:* each parser independently reproduces every `contracts/golden/*.envelope.json`
byte-identically under the serialization profile, and `serialize(parse(serialize(x)))` is a fixed
point; a message with a `1957`-only birth date yields `precision: "year"` with `m`/`d` null and an
`omop.person` carrying `year_of_birth` and null month/day; an unparseable date yields `null` plus a
diagnostic rather than today's date; the provenance walk from an `omop.measurement` reaches
`raw_blob` and the originating OBX substring is found in it; a re-sent identical message is stored,
flagged, and loads no new `naaccr_value` rows; two messages with the same PID-3 under *different*
assigning authorities produce two `intake.patient` rows; a deliberately malformed message lands a
`parse_status = 'failed'` row rather than throwing; the existing `SdcImporterTests.cs:41-154`
assertions (19 values → 19 measurements, both OBX-4 grouped shapes) still pass.

**Phase 4 — bridge broadening.** person/period/cdm_source, domain routing, thin condition + episode,
validate. Delete `phenoml-workflows/`.
*Accept when:* the importer writes zero `omop` rows; `omop.person` count equals `intake.patient`
count; a fixture with coded, numeric, and text answers produces `value_as_concept_id`,
`value_as_number` + `unit_source_value` (with `unit_concept_id` null), and an
`observation.value_as_string` respectively; no OMOP row has a non-standard concept in a
`*_concept_id` slot; `9_validate.sql` passes against
`database/seed/validate_thresholds.csv`; every stage is idempotent on a second run.

**Phase 5 — export.** CSV bundle + manifest + round-trip test.
*Accept when:* export → load into a fresh empty OMOP schema is row-for-row equal; `manifest.json`
row counts match the database; grepping the whole bundle for a known PHI string from the raw message
returns zero hits.

**Phase 6 — docs, notebooks, cleanup.** Drift fixes, roadmap, the three recreated notebooks, renames,
re-vendoring, `FindTemplateItem`.
*Accept when:* no doc statement contradicts the code (spot-check the four known drift points); the
dialect matrix is published; `TEST_PLAN.md` has no stale claims; all three notebooks execute
top-to-bottom against a database built by the Phase 0–5 pipeline, with `python_cdm_utils/` deleted
and no import logic left in `notebooks/`.

Phase 3 is the one that changes behaviour visibly; phases 1–2 are prerequisites that also happen to
fix the "everything is `concept_id = 0`" problem on their own, so they deliver value even if the
rebuild stalls after them.

---

## Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| **Athena NAACCR coverage is worse than assumed.** The whole layered map rests on the OHDSI `NAACCR` vocabulary covering most registry items. Nobody in this repo has measured it. | Layer 3 becomes the dominant layer, most concepts are local, and the export is far less interoperable than the design implies. | Measure coverage in Phase 2 **before** building the bridge on it. `concept_map_coverage` exists precisely to make this a number. If layer 1 is thin, that is a finding worth surfacing to the working group, not something to paper over with mints. |
| **The envelope contract ossifies too early.** Version 1 gets designed around HL7 v2 + CCR JSON and then NAACCR XML or FHIR won't fit. | Either a breaking `envelope_version` bump with stored envelopes to migrate, or per-format hacks that defeat the point. | `envelope_version` is in the schema from day one and stored per row. Sketch the NAACCR XML mapping onto v1 during Phase 3 design as a cheap falsification test, even though the importer is roadmap. |
| **JSON shredding in SQL is the weakest link.** `json_each` / `OPENJSON` are the one place dialects genuinely diverge, and it's the hinge of the whole "SQL owns transforms" claim. | If it gets ugly, the temptation is to move loading back into C#/Python — reintroducing the duplication this design exists to remove. | Keep the divergence to the single `load_envelope.sql` per dialect. If it can't be held there, that is a signal to reconsider, not to quietly duplicate logic. |
| **Either/or lets one implementation rot.** With the cross-implementation diff demoted to a non-blocking nightly, whichever toolchain the team uses less will quietly fall behind. | A user who picks the neglected one hits bugs nobody has seen, and the "pick either" promise in the README becomes false. | Golden-envelope conformance is blocking in **both** per-push jobs, so neither can silently break the contract. Accept that feature velocity may differ, and say so in the README rather than implying equal maturity. If one is truly unmaintained, delete it — an honest single implementation beats a fictional choice. |
| **Concept identity differs by dialect** (an accepted decision, not a defect). | A SQL Server export and a SQLite export of the same message are not concept-comparable; someone will eventually compare them and file a bug. | Documented in `SCHEMA_ARCHITECTURE.md`; recorded per row in `mapping_layer`; carried in export `manifest.json`; explicitly excluded from test assertions. |
| **Six phases is a lot of runway.** Phases 3–5 depend on 0–2 landing. | Stalling mid-rebuild leaves the repo in a worse state than today — two half-migrated layouts. | Every phase is independently valuable and independently mergeable. Phases 1–2 alone fix the `concept_id = 0` problem on the existing bridge. Do not start Phase 3 until 0–2 are merged. |
| **`4_condition_and_episode.sql` is the thinnest-specified script.** Thin condition + episode grouping is a deliberate scope cut. | The episode grain (one per accession) may not survive contact with multi-tumor reports. | Keep it in its own script so it can be replaced without touching measurement routing. Revisit with the ICD-O-3 roadmap work. |

---

## Verification

Each stage is independently runnable, so verification is per-phase rather than one big-bang test.
The toolchains are alternatives, so each of the two pipelines below must be verifiable **with the
other toolchain not installed**.

**Full pipeline — run either one, not both:**

```bash
# Python
python -m sdc_cdm build   --dialect sqlite --db out/demo.db
python -m sdc_cdm vocab load --vocab-dir database/vocab
python -m sdc_cdm constants resolve
python -m sdc_cdm dict load  --csv-dir out-egs
python -m sdc_cdm maps build
python -m sdc_cdm ingest sample_data/naaccr_v2/*.hl7
python -m sdc_cdm bridge
python -m sdc_cdm validate
python -m sdc_cdm export out/omop-csv/

# C# — identical verbs, identical result
dotnet run --project src/csharp/SdcCdm.Cli -- build --dialect sqlite --db out/demo2.db
# …

# Pure SQL — everything except parse and CSV streaming
sqlite3 out/demo3.db < database/manifest-driven build script
```

**Assertions:**

- **Envelope conformance (per language, independently).** Each parser reproduces
  `contracts/golden/*.envelope.json` byte-for-byte under the serialization profile, and
  `serialize(parse(serialize(x)))` is a fixed point. This is the blocking check, and it needs only
  one toolchain present.
- **Cross-implementation diff (nightly, non-blocking).** Both CLIs → two SQLite databases → diff on
  natural keys with surrogate IDs and timestamps excluded. Regression signal for maintainers, not a
  correctness gate — the envelope contract is what guarantees interoperability.
- **Partial dates.** A `1957`-only birth date survives as `year` precision into
  `omop.person.year_of_birth` with null month/day; an unparseable date becomes `null` plus a
  diagnostic, never today's date.
- **Provenance round-trip.** Pick any `omop.measurement`, walk
  `→ note → sdc_report → intake.inbound_message`, and assert the originating OBX substring is
  present in `raw_blob`. This is the test that proves the blob requirement is really met.
- **Concept coverage.** `SELECT * FROM naaccr.concept_map_coverage` — record a baseline per layer;
  CI fails on regression. `COUNT(*) FROM omop.measurement WHERE measurement_concept_id = 0` must
  drop from 100% to a documented residue.
- **Constants.** Deliberately drop a required concept from the vocabulary and confirm
  `constants resolve` fails loudly rather than the bridge writing a wrong ID.
- **Idempotency.** Every stage run twice leaves row counts unchanged (including `build`, which is
  the regression that the missing `IF NOT EXISTS` currently causes).
- **Export round-trip.** Export → load into a fresh empty OMOP schema → row-for-row equal. Plus:
  grep the entire export bundle for a known PHI string from the raw message and assert zero hits.
- **Domain routing.** A fixture with one coded, one numeric, and one text answer produces a
  `measurement` with `value_as_concept_id`, a `measurement` with `value_as_number` +
  `unit_source_value` (and `unit_concept_id` null, by design), and an `observation` with
  `value_as_string` respectively.
- **Person identity.** `omop.person` count equals `intake.patient` count; the same PID-3 under two
  different assigning authorities yields two patients, not one.
- **Existing coverage retained.** `SdcImporterTests.cs:41-154` already asserts 19 `naaccr_value`
  rows → 19 `omop.measurement` rows with both OBX-4 grouped shapes (item 2129 code+number, item
  820404 code+text). That test must keep passing through the refactor — it is the current
  behavioural contract.
