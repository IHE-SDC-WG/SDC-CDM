#!/usr/bin/env python3
"""Convert NAACCR-to-OMOP mapping workbooks into a JSON specification.

The PhenoML Workflows handoff is JSON-only, while the working-group mapping
inputs are XLSX files. This converter intentionally uses only Python's standard
library so the neutral SDC-CDM repo does not gain a PhenoML or Excel dependency.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

NS = {
    "a": SPREADSHEET_NS,
    "rel": RELATIONSHIP_NS,
}

REQUIRED_WORKBOOKS = {
    "extension_table_names": "extension_table_names.xlsx",
    "extension_tables_by_concept_class": "NAACCR_OMOP_Extension_Tables_by_ConceptClass.xlsx",
    "naaccr_person": "NAACCR_PERSON_proposed.xlsx",
}


def col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0

    idx = 0
    for char in match.group(1):
        idx = idx * 26 + ord(char) - ord("A") + 1
    return idx - 1


def clean_string(value: str) -> str:
    return value.replace("\xa0", " ").strip()


def parse_number(value: str) -> int | float | str:
    value = value.strip()
    if value == "":
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", value) or re.fullmatch(
            r"[-+]?\d+[eE][-+]?\d+", value
        ):
            return float(value)
    except ValueError:
        return value
    return value


def read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []

    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    shared_strings: list[str] = []
    for string_item in root.findall("a:si", NS):
        parts = [
            text_node.text or ""
            for text_node in string_item.iter(f"{{{SPREADSHEET_NS}}}t")
        ]
        shared_strings.append(clean_string("".join(parts)))
    return shared_strings


def cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        inline_string = cell.find("a:is", NS)
        if inline_string is None:
            return ""
        return clean_string(
            "".join(text.text or "" for text in inline_string.iter(f"{{{SPREADSHEET_NS}}}t"))
        )

    value_node = cell.find("a:v", NS)
    if value_node is None or value_node.text is None:
        return ""

    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type == "b":
        return raw_value == "1"
    if cell_type in {"str", "e"}:
        return clean_string(raw_value)
    return parse_number(raw_value)


def trim_trailing_empty(row: list[Any]) -> list[Any]:
    while row and row[-1] in ("", None):
        row.pop()
    return row


def read_worksheet(zf: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[Any]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[Any]] = []

    for row_node in root.findall(".//a:sheetData/a:row", NS):
        row: list[Any] = []
        for cell in row_node.findall("a:c", NS):
            index = col_index(cell.attrib.get("r", "A1"))
            while len(row) <= index:
                row.append("")
            row[index] = cell_value(cell, shared_strings)
        rows.append(trim_trailing_empty(row))

    return rows


def workbook_sheets(path: Path) -> dict[str, list[list[Any]]]:
    with ZipFile(path) as zf:
        shared_strings = read_shared_strings(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

        targets_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall("rel:Relationship", NS)
        }

        sheets: dict[str, list[list[Any]]] = {}
        for sheet in workbook.find("a:sheets", {"a": SPREADSHEET_NS}) or []:
            name = sheet.attrib["name"]
            rel_id = sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]
            target = targets_by_id[rel_id].lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            sheets[name] = read_worksheet(zf, sheet_path, shared_strings)

    return sheets


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return clean_string(str(value))


def normalize_cell(value: Any) -> Any:
    if isinstance(value, str):
        value = clean_string(value)
        return value if value else None
    return value


def row_is_empty(row: list[Any]) -> bool:
    return all(normalize_cell(value) is None for value in row)


def rows_to_dicts(rows: list[list[Any]], header_row: int = 0) -> list[dict[str, Any]]:
    if len(rows) <= header_row:
        return []

    headers = [normalize_header(value) for value in rows[header_row]]
    dict_rows: list[dict[str, Any]] = []

    for row in rows[header_row + 1 :]:
        if row_is_empty(row):
            continue

        item: dict[str, Any] = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            value = normalize_cell(row[index]) if index < len(row) else None
            item[header] = value

        if any(value is not None for value in item.values()):
            dict_rows.append(item)

    return dict_rows


def rows_to_notes(rows: list[list[Any]]) -> list[list[Any]]:
    return [
        [normalize_cell(value) for value in row]
        for row in rows
        if not row_is_empty(row)
    ]


def source_file_info(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
    }


def is_yes(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    return None


def index_by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row[key]: row for row in rows if row.get(key) is not None}


def storage_kind(row: dict[str, Any]) -> str:
    storage = row.get("storage") or row.get("suggested_storage")
    if not storage:
        return "UNSPECIFIED"

    normalized = str(storage).upper().replace(" ", "_")
    if normalized.startswith("OMOP_"):
        return "OMOP_CORE"
    if normalized == "EXTENSION_TABLE_COLUMN":
        return "EXTENSION_TABLE_COLUMN"
    return normalized


def build_spec(input_dir: Path) -> dict[str, Any]:
    workbook_paths = {
        key: input_dir / filename for key, filename in REQUIRED_WORKBOOKS.items()
    }
    missing = [path.as_posix() for path in workbook_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing required workbook(s): {', '.join(missing)}")

    extension_name_sheets = workbook_sheets(workbook_paths["extension_table_names"])
    extension_table_sheets = workbook_sheets(
        workbook_paths["extension_tables_by_concept_class"]
    )
    person_sheets = workbook_sheets(workbook_paths["naaccr_person"])

    extension_inventory = rows_to_dicts(
        next(iter(extension_name_sheets.values()), []), header_row=0
    )
    inventory_by_class = index_by(extension_inventory, "concept_class_id")

    summary_rows = rows_to_dicts(extension_table_sheets["Summary_Tables"], header_row=0)
    summary_by_class = index_by(summary_rows, "concept_class_id")
    foreign_keys = rows_to_dicts(extension_table_sheets["FK_Relationships"], header_row=0)

    concept_classes: dict[str, Any] = {}
    flattened_items: list[dict[str, Any]] = []

    for sheet_name, rows in extension_table_sheets.items():
        if sheet_name in {"README", "Summary_Tables", "FK_Relationships"}:
            continue

        concepts = rows_to_dicts(rows, header_row=0)
        summary = summary_by_class.get(sheet_name, {})
        inventory = inventory_by_class.get(sheet_name, {})
        is_mappable = is_yes(inventory.get("IsMappable"))

        concept_classes[sheet_name] = {
            "concept_class_id": sheet_name,
            "concept_class_name": inventory.get("concept_class_name"),
            "concept_class_concept_id": inventory.get("concept_class_concept_id"),
            "is_mappable": is_mappable,
            "proposed_table": summary.get("proposed_table"),
            "grain": summary.get("grain"),
            "row_key": summary.get("row_key"),
            "required_foreign_keys": summary.get("required_foreign_keys"),
            "notes": summary.get("notes"),
            "concepts": concepts,
        }

        for concept in concepts:
            flattened = {
                "concept_class_id": sheet_name,
                "source_sheet": sheet_name,
                "is_mappable": is_mappable,
                "mapping_kind": storage_kind(concept),
                **concept,
            }
            flattened_items.append(flattened)

    naaccr_person = {
        "mapping": rows_to_dicts(person_sheets["NAACCR_PERSON_Mapping"], header_row=0),
        "ddl": rows_to_dicts(person_sheets["NAACCR_PERSON_DDL"], header_row=0),
        "storage_summary": rows_to_dicts(person_sheets["Summary"], header_row=2),
        "csv_inventory_notes": rows_to_notes(person_sheets["CSV_Inventory"]),
        "readme_notes": rows_to_notes(person_sheets["README"]),
        "omop_cdm_5_4_reference": rows_to_dicts(
            person_sheets["OMOP_CDM_5_4_Reference"], header_row=0
        ),
    }

    return {
        "schema_version": "0.1.0",
        "name": "NAACCR to OMOP extension mapping specification",
        "omop_cdm_version": "5.4",
        "purpose": (
            "Vendor-neutral JSON representation of the NAACCR extension-table "
            "workbooks for downstream ETL and PhenoML Workflows consumption."
        ),
        "pipeline_position": {
            "sdc_cdm_repo_path": "SQL_SERVER_DIRECT_STAGING_TO_OMOP",
            "workflow_handoff_path": "NAACCR_XML_OR_V2_TO_JSON_TO_PHENOML_WORKFLOW_TO_OMOP_ROWS",
            "workflows_repo_boundary": (
                "PhenoML auth, workflow definitions, and execution harness live "
                "under phenoml-workflows/ in this repo. Credentials stay outside "
                "committed files."
            ),
        },
        "working_group_rules": {
            "default_target": (
                "Pathology and measurement-like NAACCR items, including SSDIs, "
                "grades, staging, and constrained pick lists, default to MEASUREMENT."
            ),
            "extension_table_use": (
                "Demographic, registry-management, confidential, and other "
                "NAACCR-specific fields remain in extension tables unless they "
                "map cleanly into OMOP core."
            ),
            "foreign_key_policy": (
                "Foreign keys live on the NAACCR extension-table side and point "
                "to OMOP records."
            ),
            "omop_core_policy": "Do not add non-FK NAACCR fields to OMOP core tables.",
            "mapping_direction": "CAP_TO_NAACCR_TO_MEASUREMENT",
        },
        "references": {
            "local_diagrams": [
                "diagrams/original-omop/by-domain/clinical-events.mmd",
                "diagrams/original-omop/by-domain/eras-episodes-cohorts-metadata.mmd",
                "diagrams/sdc-sdm-modifications/by-domain/CancerCase.mmd",
            ],
            "ohdsi_cdm_v5_4": "https://ohdsi.github.io/CommonDataModel/cdm54.html",
            "ohdsi_legacy_cdm_wiki": "https://www.ohdsi.org/web/wiki/doku.php?id=documentation:cdm:common_data_model",
            "fhir_to_omop_ig": "https://build.fhir.org/ig/HL7/fhir-omop-ig/en/technical_artifacts.html",
            "phenoml_workflows": "https://developer.pheno.ml/docs/workflows",
            "wg_discussion_77": "https://github.com/IHE-SDC-WG/SDC-CDM/discussions/77",
            "wg_discussion_78": "https://github.com/IHE-SDC-WG/SDC-CDM/discussions/78",
        },
        "source_workbooks": {
            key: source_file_info(path) for key, path in workbook_paths.items()
        },
        "extension_table_inventory": extension_inventory,
        "extension_tables": {
            "summary": summary_rows,
            "foreign_keys": foreign_keys,
            "concept_classes": concept_classes,
        },
        "workflow_input": {
            "item_mappings": flattened_items,
            "naaccr_person_mapping": naaccr_person["mapping"],
        },
        "naaccr_person": naaccr_person,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert NAACCR-to-OMOP XLSX mapping workbooks into JSON."
    )
    parser.add_argument(
        "--input-dir",
        default="NAACRToOMOPmaps",
        type=Path,
        help="Directory containing the three mapping workbooks.",
    )
    parser.add_argument(
        "--output",
        default="database/naaccr_omop/naaccr_omop_extension_mapping_spec.json",
        type=Path,
        help="JSON output path, or '-' for stdout.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    spec = build_spec(args.input_dir)

    json_text = json.dumps(
        spec,
        ensure_ascii=True,
        indent=None if args.compact else 2,
        separators=(",", ":") if args.compact else None,
    )

    if args.output.as_posix() == "-":
        print(json_text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_text + "\n", encoding="utf-8")

    print(
        "Converted "
        f"{len(spec['extension_table_inventory'])} extension-table inventory rows, "
        f"{len(spec['extension_tables']['concept_classes'])} concept-class sheets, "
        f"{len(spec['workflow_input']['item_mappings'])} item mappings, and "
        f"{len(spec['naaccr_person']['mapping'])} NAACCR_PERSON mappings.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
