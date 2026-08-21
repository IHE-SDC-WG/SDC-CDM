"""Shared database-target arguments and backend construction."""

from __future__ import annotations

import argparse
import os
from contextlib import AbstractContextManager
from pathlib import Path

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import UsageError
from sdc_cdm.db.manifest import SUPPORTED_DIALECTS
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend


def add_target_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared database-target arguments to parser."""

    parser.add_argument("--dialect", choices=SUPPORTED_DIALECTS, required=True)
    parser.add_argument("--db", type=Path, help="SQLite control database path")
    parser.add_argument(
        "--connection-string", help="complete SQL Server ODBC connection string"
    )


def open_backend(
    args: argparse.Namespace, *, read_only: bool
) -> AbstractContextManager[DatabaseBackend]:
    """Open the database backend selected by parsed target arguments."""

    if args.dialect == "sqlite":
        if args.db is None:
            raise UsageError("SQLite build requires --db")
        return SQLiteBackend(args.db, read_only=read_only)

    connection_string = args.connection_string or os.environ.get(
        "SDC_CDM_SQLSERVER_CONNECTION_STRING"
    )
    if not connection_string:
        raise UsageError(
            "SQL Server build requires --connection-string or "
            "SDC_CDM_SQLSERVER_CONNECTION_STRING"
        )
    return SqlServerBackend(connection_string)
