# Future work: SEER\*API reference tables (deferred)

These SEER\*API / NAACCR resources describe data that SEER *constructs* but that our NAACCR Schema
does not yet represent. They are reference / lookup databases and algorithms — distinct from the
staging dictionary that `database/schemas/naaccr/` currently projects — so they are **deferred** to
avoid conflating them with the "project the SEER Staging API" design.

Each would become one or more read-only reference tables in the `naaccr` schema (or a new
`reference` schema), version-stamped via the `data_dictionary_version` dimension introduced for
gaps 1–5 (see `database/SCHEMA_ARCHITECTURE.md`).

## Candidate sources

| Source | SEER / NAACCR API | Proposed table(s) | Notes |
|---|---|---|---|
| **Full NAACCR Data Dictionary catalog** | `apps.naaccr.org/data-dictionary/api` | `naaccr_dd_item(dd_version_id, item_num, xml_id, name, data_type, length, section, source, allowable_values…)` | Superset of `naaccr_item` (every item, not just staging items). Also the source that fully populates the gap #2b field-metadata columns (`data_type`, `length`, `padding`, …). |
| **SEER Site Recode** (SEER, ICCC, AYA) | `/rest/recode` | `site_recode(scheme, dd_version_id, site, histology, behavior, recode, recode_label)` | Three analytic grouping schemes. Could alternatively be modeled as an OMOP concept hierarchy rather than a NAACCR reference table. |
| **Multiple Primary / Histology (MPH)** | `/rest/mph` | `mph_ruleset(site_group, dd_version_id, rule_id, …)` + rule tables | An *algorithm*, not just data; persisting the ruleset enables same-primary determination without live API calls. |
| **Disease DB** (hematopoietic + solid tumor) | `/rest/disease` | `disease(id, name, icdo3_morphology, behavior, reportability, obsolete, same_primaries…)` | Large; solid-tumor data is still preview at SEER. |
| **SEER\*Rx / NDC / HCPCS** | `/rest/rx`, `/rest/ndc`, `/rest/hcpcs` | `drug`, `regimen`, `ndc_code`, `hcpcs_code` | Oncology drug/regimen coding; ties naturally to the OMOP DRUG domain. |
| **Glossary** | `/rest/glossary` | `glossary_term(term, definition, category, dd_version_id)` | Terminology; overlaps the existing `schema_item.coding_guidelines`. |

## Cross-cutting design notes

- Every reference table should carry a `dd_version_id` (FK to `naaccr.data_dictionary_version`) and
  a `source_api` column so its provenance and version are explicit.
- Loading: extend `tools/ssdi-ts` with one fetcher per endpoint plus loader coverage, mirroring the
  existing staging-dictionary export/load flow.
- Suggested sequencing: **NAACCR DD catalog first** (it also unblocks full field-metadata
  enrichment for gap #2b), then site recodes, then the remaining sources as demand arises.

> Scope note: these were explicitly deferred out of the gaps 1–5 work (version dimension, field
> metadata, staging tables, staging outputs, SSDI reconciliation). See the accompanying plan and
> `database/SCHEMA_ARCHITECTURE.md`.
