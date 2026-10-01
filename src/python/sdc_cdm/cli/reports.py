"""CLI command for explicit report-version supersession."""

from __future__ import annotations

import argparse

from sdc_cdm.cli.target import open_backend
from sdc_cdm.reports import supersede_report


def configure_supersede(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("predecessor_id", type=int, help="sdc_report_id of the selected version")
    parser.add_argument("successor_id", type=int, help="sdc_report_id of the version to select")


def run_supersede(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        result = supersede_report(backend, args.predecessor_id, args.successor_id)
    print(f"sdc_report {result.successor_id} supersedes {result.predecessor_id} "
          f"(report group {result.report_group_id}, type {result.report_loinc!r}); "
          f"{result.successor_id} is selected")
    return 0
