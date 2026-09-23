"""CLI for NAACCR concept maps."""

from __future__ import annotations

import argparse
from pathlib import Path

from sdc_cdm.cli.target import open_backend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.paths import repository_path
from sdc_cdm.maps.build import build_concept_maps
from sdc_cdm.maps.coverage import report_coverage


def configure_maps_build(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--algorithm", help="current dictionary algorithm")
    parser.add_argument("--seed-dir", type=Path, default=repository_path("database/seed"))


def run_maps_build(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=False) as backend:
        report = build_concept_maps(backend, algorithm=args.algorithm, csv_dir=args.seed_dir)
    print(f"generation | {report.algorithm}/{report.dd_version_id}")
    for scope, layers in (("item", report.item_layers), ("value", report.value_layers)):
        for layer in ("athena_standard", "curated_override", "local_mint"):
            print(f"{scope} {layer} | {layers.get(layer, 0)}")
    print(f"new allocations | {report.new_allocations}")
    print(f"reused allocations | {report.reused_allocations}")
    print(f"layer1_ambiguous | {report.layer1_ambiguous}")
    print(f"excluded items | {report.excluded_items}")
    return 0


def configure_maps_coverage(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--algorithm", help="current dictionary algorithm")
    parser.add_argument("--seed-dir", type=Path, default=repository_path("database/seed"))
    parser.add_argument("--expect", type=Path, help="counts-only expectation JSON")


def run_maps_coverage(args: argparse.Namespace) -> int:
    with open_backend(args, read_only=True) as backend:
        report = report_coverage(
            backend, algorithm=args.algorithm, csv_dir=args.seed_dir,
            expectation_path=args.expect,
        )
    print("scope | section | layer | count")
    for scope, section, layer, count in report.rows:
        print(f"{scope} | {section} | {layer} | {count}")
    for name in ("excluded_items", "schema_value_collisions", "foreign_captured_item_numbers"):
        print(f"{name} | {report.checks[name]}")
    if args.expect:
        print("check | expected | actual | PASS/FAIL")
        for name, expected, actual, passed in report.comparisons:
            print(f"{name} | {expected} | {actual} | {'PASS' if passed else 'FAIL'}")
    if report.failures:
        raise VocabularyError(f"maps coverage FAIL: {report.failures[0]}")
    if args.expect:
        print("maps coverage PASS")
    return 0
