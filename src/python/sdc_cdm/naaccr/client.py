"""Small, retrying client for the SEER NAACCR REST endpoints."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from sdc_cdm.db.errors import SdcCdmError, UsageError

BASE_URL = "https://api.seer.cancer.gov"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class SeerApiError(SdcCdmError):
    """Raised when SEER returns an error or an invalid JSON payload."""


class JsonTransport(Protocol):
    def __call__(self, path: str) -> Any: ...


class UrllibJsonTransport:
    """urllib transport with bounded retries and injectable timing for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 40.0,
        attempts: int = 4,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.attempts = attempts
        self.opener = opener
        self.sleep = sleep
        self.jitter = jitter

    def __call__(self, path: str) -> Any:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={
                "Accept": "application/json",
                "X-SEERAPI-Key": self.api_key,
            },
        )
        for attempt in range(self.attempts):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                message = _http_error_message(exc)
                if exc.code not in RETRYABLE_STATUSES or attempt + 1 == self.attempts:
                    raise SeerApiError(message) from exc
                self.sleep(_retry_delay(attempt, exc.headers, self.jitter))
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt + 1 == self.attempts:
                    raise SeerApiError(f"GET {path} failed: {exc}") from exc
                self.sleep(_retry_delay(attempt, None, self.jitter))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SeerApiError(f"GET {path} returned invalid JSON: {exc}") from exc
        raise AssertionError("retry loop exhausted without returning or raising")


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if isinstance(payload, Mapping) and isinstance(payload.get("message"), str):
        return payload["message"]
    return f"HTTP {exc.code}: {exc.reason}"


def _retry_delay(
    attempt: int,
    headers: Mapping[str, str] | None,
    jitter: Callable[[], float],
) -> float:
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return float(2**attempt) + float(jitter())


class SeerApiClient:
    """Typed path wrapper over an injected ``get(path)`` JSON transport."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: JsonTransport | None = None,
        concurrency: int = 8,
    ):
        if not api_key:
            raise UsageError("dict fetch requires SEER_API_KEY")
        self.transport = transport or UrllibJsonTransport(api_key)
        self.concurrency = max(1, min(int(concurrency), 16))

    def versions(self) -> list[dict[str, Any]]:
        return self._object_list(self.transport("/rest/naaccr/versions"), "versions")

    def item_index(self, version: str) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(str(version), safe="")
        return self._object_list(
            self.transport(f"/rest/naaccr/{encoded}"), "item index"
        )

    def item(self, version: str, key: str) -> dict[str, Any]:
        encoded_version = urllib.parse.quote(str(version), safe="")
        encoded_key = urllib.parse.quote(str(key), safe="")
        payload = self.transport(f"/rest/naaccr/{encoded_version}/{encoded_key}")
        if not isinstance(payload, dict):
            raise SeerApiError("SEER NAACCR item response must be an object")
        return payload

    def items(self, version: str) -> list[dict[str, Any]]:
        index = self.item_index(version)

        def detail(entry: Mapping[str, Any]) -> dict[str, Any]:
            # Retired index entries omit id; SEER accepts their item number as
            # the detail key. This fallback is required for all 166 v25 retirees.
            try:
                key = entry.get("id") or entry["item"]
            except KeyError as exc:
                raise SeerApiError(
                    "SEER NAACCR index entry is missing both id and item"
                ) from exc
            return self.item(version, str(key))

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            items = list(executor.map(detail, index))
        try:
            return sorted(items, key=lambda item: int(str(item["item_number"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise SeerApiError(
                "SEER NAACCR detail response has an invalid item_number"
            ) from exc

    @staticmethod
    def _object_list(payload: Any, label: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or not all(
            isinstance(entry, dict) for entry in payload
        ):
            raise SeerApiError(
                f"SEER NAACCR {label} response must be an array of objects"
            )
        return payload
