#!/usr/bin/env python3
"""Convert CSV/TSV files into SQL INSERT statements.

Designed for simple data-loading workflows where you want a plain SQL script:
- Table name defaults to the input filename stem (e.g., DOMAIN.csv -> DOMAIN)
- Column list is taken from the header row
- Values are SQL-escaped and emitted as INSERT ... VALUES (...), (...);

Examples:
  python tools/csv_to_sql_insert.py out-egs/DOMAIN.csv > domain_inserts.sql
  python tools/csv_to_sql_insert.py out-egs/*.csv --batch-size 5000 -o inserts.sql

Notes:
- Autodetects delimiter (comma vs tab) and common quoting.
- Empty fields default to NULL (override with --empty-as-null false).
- Type inference is OFF by default to avoid accidental coercions (enable with --infer-types).
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, TextIO


@dataclass(frozen=True)
class Options:
    quote_identifiers: bool
    empty_as_null: bool
    infer_types: bool
    batch_size: int


def _quote_ident(name: str, *, enabled: bool) -> str:
    name = name.strip()
    if not enabled:
        return name
    return '"' + name.replace('"', '""') + '"'


def _sql_literal(value: str, *, options: Options) -> str:
    if value is None:
        return "NULL"

    # Preserve exact text as read from the CSV layer.
    if value == "" and options.empty_as_null:
        return "NULL"

    if options.infer_types:
        numeric = _try_parse_number(value)
        if numeric is not None:
            return numeric

    escaped = value.replace("'", "''")
    return "'" + escaped + "'"


def _try_parse_number(text: str) -> Optional[str]:
    """Return SQL numeric literal string if text is safely numeric, else None.

    Conservative on purpose:
    - Reject leading/trailing whitespace
    - Reject leading zeros for ints (except '0' or '-0') to avoid changing semantics
    """

    if text == "":
        return None
    if text != text.strip():
        return None

    # Integers
    neg = text.startswith("-")
    digits = text[1:] if neg else text
    if digits.isdigit():
        # Avoid coercing IDs like "00123" into 123
        if len(digits) > 1 and digits.startswith("0"):
            return None
        return text

    # Floats / scientific notation (still conservative)
    try:
        # float() accepts many things; ensure round-trippable-ish.
        f = float(text)
    except ValueError:
        return None

    # Reject NaN/Inf which some engines won't accept as numeric literals.
    if f != f or f in (float("inf"), float("-inf")):
        return None

    # Keep original spelling to avoid "1e-06" turning into "0.000001".
    # Only allow a limited character set.
    allowed = set("0123456789+-.eE")
    if any(ch not in allowed for ch in text):
        return None

    # Require at least one digit.
    if not any(ch.isdigit() for ch in text):
        return None

    return text


def _sniff_dialect(sample: str) -> csv.Dialect:
    sniffer = csv.Sniffer()

    # Heuristic: many "*.csv" in this repo are tab-delimited.
    if "\t" in sample and "," not in sample:
        dialect = csv.excel_tab
        dialect.delimiter = "\t"  # type: ignore[attr-defined]
        return dialect

    try:
        return sniffer.sniff(sample, delimiters=[",", "\t", ";", "|"])
    except csv.Error:
        # Fallback: tab if present, else comma.
        if "\t" in sample:
            dialect = csv.excel_tab
            dialect.delimiter = "\t"  # type: ignore[attr-defined]
            return dialect
        return csv.excel


def _chunks(iterable: Iterable[List[str]], size: int) -> Iterator[List[List[str]]]:
    batch: List[List[str]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def write_inserts_for_file(
    input_path: Path,
    out: TextIO,
    *,
    options: Options,
    table_name: Optional[str] = None,
) -> None:
    table = table_name if table_name is not None else input_path.stem

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(64 * 1024)
        f.seek(0)
        dialect = _sniff_dialect(sample)
        reader = csv.reader(f, dialect)

        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"Empty file: {input_path}")

        header = [h.strip() for h in header]

        q_table = _quote_ident(table, enabled=options.quote_identifiers)
        q_cols = ", ".join(
            _quote_ident(c, enabled=options.quote_identifiers) for c in header
        )

        def iter_rows() -> Iterator[List[str]]:
            for row in reader:
                # csv can return shorter rows; pad to header length.
                if len(row) < len(header):
                    row = list(row) + [""] * (len(header) - len(row))
                elif len(row) > len(header):
                    raise ValueError(
                        f"Row has {len(row)} fields but header has {len(header)} fields in {input_path}"
                    )
                yield row

        for batch in _chunks(iter_rows(), options.batch_size):
            out.write(f"INSERT INTO {q_table} ({q_cols}) VALUES\n")

            for i, row in enumerate(batch):
                values = ", ".join(_sql_literal(v, options=options) for v in row)
                suffix = ",\n" if i < len(batch) - 1 else "\n"
                out.write(f"  ({values})" + suffix)

            out.write(";\n")


def _parse_bool(text: str) -> bool:
    t = text.strip().lower()
    if t in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if t in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean, got: {text!r}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert CSV/TSV files into SQL INSERT statements using the filename as table name."
    )
    p.add_argument(
        "inputs",
        nargs="+",
        help="Input CSV/TSV file(s)",
    )
    p.add_argument(
        "-o",
        "--output",
        help="Output .sql file (default: stdout)",
    )
    p.add_argument(
        "--table",
        help="Override table name (applies only when a single input is provided)",
    )
    p.add_argument(
        "--quote-identifiers",
        type=_parse_bool,
        default=True,
        help="Whether to quote table/column identifiers with double quotes (default: true)",
    )
    p.add_argument(
        "--empty-as-null",
        type=_parse_bool,
        default=True,
        help="Treat empty fields as NULL (default: true)",
    )
    p.add_argument(
        "--infer-types",
        action="store_true",
        help="Infer numeric types and emit unquoted numbers (default: off)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows per INSERT statement (default: 1000)",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    ns = parse_args(argv)

    input_paths = [Path(p) for p in ns.inputs]
    for p in input_paths:
        if not p.exists():
            print(f"Input not found: {p}", file=sys.stderr)
            return 2

    if ns.table and len(input_paths) != 1:
        print("--table can only be used with a single input file", file=sys.stderr)
        return 2

    if ns.batch_size <= 0:
        print("--batch-size must be > 0", file=sys.stderr)
        return 2

    options = Options(
        quote_identifiers=bool(ns.quote_identifiers),
        empty_as_null=bool(ns.empty_as_null),
        infer_types=bool(ns.infer_types),
        batch_size=int(ns.batch_size),
    )

    if ns.output:
        out_path = Path(ns.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as out:
            for idx, input_path in enumerate(input_paths):
                if idx:
                    out.write("\n")
                write_inserts_for_file(
                    input_path,
                    out,
                    options=options,
                    table_name=ns.table,
                )
    else:
        out = sys.stdout
        for idx, input_path in enumerate(input_paths):
            if idx:
                out.write("\n")
            write_inserts_for_file(
                input_path,
                out,
                options=options,
                table_name=ns.table,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
