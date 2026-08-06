"""Load and validate the ordered database build manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sdc_cdm.db.errors import ManifestError
from sdc_cdm.db.paths import DEFAULT_MANIFEST_PATH, REPO_ROOT


SUPPORTED_DIALECTS = ("sqlite", "sqlserver")
SCHEMA_ORDER = ("etl", "intake", "omop", "naaccr", "sdc")


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    schema: str
    reapply_on_change: bool


@dataclass(frozen=True)
class ManifestExclusion:
    path: str
    reason: str


@dataclass(frozen=True)
class DatabaseManifest:
    manifest_version: int
    build: dict[str, tuple[ManifestEntry, ...]]
    excluded: tuple[ManifestExclusion, ...]

    def entries_for(self, dialect: str) -> tuple[ManifestEntry, ...]:
        try:
            return self.build[dialect]
        except KeyError as exc:
            raise ManifestError(f"unsupported dialect: {dialect}") from exc


def _relative_posix_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{field} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ManifestError(f"{field} must be a normalized repo-relative POSIX path: {value!r}")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> DatabaseManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be an object")
    if raw.get("manifest_version") != 1:
        raise ManifestError("manifest_version must be 1")
    build_raw = raw.get("build")
    if not isinstance(build_raw, dict):
        raise ManifestError("build must be an object")

    build: dict[str, tuple[ManifestEntry, ...]] = {}
    all_paths: set[str] = set()
    for dialect in SUPPORTED_DIALECTS:
        entries_raw = build_raw.get(dialect)
        if not isinstance(entries_raw, list) or not entries_raw:
            raise ManifestError(f"build.{dialect} must be a non-empty array")
        entries: list[ManifestEntry] = []
        for index, item in enumerate(entries_raw):
            field = f"build.{dialect}[{index}]"
            if not isinstance(item, dict):
                raise ManifestError(f"{field} must be an object")
            path_value = _relative_posix_path(item.get("path"), f"{field}.path")
            schema = item.get("schema")
            if schema not in SCHEMA_ORDER:
                raise ManifestError(f"{field}.schema is invalid: {schema!r}")
            reapply = item.get("reapply_on_change")
            if not isinstance(reapply, bool):
                raise ManifestError(f"{field}.reapply_on_change must be boolean")
            if path_value in all_paths:
                raise ManifestError(f"duplicate manifest path: {path_value}")
            all_paths.add(path_value)
            entries.append(ManifestEntry(path_value, schema, reapply))
        schema_positions = [SCHEMA_ORDER.index(entry.schema) for entry in entries]
        if schema_positions != sorted(schema_positions):
            raise ManifestError(f"build.{dialect} does not follow schema apply order")
        build[dialect] = tuple(entries)

    excluded_raw = raw.get("excluded")
    if not isinstance(excluded_raw, list):
        raise ManifestError("excluded must be an array")
    excluded: list[ManifestExclusion] = []
    for index, item in enumerate(excluded_raw):
        field = f"excluded[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{field} must be an object")
        path_value = _relative_posix_path(item.get("path"), f"{field}.path")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ManifestError(f"{field}.reason must be a non-empty string")
        if path_value in all_paths:
            raise ManifestError(f"duplicate manifest path: {path_value}")
        all_paths.add(path_value)
        excluded.append(ManifestExclusion(path_value, reason))

    manifest = DatabaseManifest(1, build, tuple(excluded))
    validate_manifest_files(manifest)
    return manifest


def validate_manifest_files(manifest: DatabaseManifest) -> None:
    declared = {
        entry.path
        for dialect in SUPPORTED_DIALECTS
        for entry in manifest.entries_for(dialect)
    }
    declared.update(exclusion.path for exclusion in manifest.excluded)

    missing = sorted(path for path in declared if not (REPO_ROOT / path).is_file())
    if missing:
        raise ManifestError(f"manifest paths do not exist: {', '.join(missing)}")

    ddl_files = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "database" / "schemas").glob("*/ddl/*/*.sql")
    }
    omitted = sorted(ddl_files - declared)
    stale = sorted(declared - ddl_files)
    if omitted:
        raise ManifestError(f"DDL files omitted from manifest: {', '.join(omitted)}")
    if stale:
        raise ManifestError(f"declared paths outside schema DDL tree: {', '.join(stale)}")
