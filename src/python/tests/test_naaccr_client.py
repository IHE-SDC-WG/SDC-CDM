from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any, Self

import pytest
from sdc_cdm.cli.main import main
from sdc_cdm.naaccr.client import (
    SeerApiClient,
    SeerApiError,
    UrllibJsonTransport,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "sample_data/test-fixtures/naaccr-dict/seer_api"
)


class _FixtureTransport:
    def __init__(self):
        self.paths: list[str] = []
        self.index = json.loads(
            (FIXTURE_ROOT / "index-25.json").read_text(encoding="utf-8")
        )

    def __call__(self, path: str) -> Any:
        self.paths.append(path)
        if path == "/rest/naaccr/versions":
            return json.loads(
                (FIXTURE_ROOT / "versions.json").read_text(encoding="utf-8")
            )
        if path == "/rest/naaccr/25":
            return self.index
        key = path.rsplit("/", 1)[-1]
        entry = next(
            entry
            for entry in self.index
            if str(entry.get("id") or entry["item"]) == key
        )
        return json.loads(
            (FIXTURE_ROOT / "items" / f"{int(entry['item'])}.json").read_text(
                encoding="utf-8"
            )
        )


def test_client_uses_item_number_for_retired_entries_and_sorts_details() -> None:
    transport = _FixtureTransport()
    client = SeerApiClient("test-key", transport=transport, concurrency=99)

    items = client.items("25")

    assert client.concurrency == 16
    assert [int(item["item_number"]) for item in items] == sorted(
        int(item["item_number"]) for item in items
    )
    assert "/rest/naaccr/25/1500" in transport.paths
    assert sum(not entry.get("id") for entry in transport.index) == 3


class _Response(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _http_error(status: int, message: str, retry_after: str | None = None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError(
        "https://api.seer.cancer.gov/test",
        status,
        "error",
        headers,
        io.BytesIO(json.dumps({"message": message}).encode("utf-8")),
    )


def test_transport_honours_retry_after_and_sends_the_key() -> None:
    calls: list[object] = []
    sleeps: list[float] = []

    def opener(request: object, *, timeout: float):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error(429, "slow down", "7")
        return _Response(b'{"ok": true}')

    transport = UrllibJsonTransport(
        "secret-key",
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda: 0.0,
    )

    assert transport("/test") == {"ok": True}
    assert sleeps == [7.0]
    assert len(calls) == 2
    assert calls[0].get_header("X-seerapi-key") == "secret-key"


def test_transport_does_not_retry_404_and_surfaces_envelope_message() -> None:
    calls = 0

    def opener(_request: object, *, timeout: float):
        nonlocal calls
        calls += 1
        raise _http_error(404, "Item does not exist: missing")

    transport = UrllibJsonTransport(
        "test-key", opener=opener, sleep=lambda _delay: None
    )

    with pytest.raises(SeerApiError, match="Item does not exist: missing"):
        transport("/rest/naaccr/25/missing")
    assert calls == 1


def test_transport_retries_url_errors_four_times() -> None:
    calls = 0
    sleeps: list[float] = []

    def opener(_request: object, *, timeout: float):
        nonlocal calls
        calls += 1
        raise urllib.error.URLError("offline")

    transport = UrllibJsonTransport(
        "test-key",
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda: 0.0,
    )

    with pytest.raises(SeerApiError, match="offline"):
        transport("/test")
    assert calls == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_transport_retries_timeouts_four_times() -> None:
    calls = 0

    def opener(_request: object, *, timeout: float):
        nonlocal calls
        calls += 1
        raise TimeoutError("timed out")

    transport = UrllibJsonTransport(
        "test-key",
        opener=opener,
        sleep=lambda _delay: None,
        jitter=lambda: 0.0,
    )

    with pytest.raises(SeerApiError, match="timed out"):
        transport("/test")
    assert calls == 4


def test_dict_fetch_without_key_exits_two_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SEER_API_KEY", raising=False)

    def unexpected_fetch(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network fetch was attempted")

    monkeypatch.setattr("sdc_cdm.cli.dictionary.fetch_dictionary", unexpected_fetch)
    with pytest.raises(SystemExit) as exc_info:
        main(["dict", "fetch", "--dialect", "sqlite"])

    assert exc_info.value.code == 2
    assert "SEER_API_KEY" in capsys.readouterr().err
