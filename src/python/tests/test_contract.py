from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_envelope_schema_is_strict_and_versioned() -> None:
    schema = json.loads((ROOT / "contracts/envelope.schema.json").read_text())

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["envelope_version"] == {"const": "1"}
    assert schema["properties"]["values"]["items"]["additionalProperties"] is False
    assert schema["properties"]["values"]["items"]["properties"]["value_num"]["type"] == [
        "string",
        "null",
    ]


def _goldens() -> list[Path]:
    return sorted((ROOT / "contracts/golden").glob("*.json"))


def test_every_frozen_contract_names_its_source_commit_and_fixture() -> None:
    goldens = _goldens()
    assert len(goldens) == 5

    for path in goldens:
        source = json.loads(path.read_text())["source"]
        assert source["commit"] == "c29d01dc6a042b13217bbb511864b98aa714aee5"
        assert (ROOT / source["fixture"]).is_file()
        # These record database rows, not envelopes; SERIALIZATION.md does not
        # govern them. See contracts/golden/README.md.
        assert "database snapshot" in source["kind"]


def test_the_deleted_csharp_hl7_assertions_all_have_a_golden() -> None:
    """Every value assertion in the retired C# HL7 tests survives as a file.

    The C# HL7 importer was deleted before the Python port exists, so these files
    are the only oracle Phase 3 has. `git show
    c29d01dc6a042b13217bbb511864b98aa714aee5:SdcCdmLib/SdcCdm.Tests/SdcImporterTests.cs`
    is the original.
    """

    assert {path.name for path in _goldens()} == {
        "24-11-000312-2.sdc_report.json",
        "obx-Adrenal.importer_boundary.json",
        "obx-Adrenal.measurement.json",
        "obx-Adrenal.naaccr_value.json",
        "obx-Adrenal.obr_date_fallback.json",
    }


def test_the_envelope_and_the_snapshots_disagree_about_value_num_on_purpose() -> None:
    schema = json.loads((ROOT / "contracts/envelope.schema.json").read_text())
    snapshot = json.loads(
        (ROOT / "contracts/golden/obx-Adrenal.naaccr_value.json").read_text()
    )

    # The envelope carries the source lexeme as a string; naaccr_value.value_num is
    # a REAL column. Same name, different contracts - do not reconcile them.
    assert schema["properties"]["values"]["items"]["properties"]["value_num"]["type"] == [
        "string",
        "null",
    ]
    item_2129 = next(
        row for row in snapshot["load"]["naaccr_value"]["rows"] if row["item_num"] == 2129
    )
    assert isinstance(item_2129["value_num"], float)
    assert "value_num_note" in snapshot["source"]
