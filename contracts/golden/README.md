# Frozen importer outputs

These files record what the retired C# HL7 importer produced, so the Python port in Phase 3 (#93)
has an oracle after the C# code is gone. Every value here was read out of
`SdcCdmLib/SdcCdm.Tests/SdcImporterTests.cs` at commit `c29d01dc6a042b13217bbb511864b98aa714aee5`;
`git show` that path to see the original assertions.

## These are database snapshots, not envelopes

Each file describes rows **after** load or bridge, so its field types are the *column* types in
`database/schemas/`. They are not envelope documents and `contracts/SERIALIZATION.md` does not
govern them.

That distinction matters for one field in particular, because the same name means two things:

| Where | Type | Why |
|---|---|---|
| `naaccr.naaccr_value.value_num` — snapshotted here as `10.0` | `REAL` / `FLOAT` | a numeric column; JSON number is the faithful rendering |
| envelope `values[].value_num` — will be `"10"` | JSON string | `SERIALIZATION.md` requires the exact source lexeme, and OBX-5 in the fixture is `10` |

A conforming parser emitting `"10"` and a loader storing `10.0` are both correct. Do not relax
`envelope.schema.json` to match these files.

## Inventory

| File | Fixture | Ported from |
|---|---|---|
| `obx-Adrenal.naaccr_value.json` | `sample_data/naaccr_v2/obx-Adrenal.hl7` | `ImportNaaccrVolV_ExecutesWithoutError` (load half) |
| `obx-Adrenal.measurement.json` | same | `ImportNaaccrVolV_ExecutesWithoutError` (bridge half) |
| `obx-Adrenal.importer_boundary.json` | same | `ImportNaaccrVolV_DoesNotWriteSdcFormTables` |
| `obx-Adrenal.obr_date_fallback.json` | same, OBX-14 stripped | `ImportNaaccrVolV_MissingObxDateFallsBackToObrDate` |
| `24-11-000312-2.sdc_report.json` | `sample_data/naaccr_v2/24-11-000312-2.txt.hl7` | `ImportNaaccrVolV_BlankNarrativeUsesBridgeFallback` |

One deleted test has no golden because it asserted no values:
`ImportAllHL7Files_ExecutesWithoutError` ran the importer over every fixture in
`sample_data/naaccr_v2/` and only required that nothing threw. Phase 3 should reproduce it as a
parametrized smoke test over the same glob rather than as a file here.
