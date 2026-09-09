"""Fetch a complete NAACCR dictionary and write the stable CSV contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdc_cdm.naaccr.client import BASE_URL, SeerApiClient, SeerApiError
from sdc_cdm.naaccr.columns import (
    ALLOWED_CODE_COLUMNS,
    ALLOWED_CODE_FILE,
    DICTIONARY_COLUMNS,
    DICTIONARY_FILE,
    REGISTRY_REQUIREMENT_COLUMNS,
    REGISTRY_REQUIREMENT_FILE,
    VERSION_COLUMNS,
    VERSION_FILE,
    allowed_code_rows,
    dictionary_rows,
    registry_requirement_rows,
)
from sdc_cdm.naaccr.csv_io import DEFAULT_CSV_DIR, write_csv


@dataclass(frozen=True)
class FetchResult:
    naaccr_version: str
    item_count: int
    live_item_count: int
    retired_item_count: int
    section_count: int
    allowed_code_count: int
    registry_requirement_count: int


def write_dictionary_csvs(
    items: list[dict[str, Any]],
    *,
    naaccr_version: str,
    algorithm: str = "eod_public",
    algorithm_version: str = "3.3",
    output_dir: Path = DEFAULT_CSV_DIR,
) -> FetchResult:
    """Derive all four dictionary CSVs from already-fetched item DTOs."""

    item_rows = dictionary_rows(items)
    code_rows = allowed_code_rows(items)
    requirement_rows = registry_requirement_rows(items)
    source_api = f"{BASE_URL}/rest/staging/{algorithm}/{algorithm_version}"

    write_csv(output_dir / DICTIONARY_FILE, DICTIONARY_COLUMNS, item_rows)
    write_csv(output_dir / ALLOWED_CODE_FILE, ALLOWED_CODE_COLUMNS, code_rows)
    write_csv(
        output_dir / REGISTRY_REQUIREMENT_FILE,
        REGISTRY_REQUIREMENT_COLUMNS,
        requirement_rows,
    )
    # This shared row is written last. The SSDI files and dictionary files have
    # no independent version id; dict load injects the id resolved from this row.
    write_csv(
        output_dir / VERSION_FILE,
        VERSION_COLUMNS,
        [(algorithm, algorithm_version, naaccr_version, source_api)],
    )

    live = [item for item in items if item.get("xml_naaccr_id")]
    retired = [item for item in items if item.get("year_retired")]
    sections = {item.get("section") for item in live if item.get("section")}
    return FetchResult(
        naaccr_version=str(naaccr_version),
        item_count=len(item_rows),
        live_item_count=len(live),
        retired_item_count=len(retired),
        section_count=len(sections),
        allowed_code_count=len(code_rows),
        registry_requirement_count=len(requirement_rows),
    )


def fetch_dictionary(
    client: SeerApiClient,
    *,
    naaccr_version: str = "25",
    algorithm: str = "eod_public",
    algorithm_version: str = "3.3",
    output_dir: Path = DEFAULT_CSV_DIR,
) -> FetchResult:
    """Call versions, the thin index, then every detail endpoint and write CSVs."""

    versions = client.versions()
    if str(naaccr_version) not in {str(entry.get("version")) for entry in versions}:
        raise SeerApiError(f"Version does not exist: {naaccr_version}")
    items = client.items(str(naaccr_version))
    return write_dictionary_csvs(
        items,
        naaccr_version=str(naaccr_version),
        algorithm=algorithm,
        algorithm_version=algorithm_version,
        output_dir=output_dir,
    )
