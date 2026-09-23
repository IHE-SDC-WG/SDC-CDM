"""CSV contract shared by the NAACCR dictionary producer and loader."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.paths import repository_path

DEFAULT_CSV_DIR = repository_path("out-egs")


def write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> int:
    """Write an always-quoted UTF-8/LF CSV atomically and return its row count."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    count = 0
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(
                stream,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
            )
            writer.writerow(columns)
            for row in rows:
                writer.writerow("" if value is None else value for value in row)
                count += 1
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return count


def read_csv(
    directory: Path,
    filename: str,
    columns: Sequence[str],
    *,
    required: bool = True,
) -> list[dict[str, str]]:
    """Read one contract CSV, trimming every field like fast-csv's trim mode."""
    return [row for _line, row in read_csv_with_lines(directory, filename, columns, required=required)]


def read_csv_with_lines(
    directory: Path,
    filename: str,
    columns: Sequence[str],
    *,
    required: bool = True,
) -> list[tuple[int, dict[str, str]]]:
    """Read CSV records with their physical ending line, including quoted newlines."""

    path = directory / filename
    if not path.is_file():
        if not required:
            return []
        raise VocabularyError(f"required CSV not found: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            actual = tuple(reader.fieldnames or ())
            if actual != tuple(columns):
                raise VocabularyError(
                    f"{path} columns must be {tuple(columns)!r}, got {actual!r}"
                )
            rows: list[tuple[int, dict[str, str]]] = []
            for row in reader:
                line_number = reader.line_num
                if None in row:
                    raise VocabularyError(f"{path}:{line_number} has extra fields")
                rows.append((line_number, {
                    column: (row.get(column) or "").strip() for column in columns
                }))
            return rows
    except UnicodeDecodeError as exc:
        raise VocabularyError(f"{path} is not UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise VocabularyError(f"cannot parse {path}: {exc}") from exc


def read_single_row(
    directory: Path, filename: str, columns: Sequence[str]
) -> dict[str, str]:
    rows = read_csv(directory, filename, columns)
    if len(rows) != 1:
        raise VocabularyError(
            f"{directory / filename} must contain exactly one data row, got {len(rows)}"
        )
    return rows[0]
