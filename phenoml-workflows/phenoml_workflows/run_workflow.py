from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from .config import create_client, require_config
from .json_io import read_json, resolve_package_path, resolve_repo_path, write_json
from .mapper import map_naaccr_case_to_omop


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the NAACCR to OMOP workflow harness."
    )
    parser.add_argument(
        "--workflow",
        default="workflows/naaccr-to-omop.workflow.json",
        help="Workflow JSON path, package-relative by default.",
    )
    parser.add_argument(
        "--mapping-spec",
        default="database/naaccr_omop/naaccr_omop_extension_mapping_spec.json",
        help="Mapping spec path, repo-relative by default.",
    )
    parser.add_argument("--input", required=True, help="NAACCR case JSON input path.")
    parser.add_argument("--output", help="Write JSON output to a file instead of stdout.")
    parser.add_argument(
        "--require-phenoml",
        action="store_true",
        help="Require credentials and construct a PhenomlClient.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict:
    if args.require_phenoml:
        config = require_config()
        create_client(config)

    workflow = read_json(resolve_package_path(args.workflow))
    mapping_spec = read_json(resolve_repo_path(args.mapping_spec))
    source = read_json(resolve_package_path(args.input))
    rows = map_naaccr_case_to_omop(
        source=source,
        mapping_spec=mapping_spec,
        workflow=workflow,
    )

    return {
        "workflow": workflow["name"],
        "source_case_id": source.get("case_id"),
        "used_phenoml_client": args.require_phenoml,
        "rows": rows,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args)
    except Exception as error:
        print(str(error))
        return 1

    if args.output:
        write_json(resolve_package_path(args.output), result)
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
