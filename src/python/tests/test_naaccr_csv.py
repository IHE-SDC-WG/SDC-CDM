from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sdc_cdm.naaccr.client import SeerApiClient
from sdc_cdm.naaccr.columns import (
    ALLOWED_CODE_FILE,
    DICTIONARY_FILE,
    REGISTRY_REQUIREMENT_FILE,
    VERSION_FILE,
)
from sdc_cdm.naaccr.csv_io import read_csv, write_csv
from sdc_cdm.naaccr.fetch import fetch_dictionary

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = ROOT / "sample_data/test-fixtures/naaccr-dict"


class _RawFixtureTransport:
    def __init__(self):
        raw = FIXTURE_ROOT / "seer_api"
        self.versions = json.loads((raw / "versions.json").read_text(encoding="utf-8"))
        self.index = json.loads((raw / "index-25.json").read_text(encoding="utf-8"))
        self.items = {
            str(item["item_number"]): item
            for item in (
                json.loads(path.read_text(encoding="utf-8"))
                for path in (raw / "items").glob("*.json")
            )
        }

    def __call__(self, path: str) -> Any:
        if path == "/rest/naaccr/versions":
            return self.versions
        if path == "/rest/naaccr/25":
            return self.index
        key = path.rsplit("/", 1)[-1]
        entry = next(
            entry
            for entry in self.index
            if str(entry.get("id") or entry["item"]) == key
        )
        return self.items[str(entry["item"])]


def test_csv_contract_is_always_quoted_utf8_lf_and_preserves_newlines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.csv"
    write_csv(
        path,
        ("a", "b"),
        [("x,y", 'say "hi"\nnext'), (None, "é")],
    )

    assert path.read_bytes() == (b'"a","b"\n"x,y","say ""hi""\nnext"\n"","\xc3\xa9"\n')
    assert read_csv(tmp_path, path.name, ("a", "b")) == [
        {"a": "x,y", "b": 'say "hi"\nnext'},
        {"a": "", "b": "é"},
    ]


def test_committed_csvs_recompute_byte_for_byte_from_raw_json(
    tmp_path: Path,
) -> None:
    result = fetch_dictionary(
        SeerApiClient("fixture-key", transport=_RawFixtureTransport()),
        naaccr_version="25",
        output_dir=tmp_path,
    )

    assert result.item_count == 12
    assert result.live_item_count == 9
    assert result.retired_item_count == 3
    assert result.section_count == 4
    for filename in (
        VERSION_FILE,
        DICTIONARY_FILE,
        ALLOWED_CODE_FILE,
        REGISTRY_REQUIREMENT_FILE,
    ):
        assert (tmp_path / filename).read_bytes() == (
            FIXTURE_ROOT / "csv" / filename
        ).read_bytes()


def test_fixture_covers_the_declared_shapes_without_claiming_all_sections() -> None:
    items = list(_RawFixtureTransport().items.values())

    assert len({item.get("section") for item in items if item.get("section")}) == 4
    assert any(
        "\n" in (code.get("description") or "")
        for item in items
        for code in item.get("allowed_codes", [])
    )
    assert any(
        len(codes := [code["code"] for code in item.get("allowed_codes", [])])
        != len(set(codes))
        for item in items
    )
    assert any(
        any(ord(character) > 127 for character in json.dumps(item, ensure_ascii=False))
        for item in items
    )
    assert any("," in item["item_name"] for item in items)
    assert any(
        len(item.get("alternate_names", [])) == 5
        and any("," in name for name in item["alternate_names"])
        for item in items
    )
    assert any(item.get("year_retired") and len(item) == 6 for item in items)
    assert any(item.get("year_retired") and len(item) == 7 for item in items)
    assert any(item.get("year_retired") and item.get("record_types") for item in items)
    assert any(
        item.get("xml_naaccr_id") and not item.get("item_data_type") for item in items
    )


def test_interrupted_dictionary_refresh_leaves_no_version_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / VERSION_FILE
    stale.write_text("stale\n", encoding="utf-8")

    def fail_first_write(*_args: object, **_kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr("sdc_cdm.naaccr.fetch.write_csv", fail_first_write)
    with pytest.raises(OSError, match="disk full"):
        fetch_dictionary(
            SeerApiClient("fixture-key", transport=_RawFixtureTransport()),
            naaccr_version="25",
            output_dir=tmp_path,
        )

    assert not stale.exists()
