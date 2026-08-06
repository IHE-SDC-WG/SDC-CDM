# Rebuild SDC-CDM around a canonical intake envelope

**Status:** proposed. **Scope:** seven phases (0–6), each landing on `main` by fast-forward from its
own `phase-<N>-<topic>` branch — see "Starting point" for why this is not a stack of PRs.

This is the controlling design document for the rebuild. Each phase's GitHub issue links to its
section here, and the acceptance criteria in that section are the gate — not intent to be
re-derived. Amend this file in the same commit whenever a decision in it changes; this repo has
already been bitten by docs that contradict the code, and that list is in the Doc drift section
below.

PR #81 (`three-schema-repo-reorg` → `omop`) is closed unmerged, but the **branch** is where all
current work lives and becomes `main` — see **Starting point** below.

## Context

The three-schema design (`naaccr` / `sdc` / `omop`) is sound and should survive. What doesn't work
is everything around it:

- The raw HL7 v2 message is discarded at parse time — no provenance, no replay, warnings go to
  `Console.WriteLine` and vanish.
- The C# importer (`ImportNaaccrVolV.cs`) and its Python port
  (`import_vol_v_message_sqlite.py`) reimplement the same 600 lines of parsing with no automated
  parity test. A third variant (`ccr_labreport_to_naaccr.py`) reimplements the OBX-4 grouping again
  for JSON input and should be dropped, this will be moved to a private project.
- `naaccr_concept_map` / `naaccr_value_concept_map` are joined by the bridge but populated only by
  a SQL-Server-only script, so every SQLite measurement lands at `measurement_concept_id = 0`.
- The bridge writes only `note` + `measurement`. `observation_period`, `cdm_source`,
  `condition_occurrence`, `episode`/`episode_event` are never written — and a *second*,
  database-less mapper (`phenoml_workflows/mapper.py`) implements exactly those, divergently.
- Concept IDs `32817` / `32879` / `1147289` are hardcoded in SQL.
- There is no export. `omop` is populated in place with no way to hand it to anyone.

**The organizing idea of this rebuild:** insert a **canonical intake envelope** (versioned JSON)
between parsers and the database. Parsing becomes the only place raw source formats are understood;
everything downstream — load, map, bridge, validate, export — runs against the envelope and the
schema, never against HL7. **Python is the single implementation.** The duplication problem is
solved by deleting the duplicate, not by making two implementations agree.

The envelope earns its place even with one implementation, for three reasons that have nothing to do
with cross-language parity:

1. **Parsers become replaceable and testable in isolation** — `contracts/golden/*.envelope.json` is a
   regression oracle that catches parser drift before the database is involved.
2. **Out-of-tree parsers stay interoperable.** The CCR JSON path is deleted from this repo and
   continues life as a private project; because it can emit the same contract, it stays compatible
   without sharing code. NAACCR XML and FHIR can arrive the same way.
3. **Stored envelopes make replay real** — a parse fix can be re-applied to historical messages
   without re-reading the raw bytes.

### Decisions locked in

| Decision | Choice |
|---|---|
| Transform ownership | **Python owns transforms.** Python is the only driver: it owns orchestration, ordering, parameters, transactions, and all conditional logic. SQL is the set-based DML Python executes — schema creation plus `INSERT…SELECT` — not a parallel interface. Nothing is duplicated across languages. |
| C# vs Python | **Python is the implementation; C# handles SDC XML import only.** No C# HL7 parser — if C# ever needs one it shells out to the Python parser rather than reimplementing it. The C# SDC importer is refactored later to use the SDC Object Model. |
| Person identity | **`intake.patient` is the local registry.** `naaccr_value.person_id` / `sdc_report.person_id` hold an `intake.patient_id`; the bridge maps it 1:1 to `omop.person`. Matching is on `(assigning_authority, person_source_value)`; no cross-authority linkage. |
| Dates in the envelope | **Structured, never strings** — `{y, m, d, precision}`, so partial HL7 dates survive into OMOP's separate year/month/day columns. |
| Decimals in the envelope | **JSON strings, not numbers**, carrying the exact source lexeme so two languages cannot disagree via IEEE-754. |
| Units | **`unit_source_value` only.** `unit_concept_id` stays `NULL`; no UCUM mapping table is built. Roadmap. |
| SDC reference leg | **Not wired.** The eCP path stays NAACCR-dictionary-driven; `sdc.template_*` is intake-only for the SDC XML path, and this gets documented as intentional rather than implied-but-missing. |
| Concept mapping | **Layered**: Athena standard NAACCR vocabulary → curated overrides → locally minted 2B-range concepts, with a `mapping_layer` provenance column. |
| Item→schema provenance | **Both axes, both in the dictionary layer.** Vol II *section* is a column on `naaccr_item`, seeded from the imsweb layout extra-info CSV; the site-specific *staging schema* stays the `schema_item` → `staging_schema` many-to-many from SSDI. Captured values stamp `dd_version_id` always and `schema_id_number` only when derivable. |
| Concept slots | **Two-slot contract**: `*_source_concept_id` = the NAACCR source concept, `*_concept_id` = the standard concept reached via `concept_relationship` `'Maps to'`. Never the same value in both. |
| `NAACCR2026` minting script | **Kept, SQL-Server-only, as a supplement.** Concept identity legitimately differs by dialect; this is documented, not treated as drift. |
| `condition_occurrence` | **Thin version**: one row per report from the primary-site item alone, `concept_id = 0` where unmapped. ICD-O-3 combination-concept derivation goes to the roadmap. |
| Duplicate inbound bytes | **Store, flag, don't re-load.** Mirrors the existing insert-and-flag accession behaviour. |
| Export format | **CSV per OMOP table**, canonical OHDSI layout, with `manifest.json` and a `CDM_SOURCE` row. |
| Dialects | **SQLite + SQL Server only.** PostgreSQL is **removed from the tree**, not deferred in place — see below. The OHDSI PostgreSQL CDM files remain in the vendored upstream drop but are absent from `manifest.json`, so no driver applies them. Re-adding the dialect is roadmap. |
| FHIR | Roadmap only. |

---

## Starting point: `main` is trunk, phases land by fast-forward

`main` stays trunk and stays the default branch. It starts pointing at
`three-schema-repo-reorg`, which holds all current work.

`main` was merged into the branch by PR #88, so `main` is now an ancestor and two steps remain:

```bash
git push origin three-schema-repo-reorg:main   # fast-forward, 86 commits
git push origin --delete omop                  # ahead=0; a strict ancestor of main
```

`omop` is deleted only after the first push, so no commit is briefly unreferenced. The other stale
branches (`sql-refactor`, `add-sdc-template-row-data`, `copilot/fix-*`, `update-readme`,
`importFHIRIps`, `mvp`) hold unmerged commits and are out of scope here — they belong to a cleanup
project after this rebuild.

### Per-phase branches

Each phase runs on its own branch cut from `main`, and lands by fast-forward:

`phase-0-skeleton`, `phase-1-vocab`, `phase-2-maps`, `phase-3-intake`, `phase-4-bridge`,
`phase-5-export`, `phase-6-docs`.

```bash
git checkout main && git pull
git checkout -b phase-1-vocab
# …work…  then, with CI green and the phase's "Accept when" criteria met:
git push origin phase-1-vocab:main
git push origin --delete phase-1-vocab
```

Branches are **sequential, not stacked** — each is cut after the previous lands, so there is no stack
to rebase. The one rule: **do not start phase N+1 until phase N is on `main`.** Phase 0 is the
exception, running on the current branch because it is the phase that builds the CI.

A phase is done when its acceptance criteria pass, `main` is fast-forwarded to it, and its GitHub
issue is closed. If `main` diverges, merge it back into the phase branch and push again.

### Assets to preserve through the restructure

The rebuild is a **restructure, not a rewrite**. Use `git mv` for layout moves so rename detection
and `git blame` survive — the blame trail is how anyone will ever find out *why* an identifier like
`2118.1000043` is in the code.

| Asset | Why it cannot be cheaply recreated |
|---|---|
| `tools/ssdi-ts/` | Working SEER Staging REST API client + 3NF export. API-specific knowledge, weeks of work. It is now **load-bearing**, not a convenience export: it is the only source for the item→site-schema axis. |
| `tools/load_athena_vocab.py` | Three DB backends, freshness guards, CDM 5.4 column metadata, 8 tests. **The only vocabulary loader** — the C# `ImportCsv.cs` is a single-table stub and is deleted, not merged. |
| `database/schemas/naaccr/ddl/` | The `data_dictionary_version` dimension, staging-table catalog, `item_role` — real modelling. |
| `.../sqlserver/2_naaccr_omop_vocab_sqlserver.sql` | 665 lines, and we have decided to **keep** it. |
| OBX identifier constants in `ImportNaaccrVolV.cs` | `60573-3`, `60572-5`, `60574-1`, `2118.1000043`, `2168.1000043`, `52756.1000043`, `820603.1000043` — hard-won domain knowledge; the code structure changes, these do not. |
| The OBX-4 grouping rule | Re-derived three times already in this repo. Port it to the parsers verbatim. |
| Occurrence-aware idempotency SQL | The one genuinely well-built part of the current bridge. |
| `sample_data/` | Real HL7 messages, SDC templates, FHIR bundles. |
| `SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154` | The behavioural contract: 19 values → 19 measurements, items 2129 and 820404. **This is `ImportNaaccrVolV_ExecutesWithoutError` — an HL7 test, on the path C# is losing.** It must be **ported to pytest**, assertion for assertion, not simply kept. Porting it is how Phase 3 proves the Python parser matches the behaviour being retired. |
| `TEST_PLAN.md` | ~85 catalogued test IDs. Retarget, don't discard. |
| Git history | Why `sdc_report_id` and not accession; why SQLitePCLRaw is pinned; the 17 review findings. |

Deliberately discarded: the C# HL7 importer's *structure* (not its constants),
`notebooks/python_cdm_utils/`, the three-way DDL wiring, `phenoml_workflows/mapper.py` as a mapper,
hardcoded concept IDs, and the PostgreSQL dialect with its container wiring.

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

1. **Parser regressions are a file diff.** `contracts/golden/<fixture>.envelope.json` is the oracle:
   the parser must reproduce it byte-identically under the serialization profile below. It is also
   what an out-of-tree parser conforms to.
2. **The remaining intake shapes converge.** HL7 v2 ER7 text and (later) NAACCR XML become *parsers
   emitting the same envelope*. `ccr_labreport_to_naaccr.py` and its tests are **deleted** from this
   tree — but the envelope is what makes that safe: whatever the private project becomes, it can emit
   the same contract and stay interoperable without sharing code with this repo.
3. **Everything after the envelope is set-based.** `database/load/<dialect>/1_load_envelope.sql`
   shreds the JSON with `json_each` (SQLite) / `OPENJSON` (SQL Server) into `naaccr.naaccr_value` +
   `sdc.sdc_report`. Python drives it; the dialect difference is confined to that one file.

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
is accompanied by a written profile, and the parser has a single `serialize_envelope` routine whose
only job is to obey it. The profile is still worth pinning with one implementation: it is what makes
the golden files a stable diff across Python versions, and what an out-of-tree parser must match to
submit compatible envelopes.

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

A conformance test round-trips every golden envelope through
`serialize_envelope(parse(serialize_envelope(x)))` and asserts a fixed point.

### Raw message storage (`intake`)

`intake.inbound_message`:

| Column | Purpose |
|---|---|
| `inbound_message_id` | PK |
| `source_format`, `media_type` | `hl7v2` / `naaccr_xml` / `sdc_xml` — the enum stays open so an out-of-tree parser (e.g. the deleted CCR JSON one, in its private home) can submit its own envelopes |
| `raw_blob` | **The exact bytes, unaltered.** `BLOB` / `VARBINARY(MAX)` |
| `raw_sha256`, `byte_length` | content hash; non-unique index for duplicate detection |
| `is_content_duplicate`, `first_seen_inbound_message_id` | set when `raw_sha256` already exists; self-FK to the original |
| `received_datetime`, `received_by` | who/what submitted it |
| `message_control_id`, `sending_facility`, `message_profile` | MSH-10 / MSH-4 / MSH-21, denormalized for triage |
| `envelope_json`, `envelope_version` | the canonical parse result |
| `parser_name`, `parser_version` | **which parser and which version produced this envelope** — the forensic key when a parse bug is found later and you need to identify exactly which stored messages are affected, and the discriminator for envelopes submitted by out-of-tree parsers |
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

### One driver, one set of stages

Every stage is idempotent and separately invocable, and **Python runs all of them**.
`database/manifest.json` lists the SQL files in apply order, replacing the fragile alphabetical
resource glob in `BuildSchema()` (`SdcCdmInSqlite.cs:127-135`).

| Stage | What it does | Where the logic lives |
|---|---|---|
| `build` | apply `database/schemas/*/ddl/<dialect>/` per manifest | DDL, Python-ordered |
| `vocab load` | Athena bundle → `omop.concept` et al. | **Python only** — `tools/load_athena_vocab.py` promoted; no C# path |
| `constants resolve` | populate `etl.concept_constant` by `(vocabulary_id, concept_code)` lookup | Python |
| `dict load` | imsweb base dictionary + section CSV → `naaccr.naaccr_item`; SEER 3NF CSVs → `naaccr.staging_schema` / `schema_item` / `schema_item_code` / `schema_item_requirement`. Item defs load **first** so the `schema_item → naaccr_item` FK resolves. | Python (CSV/XML streaming) |
| `maps build` | layered concept-map build | set-based SQL, Python-driven |
| `ingest` | HL7 → `intake` (blob + envelope) → `naaccr` + `sdc` | **Python parser** + `load_envelope.sql` |
| `bridge` | `naaccr` + `sdc` → `omop` | set-based SQL, Python-driven |
| `validate` | DQ assertions | set-based SQL, Python-driven |
| `export` | `omop` → CSV bundle + manifest | Python (CSV writing) |

#### SQL under a Python driver

Python owns orchestration, ordering, parameters, transactions, `etl.run` logging, and every
conditional decision. The set-based stages execute SQL, because the bridge is a relational mapping
(`INSERT…SELECT` across five tables) whose occurrence-aware idempotency
(`1_naaccr_sdc_to_omop.sql:87-121`) is the best-built code in the repo, and because PHI never leaves
the database.

**SQL is not a public interface.** The `.sql` files are Python's implementation detail and may assume
Python has resolved constants, opened a transaction, and bound parameters. There is no hand-driven
`sqlite3`/`sqlcmd` path.

**DBT is rejected** — its `ref()` DAG competes with `manifest.json` as the ordering contract. Jinja is
compatible but not adopted; it is the fallback if the two dialect variants of a script start to
diverge.

**Toolchain × dialect support matrix** — publish this in the README and keep it honest. Today
neither driver is what this table describes: `BuildSchema()` is SQLite-only, Python has no schema
builder at all (just duplicated glob/`executescript` code in a notebook and a test helper), and the
pure-SQL path is Postgres-only via the Dockerfile — the one dialect this rebuild drops.

| | SQLite | SQL Server |
|---|---|---|
| Python CLI (`sdc_cdm`) | full | full |
| C# (`SdcCdm`) | SDC XML import only | SDC XML import only |

#### PostgreSQL is removed

Only `database/schemas/omop/ddl/postgresql/*` is vendored from OHDSI; the `naaccr` and `sdc`
PostgreSQL DDL are hand-maintained in this repo and are a third dialect to keep in sync. The dialect
is dropped rather than kept "schema only", which would have left it absent from `manifest.json`,
without a CI job, and without DDL for the new `intake` and `etl` schemas.

- **Delete** `database/schemas/{naaccr,sdc}/ddl/postgresql/`, `database/etl/postgresql/`, and the
  Postgres-only container wiring (`database/Dockerfile`, `docker-compose.yml`, `.env.example`).
  SQLite is the local dev story; the SQL Server CI service container covers the rest.
- **Keep** the OHDSI PostgreSQL CDM files in the vendored drop, omitted from `manifest.json`.
  `VENDORED.md` records that they are present but unapplied.
- **Correct the docs that promise it**: `README.md:18` and `:46`; `TEST_PLAN.md:20`, `:187`, `:250`.

Re-adding PostgreSQL is roadmap, starting from the SQLite DDL plus the vendored CDM.

The DDL is currently wired three separate ways — a csproj embedded-resource glob
(`SdcCdmInSqlite.csproj:11-13`), a Python runtime glob, and per-file `COPY` in the Dockerfile — so
any DDL add or rename silently breaks one of them. `database/manifest.json` becomes the single
ordering contract, read by the Python driver and by nothing else.

#### Test topology

Three jobs. Nobody needs .NET installed to work on the pipeline.

| CI job | Runs | When |
|---|---|---|
| `python-sqlite` | pytest: golden-envelope conformance, full pipeline, export round-trip | every push |
| `csharp-sdc` | `dotnet test`: SDC XML import only — `ImportXmlForm` / `ImportTemplate` and the template/form-answer contract. Note the current `SdcImporterTests.cs` is misnamed: its headline test is HL7, and that one moves to pytest. | every push |
| `python-sqlserver` | same pytest suite, `mcr.microsoft.com/mssql/server` service container | nightly + on `database/**` changes |

`contracts/golden/*.envelope.json` remains blocking, now as a **parser regression gate** rather than
a parity oracle. Keeping SQL Server off the PR path still removes the container cost from ordinary
review.

### Repo layout

```
contracts/
  envelope.schema.json                    the shared contract
  golden/                                 golden envelopes per fixture (parser regression oracle)
database/
  manifest.json                           canonical file order, read by the Python driver
  schemas/{intake,naaccr,sdc,omop,etl}/ddl/{sqlite,sqlserver}/
  schemas/omop/VENDORED.md                upstream OHDSI commit + re-vendor procedure;
                                          records that the vendored PostgreSQL CDM files
                                          are present but omitted from manifest.json
  load/{sqlite,sqlserver}/1_load_envelope.sql
  maps/{sqlite,sqlserver}/1_build_concept_maps.sql
  etl/{sqlite,sqlserver}/1_person_and_period.sql
                         2_note.sql
                         3_measurement_observation.sql
                         4_condition_and_episode.sql
                         9_validate.sql
  seed/concept_map_overrides.csv           curated layer-2 map
      naaccr_item_section_overrides.csv    section fallback for items the imsweb CSV lacks
      cdm_source.csv
src/csharp/{SdcCdm.Sdc,SdcCdm.Sdc.Tests}/  SDC XML import only — no CLI, no pipeline projects
src/python/sdc_cdm/{envelope,hl7v2,cli,db,vocab,export}/  + tests/   the implementation
tools/ssdi-ts/                             SEER dictionary export (unchanged)
tools/naaccr-dict/data/                    vendored imsweb base dictionary + items-extra-info.csv
notebooks/                                 recreated from scratch (see below)
sample_data/                               single source of fixtures
docs/{REBUILD_PLAN,SCHEMA_ARCHITECTURE,ROADMAP,TEST_PLAN}.md
```

The Python CLI exposes the full verb set above. The C# project is a library plus tests for SDC XML
import; it has no CLI and no pipeline verbs.

**Deleted outright:** `phenoml-workflows/` (mapping absorbed into Phase 4 SQL, review role replaced
by the tracked overrides CSV), `NAACRToOMOPmaps/*.xlsx` and `tools/convert_naaccr_omop_maps.py`
(after the one-time seed conversion), the whole PostgreSQL dialect (`database/etl/postgresql/`,
`database/schemas/{naaccr,sdc}/ddl/postgresql/`, `database/Dockerfile`,
`database/docker-compose.yml`, `database/.env.example` — see "PostgreSQL is removed, not deferred"
above), the CCR JSON path (`tools/ccr_labreport_to_naaccr.py` + `tools/tests/test_obx_parser.py`,
Phase 3), the FHIR code (`SdcCdm/ExportFhirCpds.cs`, `SdcCdm/FHIR/`,
`SdcCdm.Tests/FhirCpdsExporterTests.cs` — FHIR is roadmap and git history is the recovery path;
confirmed that nothing in `SdcCdm/FHIR/Importers.cs` needs preserving for the roadmap FHIR intake
work), the C# vocabulary stub (`SdcCdm/ImportCsv.cs` + `SdcCdm.Tests/VocabImporterTests.cs`), the C#
HL7 importer and its pipeline projects, and the root-level stray build artifacts
(`test_import*.db`, `etl_test_output.json`).

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

### Item provenance: which NAACCR schema an item came from

"NAACCR Schema" means two unrelated things in this repo, and today **both are empty**. They answer
different questions — *"what kind of field is this?"* versus *"which cancer site is this item staged
under?"* — so the rebuild records both rather than picking one.

#### Axis A — Vol II record-layout section

One value per item per dictionary version, on the existing `naaccr_item.section`
(`1_naaccr_sqlite_ddl.sql:59`, present in every dialect DDL, written by no code path today —
`tools/ssdi-ts/src/create-ssdi.ts:143` emits only `item_num`, `name`, `xml_id`, `unit`,
`decimal_places`).

The imsweb `naaccr-dictionary-<ver>.xml` `ItemDef` **has no section attribute** — NAACCR 25 carries
only `naaccrId`, `naaccrNum`, `naaccrName`, `length`, `recordTypes`, `parentXmlElement`, `dataType`
and `padding` across its 780 items. The section map lives in a *different* imsweb repo:
`imsweb/layout`, at `src/main/resources/layout/fixed/naaccr/items-extra-info.csv` — 895 headerless
rows of `naaccrId,short_label,section`, no quoting and no embedded commas. `dict load` joins it to
the base dictionary on `naaccrId` → `naaccr_item.xml_id`, and also lands the second column in a new
`naaccr_item.short_label`.

Both source files are vendored under the dictionary loader's `data/` with a checksum, so `dict load`
is offline and reproducible. **The licensing question the earlier `.context` plan left open is
closed:** `imsweb/layout` and `imsweb/naaccr-xml` both ship a 3-clause-BSD `LICENSE` (IMS Inc.,
2015), so redistribution is permitted with the notice retained.

**Version anchor, and its honest limit.** Anchor at **NAACCR 25** (`naaccr-dictionary-250.xml`),
where the CSV covers 780 of 780 items — zero misses, 17 distinct sections (`Stage/Prognostic
Factors` 396, `Treatment-1st Course` 91, `Demographic` 85, …). The CSV *lags* newer dictionaries: at
NAACCR 27 it misses 51 of 822 items (`geoAddrAtDxCity`, `rectalTumorLocation`,
`overRideSexAssignedAtBirth`, …). So a later anchor needs a fallback — a tracked
`database/seed/naaccr_item_section_overrides.csv` (`xml_id,section`) applied after the CSV join,
with `validate` counting NULL sections against a threshold. Do not silently ship NULLs.

**What the dictionary cannot give.** `alignment`, `trim` and start-column data exist only in the
fixed-column layouts, and those stop at `naaccr-18-layout.xml` — NAACCR retired the flat record
layout after v18. Either backfill them from the v18 layout for items that still exist, or leave them
NULL and say so; do not imply the base dictionary supplies them. Likewise `dataType` is declared on
only 526 of 780 ItemDefs — NULL there means "not declared upstream", not "not loaded".

#### Axis B — site-specific staging schema

No change of shape. `naaccr.schema_item` (with its `item_role` input/output split) →
`naaccr.staging_schema` stays the SSDI-sourced many-to-many, which is the right model: one item
number legitimately belongs to many site schemas, so this can never be a column on `naaccr_item`.
`tools/ssdi-ts` stays the loader.

The rebuild's contribution is making it actually *load* and *resolve*: the SSDI export and the
item-def seed must share one `dd_version_id` generation, and `validate` asserts zero orphan
`schema_item.item_num`. Record the canonical lookup in `SCHEMA_ARCHITECTURE.md`:

```sql
SELECT ss.schema_id, ss.schema_name, si.item_role
FROM naaccr.schema_item si
JOIN naaccr.staging_schema ss
  ON ss.dd_version_id = si.dd_version_id
 AND ss.schema_id_number = si.schema_id_number
WHERE si.item_num = ? AND si.dd_version_id = ?;
```

#### Stamping captured values

Both `naaccr_value.dd_version_id` and `naaccr_value.schema_id_number` are hard-coded NULL by every
importer today (`ImportNaaccrVolV.cs:537-614` never passes either; `ISdcCdm.cs:215` defaults them;
`ccr_labreport_to_naaccr.py:446,454` writes `None` literally).

- **`dd_version_id` becomes non-null in practice.** `load_envelope.sql` resolves it from the
  message's NAACCR record version when present, else from the `is_current` row. This is a *load-time*
  decision, not a parse-time one — the envelope stays source-faithful and gains no `dd_version_id`
  field. It also gives the missing SQL Server FK (listed under Correctness fixes below) something
  real to enforce.
- **`schema_id_number` only when derivable.** It is a function of the `schema_selection_rule` inputs
  — site, histology, behavior, `sex_at_birth`, the two discriminators, `year_dx`. Derive it at load
  where all required inputs are present in the report; otherwise leave NULL and emit a diagnostic.
  Running the full SEER staging algorithm to resolve every case is **roadmap**.

### Concept maps, layered with provenance

`naaccr.naaccr_concept_map` and `naaccr_value_concept_map` gain `mapping_layer`
(`athena_standard` | `curated_override` | `local_mint`), `source_concept_id`, `target_domain_id`,
and `created_at`. They stay version-independent (keyed on `item_num` / `(item_num, code)`) — the
existing rationale in `SCHEMA_ARCHITECTURE.md:37-40` holds. Note the one place this meets the
versioned dictionary: layer 3 below reads `naaccr_item.section`, whose PK is
`(dd_version_id, item_num)`. The map *rows* remain version-independent; the build simply reads
section from the `is_current` dictionary generation. Record that choice in the build script rather
than letting it be implicit.

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
   to both dialects. Derive the mint's `concept_class_id` from `naaccr_item.section` +
   `parent_xml_element` rather than a flat `'NAACCR Item'` — this reconstructs the
   `STAGE_PROGNOSTIC_FAC` / `TREATMENT_1ST_COURSE` / `DEMOGRAPHIC_TUMOR` class strings already baked
   into `naaccr_omop_extension_mapping_spec.json`, from a real source this time, which matters
   because this plan deletes that JSON (see the one-time conversion below).

`naaccr.concept_map_coverage` view emits items total / mapped per layer / unmapped, so coverage is
a number CI can assert on and regressions are visible. Break it down **by section** as well as by
layer: "396 `Stage/Prognostic Factors` items, N mapped" is an actionable number for the working
group, where a single global percentage is not. This is what makes the Athena-coverage risk below
measurable rather than rhetorical.

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
- **Cross-dialect concept equality is explicitly not a test assertion.** No job compares SQLite
  against SQL Server on concept IDs; the `python-sqlserver` suite asserts the same *behaviour*, not
  the same concept identifiers.
- Exports carry the resolving vocabulary in `manifest.json` so a recipient knows which concept
  universe they received.

#### Layer 2 without a review UI

`phenoml-workflows/` is retired; layer 2 is a tracked CSV and git is the review trail.

`database/seed/concept_map_overrides.csv` columns: `item_num`, `code` (blank for item-level),
`omop_concept_id`, `omop_source_concept_id`, `target_domain_id`, `rationale`, `reviewer`,
`reviewed_at`.

**One-time conversion, then retire the artifacts.** Convert
`naaccr_omop_extension_mapping_spec.json` (780 rows; the inventory is worth keeping, the mappings are
not) into two tracked seeds:

- `database/seed/concept_map_overrides.csv` — skeleton rows with `omop_concept_id` blank where
  unreviewed (which is all 780 today), so the file starts as an honest to-do list rather than a
  pretend mapping.
- `database/seed/naaccr_item_exclusions.csv` — the 74 items explicitly flagged `is_mappable: false`.

Then drop the JSON, `tools/convert_naaccr_omop_maps.py`, and the `NAACRToOMOPmaps/*.xlsx` workbooks.

Field-name trap in the converter: the spec's `concept_id` field holds a NAACCR
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

`python -m sdc_cdm bridge` executes `database/etl/<dialect>/*.sql` in manifest order, owning the
transaction, the `etl.run` log entry, and parameter binding. It is the only bridge runner — the
former C# path and the hand-driven `sqlite3` path are both gone. The one-off
`.context/verify_e2e_bridge.py` becomes a real test.

### Doc drift

- **Delete `ECP_OMOP_MAPPING.md`.** Its central claim (`:64`) is false today and its premise (`:14`)
  is replaced by domain routing. Move its numeric/coded/text → OMOP column table into
  `SCHEMA_ARCHITECTURE.md` beside the two-slot contract.
- `TEST_PLAN.md` EXP-01 asserts a `NULL AS response` bug that is **already fixed** — verified:
  `GetSdcObsClasses` selects `sdc_form_answer.response` at `SdcCdmInSqlite.cs:578-600`. Delete the
  stale claim, and see "The FHIR export code, and what that means for `EXP-01`" under Phasing for the
  rest of that ID's disposition. Retarget the other test IDs at the new stage boundaries.
- `SCHEMA_ARCHITECTURE.md` — five schemas, envelope contract, layered maps, per-dialect status
  table, the two-slot concept contract, the note that `person_id` columns now hold
  `intake.patient_id`, and an explicit statement that the SDC reference is intake-only for the XML
  path.
- `docs/ROADMAP.md` (new) — ICD-O-3 combination-concept `condition_occurrence` derivation, UCUM
  `unit_concept_id` resolution, FHIR intake/export, NAACCR XML, CCDA, **PostgreSQL support end to
  end** (DDL, load, bridge, export — the dialect is deleted in this rebuild, so re-adding it means
  re-deriving the DDL from the SQLite reference plus the vendored OHDSI CDM), `PV1` →
  `visit_occurrence`, `SPM` → `specimen`, SDC template-driven answer validation, cross-authority
  person linkage.
- **Purge the PostgreSQL claims** left behind by dropping the dialect: `README.md:18` and `:46`,
  `TEST_PLAN.md:20` (the `{sqlite,sqlserver,postgresql}` bridge glob that implies a file which never
  existed), `:187` (PostgreSQL ports), and `:250` (SCHEMA-02 DDL parity across three dialects →
  two). The two-column dialect matrix above is the honest replacement.

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
  `naaccr_value.dd_version_id` FK that SQLite already enforces, and normalize the
  UPPERCASE table names to lowercase.
- **Rename `sdc_form_answer.reponse_string_nvarchar` → `response_string`.** The typo is baked into
  every dialect DDL and the `ISdcCdm` API. A fresh PR is the moment.
- **Split and rename `SdcCdmLib/SdcCdm.Tests/SdcImporterTests.cs`.** Despite the name, only 1 of its
  7 test methods is an SDC test. The file is majority HL7, which is why the "behavioural contract"
  ended up stranded on the path C# is losing:

  | Method | Fate |
  |---|---|
  | `ProcessXmlForm_ExecutesWithoutError` | **stays in C#** — this is the only genuine SDC test |
  | `ImportNaaccrVolV_ExecutesWithoutError` (`SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154`) | **port to pytest** — the 19→19 behavioural contract |
  | `ImportNaaccrVolV_DoesNotWriteSdcFormTables` | port to pytest |
  | `ImportNaaccrVolV_BlankNarrativeUsesBridgeFallback` | port to pytest |
  | `ImportNaaccrVolV_MissingObxDateFallsBackToObrDate` | port to pytest — and tighten it, since Phase 3 replaces the today's-date fallback with a diagnostic |
  | `ImportAllHL7Files_ExecutesWithoutError` | port to pytest |
  | `ImportFHIRIPSJSONToResource_ExecutesWithoutError` | **delete** with the rest of the FHIR code — see "The FHIR export code" under Phasing |

  What remains becomes `SdcXmlImporterTests.cs`. Do the rename with `git mv` **after** the HL7
  methods have left, so the history of the ported assertions stays attached to the file they came
  from.
- **Delete `SdcCdm/ImportCsv.cs` and `SdcCdm.Tests/VocabImporterTests.cs` — nothing to port.**
  These are not a peer of the Python loader and must not be treated as one: `CsvImporter.ImportConceptCsv`
  loads a single table (`omop.concept`) and its two tests assert three rows from a three-row fixture,
  where `tools/load_athena_vocab.py` is 1024 lines covering nine CDM tables across three backends with
  freshness guards and eight tests. Phase 1 promotes the Python loader and deletes the C# one outright.
- **Implement `FindTemplateItem`** (`SdcCdmInSqlite.cs:647-650` throws `NotImplementedException`),
  so `ImportTemplateRowData` can dedupe across runs.
- **Re-vendor the OMOP DDL** from upstream OHDSI and record the commit in `VENDORED.md`. Drops the
  stale `"5.4-SDC"` header comments without hand-editing vendored files.
- **CI** (`.github/workflows/`): `pytest`, a full SQLite pipeline run, the golden-envelope
  regression gate, the concept-map coverage assertion, and `dotnet test` for the SDC XML importer.
  `TEST_PLAN.md` CLEAN-03 has been open the whole time.

---

## Phasing

Order matters — vocabulary before mapping before ingest, so nothing needs re-ingesting.

Each phase runs on its own `phase-<N>-<topic>` branch cut from `main`, ends by fast-forwarding `main`
to it, and closes one GitHub issue. Acceptance criteria are what the phase must demonstrate before
that fast-forward, not aspirations.

**Phase 0 — skeleton and contracts.** Repo layout, `contracts/envelope.schema.json`, `intake` + `etl`
DDL, `database/manifest.json`, migration ledger, CI. This plan is already committed as
`docs/REBUILD_PLAN.md` on `three-schema-repo-reorg`, so each phase issue can link to its section;
the one-time transition in "Starting point" carries it to `main`. Open the seven phase issues here
too. Phase 0 runs on the current branch rather than a `phase-0-skeleton` branch, since it is the
phase that builds the CI there is nothing yet to gate against.
*Accept when:* `build` runs twice against the same database with no error and no duplicate objects
(the current `IF NOT EXISTS` regression); the Python driver builds a SQLite database from the
manifest, and the SQL Server job does the same on its own schedule; the three CI jobs exist and the
two per-push jobs are green; **no pytest run requires .NET and no `dotnet test` requires Python** —
the SDC XML suite must not reach into the pipeline; the
promoted end-to-end no-double-count test (from the untracked `.context/verify_e2e_bridge.py`) passes
as a tracked test; `grep -ri postgres` over the tree returns hits **only** inside the vendored OHDSI
CDM files and `VENDORED.md` — no DDL, no container wiring, no doc claiming PostgreSQL support.

**Phase 1 — vocabulary and constants.** Athena loader promoted out of `tools/`; `etl.concept_constant`
resolver; SEER dictionary loader for **both** dialects.
*Accept when:* every constant resolves from a loaded Athena bundle; deleting one required concept
makes `constants resolve` exit non-zero with the missing `(vocabulary_id, concept_code)` named; the
NAACCR dictionary loads into SQLite from the same 3NF CSVs SQL Server uses, with matching row counts;
`naaccr.naaccr_item` seeds with non-null `xml_id` **and** non-null `section` for 100% of items at the
declared version anchor, and `SELECT section, COUNT(*) … GROUP BY 1` returns the 17 expected
sections; every `schema_item.item_num` resolves to a `naaccr_item` row with zero orphans.

**Phase 2 — concept maps.** Layered build, coverage view, one-time seed conversion from the mapping
spec, then delete the spec/workbooks/converter.
*Accept when:* `naaccr.concept_map_coverage` reports a nonzero layer-1 count on a real Athena bundle;
every map row has a `mapping_layer` and a `source_concept_id`; layer-3 mints are stable across two
consecutive rebuilds (same IDs); hand-editing one row of `concept_map_overrides.csv` and rebuilding
makes layer 2 win over layer 1 for that item; no OMOP row carries a non-standard concept in a
`*_concept_id` slot.

**Phase 3 — intake.** Blob + envelope + `intake.patient` + the Python HL7 parser +
`load_envelope.sql` + golden-envelope conformance. **Delete `tools/ccr_labreport_to_naaccr.py` and
`tools/tests/test_obx_parser.py`** in this phase — the envelope is what makes the split safe, so the
deletion should not land before the Python parser conforms to the golden files.
*Accept when:* the parser reproduces every `contracts/golden/*.envelope.json`
byte-identically under the serialization profile, and `serialize(parse(serialize(x)))` is a fixed
point; a message with a `1957`-only birth date yields `precision: "year"` with `m`/`d` null and an
`omop.person` carrying `year_of_birth` and null month/day; an unparseable date yields `null` plus a
diagnostic rather than today's date; the provenance walk from an `omop.measurement` reaches
`raw_blob` and the originating OBX substring is found in it; a re-sent identical message is stored,
flagged, and loads no new `naaccr_value` rows; two messages with the same PID-3 under *different*
assigning authorities produce two `intake.patient` rows; a deliberately malformed message lands a
`parse_status = 'failed'` row rather than throwing; every `naaccr_value` row written by
`load_envelope.sql` carries a non-null `dd_version_id`; a fixture carrying the staging-selection
inputs yields a non-null `schema_id_number` that resolves to a `staging_schema` row, and one lacking
them yields NULL plus a diagnostic; **`SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154` is ported to pytest** and its
assertions (19 values → 19 measurements, both OBX-4 grouped shapes) pass against the Python parser —
this is the phase's proof that nothing was lost in retiring the C# HL7 path.

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
re-vendoring, `FindTemplateItem`. Note `TEST_PLAN.md` is *not* first touched here — see "Test
artifacts per phase" below; by this point it should need only the Phase 6 row.
*Accept when:* no doc statement contradicts the code (spot-check the four known drift points); the
dialect matrix is published; `TEST_PLAN.md` has no stale claims; all three notebooks execute
top-to-bottom against a database built by the Phase 0–5 pipeline, with `python_cdm_utils/` deleted
and no import logic left in `notebooks/`.

Phase 3 is the one that changes behaviour visibly; phases 1–2 are prerequisites that also happen to
fix the "everything is `concept_id = 0`" problem on their own, so they deliver value even if the
rebuild stalls after them.

### Test artifacts per phase

`TEST_PLAN.md` catalogues **75 test IDs across 12 prefixes**. It is updated in the same phase that
invalidates it — a phase whose test IDs are not retargeted is not done. "Retire" means delete the ID
with a one-line note saying why.

| Phase | Retire | Retarget | Add |
|---|---|---|---|
| **0** skeleton | `SCHEMA-05` (C# `BuildSchema()` ↔ raw-DDL drift check — there is no C# schema builder any more) | `TEST_PLAN.md:20` bridge glob → `{sqlite,sqlserver}`; `SCHEMA-02` DDL parity → two dialects; `SCHEMA-04` → whatever survives of `update-ddl-files.py`; `CLEAN-03` → the three-job topology; `CLEAN-02` shared golden files → `contracts/golden/`, Python-only | manifest ordering is the single apply order; `build` twice is a no-op (the `CREATE INDEX` regression); migration-ledger skip works |
| **1** vocab + dict | `VocabImporterTests.cs` — deleted with `ImportCsv.cs`, not ported; the Python loader's 8 tests already cover strictly more | `SCHEMA-03` (bridge concept literals exist) → `constants resolve` fails loudly on a missing `(vocabulary_id, concept_code)` | `section` non-null for 100% of items at the anchor and the 17 expected values; zero orphan `schema_item.item_num`; dictionary row counts match across dialects |
| **2** concept maps | `PY-04` (`test_convert_naaccr_omop_maps.py` — the converter is deleted after the one-time seed conversion) | the `NAACCR`/`OMOP` map IDs at the layered build | coverage by layer **and by section**; layer 2 beats layer 1 on an edited override row; layer-3 mints stable across two rebuilds; no non-standard concept in a `*_concept_id` slot |
| **3** intake | **all of §6 "Python port parity"** — `PY-01`/`PY-02` guard drift from a C# importer that no longer exists; `PY-03` (`test_obx_parser.py`) is deleted with `ccr_labreport_to_naaccr.py` | the 9 `IMP-HL7` IDs in §1.1, from `SdcCdm.NAACCRVolVImporter.ImportNaaccrVolV` to the Python parser; `CLEAN-01` fixture dedup now that `sample_data/` is the single source | golden-envelope conformance + serialization fixed point; partial dates; provenance walk to `raw_blob`; duplicate bytes stored-flagged-not-loaded; two authorities → two patients; malformed message → `parse_status='failed'` |
| **4** bridge | — | the 11 `OMOP` IDs in §3 at the split scripts; the 6 `NAACCR` IDs in §2 | domain routing (coded/numeric/text); the two-slot contract; person/period/`cdm_source`; `9_validate.sql` against `validate_thresholds.csv`; every stage idempotent twice |
| **5** export | — | **move `EXP-01`–`EXP-04` to roadmap, do not retarget them** — all four are FHIR round-trips against `ExportFhirCpds`, not CSV-bundle tests; see below | a fresh set of CSV-export IDs: export → fresh-schema round-trip equality; manifest row counts and sha256; PHI grep returns zero; header order matches the shared CDM 5.4 `TABLE_SPECS` |
| **6** docs | — | the 12 `SDCOM` IDs at the C# SDC Object Model refactor; mark `IMP-FHIR` (12), `IMP-NXML` (2), `IMP-CCDA` (1) as roadmap-blocked rather than merely unchecked | notebooks execute top-to-bottom; no doc statement contradicts the code |

Two structural changes to `TEST_PLAN.md` itself, both in Phase 3 where the ownership actually
flips: **§6 is deleted outright** (see above), and §1.1's heading stops naming a C# type. The
`SdcImporterTests.cs` split and rename described under Correctness fixes lands in the same PR.

#### FHIR code and `EXP-01`

`SdcCdm/ExportFhirCpds.cs`, `SdcCdm/FHIR/`, and `SdcCdm.Tests/FhirCpdsExporterTests.cs` are
**deleted**; git history is the recovery path when FHIR comes off the roadmap.

`EXP-01`–`EXP-04` go to roadmap with that code — they round-trip through `ExportFhirCpds`, so they
are not CSV-export tests and must not be retargeted as if they were. Two consequences:

- `EXP-01`'s claim that `GetSdcObsClasses` returns `NULL AS response` is **stale** — it now selects
  `sdc_form_answer.response` (`SdcCdmInSqlite.cs:578-600`).
- That fix is otherwise untested. In Phase 3, before deleting the FHIR code, assert in the SDC XML
  import tests that `sdc_form_answer.response` is populated for every answered question.

`EXP-01` is cross-referenced from `TEST_PLAN.md:140`, `:288`, `:313`, `:365`, `:373` — re-point those
at the new import-side assertion rather than deleting them.

---

## Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| **Athena NAACCR coverage is worse than assumed.** Nobody has measured it. | Layer 3 dominates, most concepts are local, the export is far less interoperable than the design implies. | Measure in Phase 2 **before** the bridge is built on it; `concept_map_coverage` makes it a number. Thin layer 1 is a finding for the working group, not something to paper over with mints. |
| **The envelope contract ossifies too early.** v1 is designed around HL7 v2 alone. | A breaking `envelope_version` bump with stored envelopes to migrate, or per-format hacks. | `envelope_version` is in the schema from day one and stored per row. Sketch the NAACCR XML mapping onto v1 during Phase 3 design as a cheap falsification test. |
| **JSON shredding in SQL is the weakest link.** `json_each` / `OPENJSON` are where the two dialects genuinely diverge. | The two `load_envelope.sql` variants drift apart, invisible until a SQL Server run produces different rows. | Keep divergence to that one file per dialect; the nightly `python-sqlserver` job runs the same assertions so drift fails a test. Shredding in Python, or Jinja-templating one source into two, are the fallbacks. |
| **A single implementation is a single point of failure.** No C# pipeline, no hand-driven SQL path. | If a stage breaks there is no second way to run the pipeline. | Accepted cost of deleting the duplication. Every stage stays separately invocable and idempotent, so a failed stage can be re-run in isolation. |
| **Concept identity differs by dialect** (accepted, not a defect). | A SQL Server export and a SQLite export of the same message are not concept-comparable. | Documented in `SCHEMA_ARCHITECTURE.md`, recorded per row in `mapping_layer`, carried in export `manifest.json`, excluded from test assertions. |
| **Seven phases is a lot of runway.** Phases 3–5 depend on 0–2 landing. | Stalling mid-rebuild leaves two half-migrated layouts. | Each phase lands on `main` by fast-forward, so a stall leaves trunk holding every completed phase. Phases 1–2 alone fix the `concept_id = 0` problem. Do not start Phase 3 until 0–2 are on `main`. |
| **Dropping PostgreSQL strands a deployment.** Assumes the container was dev convenience, not a target. | Someone deploying on Postgres cannot follow the rebuild. | Confirmed with the working group before Phase 0. If it becomes a real target, fund it properly (manifest entry, CI job, `intake`/`etl` DDL). |
| **`items-extra-info.csv` is a third-party library resource**, not a NAACCR artifact, and lags: 51 of NAACCR 27's 822 items are absent. | `section` silently NULLs, breaking the layer-3 concept-class derivation. | Vendor with a checksum and fail `dict load` on drift; `naaccr_item_section_overrides.csv` is the escape hatch; `validate` counts NULL sections. NAACCR DD API is the fallback source. |
| **`4_condition_and_episode.sql` is thinly specified.** Thin condition + episode grouping is a deliberate scope cut. | The episode grain (one per accession) may not survive multi-tumor reports. | Keep it in its own script so it can be replaced without touching measurement routing. Revisit with the ICD-O-3 roadmap work. |

---

## Verification

Each stage is independently runnable, so verification is per-phase rather than one big-bang test.
The pipeline must be verifiable **with .NET not installed**, and the SDC XML suite must pass with
Python not installed.

**Full pipeline — one path:**

```bash
python -m sdc_cdm build   --dialect sqlite --db out/demo.db
python -m sdc_cdm vocab load --vocab-dir database/vocab
python -m sdc_cdm constants resolve
python -m sdc_cdm dict load  --csv-dir out-egs
python -m sdc_cdm maps build
python -m sdc_cdm ingest sample_data/naaccr_v2/*.hl7
python -m sdc_cdm bridge
python -m sdc_cdm validate
python -m sdc_cdm export out/omop-csv/

# SDC XML import is the one C# surface, and it is a library + tests, not a CLI
dotnet test src/csharp/SdcCdm.Sdc.Tests
```

**Assertions:**

- **Envelope conformance.** The parser reproduces `contracts/golden/*.envelope.json` byte-for-byte
  under the serialization profile, and `serialize(parse(serialize(x)))` is a fixed point. Blocking.
- **Dialect behaviour parity.** The same pytest suite passes against SQLite and, nightly, against
  SQL Server — asserting equal *behaviour*, never equal concept IDs.
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
- **Existing coverage retained, in the new language.** `SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154` asserts 19
  `naaccr_value` rows → 19 `omop.measurement` rows with both OBX-4 grouped shapes (item 2129
  code+number, item 820404 code+text). Because it exercises the HL7 path, it cannot stay in C#: port
  it to pytest assertion for assertion and require the port to pass before the C# HL7 importer is
  deleted. It is the current behavioural contract and the only thing standing between this rebuild
  and a silent regression.
