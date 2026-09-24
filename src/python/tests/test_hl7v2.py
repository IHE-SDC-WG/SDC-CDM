from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sdc_cdm.hl7v2 import Hl7ParseError, parse_envelope, parse_hl7, serialize_envelope
from sdc_cdm.hl7v2.parser import decode_hl7, parse_date


ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC = ROOT / "contracts/fixtures/two-obr-synthetic.hl7"
ADRENAL = ROOT / "sample_data/naaccr_v2/obx-Adrenal.hl7"
TWO_OBR = ROOT / "sample_data/naaccr_v2/24-11-000312-2.txt.hl7"
SCHEMA = json.loads((ROOT / "contracts/envelope.schema.json").read_text())


def test_synthetic_two_obr_envelopes_match_goldens_and_schema() -> None:
    envelopes = parse_hl7(SYNTHETIC.read_bytes())
    assert len(envelopes) == 2
    for index, envelope in enumerate(envelopes, 1):
        Draft202012Validator(SCHEMA).validate(envelope)
        serialized = serialize_envelope(envelope)
        assert serialized == (
            ROOT / f"contracts/golden/two-obr-synthetic.{index}.envelope.json"
        ).read_bytes()
        assert serialize_envelope(parse_envelope(serialized)) == serialized


def test_hex_narrative_escapes_are_decoded_after_field_splitting() -> None:
    assert decode_hl7("first\\X0D\\\\X0A\\second\\F\\third") == "first\nsecond|third"
    reports = parse_hl7(SYNTHETIC.read_bytes())
    assert reports[0]["report"]["narrative"] == "Synthetic diagnosis\nsecond line"
    assert [row["report"]["report_loinc"] for row in reports] == ["35265-8", "60569-1"]
    assert reports[0]["raw"] == reports[1]["raw"]


def test_retired_csharp_19_value_and_obx4_contract() -> None:
    envelopes = parse_hl7(ADRENAL.read_bytes())
    assert len(envelopes) == 1
    values = envelopes[0]["values"]
    assert len(values) == 19
    assert envelopes[0]["report"]["accession"] == "15SL-2"
    assert envelopes[0]["report"]["report_loinc"] == "60568-3"
    assert envelopes[0]["report"]["template_source"] == "CAP eCC"
    assert all("item_num" not in row for row in values)
    numeric = next(row for row in values if row["ecp_code"] == "2129.1000043")
    assert (numeric["obx_sub_id"], numeric["value_code"], numeric["value_num"]) == (
        "2131", "2131.1000043", "10",
    )
    coded_text = next(row for row in values if row["ecp_code"] == "820404.1000043")
    assert coded_text["value_code"] == "45594.1000043"
    assert coded_text["value_text"] == "Capsular invasion and sinusoidal vascular invasion identified"


def test_two_obr_real_fixture_keeps_distinct_reports_without_tracking_narrative() -> None:
    envelopes = parse_hl7(TWO_OBR.read_bytes())
    assert [row["report"]["report_loinc"] for row in envelopes] == ["35265-8", "60569-1"]
    assert envelopes[0]["report"]["narrative"]
    assert len(envelopes[1]["values"]) == 27
    assert [row["source"]["obr_ordinal"] for row in envelopes] == [1, 2]
    assert envelopes[0]["raw"]["sha256"] == envelopes[1]["raw"]["sha256"]
    assert envelopes[1]["source"]["message_profile"].startswith("VOL_V_51")


@pytest.mark.parametrize(
    ("source", "precision", "tail"),
    [
        ("1957", "year", {"m": None, "d": None}),
        ("195703", "month", {"m": 3, "d": None}),
        ("19570304", "day", {"m": 3, "d": 4}),
        ("1957030412", "hour", {"hh": 12, "mi": None, "ss": None}),
        ("195703041235-0400", "minute", {"hh": 12, "mi": 35, "ss": None, "tz": "-04:00"}),
        ("19570304123559+0530", "second", {"hh": 12, "mi": 35, "ss": 59, "tz": "+05:30"}),
    ],
)
def test_dates_preserve_precision_and_offset(source: str, precision: str, tail: dict[str, object]) -> None:
    diagnostics: list[dict[str, str]] = []
    value = parse_date(source, diagnostics, "test")
    assert value is not None
    assert value["precision"] == precision
    assert all(value[key] == expected for key, expected in tail.items())
    assert diagnostics == []


def test_invalid_date_is_null_and_diagnostic() -> None:
    diagnostics: list[dict[str, str]] = []
    assert parse_date("19571399", diagnostics, "PID-7") is None
    assert diagnostics[0]["code"] == "INVALID_DATE"


def test_orc_episode_identifier_and_non_cap_warning() -> None:
    raw = SYNTHETIC.read_bytes().replace(
        b"ORC|RE||SYN-ACC-1", b"ORC|RE||SYN-ACC-1|EP-7^^SYNTHLAB"
    ).replace(
        b"20791.100004300^Tumor Size^CAPECP", b"77777-7^Other measurement^LN"
    )
    envelopes = parse_hl7(raw)
    assert all(row["episode"] == {
        "episode_source_value": "EP-7", "assigning_authority": "SYNTHLAB"
    } for row in envelopes)
    assert any(item["code"] == "NON_CAP_IDENTIFIER" for item in envelopes[1]["diagnostics"])
    assert "values" not in envelopes[1]


def test_missing_obx_date_uses_obr_date_with_diagnostic() -> None:
    raw = SYNTHETIC.read_bytes().replace(b"F|||202609241235-0400", b"F|||")
    envelopes = parse_hl7(raw)
    assert any(item["code"] == "OBX_DATE_FALLBACK" for item in envelopes[1]["diagnostics"])


@pytest.mark.parametrize("raw", [b"", b"PID|1||one\r", b"MSH|^~\\&|one\rMSH|^~\\&|two\r"])
def test_unparseable_message_raises_typed_error(raw: bytes) -> None:
    with pytest.raises(Hl7ParseError):
        parse_hl7(raw)
