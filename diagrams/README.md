# Diagrams

Mermaid `erDiagram` sources for the data model. `.mmd` source only — no rendered images are
committed. GitHub renders `.mmd` files natively; you can also paste one into
[mermaid.live](https://mermaid.live).

## `three-schema/`: current project model

Matches the design in [../database/SCHEMA_ARCHITECTURE.md](../database/SCHEMA_ARCHITECTURE.md).
The directory name predates the `intake` and `etl` schemas and is retained to avoid breaking links.

| File | Covers |
| --- | --- |
| [`three-schema-overview.mmd`](three-schema/three-schema-overview.mmd) | Orientation map across all five schemas. Key tables only; start here. |
| [`naaccr.mmd`](three-schema/naaccr.mmd) | All 15 `naaccr` tables: versioned dictionary, staging catalog, concept maps, captured values. |
| [`sdc.mmd`](three-schema/sdc.mmd) | All 9 `sdc` tables: form design, template instances, `sdc_report`, `sdc_form_answer`. |
| [`naaccr-sdc-to-omop-bridge.mmd`](three-schema/naaccr-sdc-to-omop-bridge.mmd) | The `naaccr` + `sdc` → stock OMOP transform: what it reads, what it writes, and the guards. |

## `original-omop/` — upstream reference

Stock, unmodified OMOP CDM v5.4 (37 tables), as a full ERD plus five by-domain views.
**Do not edit these** — they document upstream OHDSI, not this project. The `omop` schema is
deliberately vanilla, so these stay accurate as-is.

## Conventions

- **Line style carries meaning.** Solid (`||--o{`) is an enforced foreign key. **Dotted
  (`||..o{`) is a logical pointer or key join with no enforced FK.** Every cross-schema link is
  dotted: this model has no crosswalk table and adds no columns to OMOP core, so those
  relationships exist only as join keys. The concept maps are dotted for a second reason — they
  are version-independent (keyed on `item_num` alone), so they cannot carry a composite FK to the
  version-scoped `naaccr_item`.
- **Entity names are UPPERCASE.** In single-schema diagrams they are bare table names; in
  mixed-schema diagrams they are prefixed with the owning schema (`NAACCR_VALUE`, `SDC_REPORT`,
  `OMOP_NOTE`).
- **PK-only stub entities** appear where a diagram needs to show a link to a table another file
  owns. Attribute types mirror the SQLite DDL (`INTEGER` / `TEXT` / `REAL`).
- Mermaid gotcha: a comment line containing only `%%` is a parse error, and comments must come
  *after* the `erDiagram` line, not before it.

## Keeping these current

**These diagrams are hand-maintained. There is no generator and no CI check** — nothing will
tell you when they drift. Update them in the same commit as the DDL.

Source of truth is the **SQLite** DDL, the only dialect with every table in one file per schema:

- `../database/schemas/etl/ddl/sqlite/1_etl_sqlite_ddl.sql`
- `../database/schemas/intake/ddl/sqlite/1_intake_sqlite_ddl.sql`
- `../database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql`
- `../database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql`
- `../database/schemas/omop/ddl/sqlite/1_OMOPCDM_sqlite_5.4_ddl.sql`
- `../database/etl/sqlite/1_naaccr_sdc_to_omop.sql` (the bridge)

SQL Server and SQLite implement the same logical model. Type and identity syntax differ by dialect.

To check your edits parse before committing (one-off, adds no project dependency):

```bash
for f in diagrams/three-schema/*.mmd; do
  npx -y @mermaid-js/mermaid-cli -i "$f" -o "/tmp/$(basename "$f").svg" || echo "FAIL $f"
done
```
