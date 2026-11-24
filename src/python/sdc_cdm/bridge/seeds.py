"""Bridge seed files: read, check, and stage them for the bridge SQL."""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import date
from pathlib import Path

from sdc_cdm.db.backend import DatabaseBackend


CDM_SOURCE_FILE = "cdm_source.csv"
# Every omop.cdm_source column except the two the bridge resolves from the
# loaded vocabulary: cdm_version_concept_id and vocabulary_version. Lengths are
# the SQL Server CDM limits, applied to both dialects so they behave alike.
CDM_SOURCE_COLUMNS = (
    ("cdm_source_name", 255, True),
    ("cdm_source_abbreviation", 25, True),
    ("cdm_holder", 255, True),
    ("source_description", None, False),
    ("source_documentation_reference", 255, False),
    ("cdm_etl_reference", 255, False),
    ("source_release_date", None, True),
    ("cdm_release_date", None, True),
    ("cdm_version", 10, True),
)
_DATE_COLUMNS = {"source_release_date", "cdm_release_date"}
# The shipped OMOP DDL is CDM 5.4, and the bridge pairs cdm_version with the
# cdm_version constant (CDM v5.4.0); any other value would contradict it.
CDM_VERSION = "5.4"


def read_cdm_source(path: Path) -> tuple[str | None, ...]:
    """Return the seed's one row, blanks as None, or raise ValueError naming the defect."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    names = tuple(name for name, _limit, _required in CDM_SOURCE_COLUMNS)
    if not rows or tuple(rows[0]) != names:
        raise ValueError(f"header must be {','.join(names)}")
    if len(rows) != 2:
        raise ValueError(f"must contain exactly one data row, found {len(rows) - 1}")
    row = rows[1]
    if len(row) != len(names):
        raise ValueError(f"line 2 has {len(row)} fields, expected {len(names)}")
    values: list[str | None] = []
    for (name, limit, required), raw in zip(CDM_SOURCE_COLUMNS, row):
        value = raw.strip() or None
        if value is None:
            if required:
                raise ValueError(f"{name} is required")
        elif limit is not None and len(value) > limit:
            raise ValueError(f"{name} is longer than {limit} characters")
        elif name in _DATE_COLUMNS:
            try:
                valid = len(value) == 10 and date.fromisoformat(value).isoformat() == value
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be a YYYY-MM-DD date, got {value!r}")
        elif name == "cdm_version" and value != CDM_VERSION:
            raise ValueError(
                f"cdm_version must be {CDM_VERSION!r}, the shipped OMOP schema, got {value!r}"
            )
        values.append(value)
    return tuple(values)


def stage_cdm_source(backend: DatabaseBackend, path: Path) -> None:
    """Replace etl.cdm_source_seed with the seed row inside the open transaction."""

    backend.execute_uncommitted("DELETE FROM etl.cdm_source_seed")
    backend.bulk_insert(
        "etl", "cdm_source_seed",
        tuple(name for name, _limit, _required in CDM_SOURCE_COLUMNS),
        (read_cdm_source(path),),
    )


VALIDATE_THRESHOLDS_FILE = "validate_thresholds.csv"
VALIDATE_THRESHOLD_COLUMNS = ("check_name", "max_count", "reason")


def read_validate_thresholds(path: Path) -> dict[str, int]:
    """Return check_name -> max_count, or raise ValueError naming the defect.

    Each row caps one `coverage` check of `sdc-cdm validate`. Python compares
    the counts, so this seed is never staged in the database.
    """

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or tuple(rows[0]) != VALIDATE_THRESHOLD_COLUMNS:
        raise ValueError(f"header must be {','.join(VALIDATE_THRESHOLD_COLUMNS)}")
    thresholds: dict[str, int] = {}
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != len(VALIDATE_THRESHOLD_COLUMNS):
            raise ValueError(
                f"line {line} has {len(row)} fields, expected {len(VALIDATE_THRESHOLD_COLUMNS)}"
            )
        name, raw_count, reason = (value.strip() for value in row)
        if not name:
            raise ValueError(f"line {line}: check_name is required")
        if name in thresholds:
            raise ValueError(f"line {line}: check_name {name!r} is repeated")
        if not raw_count.isascii() or not raw_count.isdigit():
            raise ValueError(
                f"line {line}: max_count for {name!r} must be a non-negative integer, "
                f"got {raw_count!r}"
            )
        if not reason:
            raise ValueError(f"line {line}: reason for {name!r} is required")
        thresholds[name] = int(raw_count)
    return thresholds


# Seed file name -> (checker run before the transaction, stager run inside it,
# or None for a seed that Python reads and never stages).
SEEDS: dict[
    str, tuple[Callable[[Path], object], Callable[[DatabaseBackend, Path], None] | None]
] = {
    CDM_SOURCE_FILE: (read_cdm_source, stage_cdm_source),
    VALIDATE_THRESHOLDS_FILE: (read_validate_thresholds, None),
}
