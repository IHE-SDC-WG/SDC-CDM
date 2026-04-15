#!/usr/bin/env python3
"""
ETL: dbo.CCR_LabReportECP → OMOP CDM 5.4 (Episode-centric)

Reads rows from dbo.CCR_LabReportECP, parses the HL7v2 OBX JSON stored in
the OBXCAPECPSegment column, and inserts into OMOP CDM tables:

  - dbo.episode           One per lab report row (cancer pathology report)
  - dbo.observation       Most OBX segments (histology, grade, stage, etc.)
  - dbo.measurement       Numeric OBX segments (biomarkers, tumor size, etc.)
  - dbo.episode_event     Links each inserted fact back to its episode

Usage:
  # Set connection env vars (or create tools/.env file)
  export DB_SERVER=your_server
  export DB_NAME=your_database
  export DB_USER=your_user
  export DB_PASSWORD=your_password

  python tools/ccr_labreport_to_omop.py --dry-run --limit 5   # preview
  python tools/ccr_labreport_to_omop.py                        # full run
  python tools/ccr_labreport_to_omop.py --test --limit 3       # test → log file
  python tools/ccr_labreport_to_omop.py --test -o out.json     # custom output
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# OMOP Concept ID Configuration
# ---------------------------------------------------------------------------
# Adjust these to match your vocabulary / dbo.concept entries.
# The defaults are OMOP standard concept_ids where possible,
# and 0 (unmapped) where a local mapping is needed.
# ---------------------------------------------------------------------------
@dataclass
class ConceptConfig:
    """Central place for all OMOP concept_id references used by this ETL."""

    # -- Episode --
    # episode_concept_id: The type of episode.
    #   32528 = "Disease Episode" is a common OMOP convention for cancer cases.
    episode_concept_id: int = 32528

    # episode_type_concept_id: How the episode was derived.
    #   32879 = "Registry" (or 32817 = "EHR" if these come from the EHR)
    episode_type_concept_id: int = 32879

    # episode_object_concept_id: The clinical object of the episode.
    #   Use the SNOMED concept for the specific cancer when available, else 0.
    episode_object_concept_id: int = 0

    # -- Observation / Measurement type --
    #   Indicates data provenance.  32817 = "EHR".
    observation_type_concept_id: int = 32817
    measurement_type_concept_id: int = 32817

    # -- Episode_Event field concepts --
    # These tell OMOP which table the event_id column points to.
    # They reference the "field" concepts in the Metadata vocabulary.
    #   1147165 = observation.observation_id
    #   1147138 = measurement.measurement_id
    #   1147082 = procedure_occurrence.procedure_occurrence_id
    #   1147127 = condition_occurrence.condition_occurrence_id
    field_observation_id: int = 1147165
    field_measurement_id: int = 1147138
    field_procedure_id: int = 1147082
    field_condition_id: int = 1147127


# OBX LOINC codes that carry report-level metadata, not clinical observations.
METADATA_LOINC_CODES = frozenset(
    {
        "60573-3",  # Report template source
        "60572-5",  # Report template ID
        "60574-1",  # Report template version ID
    }
)


# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    """Best-effort load of a .env file next to this script."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as fh:
        for line in fh:
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
        print("pyodbc is required.  Install with:  pip install pyodbc", file=sys.stderr)
        sys.exit(1)
    conn_str = get_connection_string()
    logger.info("Connecting to SQL Server …")
    conn = pyodbc.connect(conn_str)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# ID Generator
# ---------------------------------------------------------------------------
class IdGenerator:
    """Sequential ID generator: starts from MAX(id)+1 for each table."""

    _TABLES = {
        "episode": "episode_id",
        "observation": "observation_id",
        "measurement": "measurement_id",
        "procedure_occurrence": "procedure_occurrence_id",
        "condition_occurrence": "condition_occurrence_id",
        "episode_event": None,  # composite key, no auto-id
    }

    def __init__(self, conn: pyodbc.Connection) -> None:
        self._conn = conn
        self._counters: Dict[str, int] = {}

    def _load_max(self, table: str, column: str) -> int:
        cur = self._conn.cursor()
        # table/column are from hardcoded _TABLES, not user input
        cur.execute(f"SELECT ISNULL(MAX([{column}]), 0) FROM dbo.[{table}]")
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else 0

    def next_id(self, table: str, column: str | None = None) -> int:
        if column is None:
            column = self._TABLES.get(table)
        if column is None:
            raise ValueError(f"No PK column configured for table '{table}'")
        key = f"{table}.{column}"
        if key not in self._counters:
            self._counters[key] = self._load_max(table, column)
        self._counters[key] += 1
        return self._counters[key]


# ---------------------------------------------------------------------------
# OBX Parsing & Classification
# ---------------------------------------------------------------------------
@dataclass
class ParsedOBX:
    """Parsed representation of one OBX segment from the JSON array."""

    set_id: int
    value_type: str  # ST, CWE, NM, TX, …
    identifier_code: str  # e.g. "37277.100004300"
    identifier_text: str  # e.g. "Histologic Type"
    coding_system: str  # e.g. "CAPECC", "LN"
    value: str
    result_status: str
    observation_sub_id: Optional[str] = None  # Field "4": sub-component grouping
    units: Optional[str] = None  # Field "6": units (e.g. "^^UCUM")
    observation_datetime: Optional[datetime] = None
    performing_org: Optional[str] = None  # Field "15" or "23"
    performing_org_address: Optional[str] = None
    responsible_observer_npi: Optional[str] = None
    value_code: Optional[str] = None  # Parsed code from field "5" (CWE types)
    value_text: Optional[str] = None  # Display text from field "5" (CWE types)
    value_coding_system: Optional[str] = None  # Coding system from field "5" (CWE)
    is_metadata: bool = False
    group_index: int = 0  # Which inner array this OBX came from (0-based)
    raw: Dict[str, str] = field(default_factory=dict)


def _parse_hl7_datetime(dt_str: str) -> Optional[datetime]:
    """Parse an HL7 datetime string (yyyyMMddHHmmss variants)."""
    if not dt_str:
        return None
    for fmt, width in (
        ("%Y%m%d%H%M%S", 14),
        ("%Y%m%d%H%M", 12),
        ("%Y%m%d", 8),
    ):
        try:
            return datetime.strptime(dt_str[:width], fmt)
        except (ValueError, IndexError):
            continue
    return None


def _parse_single_obx(seg: Dict[str, str], group_index: int = 0) -> Optional[ParsedOBX]:
    """Parse one OBX JSON object into a ParsedOBX."""
    if not isinstance(seg, dict):
        return None

    # Field "3": Observation Identifier  (code^text^coding_system)
    identifier = seg.get("3", "")
    id_parts = identifier.split("^")
    id_code = id_parts[0] if len(id_parts) > 0 else ""
    id_text = id_parts[1] if len(id_parts) > 1 else ""
    coding_sys = id_parts[2] if len(id_parts) > 2 else ""

    # Field "4": Observation Sub-ID (groups related sub-answers)
    sub_id = seg.get("4") or None

    # Field "6": Units  (e.g. "^^UCUM")
    units = seg.get("6") or None

    # Field "14": HL7 datetime
    obs_dt = _parse_hl7_datetime(seg.get("14", ""))

    # Performing Organization: prefer field "23", fall back to field "15"
    org_raw = seg.get("23") or seg.get("15") or ""
    performing_org = org_raw.split("^")[0] if org_raw else None

    # Performing Org Address: field "24"
    addr_raw = seg.get("24") or ""
    performing_org_address = addr_raw if addr_raw else None

    # Field "25": Responsible Observer  (NPI^last^first…)
    obs_raw = seg.get("25") or ""
    observer_npi = obs_raw.split("^")[0] if obs_raw else None

    # Field "5": Observation Value
    # For CWE (Coded With Exceptions): code^display^coding_system
    raw_value = seg.get("5", "")
    value_type = seg.get("2", "ST")
    val_code: Optional[str] = None
    val_text: Optional[str] = None
    val_coding_sys: Optional[str] = None
    if value_type == "CWE" and raw_value:
        val_parts = raw_value.split("^")
        val_code = val_parts[0] if len(val_parts) > 0 else None
        val_text = val_parts[1] if len(val_parts) > 1 else None
        val_coding_sys = val_parts[2] if len(val_parts) > 2 else None

    is_meta = id_code in METADATA_LOINC_CODES

    return ParsedOBX(
        set_id=int(seg.get("1", 0)),
        value_type=value_type,
        identifier_code=id_code,
        identifier_text=id_text,
        coding_system=coding_sys,
        value=raw_value,
        result_status=seg.get("11", ""),
        observation_sub_id=sub_id,
        units=units,
        observation_datetime=obs_dt,
        performing_org=performing_org,
        performing_org_address=performing_org_address,
        responsible_observer_npi=observer_npi,
        value_code=val_code,
        value_text=val_text,
        value_coding_system=val_coding_sys,
        is_metadata=is_meta,
        group_index=group_index,
        raw=seg,
    )


def parse_obx_segments(json_str: str) -> List[ParsedOBX]:
    """Parse the OBXCAPECPSegment JSON into structured objects.

    Handles two shapes:
      - Flat array:   [{obx}, {obx}, …]
      - Nested array: [[{obx}, …], [{obx}, …], …]  (multiple report sections)

    Empty inner arrays are skipped.
    """
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse OBXCAPECPSegment JSON")
        return []

    if not isinstance(data, list):
        logger.warning("OBXCAPECPSegment is not a JSON array")
        return []

    # Detect flat vs nested: check if first non-empty element is a dict or list
    is_nested = any(isinstance(item, list) for item in data)

    parsed: List[ParsedOBX] = []

    if is_nested:
        for group_idx, inner in enumerate(data):
            if not isinstance(inner, list) or not inner:
                continue
            for seg in inner:
                obx = _parse_single_obx(seg, group_index=group_idx)
                if obx is not None:
                    parsed.append(obx)
    else:
        for seg in data:
            obx = _parse_single_obx(seg, group_index=0)
            if obx is not None:
                parsed.append(obx)

    return parsed


def classify_obx(obx: ParsedOBX) -> str:
    """
    Classify an OBX into an OMOP target table.

    Returns one of: 'observation', 'measurement', 'skip'.

    Extend this function to route specific OBX codes to 'procedure',
    'condition', 'drug_exposure', etc. as your mapping matures.
    """
    if obx.is_metadata:
        return "skip"

    # Numeric value type → Measurement
    if obx.value_type == "NM":
        return "measurement"

    # Coded or string types from CAP eCC / LOINC → Observation
    # (histologic type, grade, stage, margins, etc.)
    return "observation"


# ---------------------------------------------------------------------------
# Concept Lookup  (cached queries against dbo.concept)
# ---------------------------------------------------------------------------
# Map HL7v2 coding-system names to OMOP vocabulary_id values.
_HL7_CODING_TO_VOCAB: Dict[str, str] = {
    "LN": "LOINC",
    "CAPECC": "CAPECC",  # CAP eCC (College of American Pathologists)
    "I9CDX": "ICD9CM",
    "I10": "ICD10CM",
    "SCT": "SNOMED",
}


class ConceptLookup:
    """Lazy, cache-backed lookup of concept_id from dbo.concept.

    When a concept is not found:
      - read_only=True  (test mode): assigns a synthetic id from 2_000_000_000+,
        records the stub in ``pending_concepts`` for reporting.
      - read_only=False (real mode): INSERTs into dbo.concept (and
        dbo.vocabulary / dbo.domain if needed), returns the new concept_id.
    """

    _CUSTOM_ID_START = 2_000_000_000

    def __init__(self, cursor: pyodbc.Cursor, *, read_only: bool = False) -> None:
        self._cursor = cursor
        self._cache: Dict[tuple, Optional[int]] = {}
        self._read_only = read_only
        self._next_custom_id: Optional[int] = None  # lazy
        self.pending_concepts: List[Dict[str, Any]] = []
        self.pending_vocabularies: List[Dict[str, Any]] = []
        self._ensured_vocabs: set[str] = set()

    # -- ID generation -------------------------------------------------------
    def _get_next_custom_id(self) -> int:
        if self._next_custom_id is None:
            if not self._read_only:
                self._cursor.execute(
                    "SELECT ISNULL(MAX(concept_id), %d - 1) FROM dbo.concept "
                    "WHERE concept_id >= %d"
                    % (self._CUSTOM_ID_START, self._CUSTOM_ID_START)
                )
                row = self._cursor.fetchone()
                self._next_custom_id = (
                    (int(row[0]) + 1) if row else self._CUSTOM_ID_START
                )
            else:
                self._next_custom_id = self._CUSTOM_ID_START
        cid = self._next_custom_id
        self._next_custom_id += 1
        return cid

    # -- Vocabulary ensurance ------------------------------------------------
    def _ensure_vocabulary(self, vocab_id: str) -> None:
        """Make sure *vocab_id* exists in dbo.vocabulary."""
        if not vocab_id or vocab_id in self._ensured_vocabs:
            return
        if not self._read_only:
            self._cursor.execute(
                "SELECT 1 FROM dbo.vocabulary WHERE vocabulary_id = ?", (vocab_id,)
            )
            if self._cursor.fetchone() is not None:
                self._ensured_vocabs.add(vocab_id)
                return
        vocab_names = {
            "CAPECC": "CAP electronic Cancer Checklists",
            "LOINC": "Logical Observation Identifiers Names and Codes",
            "ICD9CM": "ICD-9-CM",
            "ICD10CM": "ICD-10-CM",
            "SNOMED": "SNOMED",
        }
        vocab_stub = {
            "vocabulary_id": vocab_id,
            "vocabulary_name": vocab_names.get(vocab_id, vocab_id),
            "vocabulary_reference": "",
            "vocabulary_version": "",
            "vocabulary_concept_id": 0,
        }
        if self._read_only:
            if vocab_id not in self._ensured_vocabs:
                self.pending_vocabularies.append(vocab_stub)
        else:
            self._cursor.execute(
                "INSERT INTO dbo.vocabulary "
                "(vocabulary_id, vocabulary_name, vocabulary_reference, "
                "vocabulary_version, vocabulary_concept_id) "
                "VALUES (?, ?, ?, ?, ?)",
                vocab_stub["vocabulary_id"],
                vocab_stub["vocabulary_name"],
                vocab_stub["vocabulary_reference"],
                vocab_stub["vocabulary_version"],
                vocab_stub["vocabulary_concept_id"],
            )
            logger.info("  Created vocabulary: %s", vocab_id)
        self._ensured_vocabs.add(vocab_id)

    # -- Lookup (with auto-create) -------------------------------------------
    def lookup(
        self,
        concept_code: str,
        coding_system: str | None = None,
        *,
        concept_name: str = "",
        domain_id: str = "Observation",
        concept_class_id: str = "",
    ) -> Optional[int]:
        """Return concept_id for a code.  Creates the concept if missing."""
        if not concept_code:
            return None
        vocab = _HL7_CODING_TO_VOCAB.get(coding_system or "", "")
        key = (concept_code, vocab)
        if key in self._cache:
            return self._cache[key]

        # Try DB first
        found: Optional[int] = None
        if not self._read_only or True:  # always try DB when available
            if vocab:
                self._cursor.execute(
                    "SELECT concept_id FROM dbo.concept "
                    "WHERE concept_code = ? AND vocabulary_id = ?",
                    concept_code,
                    vocab,
                )
            else:
                self._cursor.execute(
                    "SELECT TOP 1 concept_id FROM dbo.concept "
                    "WHERE concept_code = ?",
                    (concept_code,),
                )
            row = self._cursor.fetchone()
            if row:
                found = int(row[0])

        if found is not None:
            self._cache[key] = found
            return found

        # --- Not found → auto-create ----------------------------------------
        self._ensure_vocabulary(vocab)
        new_id = self._get_next_custom_id()

        # Derive a concept_class from the coding system
        if not concept_class_id:
            concept_class_id = (
                "CAP Variable" if vocab == "CAPECC" else "Observable Entity"
            )

        concept_stub = {
            "concept_id": new_id,
            "concept_name": concept_name[:255] if concept_name else concept_code,
            "domain_id": domain_id,
            "vocabulary_id": vocab or "None",
            "concept_class_id": concept_class_id,
            "standard_concept": None,
            "concept_code": concept_code,
            "valid_start_date": "1970-01-01",
            "valid_end_date": "2099-12-31",
            "invalid_reason": None,
        }

        if self._read_only:
            self.pending_concepts.append(concept_stub)
        else:
            self._cursor.execute(
                "INSERT INTO dbo.concept "
                "(concept_id, concept_name, domain_id, vocabulary_id, "
                "concept_class_id, standard_concept, concept_code, "
                "valid_start_date, valid_end_date, invalid_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                new_id,
                concept_stub["concept_name"],
                concept_stub["domain_id"],
                concept_stub["vocabulary_id"],
                concept_stub["concept_class_id"],
                concept_stub["standard_concept"],
                concept_stub["concept_code"],
                date(1970, 1, 1),
                date(2099, 12, 31),
                None,
            )
            logger.info(
                "  Created concept %d: %s (%s / %s)",
                new_id,
                concept_stub["concept_name"],
                concept_stub["vocabulary_id"],
                concept_stub["concept_class_id"],
            )

        self._cache[key] = new_id
        return new_id


# ---------------------------------------------------------------------------
# OMOP Row Builders  (single source of truth for field computation)
# ---------------------------------------------------------------------------
def _best_date(row: Dict[str, Any], obx: ParsedOBX) -> date:
    """Pick the most specific date available."""
    if obx.observation_datetime:
        return obx.observation_datetime.date()
    yyyy = row.get("date_of_diagnosis_yyyy")
    mm = row.get("date_of_diagnosis_mm")
    if yyyy:
        month = int(mm) if mm else 1
        return date(int(yyyy), max(month, 1), 1)
    return date.today()


def build_episode_resource(
    row: Dict[str, Any],
    episode_id: int,
    metadata_obxs: List[ParsedOBX],
    concepts: ConceptConfig,
) -> Dict[str, Any]:
    """Build an episode dict.  Used by both insert and test paths."""
    yyyy = row.get("date_of_diagnosis_yyyy")
    mm = row.get("date_of_diagnosis_mm")
    if yyyy:
        month = int(mm) if mm else 1
        start_date = date(int(yyyy), max(month, 1), 1)
    else:
        start_date = date.today()

    return {
        "episode_id": episode_id,
        "person_id": row["PatientID"],
        "episode_concept_id": concepts.episode_concept_id,
        "episode_start_date": start_date,
        "episode_start_datetime": datetime.combine(start_date, datetime.min.time()),
        "episode_end_date": None,
        "episode_end_datetime": None,
        "episode_parent_id": None,
        "episode_number": None,
        "episode_object_concept_id": concepts.episode_object_concept_id,
        "episode_type_concept_id": concepts.episode_type_concept_id,
        "episode_source_value": str(row["record_id"]),
        "episode_source_concept_id": None,
    }


def build_observation_resource(
    row: Dict[str, Any],
    obx: ParsedOBX,
    obs_id: int,
    concepts: ConceptConfig,
    concept_lookup: Optional[ConceptLookup] = None,
) -> Dict[str, Any]:
    """Build an observation dict.  Used by both insert and test paths."""
    obs_date = _best_date(row, obx)

    # Concept lookup for the question (field "3")
    obs_concept_id = 0
    if concept_lookup:
        obs_concept_id = (
            concept_lookup.lookup(
                obx.identifier_code,
                obx.coding_system,
                concept_name=obx.identifier_text or "",
                domain_id="Observation",
                concept_class_id=(
                    "CAP Variable" if obx.coding_system == "CAPECC" else ""
                ),
            )
            or 0
        )

    # Defaults (non-CWE path)
    source_value = f"{obx.identifier_code}^{obx.identifier_text}^{obx.coding_system}"[
        :50
    ]
    source_concept_id: Optional[int] = None
    qualifier_source = None
    value_as_concept_id = None
    value_string = obx.value[:60] if obx.value else None
    value_source = obx.value[:50] if obx.value else None

    if obx.value_type == "CWE":
        # Question: display text → source_value, item ID → source_concept_id
        # (coding system is captured in the vocabulary, not repeated per row)
        source_value = obx.identifier_text[:50] if obx.identifier_text else None
        source_concept_id = obs_concept_id if obs_concept_id else None

        # Answer: display text → value_as_string, code → value_as_concept_id
        value_string = obx.value_text[:60] if obx.value_text else None
        if concept_lookup and obx.value_code:
            value_as_concept_id = concept_lookup.lookup(
                obx.value_code,
                obx.value_coding_system,
                concept_name=obx.value_text or "",
                domain_id="Observation",
                concept_class_id=(
                    "CAP Value" if obx.value_coding_system == "CAPECC" else ""
                ),
            )

    return {
        "observation_id": obs_id,
        "person_id": row["PatientID"],
        "observation_concept_id": obs_concept_id,
        "observation_date": obs_date,
        "observation_datetime": datetime.combine(obs_date, datetime.min.time()),
        "observation_type_concept_id": concepts.observation_type_concept_id,
        "value_as_number": None,
        "value_as_string": value_string,
        "value_as_concept_id": value_as_concept_id,
        "qualifier_concept_id": None,
        "unit_concept_id": None,
        "provider_id": None,
        "visit_occurrence_id": None,
        "visit_detail_id": None,
        "observation_source_value": source_value,
        "observation_source_concept_id": source_concept_id,
        "unit_source_value": None,
        "qualifier_source_value": qualifier_source,
        "value_source_value": value_source,
        "observation_event_id": None,
        "obs_event_field_concept_id": None,
    }


def build_measurement_resource(
    row: Dict[str, Any],
    obx: ParsedOBX,
    meas_id: int,
    concepts: ConceptConfig,
    concept_lookup: Optional[ConceptLookup] = None,
) -> Dict[str, Any]:
    """Build a measurement dict.  Used by both insert and test paths."""
    meas_date = _best_date(row, obx)

    # Concept lookup for the question (field "3")
    meas_concept_id = 0
    if concept_lookup:
        meas_concept_id = (
            concept_lookup.lookup(
                obx.identifier_code,
                obx.coding_system,
                concept_name=obx.identifier_text or "",
                domain_id="Measurement",
                concept_class_id=(
                    "CAP Variable" if obx.coding_system == "CAPECC" else ""
                ),
            )
            or 0
        )

    # Question splitting: display text → source_value, concept → source_concept_id
    source_value = obx.identifier_text[:50] if obx.identifier_text else None
    source_concept_id: Optional[int] = meas_concept_id if meas_concept_id else None

    value_as_number = None
    try:
        value_as_number = float(obx.value)
    except (ValueError, TypeError):
        pass
    value_source = obx.value[:50] if obx.value else None
    return {
        "measurement_id": meas_id,
        "person_id": row["PatientID"],
        "measurement_concept_id": meas_concept_id,
        "measurement_date": meas_date,
        "measurement_datetime": datetime.combine(meas_date, datetime.min.time()),
        "measurement_time": None,
        "measurement_type_concept_id": concepts.measurement_type_concept_id,
        "operator_concept_id": None,
        "value_as_number": value_as_number,
        "value_as_concept_id": None,
        "unit_concept_id": None,
        "range_low": None,
        "range_high": None,
        "provider_id": None,
        "visit_occurrence_id": None,
        "visit_detail_id": None,
        "measurement_source_value": source_value,
        "measurement_source_concept_id": source_concept_id,
        "unit_source_value": (obx.units[:50] if obx.units else None),
        "unit_source_concept_id": None,
        "value_source_value": value_source,
        "measurement_event_id": None,
        "meas_event_field_concept_id": None,
    }


def build_episode_event_resource(
    episode_id: int,
    event_id: int,
    field_concept_id: int,
) -> Dict[str, Any]:
    """Build an episode_event dict.  Used by both insert and test paths."""
    return {
        "episode_id": episode_id,
        "event_id": event_id,
        "episode_event_field_concept_id": field_concept_id,
    }


# ---------------------------------------------------------------------------
# DB Writers  (thin wrappers around build_* functions)
# ---------------------------------------------------------------------------
_EPISODE_COLS = (
    "episode_id",
    "person_id",
    "episode_concept_id",
    "episode_start_date",
    "episode_start_datetime",
    "episode_end_date",
    "episode_end_datetime",
    "episode_parent_id",
    "episode_number",
    "episode_object_concept_id",
    "episode_type_concept_id",
    "episode_source_value",
    "episode_source_concept_id",
)

_OBSERVATION_COLS = (
    "observation_id",
    "person_id",
    "observation_concept_id",
    "observation_date",
    "observation_datetime",
    "observation_type_concept_id",
    "value_as_number",
    "value_as_string",
    "value_as_concept_id",
    "qualifier_concept_id",
    "unit_concept_id",
    "provider_id",
    "visit_occurrence_id",
    "visit_detail_id",
    "observation_source_value",
    "observation_source_concept_id",
    "unit_source_value",
    "qualifier_source_value",
    "value_source_value",
    "observation_event_id",
    "obs_event_field_concept_id",
)

_MEASUREMENT_COLS = (
    "measurement_id",
    "person_id",
    "measurement_concept_id",
    "measurement_date",
    "measurement_datetime",
    "measurement_time",
    "measurement_type_concept_id",
    "operator_concept_id",
    "value_as_number",
    "value_as_concept_id",
    "unit_concept_id",
    "range_low",
    "range_high",
    "provider_id",
    "visit_occurrence_id",
    "visit_detail_id",
    "measurement_source_value",
    "measurement_source_concept_id",
    "unit_source_value",
    "unit_source_concept_id",
    "value_source_value",
    "measurement_event_id",
    "meas_event_field_concept_id",
)

_EPISODE_EVENT_COLS = (
    "episode_id",
    "event_id",
    "episode_event_field_concept_id",
)


def _insert_row(
    cursor: pyodbc.Cursor,
    schema_table: str,
    columns: tuple[str, ...],
    data: Dict[str, Any],
) -> None:
    """Generic INSERT into dbo.[table] using a column tuple and a data dict."""
    col_list = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO dbo.[{schema_table}] ({col_list}) VALUES ({placeholders})",
        tuple(data[c] for c in columns),
    )


def insert_episode(
    cursor: pyodbc.Cursor,
    ids: IdGenerator,
    row: Dict[str, Any],
    metadata_obxs: List[ParsedOBX],
    concepts: ConceptConfig,
) -> int:
    """Insert one EPISODE row for a lab report.  Returns the new episode_id."""
    episode_id = ids.next_id("episode")
    data = build_episode_resource(row, episode_id, metadata_obxs, concepts)
    _insert_row(cursor, "episode", _EPISODE_COLS, data)
    return episode_id


def insert_observation(
    cursor: pyodbc.Cursor,
    ids: IdGenerator,
    row: Dict[str, Any],
    obx: ParsedOBX,
    concepts: ConceptConfig,
    concept_lookup: Optional[ConceptLookup] = None,
) -> int:
    """Insert one OBSERVATION row.  Returns the new observation_id."""
    obs_id = ids.next_id("observation")
    data = build_observation_resource(row, obx, obs_id, concepts, concept_lookup)
    _insert_row(cursor, "observation", _OBSERVATION_COLS, data)
    return obs_id


def insert_measurement(
    cursor: pyodbc.Cursor,
    ids: IdGenerator,
    row: Dict[str, Any],
    obx: ParsedOBX,
    concepts: ConceptConfig,
    concept_lookup: Optional[ConceptLookup] = None,
) -> int:
    """Insert one MEASUREMENT row.  Returns the new measurement_id."""
    meas_id = ids.next_id("measurement")
    data = build_measurement_resource(row, obx, meas_id, concepts, concept_lookup)
    _insert_row(cursor, "measurement", _MEASUREMENT_COLS, data)
    return meas_id


def insert_episode_event(
    cursor: pyodbc.Cursor,
    episode_id: int,
    event_id: int,
    field_concept_id: int,
) -> None:
    """Link a clinical fact to its episode via EPISODE_EVENT."""
    data = build_episode_event_resource(episode_id, event_id, field_concept_id)
    _insert_row(cursor, "episode_event", _EPISODE_EVENT_COLS, data)


def process_row_test(
    row: Dict[str, Any],
    concepts: ConceptConfig,
    id_counter: Dict[str, int],
    concept_lookup: Optional[ConceptLookup] = None,
) -> Dict[str, Any]:
    """Process one row in test mode: returns resources that *would* be created."""
    resources: List[Dict[str, Any]] = []

    def _tag(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"table": table, **data}

    obx_list = parse_obx_segments(row["OBXCAPECPSegment"])
    if not obx_list:
        return {
            "record_id": row["record_id"],
            "person_id": row["PatientID"],
            "resources": [],
        }

    metadata_obxs = [o for o in obx_list if o.is_metadata]
    clinical_obxs = [o for o in obx_list if not o.is_metadata]

    # Episode
    id_counter["episode"] = id_counter.get("episode", 0) + 1
    episode_id = id_counter["episode"]
    resources.append(
        _tag(
            "episode", build_episode_resource(row, episode_id, metadata_obxs, concepts)
        )
    )

    # Clinical facts
    skipped = 0
    for obx in clinical_obxs:
        target = classify_obx(obx)
        if target == "observation":
            id_counter["observation"] = id_counter.get("observation", 0) + 1
            obs_id = id_counter["observation"]
            resources.append(
                _tag(
                    "observation",
                    build_observation_resource(
                        row, obx, obs_id, concepts, concept_lookup
                    ),
                )
            )
            resources.append(
                _tag(
                    "episode_event",
                    build_episode_event_resource(
                        episode_id, obs_id, concepts.field_observation_id
                    ),
                )
            )
        elif target == "measurement":
            id_counter["measurement"] = id_counter.get("measurement", 0) + 1
            meas_id = id_counter["measurement"]
            resources.append(
                _tag(
                    "measurement",
                    build_measurement_resource(
                        row, obx, meas_id, concepts, concept_lookup
                    ),
                )
            )
            resources.append(
                _tag(
                    "episode_event",
                    build_episode_event_resource(
                        episode_id, meas_id, concepts.field_measurement_id
                    ),
                )
            )
        elif target == "skip":
            skipped += 1

    return {
        "record_id": row["record_id"],
        "person_id": row["PatientID"],
        "skipped": skipped,
        "resources": resources,
    }


# ---------------------------------------------------------------------------
# Source query
# ---------------------------------------------------------------------------
def fetch_lab_reports(
    cursor: pyodbc.Cursor,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch rows from dbo.CCR_LabReportECP that have OBX data."""
    base = """
        SELECT
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
        WHERE PatientID IS NOT NULL
          AND CTCID IS NOT NULL
          AND ReportTemplateVersionID IS NOT NULL
          AND OBXCAPECPSegment IS NOT NULL
          AND LEN(OBXCAPECPSegment) > 2
    """
    if limit is not None:
        # limit is validated as int by argparse; safe to interpolate
        base = base.replace("SELECT", f"SELECT TOP {int(limit)}", 1)
    cursor.execute(base)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, r)) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Row-level ETL
# ---------------------------------------------------------------------------
def process_row(
    cursor: pyodbc.Cursor,
    ids: IdGenerator,
    row: Dict[str, Any],
    concepts: ConceptConfig,
    dry_run: bool = False,
    concept_lookup: Optional[ConceptLookup] = None,
) -> Dict[str, int]:
    """Process a single CCR_LabReportECP row.  Returns per-table insert counts."""
    counts = {
        "episodes": 0,
        "observations": 0,
        "measurements": 0,
        "episode_events": 0,
        "skipped": 0,
        "duplicates": 0,
    }

    # ---- Duplicate check: skip if episode already exists for this record_id
    if not dry_run:
        record_id_str = str(row["record_id"])
        cursor.execute(
            "SELECT 1 FROM dbo.episode WHERE episode_source_value = ?",
            (record_id_str,),
        )
        if cursor.fetchone() is not None:
            logger.info(
                "  SKIP duplicate record_id=%s (episode already exists)",
                row["record_id"],
            )
            counts["duplicates"] = 1
            return counts

    obx_list = parse_obx_segments(row["OBXCAPECPSegment"])
    if not obx_list:
        logger.warning("record_id=%s: no OBX segments parsed", row["record_id"])
        return counts

    metadata_obxs = [o for o in obx_list if o.is_metadata]
    clinical_obxs = [o for o in obx_list if not o.is_metadata]

    if dry_run:
        logger.info(
            "  [DRY RUN] record_id=%s  person=%s  meta=%d  clinical=%d",
            row["record_id"],
            row["PatientID"],
            len(metadata_obxs),
            len(clinical_obxs),
        )
        for obx in clinical_obxs:
            target = classify_obx(obx)
            logger.info(
                "    OBX #%s → %-12s  %s = %s",
                obx.set_id,
                target,
                obx.identifier_text,
                obx.value[:80],
            )
        return counts

    # ---- 1) Episode --------------------------------------------------------
    episode_id = insert_episode(cursor, ids, row, metadata_obxs, concepts)
    counts["episodes"] = 1

    # ---- 2) Clinical facts --------------------------------------------------
    for obx in clinical_obxs:
        target = classify_obx(obx)

        if target == "observation":
            event_id = insert_observation(
                cursor, ids, row, obx, concepts, concept_lookup
            )
            insert_episode_event(
                cursor, episode_id, event_id, concepts.field_observation_id
            )
            counts["observations"] += 1
            counts["episode_events"] += 1

        elif target == "measurement":
            event_id = insert_measurement(
                cursor, ids, row, obx, concepts, concept_lookup
            )
            insert_episode_event(
                cursor, episode_id, event_id, concepts.field_measurement_id
            )
            counts["measurements"] += 1
            counts["episode_events"] += 1

        elif target == "skip":
            counts["skipped"] += 1

        # TODO: add 'procedure' / 'condition' branches when mapping is refined

    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETL: dbo.CCR_LabReportECP → OMOP CDM 5.4 (Episode-centric)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse & classify OBX segments without writing to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N rows (useful for testing).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Commit after every N rows (default: 100).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: fetch rows, build OMOP resources in-memory, "
        "and write results to a JSON log file instead of the database.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output file path for --test mode (default: etl_test_output.json).",
    )
    args = parser.parse_args()

    concepts = ConceptConfig()

    conn = connect()
    cursor = conn.cursor()
    concept_lookup = ConceptLookup(cursor, read_only=args.test)

    # ---- Test mode ----------------------------------------------------------
    if args.test:
        test_limit = args.limit if args.limit is not None else 5
        output_path = args.output or "etl_test_output.json"

        try:
            logger.info("[TEST] Fetching up to %d CCR_LabReportECP rows …", test_limit)
            rows = fetch_lab_reports(cursor, limit=test_limit)
            logger.info("[TEST] Found %d rows", len(rows))

            id_counter: Dict[str, int] = {}
            all_results: List[Dict[str, Any]] = []

            for i, row in enumerate(rows, 1):
                logger.info(
                    "[TEST] Processing row %d/%d  record_id=%s",
                    i,
                    len(rows),
                    row["record_id"],
                )
                result = process_row_test(row, concepts, id_counter, concept_lookup)
                all_results.append(result)

            # Summarise
            total_resources = sum(len(r["resources"]) for r in all_results)
            summary = {
                "mode": "test",
                "rows_fetched": len(rows),
                "total_resources": total_resources,
                "episodes": sum(
                    1
                    for r in all_results
                    for res in r["resources"]
                    if res["table"] == "episode"
                ),
                "observations": sum(
                    1
                    for r in all_results
                    for res in r["resources"]
                    if res["table"] == "observation"
                ),
                "measurements": sum(
                    1
                    for r in all_results
                    for res in r["resources"]
                    if res["table"] == "measurement"
                ),
                "episode_events": sum(
                    1
                    for r in all_results
                    for res in r["resources"]
                    if res["table"] == "episode_event"
                ),
                "skipped": sum(r.get("skipped", 0) for r in all_results),
            }

            # Collect pending vocabulary/concept resources
            pending = {
                "vocabularies_to_create": concept_lookup.pending_vocabularies,
                "concepts_to_create": concept_lookup.pending_concepts,
            }
            summary["vocabularies_to_create"] = len(pending["vocabularies_to_create"])
            summary["concepts_to_create"] = len(pending["concepts_to_create"])

            output = {
                "summary": summary,
                "pending_reference_data": pending,
                "rows": all_results,
            }

            with open(output_path, "w") as fh:
                json.dump(output, fh, indent=2, default=str)

            logger.info("=" * 60)
            logger.info("[TEST] Results written to %s", output_path)
            logger.info("[TEST] Summary")
            logger.info("  Rows fetched:       %d", summary["rows_fetched"])
            logger.info("  Total resources:    %d", summary["total_resources"])
            logger.info("  Episodes:           %d", summary["episodes"])
            logger.info("  Observations:       %d", summary["observations"])
            logger.info("  Measurements:       %d", summary["measurements"])
            logger.info("  Episode events:     %d", summary["episode_events"])
            logger.info("  Skipped (metadata): %d", summary["skipped"])
            logger.info(
                "  Vocabularies to create: %d", summary["vocabularies_to_create"]
            )
            logger.info("  Concepts to create:     %d", summary["concepts_to_create"])
        finally:
            cursor.close()
            conn.close()
        return

    # ---- Normal / dry-run mode ----------------------------------------------
    ids = IdGenerator(conn)

    try:
        logger.info("Fetching CCR_LabReportECP rows …")
        rows = fetch_lab_reports(cursor, limit=args.limit)
        logger.info("Found %d rows to process", len(rows))

        totals = {
            "episodes": 0,
            "observations": 0,
            "measurements": 0,
            "episode_events": 0,
            "skipped": 0,
            "duplicates": 0,
        }

        for i, row in enumerate(rows, 1):
            logger.info(
                "Processing row %d/%d  record_id=%s", i, len(rows), row["record_id"]
            )
            counts = process_row(
                cursor,
                ids,
                row,
                concepts,
                dry_run=args.dry_run,
                concept_lookup=concept_lookup,
            )
            for k in totals:
                totals[k] += counts[k]

            if not args.dry_run and i % args.batch_size == 0:
                conn.commit()
                logger.info("  Committed batch (%d rows processed so far)", i)

        if not args.dry_run:
            conn.commit()
            logger.info("Final commit complete")

        logger.info("=" * 60)
        logger.info("ETL Summary")
        logger.info("  Rows processed:     %d", len(rows))
        logger.info("  Episodes created:   %d", totals["episodes"])
        logger.info("  Observations:       %d", totals["observations"])
        logger.info("  Measurements:       %d", totals["measurements"])
        logger.info("  Episode events:     %d", totals["episode_events"])
        logger.info("  Skipped (metadata): %d", totals["skipped"])
        logger.info("  Skipped (duplicate):%d", totals["duplicates"])

    except Exception:
        logger.exception("ETL failed — rolling back")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
