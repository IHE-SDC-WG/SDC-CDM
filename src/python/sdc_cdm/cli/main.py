"""SDC-CDM command-line parser."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.errors import MigrationHashMismatch, SdcCdmError, UsageError
from sdc_cdm.db.manifest import SUPPORTED_DIALECTS, load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend


def registered_commands() -> tuple[str, ...]:
    return ("build",)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdc-cdm")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="apply the ordered database manifest")
    build.add_argument("--dialect", choices=SUPPORTED_DIALECTS, required=True)
    build.add_argument("--db", type=Path, help="SQLite control database path")
    build.add_argument("--connection-string", help="complete SQL Server ODBC connection string")
    build.add_argument("--list", action="store_true", help="list apply order without connecting")
    build.add_argument("--dry-run", action="store_true", help="show ledger decisions without writes")
    build.add_argument(
        "--accept-changed-hashes",
        action="store_true",
        help="update changed immutable hashes without executing their SQL",
    )
    return parser


def _run_build(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    if args.list:
        for index, entry in enumerate(manifest.entries_for(args.dialect), start=1):
            print(f"{index:02d} {entry.schema:<7} {entry.path}")
        return 0

    if args.dialect == "sqlite":
        if args.db is None:
            raise UsageError("SQLite build requires --db")
        backend = SQLiteBackend(args.db, read_only=args.dry_run)
    else:
        connection_string = args.connection_string or os.environ.get(
            "SDC_CDM_SQLSERVER_CONNECTION_STRING"
        )
        if not connection_string:
            raise UsageError(
                "SQL Server build requires --connection-string or "
                "SDC_CDM_SQLSERVER_CONNECTION_STRING"
            )
        backend = SqlServerBackend(connection_string)

    with backend:
        actions = BuildRunner(
            manifest,
            backend,
            accept_changed_hashes=args.accept_changed_hashes,
        ).run(dry_run=args.dry_run)
    for action in actions:
        print(f"{action.status.value:<17} {action.path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return _run_build(args)
        parser.error(f"unknown command: {args.command}")
    except MigrationHashMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except UsageError as exc:
        parser.error(str(exc))
    except (SdcCdmError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1
