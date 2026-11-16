"""CLI command for explicit report-version supersession."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.bridge import supersede_and_refresh
from sdc_cdm.bridge.runner import DEFAULT_SEED_DIR
from sdc_cdm.cli.target import open_backend
from sdc_cdm.db.manifest import load_manifest


def configure_supersede(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("predecessor_id", type=int, help="sdc_report_id of the selected version")
    parser.add_argument("successor_id", type=int, help="sdc_report_id of the version to select")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR,
                        help="bridge seed directory (default: database/seed)")


def run_supersede(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        outcome = supersede_and_refresh(backend, load_manifest(), args.predecessor_id,
                                       args.successor_id, seed_dir=args.seed_dir)
    result = outcome.supersession
    print(f"sdc_report {result.successor_id} supersedes {result.predecessor_id} "
          f"(report group {result.report_group_id}, type {result.report_loinc!r}); "
          f"{result.successor_id} is selected; "
          f"bridge {'refreshed' if outcome.bridge_refreshed else 'not yet run for this group'} "
          f"(supersede run {outcome.run_id})")
    return 0
