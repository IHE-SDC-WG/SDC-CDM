# SDC-CDM Test Plan

Tracking issue: [#82 — Create ETL Tests](https://github.com/IHE-SDC-WG/SDC-CDM/issues/82)

This is a TDD-style catalog of the tests this repo should have. Each test has an ID so it
can be referenced from PRs and checked off as it is implemented. Status legend:
`[x]` implemented, `[ ]` not currently implemented, `(blocked)` waiting on a missing
feature, `(coverage regression)` previously implemented but removed, and `(retired)` no
longer applicable.

## Architecture under test

Data flows through five logical schemas (see `database/SCHEMA_ARCHITECTURE.md`):

```
HL7v2 / FHIR / SDC XML / CCDA / NAACCR XML          (Import layer)
        │
        ├─► intake.*                                 (source identity + immutable payload)
        ├─► naaccr.naaccr_value                     ("To NAACCR": raw captured answers)
        ├─► sdc.sdc_report                          (eCP report metadata)
        └─► sdc.sdc_form_answer, sdc.template_*     (SDC XML forms and answers)
        │
        ▼  database/etl/{sqlite,sqlserver}/1_naaccr_sdc_to_omop.sql
   omop.note + omop.measurement / omop.observation  ("To OMOP": vanilla CDM 5.4)

etl.schema_migration + etl.run                      (build and run provenance)
```

"To NAACCR" tests therefore assert on `intake.*`, `naaccr.*`, and `sdc.*` after an import;
"To OMOP" tests assert on `omop.*` after running the bridge ETL. The SDC XML form tables
carry their own answer values; eCP answer values remain in `naaccr.naaccr_value`.

## Proposed folder layout

```
src/csharp/SdcCdm.Sdc.Tests/
  Import/
    SdcXml/          IMP-SDC-*
src/python/tests/    MANIFEST-*, BUILD-*, schema and bridge tests
tools/tests/         PY-* (Python ports + direct SQL tests, pytest)
contracts/golden/    frozen importer outputs
sample_data/         single source of truth for fixtures (see Cleanup)
```

## Conventions

- Python database tests build a fresh throwaway SQLite control database through the manifest;
  no test depends on another test's database.
- C# SDC tests use a fresh in-memory `SdcSqliteStore`.
- Fixtures should live in `sample_data/` only. The remaining C# test fixture copy is tracked by
  CLEAN-01 below.
- Import tests must assert on **row contents**, not just "ran without throwing" — the
  focused SDC importer tests are the floor, not the bar.
- Each ETL test that mutates state gets a matching **idempotency** test (run twice,
  same row counts).

---

## 1. Import tests

### 1.1 HL7v2 (NAACCR Vol V) (Python importer planned)

Fixtures: `sample_data/naaccr_v2/24-11-000312-2.txt.hl7`, `obx-Adrenal.hl7`

- [ ] **IMP-HL7-01** Import completes without error on a valid Vol V message.
  *(coverage regression: Phase 0 deleted `SdcImporterTests.cs` and the C# HL7 importer;
  its output is frozen under `contracts/golden/` for the Python port.)*
- [ ] **IMP-HL7-02** PID segment creates exactly one `person` with correct source values
  (MRN, birth date, gender mapping).
- [ ] **IMP-HL7-03** OBR creates one `sdc.sdc_report` with the OBR accession as
  `report_accession` and report LOINC `60568-3`.
- [ ] **IMP-HL7-04** Each logical answer yields one `naaccr.naaccr_value` row with the right
  `item_num`, `obx_sub_id`, `value_code`/`value_num`/`value_text`, `report_accession`, and
  the originating `sdc_report_id`. CWE plus numeric/text OBX components sharing OBX-4 are
  combined. A missing OBR-3 accession is stored as NULL (not `''`).
  *(coverage regression: Phase 0 deleted `SdcImporterTests.cs` and the C# HL7 importer.)*
- [ ] **IMP-HL7-05** The eCP path does not create `sdc.sdc_form_answer`, `template_sdc`, or
  `template_instance` rows; those tables are reserved for SDC XML form intake.
  *(coverage regression: Phase 0 deleted `SdcImporterTests.cs` and the C# HL7 importer.)*
- [ ] **IMP-HL7-06** Re-importing the same message flags the report
  (`is_duplicate_accession = 1`, `first_seen_report_id` points at the original) instead of
  silently duplicating or erroring.
- [ ] **IMP-HL7-07** *(regression, review finding #5)* An OBX-3 question identifier that is
  not a plain integer prefix (e.g. a LOINC code) is either imported or rejected **with a
  logged warning** so an answer is not silently omitted from `naaccr.naaccr_value`.
- [ ] **IMP-HL7-08** Malformed message (missing MSH / truncated segment) throws or returns
  an error; the database is left without a half-written report.
- [ ] **IMP-HL7-09** Units on numeric OBX values land in `value_unit_source`.

### 1.2 HL7 FHIR (CPDS bundles and mCODE) — `SdcCdm.FHIR.Importers.ImportFhir`

Fixtures: `sample_data/fhir/Bundle-CPDSBundleA.json`, `Bundle-CPDSBundleB.json`;
mCODE example bundles (patient + staging + tumor marker) to be added under
`sample_data/fhir/mcode/` from the [mCODE IG](https://hl7.org/fhir/us/mcode/) examples.

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

mCODE IG bundles (profiles the importer should recognize by `meta.profile` and map to the
same canonical NAACCR + SDC shape):

- [ ] **IMP-FHIR-07** Import an mCODE patient bundle: `CancerPatient` maps to one `person`
  and a `PrimaryCancerCondition` Condition produces a report/answer row carrying the
  primary-site and histology codings (ICD-O-3 topography/morphology → the corresponding
  NAACCR items, e.g. 400/522).
- [ ] **IMP-FHIR-08** mCODE staging observations (`TNMStageGroup`,
  `TNMPrimaryTumorCategory`, `TNMRegionalNodesCategory`, `TNMDistantMetastasesCategory`)
  map to the matching NAACCR staging items in `naaccr_value`, preserving clinical vs.
  pathologic distinction from the profile/method.
- [ ] **IMP-FHIR-09** `TumorMarkerTest` observations import as answer rows with coded or
  quantity values typed correctly (mirrors IMP-FHIR-03 for the mCODE profile).
- [ ] **IMP-FHIR-10** mCODE `HumanSpecimen` resources referenced by observations land in
  `sdc.sdc_specimen` / `observation_specimens` with the specimen linkage intact.
- [ ] **IMP-FHIR-11** A bundle mixing mCODE-profiled and unprofiled resources imports the
  recognized profiles and logs (not crashes on) the rest — profile detection is per
  resource, not per bundle.
- [ ] **IMP-FHIR-12** Equivalence: an mCODE bundle and a CPDS bundle describing the same
  case converge to equivalent `naaccr_value` rows where their data elements overlap
  (companion to NAACCR-02).

### 1.3 SDC XML form submissions — `XmlFormImporter.ProcessXmlForm`

Fixtures: `sample_data/sdc_xml/ADRENAL_GLAND.xml`, templates in `sample_data/sdc_templates/`

> The importer hand-parses SDC XML with `XElement` and handles a tested subset of the SDC
> item model. Section 7 proposes a broader differential test against the official IHE SDC
> object model (`SDC.Schema`).

- [x] **IMP-SDC-01** Import completes without error on a valid submission package (exists as smoke test).
- [x] **IMP-SDC-02** Template metadata (name, version, instance GUID) lands in
  `sdc.template_*`.
- [x] **IMP-SDC-03** Every selected list item and every supported typed response in the XML
  produces a `sdc_form_answer`, with its value and units retrievable.
- [x] **IMP-SDC-04** Unanswered direct response children do not produce value rows.
- [x] **IMP-SDC-05** Importing a template FDF (`ImportTemplate`) then a matching submission
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
  `naaccr_value` rows, including grouped code/number and code/text answers, source units,
  OBX-14 dates, and OBX-4 sub-IDs.
  *(coverage regression: Phase 0 deleted `SdcImporterTests.cs` and the C# HL7 importer;
  the expected rows remain frozen under `contracts/golden/`.)*
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

Target: `database/etl/sqlite/1_naaccr_sdc_to_omop.sql` and its SQL Server counterpart. Seed via an
importer or direct inserts, run the bridge, assert on `omop.*`.

- [x] **OMOP-01** Three-schema layout + minimal bridge smoke test
  (`tools/tests/test_three_schema_sqlite.py`): OMOP tables carry **no** `sdc_*` columns;
  a seeded report/raw value produces a note + measurement.
- [ ] **OMOP-02** One `omop.note` per `sdc_report`, with `note_source_value` =
  `report_accession` and the report narrative as note text.
- [ ] **OMOP-03** One `omop.measurement`/`observation` per answered item, with
  `*_source_value` = the item code, mapped `*_concept_id` from `naaccr_concept_map`,
  and `*_event_id` pointing at the note (event field concept `1147289` for
  measurement→note anchoring).
- [ ] **OMOP-04** Value typing: coded answers → `value_as_concept_id` (via
  `naaccr_value_concept_map`), numeric → `value_as_number` + `unit_source_value`,
  text → `value_as_string` (observation) — one test per shape.
- [x] **OMOP-05** *(regression, review finding #2a)* Duplicate-accession reports
  (`is_duplicate_accession = 1`) do **not** fan out: measurement count equals distinct
  answer count, not N×M across re-imported reports sharing an accession.
- [x] **OMOP-06** *(regression, review finding #2b)* Idempotency: running the bridge ETL
  repeatedly leaves row counts unchanged in `note` and `measurement`.
- [x] **OMOP-06a** *(regression, pre-bridge duplicate double-counting)* When the same message is
  imported twice **before** the bridge runs, the re-import's `naaccr_value` rows carry the
  duplicate-flagged report's `sdc_report_id` and do **not** bridge: measurement count equals the
  single-import count, not 2×. Values bridge only via `naaccr_value.sdc_report_id` →
  non-duplicate `sdc_report`.
- [x] **OMOP-06b** *(regression, empty-accession collisions)* Accession-less reports (OBR-3
  stored as NULL, and legacy `''` covered by the ETL's `NULLIF` guard) never bridge: no `''`
  note is created and their values do not fan out across reports.
- [ ] **OMOP-07** Back-reference join from `SCHEMA_ARCHITECTURE.md` works: from an OMOP
  measurement you can recover the report and NAACCR item name via
  note → sdc_report and measurement_source_value → naaccr_item, with no stored cross-schema FK.
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

## 4. Export / round-trip tests (roadmap-blocked)

> The FHIR importer and exporter were removed in Phase 0. These tests stay assigned to
> Phase 5 and cannot run until those paths are rebuilt. EXP-01 previously blamed a
> `GetSdcObsClasses` projection that had already been corrected; the active defect was on
> the response write path, now covered by IMP-SDC-03.

- [ ] **EXP-01** *(roadmap-blocked, review finding #1)* Full round trip: import an SDC XML
  submission, export via `ExportFhirCpds`, and assert every answered question reappears
  in the FHIR output **with its value**.
- [ ] **EXP-02** *(roadmap-blocked)* Round trip preserves units and numeric precision.
- [ ] **EXP-03** *(roadmap-blocked)* Exported bundle validates against the CPDS profile (or minimally: is
  parseable by the Firely SDK and every Observation has status/code/subject).
- [ ] **EXP-04** *(roadmap-blocked)* FHIR → import → export → compare against the original bundle for the
  supported subset (lossless where the model supports it, documented losses elsewhere).

---

## 5. Schema / DDL tests — `Schema/` and `tools/tests/`

- [x] **MANIFEST-01** `database/manifest.json` validates, names every executable DDL file
  exactly once, and applies files in `etl`, `intake`, `omop`, `naaccr`, `sdc` order.
- [x] **BUILD-01** A SQLite build succeeds twice against the same control database; the
  second run creates no duplicate objects.
- [x] **BUILD-02** The migration ledger records applied hashes and the second build reports
  every unchanged file as skipped.
- [x] **SCHEMA-01** SQLite five-schema attach builds all DDLs and OMOP stays vanilla
  (`test_three_schema_sqlite.py`).
- [ ] **SCHEMA-02** DDL parity: the set of tables/columns in the two supported dialects,
  SQLite and SQL Server, is identical after name and type normalization.
- [ ] **SCHEMA-03** Essential concept seeding: every `concept_id` literal referenced by the
  bridge ETLs exists in the seeded `omop.concept` rows.
- (retired) **SCHEMA-04** Phase 0 removed the `update-ddl-files.py` tombstone; there is no
  generated DDL output to compare.
- (retired) **SCHEMA-05** Phase 0 removed the full C# schema builder. The manifest is now
  the only complete database apply order; the surviving C# store builds only its SDC tables.

---

## 6. Python port parity — `tools/tests/`

The Python ports must not drift from the C# importers.

- [ ] **PY-01** Python HL7v2 importer produces the frozen `naaccr_value` output in
  `contracts/golden/`. These contract files are Python-only after Phase 0.
- [ ] **PY-02** *(regression, review finding #5)* Python port handles non-integer OBX-3
  identifiers the same way the C# fix does.
- [x] **PY-03** OBX parser unit tests (`test_obx_parser.py`).
- [x] **PY-04** NAACCR→OMOP map conversion tests (`test_convert_naaccr_omop_maps.py`).

---

## 7. SDC Object Model conformance & differential tests — `SdcObjectModel/`

Library under test as an **oracle**: [`rmoldwin/SDC_ObjectModel`](https://github.com/rmoldwin/SDC_ObjectModel/tree/Features/NET10/Net10Main),
project `SDC.Schema` — the official IHE SDC object model. It deserializes SDC XML into a
typed tree rooted at `FormDesignType : ITopNode`, validates it (`SdcValidate` /
`SdcValidationReport`), navigates/retrieves nodes (`SdcUtil` — `GetSortedSubtreeList`,
node dictionaries, get-by-name/id), and re-serializes / diffs (`TopNodeSerializer`, the
IComparer utilities).

Why this belongs in the plan: `ImportXmlForm.cs` is a hand-rolled `XElement` parser
(namespace `urn:ihe:qrph:sdc:2016`). It traverses nested sections, questions, and selected
list items, and supports string, integer/int, and decimal response children. Other SDC item
and response types remain outside its supported subset. The OM tells us *what a form
actually contains*, so these tests assert the pipeline is **complete against the model**,
not merely that it "ran without throwing." The response persistence defect is now pinned by
IMP-SDC-03; differential tests would extend that check across every fixture.

Fixtures: the existing `sample_data/sdc_xml/*.xml` submissions and
`sample_data/sdc_templates/*` templates; expected sets are **derived from the OM at test
time**, so no new golden files are needed for the core oracle tests (SDCOM-03/04).

- [ ] **SDCOM-01** *(build/dependency setup)* Create a separate optional conformance test
  project under `src/csharp/`, reference `SDC.Schema`, and deserialize one fixture to
  `FormDesignType`. Keep the core `SdcCdm.Sdc` project independent of the oracle package.
- [ ] **SDCOM-02** *(fixture validity)* Every SDC XML fixture (`sdc_xml/` submissions and
  `sdc_templates/` templates) deserializes into the OM and passes `SdcValidate` with zero
  errors. Guards the whole SDC test surface against malformed / hand-edited XML so later
  assertions are trustworthy.
- [ ] **SDCOM-03** *(question inventory oracle → strengthens IMP-SDC-03/04)* Deserialize the
  form with the OM, enumerate its Question/ListItem nodes via `SdcUtil`, and assert the
  importer wrote **exactly one** `sdc_form_answer` per answered question, **none** for
  unanswered ones, and that the `item_num.suffix` question identifiers match the OM-derived
  set. No hand-maintained expected list — the OM is the expected list.
- [ ] **SDCOM-04** *(answer value oracle, review finding #1)* For every answered
  `Response`/selected `ListItem`/`ResponseUnits` the OM exposes, the value that lands in
  `sdc`/`naaccr` equals the OM's value. This extends the import-side IMP-SDC-03 check; FHIR
  re-export remains the roadmap-blocked EXP-01 test.
- [ ] **SDCOM-05** *(multi-select lists)* For a multi-select `ListField`, the OM's count of
  `selected="true"` `ListItem`s equals the number of answer rows; deselected items produce
  zero rows and never leak a value.
- [ ] **SDCOM-06** *(coded list items)* `ListItem` codings surfaced by the OM (coded
  value / code system, not just `title`/`name`) are captured, so coded answers can map to
  NAACCR / OMOP concepts instead of degrading to free text.
- [ ] **SDCOM-07** *(response data types)* `ResponseField` `dataType` coverage: the OM
  distinguishes typed responses (string, integer, decimal, date/dateTime, boolean, …). One
  assertion per dataType a fixture exercises, that it imports with the correct value shape.
  Directly targets the current parser reading only `Response/string@val`. *(some variants
  blocked pending fixtures that exercise them.)*
- [ ] **SDCOM-08** *("other, specify" — `ListItemResponseField`)* A fill-in list item (a
  `ListItem` carrying a `ListItemResponseField`) must persist **both** the selected item and
  the typed-in response — the OM shows both; the importer path
  (`ProcessListField → ProcessResponseField`) must not keep one and drop the other.
- [ ] **SDCOM-09** *(repeating sections / repeated items)* Where the OM reports a repeating
  section or repeated question (multiple instances), the importer produces one answer row
  per instance with distinct section/instance context — not a single collapsed row.
- [ ] **SDCOM-10** *(item types the importer ignores — mirrors IMP-HL7-07 philosophy)*
  Enumerate the OM item types **not** handled by `ProcessChildItems`/`ProcessQuestion`
  (e.g. `DisplayedItem`, injected/lookup lists, blob/attachment responses). Each must be
  either handled or logged as a warning — never silently dropped. *(blocked on fixtures that
  contain these item types.)*
- [ ] **SDCOM-11** *(structural parity)* The section/parent nesting the importer flattens
  into `section_id`/`section_guid`/parent-observation context matches the OM's tree
  parentage from `SdcUtil` navigation for the same nodes — guards the flattened hierarchy
  against the model's actual tree.
- [ ] **SDCOM-12** *(export re-serialization round trip — companion to EXP-03)* If/when the
  pipeline emits SDC XML, that output deserializes and passes `SdcValidate`, and compares
  equal to a canonical serialization via the library's compare utility for the
  supported/documented-loss subset.

> Optionality: `SDC.Schema` is a large dependency. Keep this section in a separate test
> project so the core C# suite remains small; all current C# projects target `net10.0`.

## Cleanup (from issue #82)

- [ ] **CLEAN-01** Deduplicate fixtures: `src/csharp/SdcCdm.Sdc.Tests/TestData/` duplicates
  `sample_data/` (`ADRENAL_GLAND.xml` exists in both). Keep `sample_data/` as the single
  source of truth; the test csproj should link files from `../../../sample_data/` instead of
  carrying copies. Move `SDC_Form.xml`,
  `NAACCR_VolV.hl7`, and the IPS bundle into `sample_data/` first.
- [x] **CLEAN-02** Frozen importer outputs live under `contracts/golden/` for the Python
  conformance tests. The Phase 0 C# suite does not consume shared golden files.
- [x] **CLEAN-03** CI has independent `python-sqlite` and `csharp-sdc` jobs on every push,
  plus a scheduled and manually runnable `python-sqlserver` job.

## Suggested implementation order

1. **IMP-SDC-03, OMOP-05, OMOP-06** cover the import-side answer persistence and the
   bridge fan-out/idempotency regressions. `EXP-01` remains blocked on the Phase 5 FHIR work.
2. **IMP-HL7-02..07** — content-level assertions for the most mature importer.
3. **OMOP-02..04, OMOP-08** — the bridge contract.
4. **CLEAN-01** alongside, so new tests are written against `sample_data/` from day one.
5. FHIR and SDC XML content tests, then schema-parity tests, then blocked items
   (NAACCR XML, CCDA) as those importers land.
6. **SDCOM-01/02** to stand up the optional SDC.Schema oracle, then **SDCOM-03/04**. Once
   wired in, these replace hand-maintained SDC-XML expected sets and provide a
   fixture-agnostic check for IMP-SDC-03.
