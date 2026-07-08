# SDC-CDM Test Plan

Tracking issue: [#82 — Create ETL Tests](https://github.com/IHE-SDC-WG/SDC-CDM/issues/82)

This is a TDD-style catalog of the tests this repo should have. Each test has an ID so it
can be referenced from PRs and checked off as it is implemented. Status legend:
`[x]` implemented, `[ ]` not yet written, `(blocked)` waiting on a feature that doesn't exist yet.

## Architecture under test

Data flows through three attached schemas (see `database/SCHEMA_ARCHITECTURE.md`):

```
HL7v2 / FHIR / SDC XML / CCDA / NAACCR XML          (Import layer)
        │
        ├─► naaccr.naaccr_value                     ("To NAACCR": raw captured answers)
        └─► sdc.sdc_report, sdc.sdc_form_answer,
            sdc.template_*                          (SDC structure — reference tables)
        │
        ▼  database/etl/{sqlite,sqlserver,postgresql}/1_naaccr_sdc_to_omop.sql
   omop.note + omop.measurement / omop.observation  ("To OMOP": vanilla CDM 5.4)
```

"To NAACCR" tests therefore assert on `naaccr.*` + `sdc.*` after an import; "To OMOP"
tests assert on `omop.*` after running the bridge ETL. The `sdc` tables are structural
reference — they carry question/report context, never answer values.

## Proposed folder layout

```
SdcCdmLib/SdcCdm.Tests/
  Import/
    Hl7v2/           IMP-HL7-*
    Fhir/            IMP-FHIR-*
    SdcXml/          IMP-SDC-*
    NaaccrXml/       IMP-NXML-*   (blocked: no importer yet)
    Ccda/            IMP-CCDA-*   (blocked: no importer yet)
  EtlToNaaccr/       NAACCR-*
  EtlToOmop/         OMOP-*
  Export/            EXP-*
  Schema/            SCHEMA-*
tools/tests/         PY-* (Python ports + pure-SQL tests, pytest)
sample_data/         single source of truth for fixtures (see Cleanup)
```

## Conventions

- Every test builds a fresh throwaway SQLite database (`SdcCdmInSqlite(name, overwrite: true)`
  + `BuildSchema()`); no test depends on another test's database.
- Fixtures live in `sample_data/` only. `SdcCdm.Tests/TestData/` is deleted and the test
  csproj links files out of `sample_data/` instead (see Cleanup below).
- Import tests must assert on **row contents**, not just "ran without throwing" — the
  existing smoke tests (`SdcImporterTests`) are the floor, not the bar.
- Each ETL test that mutates state gets a matching **idempotency** test (run twice,
  same row counts).

---

## 1. Import tests

### 1.1 HL7v2 (NAACCR Vol V) — `SdcCdm.Hl7v2.Importers.ImportNaaccrVolV`

Fixtures: `sample_data/naaccr_v2/24-11-000312-2.txt.hl7`, `obx-Adrenal.hl7`

- [x] **IMP-HL7-01** Import completes without error on a valid Vol V message (exists as smoke test).
- [ ] **IMP-HL7-02** PID segment creates exactly one `person` with correct source values
  (MRN, birth date, gender mapping).
- [ ] **IMP-HL7-03** OBR creates one `sdc.sdc_report` with the OBR accession as
  `report_accession` and report LOINC `60568-3`.
- [ ] **IMP-HL7-04** Each answered OBX yields one `naaccr.naaccr_value` row with the right
  `item_num`, `value_code`/`value_num`, and `report_accession`; count matches the OBX
  count in the fixture.
- [ ] **IMP-HL7-05** Each OBX also yields one `sdc.sdc_form_answer` with question text /
  section context, and no answer value stored on the SDC side.
- [ ] **IMP-HL7-06** Re-importing the same message flags the report
  (`is_duplicate_accession = 1`, `first_seen_report_id` points at the original) instead of
  silently duplicating or erroring.
- [ ] **IMP-HL7-07** *(regression, review finding #5)* An OBX-3 question identifier that is
  not a plain integer prefix (e.g. a LOINC code) is either imported or rejected **with a
  logged warning** — it must not be silently skipped after the `sdc_form_answer` row was
  already written, leaving an answer without a value.
- [ ] **IMP-HL7-08** Malformed message (missing MSH / truncated segment) throws or returns
  an error; the database is left without a half-written report.
- [ ] **IMP-HL7-09** Units on numeric OBX values land in `value_unit_source`.

### 1.2 HL7 FHIR (CPDS bundles) — `SdcCdm.FHIR.Importers.ImportFhir`

Fixtures: `sample_data/fhir/Bundle-CPDSBundleA.json`, `Bundle-CPDSBundleB.json`

- [ ] **IMP-FHIR-01** Import of a CPDS bundle completes and creates one `sdc.sdc_report`
  per DiagnosticReport/Composition.
- [ ] **IMP-FHIR-02** Patient resource maps to one `person` (no duplicate person on
  re-import of a bundle referencing the same patient).
- [ ] **IMP-FHIR-03** Each Observation in the bundle produces an answer row with the correct
  question identifier and value (coded → code, quantity → number + unit, string → text).
- [ ] **IMP-FHIR-04** Observation `hasMember`/section grouping is preserved as SDC
  section/parent context in `sdc_form_answer`.
- [ ] **IMP-FHIR-05** A bundle with an unsupported resource type is skipped gracefully with
  a warning, not a crash.
- [ ] **IMP-FHIR-06** Invalid JSON / non-Bundle input produces a clear error and no writes.

### 1.3 SDC XML form submissions — `XmlFormImporter.ProcessXmlForm`

Fixtures: `sample_data/sdc_xml/ADRENAL_GLAND.xml`, templates in `sample_data/sdc_templates/`

- [x] **IMP-SDC-01** Import completes without error on a valid submission package (exists as smoke test).
- [ ] **IMP-SDC-02** Template metadata (name, version, instance GUID) lands in
  `sdc.sdc_report` / `sdc.template_*`.
- [ ] **IMP-SDC-03** Every answered question in the XML produces a `sdc_form_answer` **and**
  its value is retrievable (see EXP-01 round trip). *(regression, review finding #1 — the
  current `WriteSdcObsClass` shim drops `response`, `units`, and `response_*`.)*
- [ ] **IMP-SDC-04** Unanswered questions do not produce value rows.
- [ ] **IMP-SDC-05** Importing a template FDF (`ImportTemplate`) then a matching submission
  links the instance to the template.
- [ ] **IMP-SDC-06** Re-import of the same submission package is detected (duplicate
  instance GUID) rather than duplicated.

### 1.4 NAACCR XML — *(blocked: importer not implemented)*

- [ ] **IMP-NXML-01** Import a NAACCR XML file; same assertions as IMP-HL7-02..05 for the
  XML representation.
- [ ] **IMP-NXML-02** Items map through `naaccr.naaccr_item` xml_id, not item_num, where
  applicable.

### 1.5 CCDA — *(blocked: importer not implemented)*

- [ ] **IMP-CCDA-01** Import a CCDA document; patient + report + answers assertions
  mirroring 1.1/1.2. Needs a fixture in `sample_data/ccda/`.

---

## 2. ETL "To NAACCR" tests — `EtlToNaaccr/`

These verify that **every import source converges to the same canonical NAACCR + SDC
shape**, so the OMOP bridge only has to be tested once.

- [ ] **NAACCR-01** *(from HL7v2)* Importing `obx-Adrenal.hl7` yields the expected
  `naaccr_value` rows — golden-file comparison of `(item_num, value_code, value_num,
  value_unit_source)` ordered by item_num.
- [ ] **NAACCR-02** *(from FHIR)* Importing the CPDS bundle for the same case yields
  equivalent `naaccr_value` rows to NAACCR-01 where items overlap.
- [ ] **NAACCR-03** *(from SDC XML)* Importing `ADRENAL_GLAND.xml` yields answers joinable
  to the NAACCR dictionary via the `item_num.suffix` question-identifier convention
  (e.g. `2129.1000043`).
- [ ] **NAACCR-04** *(from CCDA — blocked)* Same golden comparison once the importer exists.
- [ ] **NAACCR-05** Dictionary integrity: every `naaccr_value.item_num` written by any
  importer exists in `naaccr.naaccr_item` (or is explicitly reported as unmapped).
- [ ] **NAACCR-06** Concept-map coverage: every item/value pair used by the fixtures has a
  row in `naaccr_concept_map` / `naaccr_value_concept_map`, or appears in an "unmapped"
  report — so bridge output never silently maps to concept 0 for known items.

---

## 3. ETL "To OMOP" tests — `EtlToOmop/`

Target: `database/etl/sqlite/1_naaccr_sdc_to_omop.sql` (and the SQL Server /
PostgreSQL ports). Seed via an importer or direct inserts, run the bridge, assert on `omop.*`.

- [x] **OMOP-01** Three-schema layout + minimal bridge smoke test
  (`tools/tests/test_three_schema_sqlite.py`): OMOP tables carry **no** `sdc_*` columns;
  a seeded report/answer produces a note + measurement.
- [ ] **OMOP-02** One `omop.note` per `sdc_report`, with `note_source_value` =
  `report_accession` and the report narrative as note text.
- [ ] **OMOP-03** One `omop.measurement`/`observation` per answered item, with
  `*_source_value` = the item code, mapped `*_concept_id` from `naaccr_concept_map`,
  and `*_event_id` pointing at the note (event field concept `1147289` for
  measurement→note anchoring).
- [ ] **OMOP-04** Value typing: coded answers → `value_as_concept_id` (via
  `naaccr_value_concept_map`), numeric → `value_as_number` + `unit_source_value`,
  text → `value_as_string` (observation) — one test per shape.
- [ ] **OMOP-05** *(regression, review finding #2a)* Duplicate-accession reports
  (`is_duplicate_accession = 1`) do **not** fan out: measurement count equals distinct
  answer count, not N×M across re-imported reports sharing an accession.
- [ ] **OMOP-06** *(regression, review finding #2b)* Idempotency: running the bridge ETL
  twice leaves row counts unchanged in `note`, `measurement`, and `observation`.
- [ ] **OMOP-07** Back-reference join from `SCHEMA_ARCHITECTURE.md` works: from an OMOP
  measurement you can recover the SDC question text and NAACCR item name via
  note → sdc_report → sdc_form_answer → naaccr_item, with no stored cross-schema FK.
- [ ] **OMOP-08** End-to-end: HL7v2 fixture → import → bridge → expected OMOP rows
  (golden-file comparison). Repeat from the FHIR fixture and assert equivalence.
- [ ] **OMOP-09** *(regression, review finding #3)* The SQL Server bridge ETL only
  references objects the SQL Server DDLs actually create — a dry parse/execution against a
  schema built from `database/schemas/*/ddl/sqlserver/` succeeds (`naaccr_concept_map`
  and `naaccr_value_concept_map` must exist there).
- [ ] **OMOP-10** *(regression, review finding #4)* The validation script
  (`validate_naaccr_sdc_to_omop.sql`) passes against a database produced by the shipped
  ETL — its type-concept filters and expected tables (`episode`/`episode_event`) must
  match what the ETL actually writes.
- [ ] **OMOP-11** Person linkage: measurements/notes carry the `person_id` created at
  import; no orphan rows referencing missing persons (FK check with constraints applied).

---

## 4. Export / round-trip tests — `Export/`

- [ ] **EXP-01** *(regression, review finding #1)* Full round trip: import an SDC XML
  submission, export via `ExportFhirCpds`, and assert every answered question reappears
  in the FHIR output **with its value** (currently `GetSdcObsClasses` returns
  `NULL AS response`, so exported Observations are empty).
- [ ] **EXP-02** Round trip preserves units and numeric precision.
- [ ] **EXP-03** Exported bundle validates against the CPDS profile (or minimally: is
  parseable by the Firely SDK and every Observation has status/code/subject).
- [ ] **EXP-04** FHIR → import → export → compare against the original bundle for the
  supported subset (lossless where the model supports it, documented losses elsewhere).

---

## 5. Schema / DDL tests — `Schema/` and `tools/tests/`

- [x] **SCHEMA-01** SQLite three-schema attach builds all DDLs and OMOP stays vanilla
  (`test_three_schema_sqlite.py`).
- [ ] **SCHEMA-02** DDL parity: the set of tables/columns in the sqlite, postgresql, and
  sqlserver DDLs for `naaccr` and `sdc` schemas is identical (name-normalized diff).
- [ ] **SCHEMA-03** Essential concept seeding: every `concept_id` literal referenced by the
  bridge ETLs exists in the seeded `omop.concept` rows.
- [ ] **SCHEMA-04** `update-ddl-files.py` output is committed: regenerating produces no diff
  (guards against hand-edited generated DDL).
- [ ] **SCHEMA-05** C# `SdcCdmInSqlite.BuildSchema()` and the raw DDL files produce the same
  schema (embedded-resource drift check).

---

## 6. Python port parity — `tools/tests/`

The Python ports must not drift from the C# importers.

- [ ] **PY-01** Python HL7v2 importer produces the same `naaccr_value` golden file as
  IMP-HL7 fixtures (shared expected-output files under `sample_data/expected/`).
- [ ] **PY-02** *(regression, review finding #5)* Python port handles non-integer OBX-3
  identifiers the same way the C# fix does.
- [x] **PY-03** OBX parser unit tests (`test_obx_parser.py`).
- [x] **PY-04** NAACCR→OMOP map conversion tests (`test_convert_naaccr_omop_maps.py`).

---

## Cleanup (from issue #82)

- [ ] **CLEAN-01** Deduplicate fixtures: `SdcCdmLib/SdcCdm.Tests/TestData/` duplicates
  `sample_data/` (`ADRENAL_GLAND.xml` exists in both). Keep `sample_data/` as the single
  source of truth; the test csproj should `<Content Include="../../sample_data/**">` (or
  link specific files) instead of carrying copies. Move `SDC_Form.xml`,
  `NAACCR_VolV.hl7`, and the IPS bundle into `sample_data/` first.
- [ ] **CLEAN-02** Add `sample_data/expected/` for golden files shared by C# and Python
  tests, so both stacks assert against the same expected outputs.
- [ ] **CLEAN-03** Wire both test stacks into CI (`dotnet test` + `pytest tools/tests`) so
  this plan is enforced, not aspirational.

## Suggested implementation order

1. **EXP-01, OMOP-05, OMOP-06** — they encode the currently-known bugs (answer values
   dropped; bridge fan-out and non-idempotency), so they fail today and pin the fixes.
2. **IMP-HL7-02..07** — content-level assertions for the most mature importer.
3. **OMOP-02..04, OMOP-08** — the bridge contract.
4. **CLEAN-01/02** alongside, so new tests are written against `sample_data/` from day one.
5. FHIR and SDC XML content tests, then schema-parity tests, then blocked items
   (NAACCR XML, CCDA) as those importers land.
