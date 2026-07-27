#!/usr/bin/env python3
"""Import dbo.CCR_LabReportECP into the NAACCR and SDC schemas.

Each source row becomes:

* one ``sdc.sdc_report`` row, keyed by ``record_id``;
* one ``naaccr.naaccr_value`` row per valid clinical OBX answer.

This importer does not write clinical OMOP rows. Run the SQL Server
``database/etl/sqlserver/1_naaccr_sdc_to_omop.sql`` bridge as a separate step.

Usage:

  python tools/ccr_labreport_to_naaccr.py --dry-run --limit 5
  python tools/ccr_labreport_to_naaccr.py
  python tools/ccr_labreport_to_naaccr.py --test --limit 3
  python tools/ccr_labreport_to_naaccr.py --test -o out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyodbc
else:
    try:
        import pyodbc
    except ImportError:
        pyodbc = None  # type: ignore[assignment]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


REPORT_LOINC = "60568-3"
SOURCE_INSTANCE_PREFIX = "CCR_LabReportECP"
METADATA_LOINC_CODES = frozenset({"60573-3", "60572-5", "60574-1"})
REPORT_TEMPLATE_SOURCE_CODE = "60573-3"
REPORT_TEMPLATE_ID_CODE = "60572-5"
REPORT_TEMPLATE_VERSION_CODE = "60574-1"

_SDC_REPORT_COLUMNS = (
    "template_instance_id",
    "template_name",
    "template_version",
    "template_instance_guid",
    "person_id",
    "visit_occurrence_id",
    "provider_id",
    "report_text",
    "report_template_source",
    "report_template_id",
    "report_template_version_id",
    "tumor_site",
    "procedure_type",
    "specimen_laterality",
    "report_accession",
    "report_loinc",
    "is_duplicate_accession",
    "first_seen_report_id",
)

_NAACCR_VALUE_COLUMNS = (
    "person_id",
    "episode_key",
    "sdc_report_id",
    "report_accession",
    "schema_id_number",
    "item_num",
    "value_code",
    "value_num",
    "value_unit_source",
    "observation_date",
    "dd_version_id",
)

_SUMMARY_KEYS = (
    "reports",
    "naaccr_values",
    "metadata_skipped",
    "narrative_skipped",
    "invalid_item_skipped",
    "missing_persons",
    "already_imported",
)


def _load_dotenv() -> None:
    """Load simple KEY=VALUE entries from tools/.env when present."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def get_connection_string() -> str:
    _load_dotenv()
    server = os.environ.get("DB_SERVER", "localhost")
    database = os.environ.get("DB_NAME", "")
    user = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASSWORD", "")
    driver = os.environ.get("DB_DRIVER", "{ODBC Driver 18 for SQL Server}")
    port = os.environ.get("DB_PORT", "1433")
    trust_cert = os.environ.get("DB_TRUST_CERT", "yes")

    return (
        f"DRIVER={driver};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate={trust_cert};"
    )


def connect() -> pyodbc.Connection:
    if pyodbc is None:
        print("pyodbc is required. Install with: pip install pyodbc", file=sys.stderr)
        raise SystemExit(1)

    logger.info("Connecting to SQL Server")
    connection = pyodbc.connect(get_connection_string())
    connection.autocommit = False
    return connection


@dataclass
class ParsedOBX:
    """Parsed fields used by the CCR staging import."""

    set_id: int
    value_type: str
    identifier_code: str
    identifier_text: str
    coding_system: str
    value: str
    result_status: str
    observation_sub_id: str | None = None
    units: str | None = None
    observation_datetime: datetime | None = None
    performing_org: str | None = None
    performing_org_address: str | None = None
    responsible_observer_npi: str | None = None
    value_code: str | None = None
    value_text: str | None = None
    value_coding_system: str | None = None
    is_metadata: bool = False
    group_index: int = 0
    raw: dict[str, str] = field(default_factory=dict)


def _parse_hl7_datetime(value: str) -> datetime | None:
    """Parse the common date and datetime precisions used in OBX-14."""
    if not value:
        return None

    match = re.match(r"^(\d{8,14})", value.strip())
    if not match:
        return None
    digits = match.group(1)

    for width, fmt in (
        (14, "%Y%m%d%H%M%S"),
        (12, "%Y%m%d%H%M"),
        (10, "%Y%m%d%H"),
        (8, "%Y%m%d"),
    ):
        if len(digits) < width:
            continue
        try:
            return datetime.strptime(digits[:width], fmt)
        except ValueError:
            continue
    return None


def _parse_set_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_single_obx(
    segment: dict[str, str],
    group_index: int = 0,
) -> ParsedOBX | None:
    if not isinstance(segment, dict):
        return None

    identifier_parts = str(segment.get("3", "")).split("^")
    identifier_code = identifier_parts[0] if identifier_parts else ""
    identifier_text = identifier_parts[1] if len(identifier_parts) > 1 else ""
    coding_system = identifier_parts[2] if len(identifier_parts) > 2 else ""

    value = str(segment.get("5", ""))
    value_type = str(segment.get("2", "ST"))
    value_code: str | None = None
    value_text: str | None = None
    value_coding_system: str | None = None
    if value_type == "CWE" and value:
        value_parts = value.split("^")
        value_code = value_parts[0] if value_parts else None
        value_text = value_parts[1] if len(value_parts) > 1 else None
        value_coding_system = value_parts[2] if len(value_parts) > 2 else None

    organization = str(segment.get("23") or segment.get("15") or "")
    responsible_observer = str(segment.get("25") or "")
    address = str(segment.get("24") or "")

    return ParsedOBX(
        set_id=_parse_set_id(segment.get("1")),
        value_type=value_type,
        identifier_code=identifier_code,
        identifier_text=identifier_text,
        coding_system=coding_system,
        value=value,
        result_status=str(segment.get("11", "")),
        observation_sub_id=str(segment.get("4")) if segment.get("4") else None,
        units=str(segment.get("6")) if segment.get("6") else None,
        observation_datetime=_parse_hl7_datetime(str(segment.get("14", ""))),
        performing_org=organization.split("^")[0] if organization else None,
        performing_org_address=address or None,
        responsible_observer_npi=(
            responsible_observer.split("^")[0] if responsible_observer else None
        ),
        value_code=value_code,
        value_text=value_text,
        value_coding_system=value_coding_system,
        is_metadata=identifier_code in METADATA_LOINC_CODES,
        group_index=group_index,
        raw=segment,
    )


def parse_obx_segments(json_text: str) -> list[ParsedOBX]:
    """Parse flat or nested OBX JSON arrays from CCR_LabReportECP."""
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse OBXCAPECPSegment JSON")
        return []

    if not isinstance(data, list):
        logger.warning("OBXCAPECPSegment is not a JSON array")
        return []

    parsed: list[ParsedOBX] = []
    nested = any(isinstance(item, list) for item in data)
    if nested:
        for group_index, group in enumerate(data):
            if not isinstance(group, list):
                continue
            for segment in group:
                obx = _parse_single_obx(segment, group_index)
                if obx is not None:
                    parsed.append(obx)
    else:
        for segment in data:
            obx = _parse_single_obx(segment)
            if obx is not None:
                parsed.append(obx)
    return parsed


def source_instance_guid(record_id: Any) -> str:
    if record_id is None or str(record_id).strip() == "":
        raise ValueError("CCR row is missing record_id")
    return f"{SOURCE_INSTANCE_PREFIX}:{record_id}"


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"CCR row is missing {key}")
    return str(value)


def _metadata_value(obxs: Iterable[ParsedOBX], code: str) -> str | None:
    return next((obx.value for obx in obxs if obx.identifier_code == code), None)


def _first_matching_value(
    obxs: Iterable[ParsedOBX],
    *,
    text_fragments: tuple[str, ...],
    code_prefixes: tuple[str, ...] = (),
) -> str | None:
    for obx in obxs:
        text = obx.identifier_text.lower()
        if any(fragment in text for fragment in text_fragments) or any(
            obx.identifier_code.startswith(prefix) for prefix in code_prefixes
        ):
            return obx.value or None
    return None


def _report_narrative(obxs: Iterable[ParsedOBX]) -> str | None:
    return _first_matching_value(
        obxs,
        text_fragments=("comment",),
        code_prefixes=("2168.1000043",),
    )


def _observation_date(
    row: dict[str, Any],
    obx: ParsedOBX,
) -> date | None:
    if obx.observation_datetime is not None:
        return obx.observation_datetime.date()

    year_value = row.get("date_of_diagnosis_yyyy")
    if year_value in (None, ""):
        return None

    try:
        year = int(year_value)
        month = int(row.get("date_of_diagnosis_mm") or 1)
        return date(year, month, 1)
    except (TypeError, ValueError):
        logger.warning(
            "record_id=%s has an invalid diagnosis year/month",
            row.get("record_id"),
        )
        return None


def _numeric_value(obx: ParsedOBX) -> float | None:
    if obx.value_type not in {"NM", "ST"}:
        return None
    try:
        parsed = float(obx.value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _item_number(obx: ParsedOBX) -> int | None:
    item_text = obx.identifier_code.split(".", 1)[0]
    if not re.fullmatch(r"\d+", item_text):
        return None
    return int(item_text)


def build_sdc_report_resource(
    row: dict[str, Any],
    obxs: list[ParsedOBX],
) -> dict[str, Any]:
    """Build the SDC report header for one CCR source row."""
    record_id = _required_text(row, "record_id")
    template_id = _required_text(row, "ReporttemplateID")
    template_version = _required_text(row, "ReportTemplateVersionID")

    return {
        "template_instance_id": None,
        "template_name": template_id,
        "template_version": template_version,
        "template_instance_guid": source_instance_guid(record_id),
        "person_id": row.get("PatientID"),
        "visit_occurrence_id": None,
        "provider_id": None,
        "report_text": _report_narrative(obxs),
        "report_template_source": _metadata_value(obxs, REPORT_TEMPLATE_SOURCE_CODE),
        "report_template_id": (
            _metadata_value(obxs, REPORT_TEMPLATE_ID_CODE) or template_id
        ),
        "report_template_version_id": (
            _metadata_value(obxs, REPORT_TEMPLATE_VERSION_CODE) or template_version
        ),
        "tumor_site": _first_matching_value(
            obxs,
            text_fragments=("tumor site",),
            code_prefixes=("22371.100004300", "2118.1000043"),
        ),
        "procedure_type": _first_matching_value(
            obxs,
            text_fragments=("procedure",),
            code_prefixes=("51121.100004300", "820603.1000043"),
        ),
        "specimen_laterality": _first_matching_value(
            obxs,
            text_fragments=("specimen laterality", "tumor focality"),
            code_prefixes=("8722.100004300", "52756.1000043"),
        ),
        "report_accession": record_id,
        "report_loinc": REPORT_LOINC,
        "is_duplicate_accession": False,
        "first_seen_report_id": None,
    }


def build_naaccr_value_resource(
    row: dict[str, Any],
    obx: ParsedOBX,
    *,
    sdc_report_id: int | None = None,
) -> dict[str, Any] | None:
    """Build one NAACCR captured-value row or return None for an invalid item."""
    item_num = _item_number(obx)
    if item_num is None:
        return None

    numeric_value = _numeric_value(obx)
    value_code = None
    if numeric_value is None:
        value_code = obx.value_code if obx.value_type == "CWE" else obx.value

    return {
        "person_id": row.get("PatientID"),
        "episode_key": _required_text(row, "CTCID"),
        "sdc_report_id": sdc_report_id,
        "report_accession": _required_text(row, "record_id"),
        "schema_id_number": None,
        "item_num": item_num,
        "value_code": value_code or None,
        "value_num": numeric_value,
        "value_unit_source": obx.units,
        "observation_date": _observation_date(row, obx),
        "dd_version_id": None,
    }


def build_import_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Transform one CCR row without reading from or writing to the database."""
    obxs = parse_obx_segments(str(row.get("OBXCAPECPSegment") or ""))
    report = build_sdc_report_resource(row, obxs)
    values: list[dict[str, Any]] = []
    metadata_skipped = 0
    narrative_skipped = 0
    invalid_item_skipped = 0

    for obx in obxs:
        if obx.is_metadata:
            metadata_skipped += 1
            continue
        if obx.value_type == "ST" and len(obx.value) > 200:
            narrative_skipped += 1
            continue

        value = build_naaccr_value_resource(row, obx)
        if value is None:
            invalid_item_skipped += 1
            logger.warning(
                "record_id=%s: skipping OBX with non-integer item number %r",
                row.get("record_id"),
                obx.identifier_code,
            )
            continue
        values.append(value)

    return {
        "report": report,
        "values": values,
        "metadata_skipped": metadata_skipped,
        "narrative_skipped": narrative_skipped,
        "invalid_item_skipped": invalid_item_skipped,
    }


def fetch_lab_reports(
    cursor: pyodbc.Cursor,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch eligible CCR source rows in deterministic order."""
    top = f"TOP {int(limit)} " if limit is not None else ""
    query = f"""
        SELECT {top}
            record_id,
            sending_lab,
            date_of_diagnosis_yyyy,
            date_of_diagnosis_mm,
            ReporttemplateID,
            ReportTemplateVersionID,
            OBXCAPECPSegment,
            PatientID,
            CTCID
        FROM dbo.CCR_LabReportECP
        WHERE CTCID IS NOT NULL
          AND ReporttemplateID IS NOT NULL
          AND ReportTemplateVersionID IS NOT NULL
          AND OBXCAPECPSegment IS NOT NULL
          AND LEN(OBXCAPECPSegment) > 2
        ORDER BY record_id
    """
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, values)) for values in cursor.fetchall()]


def person_exists(cursor: pyodbc.Cursor, person_id: Any) -> bool:
    if person_id is None:
        return False
    cursor.execute(
        "SELECT 1 FROM omop.person WHERE person_id = ?",
        (person_id,),
    )
    return cursor.fetchone() is not None


def report_already_imported(cursor: pyodbc.Cursor, record_id: Any) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM sdc.sdc_report
        WHERE template_instance_guid = ?
        """,
        (source_instance_guid(record_id),),
    )
    return cursor.fetchone() is not None


def _insert_returning_id(
    cursor: pyodbc.Cursor,
    table: str,
    id_column: str,
    columns: tuple[str, ...],
    data: dict[str, Any],
) -> int:
    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"""
        INSERT INTO {table} ({column_sql})
        OUTPUT INSERTED.{id_column}
        VALUES ({placeholders})
        """,
        tuple(data[column] for column in columns),
    )
    inserted = cursor.fetchone()
    if inserted is None:
        raise RuntimeError(f"{table} insert did not return {id_column}")
    return int(inserted[0])


def _insert_row(
    cursor: pyodbc.Cursor,
    table: str,
    columns: tuple[str, ...],
    data: dict[str, Any],
) -> None:
    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        tuple(data[column] for column in columns),
    )


def write_import_payload(
    cursor: pyodbc.Cursor,
    payload: dict[str, Any],
) -> int:
    """Write the report first, then its linked NAACCR captured values."""
    sdc_report_id = _insert_returning_id(
        cursor,
        "sdc.sdc_report",
        "sdc_report_id",
        _SDC_REPORT_COLUMNS,
        payload["report"],
    )
    for source_value in payload["values"]:
        value = dict(source_value, sdc_report_id=sdc_report_id)
        _insert_row(
            cursor,
            "naaccr.naaccr_value",
            _NAACCR_VALUE_COLUMNS,
            value,
        )
    return sdc_report_id


def _empty_counts() -> dict[str, Any]:
    return {key: 0 for key in _SUMMARY_KEYS}


def _payload_counts(payload: dict[str, Any]) -> dict[str, Any]:
    counts = _empty_counts()
    counts.update(
        {
            "reports": 1,
            "naaccr_values": len(payload["values"]),
            "metadata_skipped": payload["metadata_skipped"],
            "narrative_skipped": payload["narrative_skipped"],
            "invalid_item_skipped": payload["invalid_item_skipped"],
        }
    )
    return counts


def _merge_counts(total: dict[str, Any], update: dict[str, Any]) -> None:
    for key in _SUMMARY_KEYS:
        total[key] += update.get(key, 0)


def prepare_import(
    cursor: pyodbc.Cursor,
    row: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Validate database prerequisites and return a pure import payload."""
    if not person_exists(cursor, row.get("PatientID")):
        logger.warning(
            "record_id=%s: skipping missing omop.person person_id=%s",
            row.get("record_id"),
            row.get("PatientID"),
        )
        return "missing_person", None
    if report_already_imported(cursor, row.get("record_id")):
        logger.info(
            "record_id=%s: already imported",
            row.get("record_id"),
        )
        return "already_imported", None
    return "ready", build_import_payload(row)


def process_row(
    cursor: pyodbc.Cursor,
    row: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate, transform, and optionally write one source row."""
    status, payload = prepare_import(cursor, row)
    if status == "missing_person":
        counts = _empty_counts()
        counts["missing_persons"] = 1
        return counts
    if status == "already_imported":
        counts = _empty_counts()
        counts["already_imported"] = 1
        return counts

    assert payload is not None
    counts = _payload_counts(payload)
    if dry_run:
        logger.info(
            "[DRY RUN] record_id=%s report=1 naaccr_values=%d",
            row.get("record_id"),
            counts["naaccr_values"],
        )
    else:
        write_import_payload(cursor, payload)
    return counts


def import_rows(
    connection: pyodbc.Connection,
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import rows and roll back the current batch if a write fails."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    row_list = list(rows)
    totals = _empty_counts()
    missing_person_ids: list[Any] = []
    cursor = connection.cursor()
    try:
        for index, row in enumerate(row_list, 1):
            logger.info(
                "Processing row %d/%d record_id=%s",
                index,
                len(row_list),
                row.get("record_id"),
            )
            row_counts = process_row(cursor, row, dry_run=dry_run)
            _merge_counts(totals, row_counts)
            if row_counts["missing_persons"]:
                missing_person_ids.append(row.get("PatientID"))
            if not dry_run and index % batch_size == 0:
                connection.commit()
                logger.info("Committed batch through row %d", index)

        if not dry_run:
            connection.commit()
        return dict(totals, missing_person_ids=missing_person_ids)
    except Exception:
        if not dry_run:
            connection.rollback()
        raise
    finally:
        cursor.close()


def build_test_output(
    cursor: pyodbc.Cursor,
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build the read-only JSON preview used by --test."""
    row_results: list[dict[str, Any]] = []
    totals = _empty_counts()
    missing_person_ids: list[Any] = []
    row_list = list(rows)

    for row in row_list:
        status, payload = prepare_import(cursor, row)
        resources: list[dict[str, Any]] = []
        if status == "ready":
            assert payload is not None
            _merge_counts(totals, _payload_counts(payload))
            resources.append({"table": "sdc_report", **payload["report"]})
            resources.extend(
                {"table": "naaccr_value", **value} for value in payload["values"]
            )
        elif status == "missing_person":
            totals["missing_persons"] += 1
            missing_person_ids.append(row.get("PatientID"))
        else:
            totals["already_imported"] += 1

        row_results.append(
            {
                "record_id": row.get("record_id"),
                "person_id": row.get("PatientID"),
                "status": status,
                "resources": resources,
            }
        )

    return {
        "summary": {
            "mode": "test",
            "rows_fetched": len(row_list),
            **totals,
            "missing_person_ids": missing_person_ids,
        },
        "rows": row_results,
    }


def _log_summary(rows_processed: int, totals: dict[str, Any]) -> None:
    logger.info("Import summary")
    logger.info("  Source rows:          %d", rows_processed)
    logger.info("  SDC reports:          %d", totals["reports"])
    logger.info("  NAACCR values:        %d", totals["naaccr_values"])
    logger.info("  Metadata skipped:     %d", totals["metadata_skipped"])
    logger.info("  Narratives skipped:   %d", totals["narrative_skipped"])
    logger.info("  Invalid items skipped:%d", totals["invalid_item_skipped"])
    logger.info("  Missing persons:      %d", totals["missing_persons"])
    if totals.get("missing_person_ids"):
        logger.info(
            "  Missing person IDs:   %s",
            ", ".join(str(value) for value in totals["missing_person_ids"]),
        )
    logger.info("  Already imported:     %d", totals["already_imported"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import dbo.CCR_LabReportECP into the three-schema store.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate source rows without writing them.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N source rows.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Commit after every N source rows (default: 100).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Write a read-only JSON preview instead of database rows.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path for --test (default: etl_test_output.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be at least 1")

    connection = connect()
    try:
        source_cursor = connection.cursor()
        try:
            rows = fetch_lab_reports(
                source_cursor,
                limit=args.limit if not args.test else (args.limit or 5),
            )
        finally:
            source_cursor.close()

        if args.test:
            preview_cursor = connection.cursor()
            try:
                output = build_test_output(preview_cursor, rows)
            finally:
                preview_cursor.close()

            output_path = args.output or "etl_test_output.json"
            with open(output_path, "w", encoding="utf-8") as output_file:
                json.dump(output, output_file, indent=2, default=str)
                output_file.write("\n")
            logger.info("Test preview written to %s", output_path)
            _log_summary(len(rows), output["summary"])
            return 0

        totals = import_rows(
            connection,
            rows,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        _log_summary(len(rows), totals)
        return 0
    except Exception:
        logger.exception("CCR import failed")
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
