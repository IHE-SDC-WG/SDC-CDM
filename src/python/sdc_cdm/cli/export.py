"""CLI command that writes the OMOP tables as a CSV bundle with manifest.json."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.cli.target import open_backend
from sdc_cdm.export import export_bundle


def configure_export(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "output_dir", type=Path, metavar="OUTPUT_DIR",
        help="new or empty directory to write the bundle to",
    )
    parser.add_argument(
        "--include-vocabulary", action="store_true",
        help="also write the nine Athena vocabulary tables",
    )


def run_export_command(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        result = export_bundle(
            backend, args.output_dir, include_vocabulary=args.include_vocabulary,
        )
    print("file | rows | sha256")
    for table in result.tables:
        print(f"{table.file} | {table.rows} | {table.sha256}")
    print(f"export wrote {len(result.tables)} tables to {result.output_dir} "
          f"(run {result.run_id})")
    return 0
