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
class EtlEntry:
    """One ordered bridge or validation script and the prerequisites it reads.

    ``constants`` are etl.concept_constant names, ``seeds`` are file names in
    the seed directory, and ``tables`` are the schema-qualified tables whose
    row counts the runner reports after the script.
    """

    path: str
    constants: tuple[str, ...]
    seeds: tuple[str, ...]
    tables: tuple[str, ...]


@dataclass(frozen=True)
class ManifestExclusion:
    path: str
    reason: str


@dataclass(frozen=True)
class DatabaseManifest:
    manifest_version: int
    build: dict[str, tuple[ManifestEntry, ...]]
    excluded: tuple[ManifestExclusion, ...]
    bridge: dict[str, tuple[EtlEntry, ...]]
    validate: dict[str, tuple[EtlEntry, ...]]

    def entries_for(self, dialect: str) -> tuple[ManifestEntry, ...]:
        try:
            return self.build[dialect]
        except KeyError as exc:
            raise ManifestError(f"unsupported dialect: {dialect}") from exc

    def bridge_entries_for(self, dialect: str) -> tuple[EtlEntry, ...]:
        try:
            return self.bridge[dialect]
        except KeyError as exc:
            raise ManifestError(f"unsupported dialect: {dialect}") from exc


def _relative_posix_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{field} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ManifestError(f"{field} must be a normalized repo-relative POSIX path: {value!r}")
    return value


def _names(value: Any, field_name: str, *, qualified: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ManifestError(f"{field_name} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ManifestError(f"{field_name} contains duplicates")
    if qualified:
        for item in value:
            schema, _, table = item.partition(".")
            if schema not in SCHEMA_ORDER or not table or "." in table:
                raise ManifestError(f"{field_name} entry is not schema.table: {item!r}")
    return tuple(value)


def _etl_entries(
    raw: dict[str, Any], stage: str, all_paths: set[str]
) -> dict[str, tuple[EtlEntry, ...]]:
    stage_raw = raw.get(stage)
    if not isinstance(stage_raw, dict):
        raise ManifestError(f"{stage} must be an object")
    stages: dict[str, tuple[EtlEntry, ...]] = {}
    for dialect in SUPPORTED_DIALECTS:
        entries_raw = stage_raw.get(dialect)
        if not isinstance(entries_raw, list):
            raise ManifestError(f"{stage}.{dialect} must be an array")
        entries: list[EtlEntry] = []
        for index, item in enumerate(entries_raw):
            field_name = f"{stage}.{dialect}[{index}]"
            if not isinstance(item, dict):
                raise ManifestError(f"{field_name} must be an object")
            path_value = _relative_posix_path(item.get("path"), f"{field_name}.path")
            if PurePosixPath(path_value).parent != PurePosixPath("database/etl", dialect):
                raise ManifestError(
                    f"{field_name}.path must be in database/etl/{dialect}/: {path_value}"
                )
            if path_value in all_paths:
                raise ManifestError(f"duplicate manifest path: {path_value}")
            all_paths.add(path_value)
            entries.append(EtlEntry(
                path_value,
                _names(item.get("constants"), f"{field_name}.constants"),
                _names(item.get("seeds"), f"{field_name}.seeds"),
                _names(item.get("tables"), f"{field_name}.tables", qualified=True),
            ))
        stages[dialect] = tuple(entries)
    return stages


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

    bridge = _etl_entries(raw, "bridge", all_paths)
    validate = _etl_entries(raw, "validate", all_paths)

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

    manifest = DatabaseManifest(1, build, tuple(excluded), bridge, validate)
    validate_manifest_files(manifest)
    return manifest


def validate_manifest_files(manifest: DatabaseManifest) -> None:
    declared = {
        entry.path
        for dialect in SUPPORTED_DIALECTS
        for entry in (
            *manifest.entries_for(dialect),
            *manifest.bridge[dialect],
            *manifest.validate[dialect],
        )
    }
    declared.update(exclusion.path for exclusion in manifest.excluded)

    missing = sorted(path for path in declared if not (REPO_ROOT / path).is_file())
    if missing:
        raise ManifestError(f"manifest paths do not exist: {', '.join(missing)}")

    sql_files = {
        path.relative_to(REPO_ROOT).as_posix()
        for pattern in ("schemas/*/ddl/*/*.sql", "etl/*/*.sql")
        for path in (REPO_ROOT / "database").glob(pattern)
    }
    omitted = sorted(sql_files - declared)
    stale = sorted(declared - sql_files)
    if omitted:
        raise ManifestError(f"SQL files omitted from manifest: {', '.join(omitted)}")
    if stale:
        raise ManifestError(
            f"declared paths outside the DDL and ETL trees: {', '.join(stale)}"
        )
