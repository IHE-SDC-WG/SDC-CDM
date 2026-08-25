from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from sdc_cdm.cli.main import main
from sdc_cdm.naaccr.client import SeerApiClient, SeerApiError
from sdc_cdm.naaccr.ssdi import SSDI_FILES, fetch_ssdi

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = ROOT / "sample_data/test-fixtures/ssdi"


class _FixtureTransport:
    def __init__(self):
        self.payloads = json.loads(
            (FIXTURE_ROOT / "seer_api.json").read_text(encoding="utf-8")
        )
        self.paths: list[str] = []

    def __call__(self, path: str) -> Any:
        self.paths.append(path)
        return self.payloads[path]


def test_ssdi_fixture_recomputes_all_twelve_csvs_byte_for_byte(
    tmp_path: Path,
) -> None:
    transport = _FixtureTransport()
    result = fetch_ssdi(
        SeerApiClient("fixture-key", transport=transport, concurrency=4),
        algorithm="eod_public",
        staging_version="3.3",
        naaccr_version="26",
        output_dir=tmp_path,
    )

    assert result.schema_count == 2
    assert result.item_count == 4
    assert result.table_count == 9
    assert result.involved_table_count == 12
    assert transport.paths[0] == "/rest/naaccr/versions"
    assert transport.paths[1] == "/rest/staging/eod_public/3.3/schemas"
    calls = Counter(transport.paths)
    assert all(count == 1 for count in calls.values())
    assert "/rest/staging/eod_public/3.3/table/must-not-fetch" not in calls
    assert len([path for path in calls if "/table/" in path]) == 9
    for filename in SSDI_FILES:
        assert (tmp_path / filename).read_bytes() == (
            FIXTURE_ROOT / "csv" / filename
        ).read_bytes()


def test_ssdi_fixture_covers_ordering_membership_and_table_correction(
    tmp_path: Path,
) -> None:
    fetch_ssdi(
        SeerApiClient("fixture-key", transport=_FixtureTransport()),
        naaccr_version="26",
        output_dir=tmp_path,
    )
    schema_items = (tmp_path / "schema_item.csv").read_text(encoding="utf-8")
    links = (tmp_path / "schema_involved_table.csv").read_text(encoding="utf-8")
    rows = (tmp_path / "staging_table_row.csv").read_text(encoding="utf-8")

    assert schema_items.count('"10","100"') == 1
    assert '"not-naaccr"' not in schema_items
    assert '"10","extra-a"' in links
    assert '"20","extra-b"' in links
    assert '[""EA"",null,""tail""]' in rows


def test_invalid_naaccr_version_stops_before_staging_requests(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    with pytest.raises(SeerApiError, match="Version does not exist: 99"):
        fetch_ssdi(
            SeerApiClient("fixture-key", transport=transport),
            naaccr_version="99",
            output_dir=tmp_path,
        )
    assert transport.paths == ["/rest/naaccr/versions"]


def test_ssdi_fetch_without_key_exits_two_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SEER_API_KEY", raising=False)

    def unexpected_fetch(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network fetch was attempted")

    monkeypatch.setattr("sdc_cdm.cli.dictionary.fetch_ssdi", unexpected_fetch)
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "ssdi",
                "fetch",
                "--dialect",
                "sqlite",
                "--naaccr-version",
                "26",
            ]
        )

    assert exc_info.value.code == 2
    assert "SEER_API_KEY" in capsys.readouterr().err


def test_ssdi_fetch_requires_naaccr_version() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["ssdi", "fetch", "--dialect", "sqlite"])
    assert exc_info.value.code == 2
