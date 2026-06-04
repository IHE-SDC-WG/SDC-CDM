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

REVIEW_FIELDS = (
    "review_status",
    "reviewer",
    "reviewed_at",
    "review_notes",
    "rationale",
    "target_override_table",
    "target_override_field",
    "needs_wg_decision",
)

REVIEW_DEFAULTS = {
    "review_status": "unreviewed",
    "reviewer": None,
    "reviewed_at": None,
    "review_notes": None,
    "rationale": None,
    "target_override_table": None,
    "target_override_field": None,
    "needs_wg_decision": False,
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


def normalized_storage(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("_", " ")


def person_mapping_key(row: dict[str, Any]) -> str:
    concept_id = row.get("naaccr_concept_id")
    concept_code = row.get("field_code")
    if concept_id is None or concept_code is None:
        return "::"
    return f"{concept_id}::{concept_code}"


def item_person_mapping_key(mapping: dict[str, Any]) -> str:
    concept_id = mapping.get("concept_id")
    concept_code = mapping.get("concept_code")
    if concept_id is None or concept_code is None:
        return "::"
    return f"{concept_id}::{concept_code}"


def person_mapping_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = person_mapping_key(row)
        if key == "::":
            continue
        if key in index:
            raise ValueError(f"Duplicate NAACCR_PERSON mapping key: {key}")
        index[key] = row
    return index


def person_target_table(row: dict[str, Any]) -> str | None:
    storage = normalized_storage(row.get("suggested_storage"))
    storage_tables = {
        "OMOP PERSON": "PERSON",
        "OMOP LOCATION": "LOCATION",
        "OMOP DEATH": "DEATH",
        "OMOP OBSERVATION": "OBSERVATION",
        "NAACCR PERSON": "NAACCR_PERSON",
    }
    if storage in storage_tables:
        return storage_tables[storage]

    target = str(row.get("omop_target") or "").strip().lower()
    for table in ("person", "location", "death", "observation", "naaccr_person"):
        if target.startswith(table):
            return table.upper()
    return None


def person_mapping_kind(row: dict[str, Any]) -> str:
    storage = normalized_storage(row.get("suggested_storage"))
    if storage == "OMOP OBSERVATION":
        return "OMOP_OBSERVATION"
    if storage.startswith("OMOP "):
        return "OMOP_CORE"
    if storage == "NAACCR PERSON":
        return "NAACCR_PERSON"
    return storage.replace(" ", "_") or "UNSPECIFIED"


def clean_person_column(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.split("(", 1)[0].strip() or text


def person_omop_field(row: dict[str, Any], table: str | None) -> str | None:
    target = row.get("omop_target")
    if target is None:
        return None
    target_text = str(target).strip()
    if not target_text:
        return None

    if table:
        prefix = f"{table.lower()}."
        if target_text.lower().startswith(prefix):
            return target_text[len(prefix) :]
    return target_text


def apply_person_mapping_override(
    mapping: dict[str, Any],
    person_mapping: dict[str, Any],
) -> dict[str, Any]:
    """Use the NAACCR_PERSON proposal as the effective mapping for patient rows."""
    table = person_target_table(person_mapping)
    storage = person_mapping.get("suggested_storage")
    person_column = clean_person_column(person_mapping.get("naaccr_person_column"))
    direct_person_column = normalized_storage(storage) == "NAACCR PERSON"

    mapping.update(
        {
            "person_mapping_applied": True,
            "person_mapping_source": person_mapping.get("source"),
            "suggested_storage": storage,
            "omop_target": person_mapping.get("omop_target"),
            "naaccr_person_column": person_column,
            "person_mapping_notes": person_mapping.get("notes"),
            "storage": storage,
            "mapping_kind": person_mapping_kind(person_mapping),
            "omop_table": table,
            "omop_field": person_omop_field(person_mapping, table),
            "proposed_extension_table": "NAACCR_PERSON" if direct_person_column else None,
            "proposed_extension_column": person_column if direct_person_column else None,
        }
    )
    return mapping


def mapping_key(mapping: dict[str, Any]) -> str:
    return f"{mapping.get('concept_class_id') or ''}::{mapping.get('concept_code') or ''}"


def existing_review_metadata(existing_spec: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not existing_spec:
        return {}

    preserved: dict[str, dict[str, Any]] = {}
    for mapping in existing_spec.get("workflow_input", {}).get("item_mappings", []):
        key = mapping_key(mapping)
        if key == "::":
            continue
        preserved[key] = {
            field: mapping.get(field, REVIEW_DEFAULTS[field])
            for field in REVIEW_FIELDS
        }
    return preserved


def review_metadata_for(
    mapping: dict[str, Any],
    preserved: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return dict(REVIEW_DEFAULTS, **preserved.get(mapping_key(mapping), {}))


def build_spec(input_dir: Path, existing_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    preserved_review = existing_review_metadata(existing_spec)
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
    person_mappings = person_mapping_index(naaccr_person["mapping"])
    matched_person_keys: set[str] = set()

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
            person_mapping = person_mappings.get(item_person_mapping_key(flattened))
            if person_mapping is not None:
                apply_person_mapping_override(flattened, person_mapping)
                matched_person_keys.add(person_mapping_key(person_mapping))
            flattened.update(review_metadata_for(flattened, preserved_review))
            flattened_items.append(flattened)

    unmatched_person_keys = sorted(set(person_mappings) - matched_person_keys)
    if unmatched_person_keys:
        raise ValueError(
            "NAACCR_PERSON mappings did not match concept-class rows: "
            + ", ".join(unmatched_person_keys[:10])
        )

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
            "naaccr_person_merge": {
                "matching_key": "concept_id + concept_code",
                "matched_rows": len(matched_person_keys),
                "unmatched_rows": len(unmatched_person_keys),
                "effective_mapping_rule": (
                    "Rows from NAACCR_PERSON_proposed.xlsx override generic "
                    "concept-class mappings when naaccr_concept_id + field_code "
                    "matches concept_id + concept_code."
                ),
            },
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
    existing_spec = None
    if args.output.as_posix() != "-" and args.output.exists():
        existing_spec = json.loads(args.output.read_text(encoding="utf-8"))
    spec = build_spec(args.input_dir, existing_spec=existing_spec)

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
