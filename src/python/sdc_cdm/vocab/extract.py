"""Validate and stream OHDSI Athena source files without database access."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

from sdc_cdm.cdm.tables import EXPECTED_HEADERS, TABLE_SPECS, TableSpec
from sdc_cdm.db.errors import VocabularyError


def _parse_date(value: str, file_name: str, line_number: int) -> str:
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, format_string).date().isoformat()
        except ValueError:
            pass
    raise VocabularyError(
        f"{file_name}:{line_number}: invalid date {value!r}; "
        "expected YYYYMMDD or YYYY-MM-DD"
    )


def _convert_value(
    value: str, kind: str, file_name: str, line_number: int
) -> Any:
    if value == "":
        return None
    if kind == "text":
        return value
    if kind == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise VocabularyError(
                f"{file_name}:{line_number}: invalid integer {value!r}"
            ) from exc
    if kind == "decimal":
        try:
            return str(Decimal(value))
        except InvalidOperation as exc:
            raise VocabularyError(
                f"{file_name}:{line_number}: invalid decimal {value!r}"
            ) from exc
    if kind == "date":
        return _parse_date(value, file_name, line_number)
    raise AssertionError(f"Unsupported field kind: {kind}")


def _read_header(path: Path, delimiter: str) -> tuple[str, ...]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter, quotechar='"')
            header = next(reader)
    except StopIteration as exc:
        raise VocabularyError(f"{path.name}: file is empty") from exc
    except UnicodeDecodeError as exc:
        raise VocabularyError(f"{path.name}: file is not valid UTF-8") from exc
    return tuple(value.strip().upper() for value in header)


def validate_source_files(vocab_dir: Path, delimiter: str) -> dict[str, Path]:
    if not vocab_dir.is_dir():
        raise VocabularyError(f"Vocabulary directory does not exist: {vocab_dir}")

    paths: dict[str, Path] = {}
    errors: list[str] = []
    for spec in TABLE_SPECS:
        path = vocab_dir / spec.file_name
        if not path.is_file():
            errors.append(f"missing {spec.file_name}")
            continue
        actual_header = _read_header(path, delimiter)
        expected_header = EXPECTED_HEADERS[spec.file_name]
        if actual_header != expected_header:
            errors.append(
                f"{spec.file_name} header mismatch\n"
                f"  expected: {delimiter.join(expected_header)}\n"
                f"  actual:   {delimiter.join(actual_header)}"
            )
            continue
        paths[spec.table_name] = path

    if errors:
        raise VocabularyError(
            "Athena extract preflight failed:\n- " + "\n- ".join(errors)
        )
    return paths


def iter_table_rows(
    spec: TableSpec, path: Path, delimiter: str
) -> Iterator[tuple[Any, ...]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter, quotechar='"')
        next(reader)
        for line_number, raw_row in enumerate(reader, start=2):
            if not raw_row or all(value == "" for value in raw_row):
                continue
            if len(raw_row) != len(spec.columns):
                raise VocabularyError(
                    f"{path.name}:{line_number}: expected {len(spec.columns)} "
                    f"fields, found {len(raw_row)}"
                )
            yield tuple(
                _convert_value(value, kind, path.name, line_number)
                for value, kind in zip(raw_row, spec.kinds)
            )


def inspect_extract(vocab_dir: Path, delimiter: str) -> dict[str, int]:
    paths = validate_source_files(vocab_dir, delimiter)
    return {
        spec.table_name: sum(
            1 for _ in iter_table_rows(spec, paths[spec.table_name], delimiter)
        )
        for spec in TABLE_SPECS
    }
