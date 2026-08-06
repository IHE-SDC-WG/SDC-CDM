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


def test_frozen_hl7_contract_names_its_source_commit() -> None:
    for path in sorted((ROOT / "contracts/golden").glob("obx-Adrenal.*.json")):
        golden = json.loads(path.read_text())
        assert golden["source"]["commit"] == "c29d01dc6a042b13217bbb511864b98aa714aee5"
