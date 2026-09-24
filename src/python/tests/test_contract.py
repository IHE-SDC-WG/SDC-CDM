from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]


def test_node_producer_files_are_fully_retired() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden = [
        path
        for path in tracked
        if (ROOT / path).is_file()
        and (
            path.endswith((".ts", "/package.json", "/package-lock.json"))
            or path in {"package.json", "package-lock.json"}
        )
    ]
    assert forbidden == []
    assert all(
        "node_modules/" not in (ROOT / path).read_text(encoding="utf-8")
        for path in tracked
        if path.endswith(".gitignore") and (ROOT / path).is_file()
    )


def test_envelope_schema_is_strict_and_versioned() -> None:
    schema = json.loads((ROOT / "contracts/envelope.schema.json").read_text())

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["envelope_version"] == {"const": "1"}
    assert schema["properties"]["values"]["items"]["additionalProperties"] is False
    identifiers = schema["properties"]["values"]["items"]
    assert identifiers["oneOf"] == [
        {"required": ["ecp_code"]},
        {"required": ["item_num"]},
    ]
    assert identifiers["properties"]["ecp_code"] == {
        "maxLength": 50,
        "minLength": 1,
        "type": "string",
    }
    assert schema["properties"]["values"]["items"]["properties"]["value_num"]["type"] == [
        "string",
        "null",
    ]


def _goldens() -> list[Path]:
    return sorted(
        path for path in (ROOT / "contracts/golden").glob("*.json")
        if not path.name.endswith(".envelope.json")
    )


def test_two_obr_envelopes_share_one_raw_message_and_validate() -> None:
    schema = json.loads((ROOT / "contracts/envelope.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    paths = sorted((ROOT / "contracts/golden").glob("*.envelope.json"))
    assert [path.name for path in paths] == [
        "two-obr-synthetic.1.envelope.json",
        "two-obr-synthetic.2.envelope.json",
    ]
    envelopes = []
    for path in paths:
        raw = path.read_bytes()
        envelope = json.loads(raw)
        Draft202012Validator(schema).validate(envelope)
        assert raw == (json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        envelopes.append(envelope)
    assert [item["source"]["obr_ordinal"] for item in envelopes] == [1, 2]
    assert len({item["raw"]["sha256"] for item in envelopes}) == 1
    assert [item["report"]["report_loinc"] for item in envelopes] == ["35265-8", "60569-1"]
    assert envelopes[0]["report"]["narrative"] == "Synthetic diagnosis\nsecond line"
    assert envelopes[0]["report"]["observation_date"]["precision"] == "hour"
    assert envelopes[1]["report"]["observation_date"]["precision"] == "minute"
    assert envelopes[1]["values"][0]["value_num"] == "1.20"

    episode = {**envelopes[1], "episode": {"episode_source_value": "SYN-TUMOR-1"}}
    Draft202012Validator(schema).validate(episode)


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


def test_corrected_cap_identifiers_are_separate_from_historical_snapshots() -> None:
    expected = json.loads(
        (ROOT / "contracts/expected/obx-Adrenal.identifiers.json").read_text()
    )
    assert expected["naaccr_value_count"] == 19
    assert {row["ecp_code"] for row in expected["rows"]} == {
        "2118.1000043",
        "2129.1000043",
        "820404.1000043",
    }
    assert all(row["item_num"] is None for row in expected["rows"])
