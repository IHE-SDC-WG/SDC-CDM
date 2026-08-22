"""Counts-only verification for a loaded NAACCR dictionary generation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError

CHECK_NAMES = (
    "item_count",
    "live_item_count",
    "retired_item_count",
    "live_items_missing_section",
    "section_count",
    "allowed_code_count",
    "registry_requirement_count",
    "schema_item_orphan_count",
)


@dataclass(frozen=True)
class VerifyResult:
    dd_version_id: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def _expectations(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VocabularyError(f"cannot read expectations {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VocabularyError(f"{path} must contain a JSON object")
    for field in ("algorithm", "version", "naaccr_version", "checks", "sections"):
        if field not in payload:
            raise VocabularyError(f"{path} is missing {field}")
    checks = payload["checks"]
    if not isinstance(checks, dict) or tuple(checks) != CHECK_NAMES:
        raise VocabularyError(
            f"{path} checks must be present in this order: {CHECK_NAMES!r}"
        )
    if not all(isinstance(value, int) and value >= 0 for value in checks.values()):
        raise VocabularyError(f"{path} check values must be non-negative integers")
    sections = payload["sections"]
    if not isinstance(sections, dict) or not all(
        isinstance(label, str) and label and isinstance(value, int) and value >= 0
        for label, value in sections.items()
    ):
        raise VocabularyError(
            f"{path} sections must map labels to non-negative integer counts"
        )
    return payload


def _actual_checks(backend: DatabaseBackend, dd_version_id: int) -> dict[str, int]:
    item = backend.qualified_name("naaccr", "naaccr_item")
    code = backend.qualified_name("naaccr", "naaccr_item_allowed_code")
    requirement = backend.qualified_name("naaccr", "naaccr_item_registry_requirement")
    schema_item = backend.qualified_name("naaccr", "schema_item")
    queries = {
        "item_count": f"SELECT COUNT(*) FROM {item} WHERE dd_version_id = ?",
        "live_item_count": (
            f"SELECT COUNT(*) FROM {item} "
            "WHERE dd_version_id = ? AND xml_id IS NOT NULL"
        ),
        "retired_item_count": (
            f"SELECT COUNT(*) FROM {item} "
            "WHERE dd_version_id = ? AND year_retired IS NOT NULL"
        ),
        "live_items_missing_section": (
            f"SELECT COUNT(*) FROM {item} "
            "WHERE dd_version_id = ? AND xml_id IS NOT NULL AND section IS NULL"
        ),
        "section_count": (
            f"SELECT COUNT(DISTINCT section) FROM {item} WHERE dd_version_id = ?"
        ),
        "allowed_code_count": (f"SELECT COUNT(*) FROM {code} WHERE dd_version_id = ?"),
        "registry_requirement_count": (
            f"SELECT COUNT(*) FROM {requirement} WHERE dd_version_id = ?"
        ),
        "schema_item_orphan_count": (
            f"SELECT COUNT(*) FROM {schema_item} si LEFT JOIN {item} ni "
            "ON ni.dd_version_id = si.dd_version_id AND ni.item_num = si.item_num "
            "WHERE si.dd_version_id = ? AND ni.item_num IS NULL"
        ),
    }
    return {
        name: int(backend.fetch_one(queries[name], (dd_version_id,))[0])
        for name in CHECK_NAMES
    }


def verify_dictionary(
    backend: DatabaseBackend,
    *,
    expectation_path: Path,
    print_line: Callable[[str], None] = print,
) -> VerifyResult:
    """Print and compare every pinned count for one current generation."""

    expected = _expectations(expectation_path)
    version_table = backend.qualified_name("naaccr", "data_dictionary_version")
    version_row = backend.fetch_one(
        f"SELECT dd_version_id, naaccr_version FROM {version_table} "
        "WHERE algorithm = ? AND version = ? AND is_current = 1",
        (str(expected["algorithm"]), str(expected["version"])),
    )
    if version_row is None:
        raise VocabularyError(
            "no current data_dictionary_version for "
            f"{expected['algorithm']}/{expected['version']}"
        )
    if str(version_row[1]) != str(expected["naaccr_version"]):
        raise VocabularyError(
            f"expected NAACCR version {expected['naaccr_version']}, "
            f"found {version_row[1]}"
        )
    dd_version_id = int(version_row[0])
    actual = _actual_checks(backend, dd_version_id)
    failures: list[str] = []
    print_line("check | expected | actual | PASS/FAIL")
    for name in CHECK_NAMES:
        expected_count = int(expected["checks"][name])
        actual_count = actual[name]
        status = "PASS" if actual_count == expected_count else "FAIL"
        print_line(f"{name} | {expected_count} | {actual_count} | {status}")
        if status == "FAIL":
            failures.append(name)

    item = backend.qualified_name("naaccr", "naaccr_item")
    actual_sections = {
        str(row[0]): int(row[1])
        for row in backend.fetch_all(
            f"SELECT section, COUNT(*) FROM {item} "
            "WHERE dd_version_id = ? AND section IS NOT NULL "
            "GROUP BY section",
            (dd_version_id,),
        )
    }
    expected_sections: Mapping[str, int] = expected["sections"]
    for label in sorted(set(expected_sections) | set(actual_sections)):
        expected_count = int(expected_sections.get(label, 0))
        actual_count = actual_sections.get(label, 0)
        status = "PASS" if actual_count == expected_count else "FAIL"
        name = f"section: {label}"
        print_line(f"{name} | {expected_count} | {actual_count} | {status}")
        if status == "FAIL":
            failures.append(name)
    return VerifyResult(dd_version_id, tuple(failures))
