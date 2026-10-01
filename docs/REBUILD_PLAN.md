# Rebuild SDC-CDM around a canonical intake envelope

**Status:** Phases 0–3 are complete on `main` (#90–#93 closed). Phase 4 (#94) is next and is split
into child issues 4.0–4.5 (#141–#146). **Scope:** seven phases (0–6), each landing on `main` as
squash-merged pull requests, one per child issue — see "Starting point".

This is the controlling design document for the rebuild. Each phase's GitHub issue links to its
section here, and the acceptance criteria in that section are the gate — not intent to be
re-derived. Amend this file in the same commit whenever a decision in it changes; this repo has
already been bitten by docs that contradict the code, and that list is in the Doc drift section
below.

## Context

Sections that describe the repository before the rebuild are historical. They explain why a
decision was made; they do not describe the current code. File and line references such as
`ImportNaaccrVolV.cs:197` point at deleted code and are recoverable from git history.

**Current state (after Phase 3).** Python owns build, vocabulary load, constant resolution,
dictionary fetch/load/verify, SSDI fetch, map build/coverage, and HL7 intake/load on SQLite and
SQL Server. The importer writes no OMOP rows. The only bridge is still the pre-rebuild
`database/etl/<dialect>/1_naaccr_sdc_to_omop.sql`, applied directly by tests: it writes `note` and
`measurement` only, embeds concept literals, and has no Python runner. Phase 4 replaces it.
Phase 4.0 adds `naaccr.report_group` and `naaccr.report_version`: `intake load` records each
accessioned report's version, `build` backfills earlier loads, and `reports supersede` moves
selection. The existing bridge does not read selection yet.

**Before the rebuild (historical).** The three-schema design (`naaccr` / `sdc` / `omop`) is sound
and should survive. What didn't work was everything around it:

- The raw HL7 v2 message is discarded at parse time — no provenance, no replay, warnings go to
  `Console.WriteLine` and vanish.
- The C# importer (`ImportNaaccrVolV.cs`) and its Python port
  (`import_vol_v_message_sqlite.py`) reimplement the same 600 lines of parsing with no automated
  parity test. The former CCR JSON variant and its tests have been removed from this repository;
  the private project now owns that path.
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
| Item→schema provenance | **Both axes, both in the dictionary layer.** Vol II *section* is a column on `naaccr_item`, populated from SEER\*API `/rest/naaccr/*`; the site-specific *staging schema* stays the `schema_item` → `staging_schema` many-to-many from SSDI. Captured values stamp `dd_version_id` always and `schema_id_number` only when derivable. |
| Concept slots | **Two-slot contract**: `*_source_concept_id` = the NAACCR source concept, `*_concept_id` = the standard concept reached via `concept_relationship` `'Maps to'`. Never the same value in both. |
| `NAACCR2026` minting script | **Kept, SQL-Server-only, as a supplement.** Concept identity legitimately differs by dialect; this is documented, not treated as drift. |
| `condition_occurrence` | **Thin version**: one row per selected report group from the primary-site item alone, `concept_id = 0` where unmapped. ICD-O-3 combination-concept derivation goes to the roadmap. |
| Duplicate inbound bytes | **Store, flag, don't re-load.** Mirrors the existing insert-and-flag accession behaviour. |
| CKey → NAACCR mapping | **Outside this project.** No crosswalk, mapping seeds, or mapping fixtures here. Verified `item_num` values arrive from external preprocessing; unmapped `ecp_code` values are retained and never interpreted by numeric prefix. |
| Report versions | **Retain every version; select explicitly.** Group by patient, sending facility, and accession; distinguish versions by report type. The first version of each type is selected until an explicit supersession names a successor — newer receipt alone never replaces. |
| Export format | **CSV per OMOP table**, canonical OHDSI layout, with `manifest.json` and a `CDM_SOURCE` row. |
| Dialects | **SQLite + SQL Server only.** PostgreSQL is **removed from the tree**, not deferred in place — see below. The OHDSI PostgreSQL CDM files remain in the vendored upstream drop but are absent from `manifest.json`, so no driver applies them. Re-adding the dialect is roadmap. |
| FHIR | Roadmap only. |

---

## Starting point: `main` is trunk, phases land by squash-merge

`main` is trunk and the default branch. The one-time transition from `three-schema-repo-reorg`
(PR #81 closed unmerged; the branch was fast-forwarded onto `main` and `omop` deleted) is complete.
The other stale branches (`sql-refactor`, `add-sdc-template-row-data`, `copilot/fix-*`,
`update-readme`, `importFHIRIps`, `mvp`) hold unmerged commits and belong to a cleanup project
after this rebuild.

### Per-phase branches

Each phase is split into child issues, and each child issue lands as one pull request to `main`,
squash-merged once CI is green. There are no long-lived `phase-<N>-<topic>` branches; Phase 4 has
no `phase-4-bridge` branch. A child's branch is normally `issue-<N>`; an existing checkout keeps
its branch name. (Phase 3's four PRs, #134–#137, used merge commits; squash-merge is the
convention from Phase 3.4 onward.)

```bash
git checkout main && git pull
git checkout -b issue-130
# …work…  then, with CI green and the child issue's "Accept when" criteria met:
gh pr create --base main
gh pr merge --squash --delete-branch
```

Child branches are **sequential, not stacked** where one depends on another — each is cut after its
prerequisite lands, so there is no stack to rebase. The one rule: **do not start phase N+1 until
phase N is on `main`.** Phase 0 was the exception, running on its own branch because it built the CI.

A phase is done when its acceptance criteria pass, every child PR is merged to `main`, and its
GitHub issue is closed. If `main` moves, merge it back into the child branch and push again.

### Assets to preserve through the restructure

The rebuild is a **restructure, not a rewrite**. Use `git mv` for layout moves so rename detection
and `git blame` survive — the blame trail is how anyone will ever find out *why* an identifier like
`2118.1000043` is in the code.

| Asset | Why it cannot be cheaply recreated |
|---|---|
| `src/python/sdc_cdm/naaccr/` | Stdlib-only SEER NAACCR and staging client, deterministic dictionary and SSDI CSV contracts, transactional loader, and counts-only verifier. |
| `tools/load_athena_vocab.py` | Three DB backends, freshness guards, CDM 5.4 column metadata, 8 tests. **The only vocabulary loader** — the C# `ImportCsv.cs` is a single-table stub and is deleted, not merged. |
| `database/schemas/naaccr/ddl/` | The `data_dictionary_version` dimension, staging-table catalog, `item_role` — real modelling. |
| `.../sqlserver/2_naaccr_omop_vocab_sqlserver.sql` | 665 lines, and we have decided to **keep** it. |
| OBX identifier constants in `ImportNaaccrVolV.cs` | `60573-3`, `60572-5`, `60574-1`, `2118.1000043`, `2168.1000043`, `52756.1000043`, `820603.1000043` — hard-won domain knowledge; the code structure changes, these do not. |
| The OBX-4 grouping rule | Re-derived three times already in this repo. Port it to the parsers verbatim. |
| Occurrence-aware idempotency SQL | The one genuinely well-built part of the current bridge. |
| `sample_data/` | Real HL7 messages, SDC templates, FHIR bundles. |
| `SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154` | The historical behavioural contract: 19 values → 19 measurements, CAP codes `2129.1000043` and `820404.1000043`. Its numeric `item_num` assertions record the retired importer's identifier error. Phase 3 ports the grouping and count assertions to pytest using the corrected `ecp_code` shape. |
| `TEST_PLAN.md` | The catalogue of test IDs and named acceptance checks. Retarget, don't discard. |
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
persistence. One HL7 OBR group produces one envelope. Envelopes are stored in
OBR order beneath one byte-preserving inbound message, so narrative and
synoptic OBRs retain their distinct report LOINCs:

Each answer carries either a verified NAACCR `item_num` or a full CAP OBX-3.1
`ecp_code`. The numeric prefix of a CAP code is never inferred as a NAACCR item.

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
  "values":  [ { "ecp_code": "2129.1000043", "obx_sub_id": "2131", "value_code": "…",
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
3. **Answers are shredded in SQL.** `_value_ids` in `src/python/sdc_cdm/intake/load.py` shreds
   the JSON with `json_each` (SQLite) / `OPENJSON` (SQL Server) into `naaccr.naaccr_value` in one
   statement per envelope; `_report_id` writes the envelope's `sdc.sdc_report` row. Python drives
   both, and the dialect difference is confined to those two functions.

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

- `precision` ∈ `year` | `month` | `day` | `hour` | `minute` | `second`. Components below the stated precision are
  `null`, never zero and never absent.
- `hour` and `minute` precision retain the known time components and leave
  later components null. `second` precision adds all of `"hh"`, `"mi"`, and
  `"ss"`. An optional `"tz"` offset uses `±HH:MM`. HL7
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
| `envelope_json`, `envelope_version` | legacy nullable columns; new ingestion writes ordered `intake.inbound_envelope` rows |
| `parser_name`, `parser_version` | **which parser and which version produced this envelope** — the forensic key when a parse bug is found later and you need to identify exactly which stored messages are affected, and the discriminator for envelopes submitted by out-of-tree parsers |
| `parse_status`, `parse_error` | `parsed` / `failed` / `quarantined` |

`intake.inbound_message_diagnostic` — one row per warning, FK to the message. This replaces the
`Console.WriteLine` warnings at `ImportNaaccrVolV.cs:541` (non-integer item number) and `:571`
(repeated OBX-4 component), which are currently unrecoverable after the run.

`intake.inbound_envelope` has one row per OBR, with a one-based ordinal unique
within the parent inbound message, the canonical JSON, and envelope version.
One raw byte stream is stored once per receipt even when it contains several
OBRs. `contracts/SERIALIZATION.md` defines the episode-key precedence for the
loader; source episode identity is optional in the envelope.

`naaccr.naaccr_value` and `sdc.sdc_report` each carry `inbound_envelope_id`, a logical reference
with no cross-schema FK (the same pattern as `naaccr_value.sdc_report_id`). The full provenance walk
becomes: `omop.measurement` → `omop.note` → `sdc.sdc_report` → `intake.inbound_envelope` →
`intake.inbound_message.raw_blob`. `intake.envelope_load` and `intake.envelope_value` are the load
ledger: they record which envelope produced which report and values, with the `episode_key`,
`dd_version_id`, and load time, and they make a repeated load a no-op.
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
the original, and **`intake load` skips it** — no `naaccr_value` or `sdc_report` rows are written
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
| `dict fetch` | SEER\*API `/rest/naaccr/*` → the item, allowed-code, registry-requirement, and shared version CSVs under `out-egs/`. | Python stdlib HTTP + CSV |
| `dict load` | Dictionary CSVs → `naaccr_item` and its two children; SEER staging CSVs → `staging_schema`, `schema_item`, codes, requirements, and lookup tables. Item definitions load first so every `schema_item` resolves. | Python batched inserts, one transaction |
| `dict verify` | Counts-only checks for the declared dictionary version and section distribution. | Python, offline SQL counts |
| `maps build` | layered concept-map build | set-based SQL, Python-driven |
| `intake ingest`, `intake load` | HL7 → `intake` (blob + envelope), then `intake` → `naaccr` + `sdc` | **Python parser**, then Python-driven SQL inline in `intake/load.py` |
| `reports supersede` | move report-version selection to a named successor (4.0) | Python, `reports/versions.py` |
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

**Toolchain × dialect support matrix:** publish this in the README and keep it honest.

**Phase 0 amendment (2026-08-06):** the Python manifest builder now supports both target
dialects. The surviving C# SDC importer uses its trimmed SQLite store only; it has no SQL Server
implementation.

| | SQLite | SQL Server |
|---|---|---|
| Python CLI (`sdc_cdm`) | full | full |
| C# (`SdcCdm.Sdc`) | SDC XML import only | not supported |

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
| `python-sqlite` | pytest: golden-envelope conformance, full pipeline, export round-trip | pull requests + pushes to `main` |
| `csharp-sdc` | `dotnet test`: SDC XML import only — `ImportXmlForm` / `ImportTemplate` and the template/form-answer contract. Note the current `SdcImporterTests.cs` is misnamed: its headline test is HL7, and that one moves to pytest. | pull requests + pushes to `main` |
| `python-sqlserver` | same pytest suite, `mcr.microsoft.com/mssql/server` service container | matching pull requests + pushes to `main` |

`contracts/golden/*.envelope.json` remains blocking, now as a **parser regression gate** rather than
a parity oracle. The SQL Server path filter removes the container cost from unrelated reviews.

### Repo layout

```
contracts/
  envelope.schema.json                    the shared contract
  golden/                                 golden envelopes per fixture (parser regression oracle)
database/
  manifest.json                           canonical file order, read by the Python driver;
                                          Phase 4 adds ordered "bridge" and "validate" entries
  schemas/{intake,naaccr,sdc,omop,etl}/ddl/{sqlite,sqlserver}/
  schemas/omop/VENDORED.md                upstream OHDSI commit + re-vendor procedure;
                                          records that the vendored PostgreSQL CDM files
                                          are present but omitted from manifest.json
  etl/{sqlite,sqlserver}/1_person_and_period.sql      (Phase 4.1)
                         2_note.sql                   (Phase 4.2)
                         3_measurement_observation.sql (Phase 4.3)
                         4_condition_and_episode.sql  (Phase 4.4)
                         9_validate.sql               (Phase 4.5)
  seed/concept_constants.csv               tracked (vocabulary_id, concept_code) pairs
      concept_map_overrides.csv            curated layer-2 map
      naaccr_item_exclusions.csv           items excluded from mapping
      cdm_source.csv                       (Phase 4.1)
      validate_thresholds.csv              (Phase 4.5)
src/csharp/{SdcCdm.Sdc,SdcCdm.Sdc.Tests}/  SDC XML import only — no CLI, no pipeline projects
src/python/sdc_cdm/{envelope,hl7v2,intake,maps,cli,db,naaccr,vocab,export}/ + tests/
expectations/naaccr-25.json                counts and section-label acceptance anchor
sample_data/test-fixtures/naaccr-dict/     raw API excerpt + derived CSV fixture
sample_data/test-fixtures/ssdi/             synthetic staging API + 12 derived CSV fixtures
notebooks/                                 recreated from scratch (see below)
sample_data/                               single source of fixtures
docs/{REBUILD_PLAN,SCHEMA_ARCHITECTURE,ROADMAP,TEST_PLAN}.md
```

`database/` holds DDL, seeds, and (from Phase 4) bridge and validation scripts only. The per-dialect statements
for `maps build` and `intake load` live inline in `src/python/sdc_cdm/maps/build.py` and
`src/python/sdc_cdm/intake/load.py`, next to the Python that parameterizes them; there is no
`database/maps/` or `database/load/` directory.

The Python CLI exposes the full verb set above. The C# project is a library plus tests for SDC XML
import; it has no CLI and no pipeline verbs.

**Deleted outright:** `phenoml-workflows/` (deleted in Phase 0; its mapper is historical reference
at `cc6e446^`, its review role replaced by the tracked overrides CSV), the legacy NAACCR spreadsheet converter and
its input workbooks (after the one-time seed conversion), the whole PostgreSQL dialect
(`database/etl/postgresql/`,
`database/schemas/{naaccr,sdc}/ddl/postgresql/`, `database/Dockerfile`,
`database/docker-compose.yml`, `database/.env.example` — see "PostgreSQL is removed, not deferred"
above), the CCR JSON path (`tools/ccr_labreport_to_naaccr.py` + `tools/tests/test_obx_parser.py`,
removed before Phase 3 after ownership moved to the private project), the FHIR code
(`SdcCdm/ExportFhirCpds.cs`, `SdcCdm/FHIR/`,
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

One value per item per dictionary version remains on `naaccr_item.section`. The source is SEER\*API:
`/rest/naaccr/versions` discovers versions, `/rest/naaccr/{version}` returns a thin index, and one
`/rest/naaccr/{version}/{id-or-item}` request returns each full DTO. Retired index entries omit `id`
and are fetched by item number. The complete fetch is therefore N+1 detail work, bounded at eight
concurrent requests and restored to numeric item order before CSV output.

The DTO directly supplies `section`, `data_type`, length, XML identifiers, record types, alternate
names, source of standard, free-text allowable values, descriptive fields, implementation and
retirement versions, and source timestamps. `record_types` and `alternate_names` remain compact JSON
arrays. Structured `allowed_codes` fan out by zero-based array ordinal so repeated codes survive;
the four `*_collect` values fan out as source text rather than Boolean flags. No `short_label` column
or section override file is needed.

**Version anchor.** NAACCR 25 has 946 items: 780 non-retired items with `xml_id` and `section`, and
166 retired items without either. Its 17 populated sections are: Stage/Prognostic Factors 355,
Demographic 71, Treatment-1st Course 71, Edit Overrides/Conversion History/System Admin 68,
Follow-up/Recurrence/Death 34, Pathology 30, Treatment-Subsequent & Other 30, Hospital-Specific 29,
Cancer Identification 23, Patient-Confidential 22, Other-Confidential 11, Text-Diagnosis 9, Record
ID 8, Text-Treatment 7, Hospital-Confidential 6, Special Use 4, and Text-Miscellaneous 2. The same
anchor has 3,900 allowed-code rows and 3,122 registry-requirement rows.

**Honest nulls.** Six non-retired v25 items omit `item_data_type`, so the acceptance rule does not
require that field. `padding`, `alignment`, and `trim` remain NULL because no NAACCR-published source
supplies them; they existed only in the fixed-column layouts retired after v18.

#### Axis B — site-specific staging schema

No change of shape. `naaccr.schema_item` (with its `item_role` input/output split) →
`naaccr.staging_schema` stays the SSDI-sourced many-to-many, which is the right model: one item
number legitimately belongs to many site schemas, so this can never be a column on `naaccr_item`.
Python `ssdi fetch` produces the SSDI CSVs; Python `dict load` is the only loader.

The rebuild's contribution is making it actually *load* and *resolve*: the SSDI export
(`ssdi_version.csv`) and the item-definition seed (`data_dictionary_version.csv`) each carry a
generation stamp that `dict load` requires to agree, and `dict load` asserts zero orphan
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
tracked importer today (`ImportNaaccrVolV.cs:537-614` never passes either; `ISdcCdm.cs:215`
defaults them). The retired private CCR path also wrote `None` literally when it was tracked here.

- **`dd_version_id` becomes non-null in practice.** `intake load` resolves it from the
  `is_current` row for the `--algorithm` it is given. This is a *load-time*
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

`sdc-cdm maps build` runs Python-controlled SQL inside one transaction. Every
eligible item and allowed value first receives a `NAACCR_LOCAL` source concept.
The target and reported layer are selected in this order:

1. **Athena standard.** Follow valid `Maps to` relationships from Athena `NAACCR`
   concepts to standard targets. Decimal item codes are matched. `item@code` is
   provisional for values until measured in a real NAACCR-containing bundle.
2. **Curated overrides** from `database/seed/concept_map_overrides.csv`, upserted over layer 1 only
   where explicitly marked as an override. This is where reviewed human decisions land.
3. **Local mint** is the reported layer when no target exists. The standard target
   is zero while the local source remains nonzero. IDs are allocated from
   2,100,000,000 through 2,147,483,647 and recorded in
   `naaccr.local_concept_allocation`. Classes derive from section and parent XML
   element. Full allowed value codes stay in the ledger; their OMOP concept codes
   use a bounded deterministic digest.

`naaccr.concept_map_coverage` view emits items total / mapped per layer / unmapped, so coverage is
a number CI can assert on and regressions are visible. Break it down **by section** as well as by
layer: "396 `Stage/Prognostic Factors` items, N mapped" is an actionable number for the working
group, where a single global percentage is not. This is what makes the Athena-coverage risk below
measurable rather than rhetorical. `naaccr.value_code_collision` (#100) lists `(item_num, code)`
pairs whose meaning differs across staging schemas; the key stays `(item_num, code)` in Phase 2,
and `maps coverage` (#119) reports these rows.

#### The two-slot contract

Before Phase 2.3 (#120), the bridge wrote **the same value** into both concept slots —
`measurement_concept_id` got `COALESCE(ncm.concept_id, 0)` and `measurement_source_concept_id` got
`ncm.concept_id`, differing only by the `COALESCE`. That was only correct when the mapped concept
happened to be standard. #120 fixed the current bridge; Phase 4 carries the contract into every new
script.

The maps therefore carry both IDs explicitly, and the ETL uses them in the right slots:

| OMOP column | Value | Source |
|---|---|---|
| `*_source_concept_id` | the NAACCR **source** concept | `naaccr_concept_map.source_concept_id` |
| `*_concept_id` | the **standard** concept | `naaccr_concept_map.concept_id`, resolved through `concept_relationship` `'Maps to'` at map-build time |
| `*_source_value` | the full CAP code or verified NAACCR item number | `ecp_code` or `item_num` |

The same contract applies to `value_as_concept_id` vs the value map's source concept, and to
`condition_concept_id` / `condition_source_concept_id`.

The two-slot contract covers **clinical target and source slots only**. It is not a rule that every
`*_concept_id` column holds a standard concept. OMOP defines each slot separately — see the
[CDM 5.4 field definitions](https://ohdsi.github.io/CommonDataModel/cdm54.html#episode) — and
Phase 4 checks each column against its own contract:

| Slot kind | Examples | Contract |
|---|---|---|
| Standard target | `measurement_concept_id`, `observation_concept_id`, `condition_concept_id`, `value_as_concept_id`, `episode_concept_id`, `episode_object_concept_id` | a standard concept in the domain OMOP specifies, or `0` / NULL where OMOP allows it |
| Source concept | `*_source_concept_id`, `episode_source_concept_id` | the NAACCR source concept; may be non-standard, including `NAACCR_LOCAL` |
| Type, field, and resolved constants | `*_type_concept_id`, `*_event_field_concept_id`, `episode_event_field_concept_id`, `gender_concept_id` | the vocabulary OMOP names for that field (Type Concept, CDM field, Gender), resolved through `etl.concept_constant` |

Episode constants resolve from Athena vocabularies that both dialects load. They **must not**
depend on the SQL-Server-only `NAACCR2026` supplement, which is optional and excluded from the
manifest.

**Unmapped policy and its DQD consequence.** Items that reach layer 3 get a real (local, non-standard)
concept in `*_source_concept_id` and — having no standard target — `0` in `*_concept_id`. Items
flagged not mappable stay `0` in both. This is the deliberate trade: DQD will report unmapped-concept
counts rather than silently accepting local IDs in standard slots, which is the correct failure mode.
`concept_map_coverage` makes the number explicit rather than something a reviewer discovers.

#### Fate of the SQL Server minting script

`2_naaccr_omop_vocab_sqlserver.sql` is **kept as a SQL-Server-only supplement**, not retired and not
ported. It continues to seed its `NAACCR2026` vocabulary, `omop.concept`, and
`omop.source_to_concept_map`. Since Phase 2.0 (#117) it no longer creates or writes either map
table — those are owned by manifest DDL (`2_naaccr_concept_maps_sqlserver.sql`) and populated by
`maps build` — and it re-derives its item and value concepts from `omop.concept` on each run.

The consequence must be stated plainly in `SCHEMA_ARCHITECTURE.md` rather than discovered later:
**Local concept identity depends on each database's allocation history.** Both
dialects use `NAACCR_LOCAL` as the map source. The SQL Server-only `NAACCR2026`
supplement remains independent of these map tables. Therefore:

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
`omop_concept_id`, `target_domain_id`, `rationale`, `reviewer`,
`reviewed_at`.

**One-time conversion completed.** Phase 2.1 converted the 780-row legacy mapping inventory into
two tracked seeds:

- `database/seed/concept_map_overrides.csv`: 706 non-excluded skeleton rows with
  `omop_concept_id` blank, so every imported row remained inactive pending review.
- `database/seed/naaccr_item_exclusions.csv`: the 74 items explicitly flagged
  `is_mappable: false`.

The old JSON inventory, its converter and test, and the input workbooks were then deleted.

The retired input had a field-name trap: `concept_id` held a NAACCR **item number**
(e.g. `442` / `ambiguousTerminologyDx`), while `domain_id` held an invented value (`DIGITS`,
`TEXT`) rather than an OMOP domain. The conversion mapped the former to `item_num` and dropped the
latter.

**Local-source gating.** Mint a local concept for every current non-retired item
and distinct allowed value, **except** items in `naaccr_item_exclusions.csv`.
The retired input left
`is_mappable` null for 478 of 780 rows, so the active build must use the exclusions seed rather
than that historical flag.

### OMOP breadth, domain-routed (Phase 4)

Phase 4 replaces the monolithic `1_naaccr_sdc_to_omop.sql` with a Python-run sequence of ordered
scripts. Phase 3 established intake identity (`intake.patient`) and source-row provenance
(`inbound_envelope_id` on every report and value). Phase 4 owns everything downstream: report
version selection, `omop.person`, and the provenance walk from an OMOP row back to raw bytes.

**Historical reference, not a specification.** `phenoml-workflows/` was deleted in Phase 0. Its
mapper made episode-grain and domain-routing choices that are worth reading once:

```bash
git show cc6e446^:phenoml-workflows/phenoml_workflows/mapper.py
```

Treat it as prior work. Where it disagrees with this section, this section wins.

#### Public mapping boundary

CKey-to-NAACCR mapping (CAP eCC/eCP question codes to NAACCR items) belongs **outside this
project**. This repository adds no proprietary crosswalk, mapping seeds, mapping fixtures, or future
public mapping work for it. The bridge accepts verified NAACCR `item_num` values supplied by
external preprocessing. It retains unmapped `ecp_code` values as source identifiers and never
interprets their numeric prefixes. Unmapped CKey input is a supported case and is counted
explicitly, not treated as an error.

#### Report history and selection

A **report group** is `(intake patient, sending facility, report accession)`. Within a group,
`report_loinc` distinguishes **report types** (narrative versus synoptic, per the parser's LOINC
sets). Complementary report types combine across messages: a narrative OBR sent in one message and
a synoptic OBR sent in another belong to the same group.

- **Versions are retained.** A changed report is a new version of its type. Its `sdc_report` and
  `naaccr_value` rows stay loaded. Version relationships are recorded in `naaccr` and reference the
  existing `sdc_report`, `inbound_envelope`, and raw-message rows. Source rows are never deleted.
- **Initial selection is the first version of each type.** A newer receipt alone never authorizes
  replacement.
- **Explicit supersession.** One operation accepts a predecessor and successor `sdc_report_id`. It
  rejects cross-group or cross-type pairs, cycles, and a second successor for the same predecessor.
  In the same transaction, it refreshes the affected group's bridge-owned OMOP rows. Source history
  and unrelated OMOP rows are preserved.
- **Identical-byte resends** keep Phase 3 behavior: they are stored and flagged, but they are not
  loaded and cannot create versions.
- **Accession-less reports** stay excluded from the bridge, as they are today. `validate` reports
  them explicitly rather than dropping them silently.
- **Note provenance lives in `sdc`.** Each note has links to every contributing report. OMOP's
  schema is unchanged. The existing `is_duplicate_accession` / `first_seen_report_id` columns remain
  as intake provenance. Selection no longer depends on them. Phase 4.0 backfills version rows for
  already-loaded reports.

#### Mapping and data quality

- **#100 stays open.** When a coded value appears in `naaccr.value_code_collision`, its meaning
  differs across staging schemas. The bridge suppresses its coded target. The source value is kept
  in `value_source_value` and the source-concept slot. `validate` reports the affected rows. The
  absence of staging data does not prove that a mapping is unambiguous.
- **Mapping correctness is proven with synthetic NAACCR input.** Coded, numeric, and text fixtures
  carry verified `item_num` values. Real Athena NAACCR coverage remains unmeasured (#119) and is not
  a Phase 4 gate.
- **Required data fails loudly.** If a required birth year or clinical date cannot be derived, the
  bridge fails and rolls back every derived change from that run. The failure names the offending
  rows. Partial-date precision is preserved. The bridge never substitutes today's date, which is
  what the current bridge's `DATE('now')` fallback does.
- **Units: `unit_source_value` only.** `unit_concept_id` stays NULL, and no UCUM table is built.

#### Scripts

Occurrence-aware idempotency is preserved in every script. The current bridge's `ROW_NUMBER()`
plus correlated `COUNT(*)` pattern is the model: an unchanged rerun adds no rows, and legitimate
repeated identical answers survive.

0. **Report versions** (4.0) — Add the `naaccr` version-relationship DDL, backfill it from loaded
   reports, and add the supersession operation. No OMOP writes.
1. **`1_person_and_period.sql`** (4.1) — Map `omop.person` 1:1 from `intake.patient`, with gender
   resolved through `etl.concept_constant`. Write `observation_period` and `cdm_source` from
   `database/seed/cdm_source.csv`. **`observation_period` source order:** NAACCR date of diagnosis
   to date of last contact when present, otherwise the MIN/MAX span of the person's clinical dates.
   Record the derivation per row and count one-day periods in `validate`. Do not pad periods.
2. **`2_note.sql`** (4.2) — Write one note per report group from the selected reports. It is
   anchored to the selected synoptic report and uses the selected narrative text when present. Every
   contributing report has a link in `sdc`. A complementary report that arrives later refreshes the
   group's note and links.
3. **`3_measurement_observation.sql`** (4.3) — Route on the target concept's `domain_id`:
   `Measurement` rows go to `measurement` and `Observation` rows go to `observation`. Unmapped rows
   follow a documented default. Type values as follows: coded values use `value_as_concept_id`
   (with #100 suppression), numeric values use `value_as_number` plus `unit_source_value`, and text
   uses `observation.value_as_string`. Source and target slots follow the slot table above.
   Supersession replaces the affected derived rows.
4. **`4_condition_and_episode.sql`** (4.4) —
   - **`condition_occurrence`, thin version:** one row per selected report group, from the
     **primary-site item alone**. Use `condition_concept_id = 0` when there is no standard target,
     and put the NAACCR source concept in `condition_source_concept_id`. There is no histology
     combination logic. ICD-O-3 combination concepts are roadmap work.
   - **`episode` / `episode_event`:** group episodes by tumor/accession within a patient, never by
     accession alone. `episode_event` connects the selected measurements, observations, and
     condition. Episode type and event-field concepts resolve through `etl.concept_constant` from
     Athena. They do not come from the `NAACCR2026` supplement.
5. **`9_validate.sql`** (4.5) — This generalizes
   `database/etl/sqlserver/validate_naaccr_sdc_to_omop.sql` for both dialects. It checks for orphan
   foreign keys and event links, checks each concept slot against its contract, and traces every
   bridge-owned row to an `inbound_message`. It reconciles selected, historical, excluded, and
   unmapped inputs; counts one-day periods and #100 suppressions; and checks unmapped counts against
   `database/seed/validate_thresholds.csv`. Structural and provenance errors must be zero. Expected
   unmapped coverage is tracked separately, so an accepted mapping limitation cannot hide a
   structural failure.

After 4.5 reaches equivalent regression coverage, the old `1_naaccr_sdc_to_omop.sql` and
`validate_naaccr_sdc_to_omop.sql` are retired.

`omop` stays vanilla. No crosswalk table exists. OMOP-side back-references remain
`note_source_value`, `measurement_event_id`, and `*_source_value`; the rest of the provenance walk
runs through `sdc` and `intake`.

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

`python -m sdc_cdm bridge --dialect <d> --db <target>` is the only bridge runner. The former C#
path and the hand-driven `sqlite3` path are both gone. Phase 4.1 adds the runner; later children
add their scripts to it.

- **Ordering.** `database/manifest.json` gains ordered `bridge` and `validate` entries per dialect.
  The runner executes those entries, never a directory glob. `test_manifest.py` asserts that every
  `database/etl/<dialect>/*.sql` file is listed or explicitly excluded.
- **Preconditions.** Before opening a write transaction, the runner verifies the required seeds
  (`cdm_source.csv`, and from 4.5 `validate_thresholds.csv`), the resolved `etl.concept_constant`
  rows, and a built concept map. A missing prerequisite exits non-zero and names the absent item.
- **Transactions.** Python owns one transaction per run. Any script failure rolls back every derived
  change from that run. The supersession operation runs its refresh in its own single transaction.
- **Run log.** Each run writes an `etl.run` row (command, dialect, status, timestamps,
  `error_message`) and prints per-script row counts. The run row is written outside the data
  transaction, so a failed run keeps its `failed` status and error text after the rollback.
- **Validation.** `python -m sdc_cdm validate` runs the validation entries, reports each check with
  PASS/FAIL, and exits non-zero on any structural or provenance error or a threshold breach.

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

These are cheap now and expensive later. The descriptions record the pre-rebuild problem. Several
have since landed: OBX classification by identifier, ledger-based build idempotency, the
`response_string` rename, the `SdcImporterTests.cs` split, the `ImportCsv.cs` deletion,
`FindTemplateItem`, and CI. MSH-21 is stored as `message_profile` but is not yet validated. The
SQL Server `naaccr_value.dd_version_id` FK and OMOP re-vendoring remain open.

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

Each phase lands as squash-merged pull requests to `main`, one per child issue, and closes one
parent GitHub issue. Acceptance criteria are what the phase must demonstrate before its last child
PR merges, not aspirations.

**Phase 0 — skeleton and contracts. Complete (#90).** Repo layout, `contracts/envelope.schema.json`,
`intake` + `etl` DDL, `database/manifest.json`, migration ledger, CI. Phase 0 ran on the
pre-transition branch because it built the CI there was nothing yet to gate against.
*Accepted:* `build` runs twice against the same database with no error and no duplicate objects;
the Python driver builds SQLite from the manifest, and the SQL Server job does the same for
matching changes; the three CI jobs are green on pull requests and pushes to `main`; **no pytest
run requires .NET and no `dotnet test` requires Python**; the end-to-end no-double-count test is
tracked; `test_no_postgres.py` verifies that removed-dialect text occurs only in the four vendored
OHDSI files, `VENDORED.md`, this plan, and the manifest entries that declare those files excluded.

**Phase 1 — vocabulary and constants. Complete (#91).** Athena loader promoted out of `tools/`;
`etl.concept_constant` resolver; SEER dictionary loader for **both** dialects.
*Accepted:* every constant resolves from a loaded Athena bundle; deleting one required concept
makes `constants resolve` exit non-zero with the missing `(vocabulary_id, concept_code)` named; the
NAACCR dictionary loads into SQLite from the same 3NF CSVs SQL Server uses, with matching row counts;
`naaccr.naaccr_item` seeds with non-null `xml_id` **and** non-null `section` for 100% of non-retired
items at the declared version anchor, and `SELECT section, COUNT(*) … GROUP BY 1` returns the 17
expected sections; every `schema_item.item_num` resolves to a `naaccr_item` row with zero orphans.

**Phase 2 — concept maps. Complete (#92).** Layered build, coverage view, one-time seed conversion
from the mapping spec, then delete the spec/workbooks/converter.
*Accepted:* every map row has a `mapping_layer` and a `source_concept_id`; synthetic Athena
fixtures prove layer-1 `Maps to` resolution, layer-2 override precedence (including an explicit
zero target), exclusions, and stable layer-3 mints across rebuilds (`MAPS-01..10`); the current
bridge puts source and standard concepts in separate slots (#120).
*Deferred, unverified (#119):* real Athena NAACCR coverage. The available extract lacks `NAACCR`,
so a nonzero layer-1 count on a real bundle has not been measured and is not a gate for any later
phase. Standard-slot validation of OMOP rows moved to Phase 4, where the rows are written.

**Phase 3 — intake. Complete (#93).** Blob + envelope + `intake.patient` + the Python HL7 parser +
`intake load` + golden-envelope conformance.
*Accepted:* the parser reproduces every `contracts/golden/*.envelope.json` byte-identically under
the serialization profile, and `serialize(parse(serialize(x)))` is a fixed point; a `1957`-only
birth date yields `precision: "year"` with `m`/`d` null in the envelope and `intake.patient`; an
unparseable date yields `null` plus a diagnostic rather than today's date; every loaded
`naaccr_value` and `sdc_report` row walks through `inbound_envelope_id` to a `raw_blob` containing
its originating OBX bytes; a re-sent identical message is stored, flagged, and loads no new rows;
the same PID-3 under two assigning authorities yields two `intake.patient` rows; a malformed
message lands a `parse_status = 'failed'` row; every `naaccr_value` row carries a non-null
`dd_version_id`; `schema_id_number` resolves when complete selection inputs are present and is
NULL plus a diagnostic otherwise; the retired C# 19-value contract passes in pytest with the
corrected CAP identifiers in `contracts/expected/`.
*Moved to Phase 4:* `omop.person` creation (including `year_of_birth` from a partial birth date)
and the provenance walk from an OMOP row to raw bytes. Phase 3 established intake identity and
source-row provenance. Phase 4 owns both OMOP-side criteria.

**Phase 4 — bridge broadening (#94).** Report versions and selection, the Python runner,
person/period/`cdm_source`, combined notes with provenance, domain-routed measurements and
observations, thin condition + episode, and validation — see "OMOP breadth, domain-routed" and
"Python bridge runner". #94 is the parent tracker. Its children land sequentially, each as its own
PR to `main` with its tests and documentation changes:

| Child | Work and acceptance |
|---|---|
| **4.0** (#141) Report versions and selection | NAACCR version relationships and explicit supersession; backfill loaded reports without deleting source rows. Tests: first-version selection, cross-group/cross-type, cycle, and conflicting-successor rejections. |
| **4.1** (#142) Runner, person, period, source | `bridge` orchestration and ordered manifest entries; `person`, `observation_period`, `cdm_source`; required constants and seeds resolved before writes. Tests: rollback on script failure; missing birth year or clinical date fails with no derived rows; partial birth dates keep precision. |
| **4.2** (#143) Combined notes and provenance | Combine selected narrative/synoptic reports across messages, anchor notes to the synoptic report, link every contributing report in `sdc`, and handle late-arriving complementary reports. |
| **4.3** (#144) Measurements and observations | Domain routing, value typing, source/target slots, #100 suppression, occurrence-preserving idempotency, and replacement of affected derived rows after supersession. |
| **4.4** (#145) Conditions and episodes | Thin primary-site conditions; patient-qualified episode grouping; `episode_event` links to selected measurements, observations, and conditions. |
| **4.5** (#146) Validation and final acceptance | `validate` verb, both dialects' validation SQL, `validate_thresholds.csv`; reconcile selected, historical, excluded, and unmapped inputs; retire the old bridge after equivalent regression coverage passes. |

*Accept when* (#94 closes only after every child merges and these pass on SQLite and SQL Server):

- **Boundary.** The importer writes zero `omop` rows; `omop.person` count equals `intake.patient`
  count, and a year-only birth date yields `year_of_birth` with null month and day.
- **Grouping and history.** Equivalent cases pass on both dialects for cross-message grouping, late
  narrative arrival, retained versions, explicit replacement, and exact raw-byte provenance from
  every bridge-owned OMOP row.
- **Source edge cases.** Identical resends, repeated identical answers, accession reuse across
  patients and facilities, and accession-less exclusions behave as specified and are reported.
- **Failure.** Missing required birth years or clinical dates roll back every derived change, and
  the failure names what was missing.
- **Mapping.** Synthetic coded, numeric, and text inputs produce `value_as_concept_id`,
  `value_as_number` + `unit_source_value` (with `unit_concept_id` NULL), and
  `observation.value_as_string`; ambiguous (#100) coded targets are suppressed with source values
  kept and rows reported; non-standard source concepts are preserved; standard-target slots pass
  their contract; unmapped CKey input is retained and counted.
- **Idempotency and replacement.** An unchanged rerun adds no rows; replacement leaves no obsolete
  bridge-owned clinical rows or orphan event links.
- **Validation.** `validate` reports zero structural and provenance errors, and unmapped coverage
  is within `validate_thresholds.csv`, tracked separately from structural checks.

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

`TEST_PLAN.md` is updated in the same phase that invalidates it — a phase whose test IDs are not
retargeted is not done. Rows below name the affected checks rather than counting IDs. "Retire" means
delete the ID with a one-line note saying why.

| Phase | Retire | Retarget | Add |
|---|---|---|---|
| **0** skeleton | `SCHEMA-05` (C# `BuildSchema()` ↔ raw-DDL drift check — there is no C# schema builder any more) | `TEST_PLAN.md:20` bridge glob → `{sqlite,sqlserver}`; `SCHEMA-02` DDL parity → two dialects; `SCHEMA-04` → whatever survives of `update-ddl-files.py`; `CLEAN-03` → the three-job topology; `CLEAN-02` shared golden files → `contracts/golden/`, Python-only | manifest ordering is the single apply order; `build` twice is a no-op (the `CREATE INDEX` regression); migration-ledger skip works |
| **1** vocab + dict | `VocabImporterTests.cs` — deleted with `ImportCsv.cs`, not ported; the Python loader tests cover the active contract | `SCHEMA-03` (bridge concept literals exist) → `constants resolve` fails loudly on a missing `(vocabulary_id, concept_code)`; `SCHEMA-01` / `SCHEMA-02` cover both active dialects and documented storage normalization | `DICT-01..15`: `section` non-null for 100% of non-retired items at the anchor and the 17 expected values; zero orphan `schema_item.item_num`; API/CSV behavior; retry and auth; idempotent load and rollback; dictionary row counts match across dialects |
| **2** concept maps | `PY-04` (the one-time converter test was retired after its conversion code was deleted) | the concept-map checks at the layered build | `MAPS-01..10`: layered resolution, overrides, exclusions, stable mints, coverage by layer **and by section**. Real Athena coverage deferred (#119); standard-slot checks moved to Phase 4 |
| **3** intake | `PY-01`/`PY-02` after their assertions move to the active parser; `PY-03` is already retired because the private project owns the former CCR path | `IMP-HL7-01..09` from the C# importer to the Python parser; `CLEAN-01` fixture dedup now that `sample_data/` is the single source | `INT-01..07`: golden conformance and fixed point; partial dates; source-row provenance to `raw_blob`; duplicate bytes; two authorities → two patients; failed parse; staging-schema resolution |
| **4** bridge | `OMOP-01` and the old-bridge references in `OMOP-09`, once 4.5 retires `1_naaccr_sdc_to_omop.sql` | `OMOP-02..12` at the child that owns each; `NAACCR-05`/`NAACCR-06` at `validate`. FHIR and CCDA checks (`NAACCR-02`, `NAACCR-04`, the FHIR half of `OMOP-08`) stay outside Phase 4; `NAACCR-03` is out of scope under the public mapping boundary | `BRIDGE-01..12`: version selection and supersession; runner; person/period/`cdm_source`; required-data rollback; cross-message grouping and late arrival; domain routing; #100 suppression; unmapped CKey; replacement; condition and episode; validation reconciliation. All run on both dialects |
| **5** export | — | **move `EXP-01`–`EXP-04` to roadmap, do not retarget them** — all four are FHIR round-trips against `ExportFhirCpds`, not CSV-bundle tests; see below | a fresh set of CSV-export IDs: export → fresh-schema round-trip equality; manifest row counts and sha256; PHI grep returns zero; header order matches the shared CDM 5.4 `TABLE_SPECS` |
| **6** docs | — | the 12 `SDCOM` IDs at the C# SDC Object Model refactor; mark `IMP-FHIR` (12), `IMP-NXML` (2), `IMP-CCDA` (1) as roadmap-blocked rather than merely unchecked | notebooks execute top-to-bottom; no doc statement contradicts the code |

Phase 3's structural changes to `TEST_PLAN.md` are done: §1.1's heading no longer names a C# type,
`PY-01` and `PY-02` are retired to the Python tests that now carry their assertions, and the Phase 3
additions above are checked as `INT-01..07` in §1.1a, each naming its test functions.

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
| **Athena NAACCR coverage is worse than assumed.** Nobody has measured it. | Layer 3 dominates, most concepts are local, the export is far less interoperable than the design implies. | Still unmeasured: the available extract lacks `NAACCR` (#119). Phase 4 proves mapping correctness with synthetic inputs and reports unmapped coverage separately from structural checks, so a thin layer 1 is visible as a number. A bundle-holder measures real coverage later; thin layer 1 is a finding for the working group, not something to paper over with mints. |
| **The envelope contract ossifies too early.** v1 is designed around HL7 v2 alone. | A breaking `envelope_version` bump with stored envelopes to migrate, or per-format hacks. | `envelope_version` is in the schema from day one and stored per row. Sketch the NAACCR XML mapping onto v1 during Phase 3 design as a cheap falsification test. |
| **JSON shredding in SQL is the weakest link.** `json_each` / `OPENJSON` are where the two dialects genuinely diverge. | The two dialect branches of the loader drift apart, invisible until a SQL Server run produces different rows. | Divergence is confined to `_report_id` and `_value_ids` in `intake/load.py`; the path-filtered `python-sqlserver` job runs the same load and provenance assertions, so drift fails a test. Shredding in Python, or Jinja-templating one source into two, are the fallbacks. |
| **A single implementation is a single point of failure.** No C# pipeline, no hand-driven SQL path. | If a stage breaks there is no second way to run the pipeline. | Accepted cost of deleting the duplication. Every stage stays separately invocable and idempotent, so a failed stage can be re-run in isolation. |
| **Concept identity differs by dialect** (accepted, not a defect). | A SQL Server export and a SQLite export of the same message are not concept-comparable. | Documented in `SCHEMA_ARCHITECTURE.md`, recorded per row in `mapping_layer`, carried in export `manifest.json`, excluded from test assertions. |
| **Seven phases is a lot of runway.** Phases 3–5 depend on 0–2 landing. | Stalling mid-rebuild leaves two half-migrated layouts. | Each child issue lands on `main` as it completes, so a stall leaves trunk holding every completed phase. Phases 1–2 alone fix the `concept_id = 0` problem. Do not start Phase 3 until 0–2 are on `main`. |
| **Dropping PostgreSQL strands a deployment.** Assumes the container was dev convenience, not a target. | Someone deploying on Postgres cannot follow the rebuild. | Confirmed with the working group before Phase 0. If it becomes a real target, fund it properly (manifest entry, CI job, `intake`/`etl` DDL). |
| **SEER\*API dictionary refresh requires an authorized key and N+1 detail requests.** | A revoked key or API change can block a refresh. | Keep fetch separate from build/load, retain deterministic gitignored CSVs for local use, commit a raw 12-item fixture for offline CI, retry transient failures, and require an owned key-rotation policy before scheduling refreshes. |
| **`4_condition_and_episode.sql` is thinly specified.** Thin condition + episode grouping is a deliberate scope cut. | The episode grain (one per patient-qualified tumor/accession group) may not survive multi-tumor reports. | Keep it in its own script so it can be replaced without touching measurement routing. Revisit with the ICD-O-3 roadmap work. |

---

## Verification

Each stage is independently runnable, so verification is per-phase rather than one big-bang test.
The pipeline must be verifiable **with .NET not installed**, and the SDC XML suite must pass with
Python not installed.

**Full pipeline — one path:**

```bash
python -m sdc_cdm build --dialect sqlite --db out/demo.db
python -m sdc_cdm vocab load --dialect sqlite --db out/demo.db \
  --vocab-dir database/vocab
python -m sdc_cdm dict fetch --dialect sqlite --version 25 \
  --csv-dir .context/naaccr-25
python -m sdc_cdm dict load --dialect sqlite --db out/demo.db \
  --csv-dir .context/naaccr-25
python -m sdc_cdm dict verify --dialect sqlite --db out/demo.db \
  --expect expectations/naaccr-25.json
python -m sdc_cdm constants resolve --dialect sqlite --db out/demo.db
python -m sdc_cdm maps build --dialect sqlite --db out/demo.db
python -m sdc_cdm maps coverage --dialect sqlite --db out/demo.db \
  --expect expectations/concept-maps-naaccr-25.json
python -m sdc_cdm intake ingest --dialect sqlite --db out/demo.db sample_data/naaccr_v2/*.hl7
python -m sdc_cdm intake load --dialect sqlite --db out/demo.db --algorithm eod_public 1 2 3
python -m sdc_cdm bridge --dialect sqlite --db out/demo.db
python -m sdc_cdm validate --dialect sqlite --db out/demo.db
python -m sdc_cdm export out/omop-csv/

# SDC XML import is the one C# surface, and it is a library + tests, not a CLI
dotnet test src/csharp/SdcCdm.Sdc.Tests
```

**Assertions:**

- **Envelope conformance.** The parser reproduces `contracts/golden/*.envelope.json` byte-for-byte
  under the serialization profile, and `serialize(parse(serialize(x)))` is a fixed point. Blocking.
- **Dialect behaviour parity.** The same pytest suite passes against SQLite and, for matching CI
  changes, against SQL Server — asserting equal *behaviour*, never equal concept IDs.
- **Partial dates.** A `1957`-only birth date survives as `year` precision into
  `omop.person.year_of_birth` with null month/day; an unparseable date becomes `null` plus a
  diagnostic, never today's date.
- **Provenance round-trip.** Pick any bridge-owned OMOP row, walk
  `→ note → sdc note-report links → sdc_report → intake.inbound_envelope → inbound_message`, and
  assert the originating OBX substring is present in `raw_blob`. Phase 3 proves the
  `sdc_report`/`naaccr_value` → `raw_blob` half; Phase 4 proves the OMOP half.
- **Concept coverage.** `SELECT * FROM naaccr.concept_map_coverage` — record a baseline per layer;
  CI fails on regression. Unmapped OMOP rows are counted against `validate_thresholds.csv`,
  separately from structural checks. The real-bundle Athena baseline is deferred (#119).
- **Constants.** Deliberately drop a required concept from the vocabulary and confirm
  `constants resolve` fails loudly rather than the bridge writing a wrong ID.
- **Idempotency.** Every stage run twice leaves row counts unchanged (including `build`, whose
  second run is a ledger no-op). Repeated identical answers survive as distinct occurrences.
- **Export round-trip.** Export → load into a fresh empty OMOP schema → row-for-row equal. Plus:
  grep the entire export bundle for a known PHI string from the raw message and assert zero hits.
- **Domain routing.** A fixture with one coded, one numeric, and one text answer produces a
  `measurement` with `value_as_concept_id`, a `measurement` with `value_as_number` +
  `unit_source_value` (and `unit_concept_id` null, by design), and an `observation` with
  `value_as_string` respectively.
- **Person identity.** `omop.person` count equals `intake.patient` count; the same PID-3 under two
  different assigning authorities yields two patients, not one.
- **Report history.** Narrative and synoptic reports sent in separate messages combine into one
  note, including when the narrative arrives after the first bridge run. A changed report is
  retained, but the first version stays selected until an explicit supersession. That
  supersession replaces the group's bridge-owned rows and leaves no obsolete rows or orphan event
  links. The same accession under another patient or facility is a separate group.
- **Required data.** A missing birth year or clinical date fails the bridge and rolls back every
  derived change from the run.
- **Existing coverage retained, in the new language.** `SdcImporterTests.cs@c29d01dc6a042b13217bbb511864b98aa714aee5:41-154` asserts 19
  `naaccr_value` rows → 19 `omop.measurement` rows with both OBX-4 grouped shapes (CAP code
  `2129.1000043` code+number, CAP code `820404.1000043` code+text). Phase 3 ported
  its count and grouping assertions to pytest at the `naaccr_value` level; Phase 4 extends them to
  OMOP rows, with the corrected identifier shape: full CAP codes
  in `ecp_code` and NULL `item_num`. The retired C# snapshots remain historical evidence; the
  corrected expected identifiers are in `contracts/expected/obx-Adrenal.identifiers.json`.
