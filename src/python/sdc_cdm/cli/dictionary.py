"""CLI argument configuration and handlers for ``dict`` commands."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sdc_cdm.cli.target import open_backend
from sdc_cdm.db.errors import UsageError, VocabularyError
from sdc_cdm.naaccr.client import SeerApiClient
from sdc_cdm.naaccr.csv_io import DEFAULT_CSV_DIR
from sdc_cdm.naaccr.fetch import fetch_dictionary
from sdc_cdm.naaccr.load import load_dictionary
from sdc_cdm.naaccr.ssdi import fetch_ssdi
from sdc_cdm.naaccr.verify import verify_dictionary


def configure_dict_fetch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--version", default="25", help="NAACCR dictionary version (default: 25)"
    )
    parser.add_argument(
        "--algorithm",
        default="eod_public",
        help="staging algorithm recorded in the shared version row",
    )
    parser.add_argument(
        "--staging-version",
        default="3.3",
        help="staging version recorded in the shared version row",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help="CSV directory (default: repository out-egs)",
    )


def run_dict_fetch(args: argparse.Namespace) -> int:
    # --dialect is inherited for a uniform CLI target contract. Fetch is the
    # sole networked verb and intentionally does not open that target.
    api_key = os.environ.get("SEER_API_KEY", "")
    if not api_key:
        raise UsageError("dict fetch requires SEER_API_KEY")
    result = fetch_dictionary(
        SeerApiClient(api_key),
        naaccr_version=args.version,
        algorithm=args.algorithm,
        algorithm_version=args.staging_version,
        output_dir=args.csv_dir,
    )
    print(f"NAACCR version | {result.naaccr_version}")
    print(f"items | {result.item_count}")
    print(f"live items | {result.live_item_count}")
    print(f"retired items | {result.retired_item_count}")
    print(f"sections | {result.section_count}")
    print(f"allowed codes | {result.allowed_code_count}")
    print(f"registry requirements | {result.registry_requirement_count}")
    print(f"wrote CSVs | {args.csv_dir}")
    return 0


def configure_ssdi_fetch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--algorithm",
        default="eod_public",
        help="staging algorithm (default: eod_public)",
    )
    parser.add_argument(
        "--staging-version", default="3.3", help="staging version (default: 3.3)"
    )
    parser.add_argument(
        "--naaccr-version",
        required=True,
        help="NAACCR dictionary version recorded with the staging data",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help="CSV directory (default: repository out-egs)",
    )


def run_ssdi_fetch(args: argparse.Namespace) -> int:
    # As with dict fetch, the inherited target is not opened.
    api_key = os.environ.get("SEER_API_KEY", "")
    if not api_key:
        raise UsageError("ssdi fetch requires SEER_API_KEY")
    result = fetch_ssdi(
        SeerApiClient(api_key),
        algorithm=args.algorithm,
        staging_version=args.staging_version,
        naaccr_version=args.naaccr_version,
        output_dir=args.csv_dir,
    )
    print(f"generation | {result.algorithm}/{result.staging_version}")
    print(f"NAACCR version | {result.naaccr_version}")
    print(f"schemas | {result.schema_count}")
    print(f"items | {result.item_count}")
    print(f"tables | {result.table_count}")
    print(f"schema/table links | {result.involved_table_count}")
    print(f"wrote CSVs | {args.csv_dir}")
    return 0


def configure_dict_load(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help="CSV directory (default: repository out-egs)",
    )


def run_dict_load(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        result = load_dictionary(backend, csv_dir=args.csv_dir)
    print(f"dd_version_id | {result.dd_version_id}")
    print(f"generation | {result.algorithm}/{result.version}")
    for table, row_count in result.row_counts.items():
        print(f"{table} | {row_count}")
    print(f"SSDI dictionary stubs | {result.stub_item_count}")
    if result.stub_item_nums:
        print(
            "SSDI stub item_num values | "
            + ", ".join(str(value) for value in result.stub_item_nums[:10])
        )
    return 0


def configure_dict_verify(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--expect",
        type=Path,
        required=True,
        help="counts-only expectation JSON",
    )


def run_dict_verify(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=True) as backend:
        result = verify_dictionary(backend, expectation_path=args.expect)
    if result.failures:
        raise VocabularyError(f"dict verify failed: {result.failures[0]}")
    return 0
