"""Reviewed map targets and item exclusions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.naaccr.csv_io import read_csv_with_lines

OVERRIDE_FILE = "concept_map_overrides.csv"
EXCLUSION_FILE = "naaccr_item_exclusions.csv"
OVERRIDE_COLUMNS = (
    "item_num", "code", "omop_concept_id", "target_domain_id",
    "rationale", "reviewer", "reviewed_at",
)
EXCLUSION_COLUMNS = ("item_num", "item_name", "reason")


@dataclass(frozen=True)
class Override:
    item_num: int
    code: str | None
    target_id: int | None
    target_domain_id: str | None
    line: int


@dataclass(frozen=True)
class Seeds:
    overrides: tuple[Override, ...]
    exclusions: frozenset[int]


def _integer(value: str, path: Path, line: int, column: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise VocabularyError(f"{path}:{line}: {column} must be an integer") from exc
    if result < 0:
        raise VocabularyError(f"{path}:{line}: {column} must be non-negative")
    return result


def read_seeds(directory: Path) -> Seeds:
    overrides: list[Override] = []
    seen: set[tuple[int, str | None]] = set()
    path = directory / OVERRIDE_FILE
    for line, row in read_csv_with_lines(directory, OVERRIDE_FILE, OVERRIDE_COLUMNS):
        item_num = _integer(row["item_num"], path, line, "item_num")
        code = row["code"] or None
        key = (item_num, code)
        if key in seen:
            raise VocabularyError(f"{path}:{line}: duplicate override {key}")
        seen.add(key)
        target = row["omop_concept_id"]
        overrides.append(Override(
            item_num, code,
            _integer(target, path, line, "omop_concept_id") if target else None,
            row["target_domain_id"] or None,
            line,
        ))

    exclusions: set[int] = set()
    path = directory / EXCLUSION_FILE
    for line, row in read_csv_with_lines(directory, EXCLUSION_FILE, EXCLUSION_COLUMNS):
        item_num = _integer(row["item_num"], path, line, "item_num")
        if item_num in exclusions:
            raise VocabularyError(f"{path}:{line}: duplicate exclusion {item_num}")
        exclusions.add(item_num)
    overlap = sorted({row.item_num for row in overrides} & exclusions)
    if overlap:
        raise VocabularyError(
            f"{directory}: item {overlap[0]} appears in both override and exclusion CSVs"
        )
    return Seeds(tuple(overrides), frozenset(exclusions))
