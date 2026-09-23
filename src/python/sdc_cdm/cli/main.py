"""SDC-CDM command-line parser."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sdc_cdm.cdm.tables import TABLE_SPECS
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.dictionary import (
    configure_dict_fetch,
    configure_dict_load,
    configure_dict_verify,
    configure_ssdi_fetch,
    run_dict_fetch,
    run_dict_load,
    run_dict_verify,
    run_ssdi_fetch,
)
from sdc_cdm.cli.target import add_target_arguments, open_backend
from sdc_cdm.cli.maps import (
    configure_maps_build, configure_maps_coverage, run_maps_build, run_maps_coverage,
)
from sdc_cdm.db.errors import MigrationHashMismatch, SdcCdmError, UsageError
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.vocab.constants import resolve_constants
from sdc_cdm.vocab.extract import inspect_extract
from sdc_cdm.vocab.loader import load_vocab

_Configure = Callable[[argparse.ArgumentParser], None]
_Handler = Callable[[argparse.Namespace], int]


def _configure_build(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--list", action="store_true", help="list apply order without connecting"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show ledger decisions without writes"
    )
    parser.add_argument(
        "--accept-changed-hashes",
        action="store_true",
        help="update changed immutable hashes without executing their SQL",
    )


def _run_build(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    if args.list:
        for index, entry in enumerate(manifest.entries_for(args.dialect), start=1):
            print(f"{index:02d} {entry.schema:<7} {entry.path}")
        return 0

    with open_backend(args, read_only=args.dry_run) as backend:
        actions = BuildRunner(
            manifest,
            backend,
            accept_changed_hashes=args.accept_changed_hashes,
        ).run(dry_run=args.dry_run)
    for action in actions:
        print(f"{action.status.value:<17} {action.path}")
    return 0


def _configure_vocab_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--vocab-dir",
        type=Path,
        default=Path("database/vocab"),
        help="directory containing the extracted Athena files",
    )
    parser.add_argument(
        "--delimiter",
        choices=("tab", "comma"),
        default="tab",
        help="extract delimiter (default: tab)",
    )


def _configure_vocab_load(parser: argparse.ArgumentParser) -> None:
    _configure_vocab_source(parser)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="rows per database batch (default: 10000)",
    )


def _configure_vocab_check(parser: argparse.ArgumentParser) -> None:
    _configure_vocab_source(parser)


def _configure_constants_resolve(_parser: argparse.ArgumentParser) -> None:
    pass


def _delimiter(name: str) -> str:
    return "\t" if name == "tab" else ","


def _run_vocab_load(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        report = load_vocab(
            backend,
            args.vocab_dir,
            _delimiter(args.delimiter),
            batch_size=args.batch_size,
        )
    print("Athena vocabulary load completed.")
    for spec in TABLE_SPECS:
        print(f"  {spec.table_name}: {report.row_counts[spec.table_name]} rows")
    print("Loaded vocabulary versions:")
    for vocabulary_id, version in report.vocabulary_versions:
        print(f"  {vocabulary_id}: {version or '(not supplied)'}")
    return 0


def _run_vocab_check(args: argparse.Namespace) -> int:
    counts = inspect_extract(args.vocab_dir, _delimiter(args.delimiter))
    print("Athena extract is valid.")
    for spec in TABLE_SPECS:
        print(f"  {spec.file_name}: {counts[spec.table_name]} rows")
    return 0


def _run_constants_resolve(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        resolved = resolve_constants(backend)
    print("OMOP concept constants resolved.")
    for constant in resolved:
        print(f"  {constant.constant_name}: {constant.concept_id}")
    return 0


# (verb path, help text, argument configuration, handler). Siblings append one
# tuple each; a multi-word path such as ("vocab", "load") creates the "vocab"
# group on first use.
_VERBS: tuple[tuple[tuple[str, ...], str, _Configure, _Handler], ...] = (
    (("build",), "apply the ordered database manifest", _configure_build, _run_build),
    (
        ("dict", "fetch"),
        "fetch the NAACCR dictionary from SEER",
        configure_dict_fetch,
        run_dict_fetch,
    ),
    (
        ("dict", "load"),
        "load NAACCR dictionary CSVs",
        configure_dict_load,
        run_dict_load,
    ),
    (
        ("dict", "verify"),
        "verify loaded NAACCR dictionary counts",
        configure_dict_verify,
        run_dict_verify,
    ),
    (
        ("ssdi", "fetch"),
        "fetch the SSDI staging tables from SEER",
        configure_ssdi_fetch,
        run_ssdi_fetch,
    ),
    (
        ("vocab", "load"),
        "load an Athena extract into a fresh OMOP vocabulary",
        _configure_vocab_load,
        _run_vocab_load,
    ),
    (
        ("vocab", "check"),
        "validate and count an Athena extract",
        _configure_vocab_check,
        _run_vocab_check,
    ),
    (
        ("constants", "resolve"),
        "resolve tracked OMOP concept constants",
        _configure_constants_resolve,
        _run_constants_resolve,
    ),
    (("maps", "build"), "build NAACCR concept maps", configure_maps_build, run_maps_build),
    (("maps", "coverage"), "report concept map coverage", configure_maps_coverage, run_maps_coverage),
)

_TARGET = argparse.ArgumentParser(add_help=False)
add_target_arguments(_TARGET)


def registered_commands() -> tuple[str, ...]:
    return tuple(" ".join(path) for path, _help, _configure, _handler in _VERBS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdc-cdm")
    groups = {(): parser.add_subparsers(dest="command", required=True)}
    for path, help_text, configure, handler in _VERBS:
        group = groups[()]
        for depth, name in enumerate(path[:-1], start=1):
            prefix = path[:depth]
            if prefix not in groups:
                node = group.add_parser(name, help=f"{name} commands")
                groups[prefix] = node.add_subparsers(
                    dest="_".join((*prefix, "command")), required=True
                )
            group = groups[prefix]
        leaf = group.add_parser(path[-1], help=help_text, parents=[_TARGET])
        configure(leaf)
        leaf.set_defaults(_handler=handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args._handler(args)
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
