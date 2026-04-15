#!/usr/bin/env python3
"""
Reads etl_test_output.json and prints SQL-style query result sets.

Usage:
  python tools/simulate_sql_output.py                          # default file
  python tools/simulate_sql_output.py path/to/output.json      # custom file
  python tools/simulate_sql_output.py --tables episode,observation
  python tools/simulate_sql_output.py --pending-only            # just ref data
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional


def _col_width(rows: List[Dict[str, Any]], col: str, min_w: int = 4) -> int:
    """Compute display width for a column: max of header and all values."""
    widths = [len(col)]
    for r in rows:
        val = r.get(col)
        widths.append(len(_fmt(val)))
    return max(max(widths), min_w)


def _fmt(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    return str(val)


def _print_result_set(
    title: str,
    rows: List[Dict[str, Any]],
    columns: Optional[List[str]] = None,
) -> None:
    """Print rows as a SQL Server Management Studio-style result set."""
    if not rows:
        print(f"\n-- {title}")
        print("(0 rows affected)\n")
        return

    if columns is None:
        # Preserve key order from first row, then add any extras
        seen = set()
        columns = []
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    columns.append(k)

    widths = {c: _col_width(rows, c) for c in columns}

    header = " | ".join(c.ljust(widths[c]) for c in columns)
    sep = "-+-".join("-" * widths[c] for c in columns)

    print(f"\n-- {title}")
    print(header)
    print(sep)
    for r in rows:
        line = " | ".join(_fmt(r.get(c)).ljust(widths[c]) for c in columns)
        print(line)
    print(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''} affected)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate SQL output from ETL test JSON"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="etl_test_output.json",
        help="Path to the ETL test output JSON file",
    )
    parser.add_argument(
        "--tables",
        default=None,
        help="Comma-separated list of tables to show (e.g. episode,observation)",
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Only show pending reference data (vocabularies, concepts)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max rows per result set"
    )
    args = parser.parse_args()

    try:
        with open(args.file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    wanted = set(args.tables.split(",")) if args.tables else None

    # ---- Pending reference data -------------------------------------------
    pending = data.get("pending_reference_data", {})

    vocabs = pending.get("vocabularies_to_create", [])
    if vocabs and (not wanted or "vocabulary" in wanted or args.pending_only):
        _print_result_set(
            "SELECT * FROM dbo.vocabulary  -- (pending, to be created)",
            vocabs[: args.limit] if args.limit else vocabs,
        )

    concepts = pending.get("concepts_to_create", [])
    if concepts and (not wanted or "concept" in wanted or args.pending_only):
        _print_result_set(
            "SELECT * FROM dbo.concept  -- (pending, to be created)",
            concepts[: args.limit] if args.limit else concepts,
        )

    if args.pending_only:
        return

    # ---- Collect resources by table ---------------------------------------
    by_table: Dict[str, List[Dict[str, Any]]] = {}
    for row_block in data.get("rows", []):
        for resource in row_block.get("resources", []):
            tbl = resource.get("table", "unknown")
            if wanted and tbl not in wanted:
                continue
            by_table.setdefault(tbl, []).append(
                {k: v for k, v in resource.items() if k != "table"}
            )

    # ---- Print each table as a result set ---------------------------------
    table_order = ["episode", "observation", "measurement", "episode_event"]
    printed = set()

    def _non_null_columns(rows: List[Dict[str, Any]]) -> List[str]:
        """Return columns that have at least one non-NULL value."""
        all_cols: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    all_cols.append(k)
        return [c for c in all_cols if any(r.get(c) is not None for r in rows)]

    def _print_table(tbl: str, rows: List[Dict[str, Any]]) -> None:
        display_rows = rows[: args.limit] if args.limit else rows
        cols = _non_null_columns(display_rows)
        skipped = {c for c in {k for r in display_rows for k in r} if c not in cols}
        title = f"SELECT * FROM dbo.{tbl}"
        if skipped:
            title += f"  -- (omitting {len(skipped)} always-NULL columns)"
        _print_result_set(title, display_rows, columns=cols)

    for tbl in table_order:
        if tbl in by_table:
            _print_table(tbl, by_table[tbl])
            printed.add(tbl)

    # Any remaining tables not in the standard order
    for tbl, rows in sorted(by_table.items()):
        if tbl not in printed:
            _print_table(tbl, rows)

    # ---- Summary ----------------------------------------------------------
    summary = data.get("summary", {})
    if summary:
        print("-- ETL Test Summary")
        for k, v in summary.items():
            print(f"--   {k}: {v}")
        print()


if __name__ == "__main__":
    main()
