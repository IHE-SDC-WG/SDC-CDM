"""CLI commands for durable HL7 intake and OBR-level loading."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.cli.target import open_backend
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.hl7v2.parser import PARSER_NAME, PARSER_VERSION
from sdc_cdm.intake import ingest_message, load_message


def configure_ingest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", type=Path, help="HL7 ER7 files to retain and parse")
    parser.add_argument("--received-by", help="optional intake operator or system identifier")


def run_ingest(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        for path in args.files:
            result = ingest_message(
                backend, path.read_bytes(), parse_hl7,
                parser_name=PARSER_NAME, parser_version=PARSER_VERSION,
                received_by=args.received_by,
            )
            print(f"{path}: intake {result.inbound_message_id}, {result.parse_status}, "
                  f"{result.envelope_count} envelopes, duplicate={result.is_content_duplicate}")
    return 0


def configure_load(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("message_ids", nargs="+", type=int, help="intake message IDs to load")
    parser.add_argument("--algorithm", required=True, help="current NAACCR dictionary algorithm")


def run_load(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        for message_id in args.message_ids:
            result = load_message(backend, message_id, algorithm=args.algorithm)
            print(f"intake {message_id}: {result.report_count} reports, "
                  f"{result.value_count} values, {result.skipped_duplicate_messages} duplicate skipped")
    return 0
