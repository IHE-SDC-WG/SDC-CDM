# SEER\*API reference tables

The full NAACCR Data Dictionary catalog landed in Phase 1. The remaining SEER\*API resources
describe reference databases and algorithms that the current NAACCR schema does not represent, so
they remain deferred.

Each would become one or more read-only reference tables in the `naaccr` schema (or a new
`reference` schema), version-stamped via the `data_dictionary_version` dimension introduced for
gaps 1–5 (see `database/SCHEMA_ARCHITECTURE.md`).

## Candidate sources

| Source | SEER\*API endpoint | Table(s) / status | Notes |
|---|---|---|---|
| **Full NAACCR Data Dictionary catalog** | `/rest/naaccr/*` | **Landed in Phase 1:** `naaccr_item`, `naaccr_item_allowed_code`, `naaccr_item_registry_requirement` | SEER supplies item details, section, structured codes, registry collection text, and retirement metadata. See [DICTIONARY_LOAD.md](DICTIONARY_LOAD.md). |
| **SEER Site Recode** (SEER, ICCC, AYA) | `/rest/recode` | Proposed `site_recode` tables | Three analytic grouping schemes. Could alternatively be modeled as an OMOP concept hierarchy. |
| **Multiple Primary / Histology (MPH)** | `/rest/mph` | Proposed `mph_ruleset` and rule tables | An algorithm as well as data; persisting it would allow same-primary determination without live API calls. |
| **Disease DB** (hematopoietic + solid tumor) | `/rest/disease` | Proposed `disease` tables | Large; solid-tumor data remains preview at SEER. |
| **SEER\*Rx / NDC / HCPCS** | `/rest/rx`, `/rest/ndc`, `/rest/hcpcs` | Proposed drug, regimen, NDC, and HCPCS tables | Oncology drug and regimen coding; relates naturally to the OMOP DRUG domain. |
| **Surgery** | `/rest/surgery` | To be specified | Available under the same API host but not documented in the current OpenAPI description. |
| **Glossary** | `/rest/glossary` | Proposed `glossary_term` table | Terminology; overlaps `schema_item.coding_guidelines`. |

## Cross-cutting design notes

- Every reference table should carry a `dd_version_id` (FK to `naaccr.data_dictionary_version`) and
  a `source_api` column so its provenance and version are explicit.
- The remaining endpoints use the same SEER host and `X-SEERAPI-Key` as `/rest/naaccr/*`. Future
  loaders should extend the stdlib Python client and retain offline CSV/load tests.
- Suggested sequencing after the landed dictionary: site recodes, then the remaining sources as
  demand arises.

> Scope note: all rows except the NAACCR dictionary remain future work. Their presence here does not
> add tables or supported commands.
