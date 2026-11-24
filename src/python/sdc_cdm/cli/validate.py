"""CLI command for the manifest-ordered validation of the bridge's OMOP output."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.bridge.runner import DEFAULT_SEED_DIR
from sdc_cdm.bridge.validate import run_validate
from sdc_cdm.cli.target import open_backend
from sdc_cdm.db.manifest import load_manifest


def configure_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--seed-dir", type=Path, default=DEFAULT_SEED_DIR,
        help="directory holding validate_thresholds.csv (default: database/seed)",
    )


def run_validate_command(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    with open_backend(args, read_only=False) as backend:
        result = run_validate(backend, manifest, seed_dir=args.seed_dir)
    print("check | category | actual | limit | PASS/FAIL")
    for check in result.checks:
        limit = "-" if check.limit is None else str(check.limit)
        print(f"{check.name} | {check.category} | {check.actual} | {limit} | {check.status}")
    if result.failures:
        print(f"validate FAIL: {'; '.join(result.failures)}")
        return 1
    print(f"validate PASS (run {result.run_id})")
    return 0
