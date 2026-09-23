"""Counts-only map coverage and local data-quality signals."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.paths import repository_path
from sdc_cdm.maps.build import current_generation
from sdc_cdm.maps.seeds import read_seeds


@dataclass(frozen=True)
class CoverageReport:
    algorithm: str
    rows: tuple[tuple[str, str, str, int], ...]
    checks: dict[str, int]
    comparisons: tuple[tuple[str, int, int, bool], ...]
    failures: tuple[str, ...]


def report_coverage(
    backend: DatabaseBackend, *, algorithm: str | None = None,
    csv_dir: Path | None = None, expectation_path: Path | None = None,
) -> CoverageReport:
    selected, generation = current_generation(backend, algorithm)
    if not backend.table_exists("naaccr", "concept_map_build_state"):
        raise VocabularyError(
            "rebuild required: missing naaccr.concept_map_build_state; re-run build"
        )
    built = backend.fetch_one(
        "SELECT algorithm, dd_version_id FROM naaccr.concept_map_build_state "
        "WHERE singleton_id = 1"
    )
    if built is None or str(built[0]) != selected or int(built[1]) != generation:
        built_label = "none" if built is None else f"{built[0]}/{built[1]}"
        raise VocabularyError(
            f"maps coverage requires maps build for {selected}/{generation}; "
            f"recorded build is {built_label}"
        )
    rows = tuple(
        (str(row[0]), str(row[1] or ""), str(row[2]), int(row[3]))
        for row in backend.fetch_all(
            "SELECT scope, section, mapping_layer, item_count "
            "FROM naaccr.concept_map_coverage WHERE algorithm = ? "
            "ORDER BY scope, section, mapping_layer", (selected,),
        )
    )
    counts: Counter[str] = Counter()
    for scope, _section, layer, count in rows:
        counts[f"{scope}_total"] += count
        counts[f"{scope}_{layer}"] += count
    for scope in ("item", "value"):
        counts[f"{scope}_total"] += 0
        for layer in ("athena_standard", "curated_override", "local_mint", "unmapped"):
            counts[f"{scope}_{layer}"] += 0
    seeds = read_seeds(csv_dir or repository_path("database/seed"))
    current_items = {
        int(row[0]) for row in backend.fetch_all(
            "SELECT item_num FROM naaccr.naaccr_item "
            "WHERE dd_version_id = ? AND year_retired IS NULL", (generation,),
        )
    }
    counts["excluded_items"] = len(current_items & seeds.exclusions)
    # A shared item/code pair across schemas may carry different meanings.
    schema_rows = backend.fetch_all(
        "SELECT item_num, code, description FROM naaccr.schema_item_code "
        "WHERE dd_version_id = ?", (generation,),
    )
    descriptions: dict[tuple[int, str], set[str]] = defaultdict(set)
    for item_num, code, description in schema_rows:
        descriptions[(int(item_num), str(code))].add(str(description or ""))
    counts["schema_value_collisions"] = sum(len(names) > 1 for names in descriptions.values())
    counts["foreign_captured_item_numbers"] = int(backend.fetch_one(
        "SELECT COUNT(*) FROM (SELECT DISTINCT value.item_num "
        "FROM naaccr.naaccr_value value "
        "LEFT JOIN naaccr.naaccr_item item ON item.item_num = value.item_num "
        "AND item.dd_version_id = ? "
        "WHERE item.item_num IS NULL) foreign_items", (generation,),
    )[0])
    checks = dict(sorted(counts.items()))
    comparisons: list[tuple[str, int, int, bool]] = []
    failures: list[str] = []
    if expectation_path is not None:
        try:
            expected = json.loads(expectation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VocabularyError(f"cannot read expectations {expectation_path}: {exc}") from exc
        if not isinstance(expected, dict) or expected.get("algorithm") != selected or not isinstance(expected.get("checks"), dict):
            raise VocabularyError(f"{expectation_path} must contain algorithm {selected!r} and checks")
        expected_version = expected.get("naaccr_version")
        if not isinstance(expected_version, str) or not expected_version:
            raise VocabularyError(f"{expectation_path} must contain naaccr_version")
        actual_version = backend.fetch_one(
            "SELECT naaccr_version FROM naaccr.data_dictionary_version "
            "WHERE dd_version_id = ?", (generation,),
        )[0]
        if expected_version != str(actual_version):
            raise VocabularyError(
                f"expected NAACCR version {expected_version}, found {actual_version}"
            )
        for key, value in expected["checks"].items():
            if type(value) is not int or value < 0 or key not in checks:
                raise VocabularyError(f"{expectation_path}: invalid check {key!r}")
            actual = checks[key]
            passed = actual == value
            comparisons.append((key, value, actual, passed))
            if not passed:
                failures.append(f"{key}: expected {value}, got {actual}")
    return CoverageReport(selected, rows, checks, tuple(comparisons), tuple(failures))
