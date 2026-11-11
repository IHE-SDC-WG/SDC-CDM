"""CLI command for the manifest-ordered OMOP bridge."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.bridge import run_bridge
from sdc_cdm.bridge.runner import DEFAULT_SEED_DIR
from sdc_cdm.cli.target import open_backend
from sdc_cdm.db.manifest import load_manifest


def configure_bridge(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--seed-dir", type=Path, default=DEFAULT_SEED_DIR,
        help="directory holding cdm_source.csv (default: database/seed)",
    )


def run_bridge_command(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    with open_backend(args, read_only=False) as backend:
        result = run_bridge(backend, manifest, seed_dir=args.seed_dir)
    for script in result.scripts:
        print(script.path)
        for table, count in script.row_counts:
            print(f"  {table} | {count}")
    print(f"bridge run {result.run_id} succeeded")
    return 0
