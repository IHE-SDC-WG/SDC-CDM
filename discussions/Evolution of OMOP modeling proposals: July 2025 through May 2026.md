# Evolution of OMOP modeling proposals: July 2025 through May 2026

## Summary

The working group's thinking about how to represent SDC-derived and NAACCR-derived content in OMOP evolved significantly between July 2025 and May 2026.

### High-level evolution

- **Early July 2025:** The group was still clarifying the distinction between the **Measurement** and **Observation** tables and whether an SDC-specific observations table should be renamed to align with OMOP semantics.
- **Late July 2025:** A strong interim position emerged that most **SDC-derived content should enter OMOP Observation**, with **Measurement** reserved mainly for standardized laboratory test cases.
- **Early August 2025:** The direction shifted toward placing more SDC data into **Measurement** so that standard OMOP users could query the data more easily without learning custom SDC tables.
- **August–September 2025:** A clearer separation appeared:
  - **Observation** was often treated as the **report / OBR / diagnostic report instance**
  - **Measurement** was treated as the **individual data items** within the report, including question/answer pairs and sections
  - **Template instance** became an important shared anchor for provenance and grouping
- **Late 2025 into 2026:** The architecture became more formalized:
  - **Episode** became the explicit **case boundary** for cancer-case modeling
  - **Measurement** was used for analyzable pathology-like facts such as SSDIs, grade, staging, and other constrained-value clinical items
  - Not everything was forced into OMOP core tables; some content remained in **NAACCR/SDC extension tables**

## Discussion timeline

### July 9, 2025 — distinction between Measurement and Observation begins to sharpen
In the July 9 discussion, the group explicitly noted a distinction between **measurement** and **observations**, and discussed whether the SDC observations table should be renamed for OMOP compatibility. This appears to be one of the first points where the semantics of the two tables were being actively sorted out.

### July 23, 2025 — unresolved decision point
By July 23, the group still had not finalized whether data should go into **Observation** or **Measurement**, and flagged that decision as necessary in order to simplify downstream queries.

### July 30, 2025 — Observation-first proposal
A strong proposal emerged that:
- all **SDC-derived content** should enter the OMOP **Observation** table
- the **Measurement** table should be used only for standardized laboratory test cases
- direct foreign-key relationships were preferred over OMOP's `fact_relationship` table for clarity and performance

This was a key interim design point, but it did not remain the long-term direction.

### August 6, 2025 — shift toward Measurement for broader OMOP usability
In early August, the team pivoted toward putting more SDC-related data into **Measurement**. The rationale was that this would allow “vanilla OMOP” users to query the data without learning additional SDC-specific structures.

At this point the group also discussed:
- adding **SDC-specific columns** to the OMOP Measurement table
- introducing an **SDC Template table** for report-level metadata

This discussion marks a major transition in the modeling direction.

### August 13–20, 2025 — linkage between cases, reports, and measurements becomes clearer
By mid to late August, the group was refining how the detailed data should connect to report-level and case-level structures.

Key ideas included:
- **Episode** as the preferred representation of a **cancer case**
- **Observation** representing the **diagnostic report instance**
- **Measurement** representing the **individual findings/items** within that report
- linkage approaches including:
  - event-link fields such as `meas_event_field_concept_id` and `measurement_event_id`
  - OMOP `fact_relationship`
  - explicit foreign-key style linkage where practical

This period contains some of the clearest discussion of how **Measurement** links to **Observation**.

### August 27 and September 10, 2025 — concrete table pattern emerges
By late August and early September, a more concrete pattern was described:

- **Measurement** = every item that is part of an SDC template, including:
  - question/answer pairs
  - sections
- **Observation** = each **OBR row** / report-level structure present in the message
- both **Measurement** and **Observation** reference a shared **template_instance**
- **Fact-Relationship** could be used to represent containment, i.e. that measurements belong to a report

This is one of the clearest formulations of the model that emerged during 2025.

### September 17, 2025 — reinforcement of Measurement as item-level storage
By mid-September, the group reinforced that the **Measurement** table would include all question/answer pairs and sections, confirming its role as the item-level storage layer for SDC-derived content.

### 2026 — methodology and constraints become explicit
During 2026, the discussion shifted from “which table should we use?” to a more formal methodology.

Key principles that emerged:
- **Episode** is the explicit case boundary
- **Measurement** is appropriate for pathology-like analyzable facts, such as:
  - SSDIs
  - grade
  - staging
  - other constrained-value clinical/pathology items
- demographic fields and registry-management picklists should **not** automatically go into Measurement
- the architecture should avoid forcing all content into OMOP core tables
- **NAACCR/SDC extension tables** remain appropriate for some data, especially where OMOP fit is weak or where preserving source structure matters

By May 2026, the group had largely moved toward a methodology in which:
- SDC/pathology-style facts are more likely to land in **Measurement**
- case organization is handled through **Episode**
- not every concept is forced into core OMOP if an extension model is more appropriate

## How the Measurement table links to other tables

### Measurement ↔ Observation
The most recurring pattern is:
- **Observation** represents the **report / OBR / diagnostic report instance**
- **Measurement** represents the **individual data elements contained in that report**

Proposed linkage mechanisms included:
1. shared reference to **template_instance**
2. OMOP event-link fields such as `meas_event_field_concept_id` and `measurement_event_id`
3. `fact_relationship`

Conceptually, the model became:
- **Observation = report container**
- **Measurement = report contents**

### Measurement ↔ Template Instance / Template Tables
Multiple discussions described SDC-specific tables such as:
- `template_sdc`
- `template_item`
- `template_instance`

In this model, **Measurement** rows are tied to a **template_instance**, making it possible to trace each measurement back to the originating report instance and its template definition.

### Measurement ↔ Episode / Episode Event
As cancer-case modeling matured, **Episode** became the case-level anchor.

That implies another important relationship:
- **Episode** = cancer case / tumor / major clinical episode
- **Observation** and **Measurement** = facts attached to that case
- linkage may occur directly or via **Episode Event** depending on the design pattern used

### Measurement ↔ NAACCR / SDC extension tables
In 2026 the group made explicit that not everything belongs in **Measurement**.

The emerging rule was:
- put analyzable clinical/pathology facts into **Measurement**
- keep registry/admin/specialized or weak-fit content in **extension tables**
- link those extension tables back to OMOP entities, often with **Episode** as the primary grain

## Bottom line

Across these discussions, the proposals evolved from an unresolved **Observation vs. Measurement** debate into a more layered model:

- **Observation** often serves as the **report-level** or **OBR-level** entity
- **Measurement** serves as the **item-level clinical content layer**
- **Template Instance** provides provenance and grouping
- **Episode** provides the case boundary
- **Extension tables** preserve data that does not fit cleanly into OMOP core

The overall trend from July 2025 through May 2026 is toward a pragmatic hybrid model: use **Measurement** for analyzable structured pathology content, use **Observation** and **Template Instance** for grouping/report context, use **Episode** for cancer-case organization, and retain extensions where forcing data into OMOP would reduce clarity or fidelity.
