"""Append-only local concept IDs, independent of Athena concept IDs."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError

LOCAL_RANGE = (2_100_000_000, 2_147_483_647)
LOCAL_VOCABULARY_ID = "NAACCR_LOCAL"


def local_code(kind: str, item_num: int = 0, code: str = "") -> str:
    if kind == "vocabulary":
        return LOCAL_VOCABULARY_ID
    if kind == "concept_class":
        return f"C:{code}"
    if kind == "item":
        return f"I:{item_num}"
    if kind == "value":
        digest = hashlib.sha256(f"{item_num}\x00{code}".encode("utf-8")).hexdigest()[:32]
        return f"V:{item_num}:{digest}"
    raise ValueError(f"unknown local concept kind {kind!r}")


def reserve(
    backend: DatabaseBackend, kind: str, item_num: int = 0, code: str = "", name: str = ""
) -> tuple[int, bool]:
    """Return (concept_id, newly_allocated); caller owns one open transaction."""
    concept_code = local_code(kind, item_num, code)
    if len(concept_code) > 50:
        raise VocabularyError(f"local concept code exceeds OMOP width: {concept_code}")
    row = backend.fetch_one(
        "SELECT concept_id, concept_code FROM naaccr.local_concept_allocation "
        "WHERE concept_kind = ? AND item_num = ? AND code = ?",
        (kind, item_num, code),
    )
    if row is not None:
        if row[1] != concept_code:
            raise VocabularyError(f"allocation code changed for {kind}/{item_num}/{code}")
        return int(row[0]), False
    collision = backend.fetch_one(
        "SELECT concept_id FROM naaccr.local_concept_allocation WHERE concept_code = ?",
        (concept_code,),
    )
    if collision:
        raise VocabularyError(f"local concept code collision: {concept_code}")
    top = backend.fetch_one("SELECT MAX(concept_id) FROM naaccr.local_concept_allocation")
    concept_id = max(LOCAL_RANGE[0] - 1, int(top[0]) if top and top[0] is not None else 0) + 1
    if concept_id > LOCAL_RANGE[1]:
        raise VocabularyError("NAACCR_LOCAL concept ID range exhausted")
    occupied = backend.fetch_one("SELECT vocabulary_id FROM omop.concept WHERE concept_id = ?", (concept_id,))
    if occupied is not None:
        raise VocabularyError(f"local concept ID {concept_id} is already used by {occupied[0]}")
    backend.execute_uncommitted(
        "INSERT INTO naaccr.local_concept_allocation "
        "(concept_id, concept_kind, item_num, code, concept_code, concept_name, allocated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (concept_id, kind, item_num, code, concept_code, name[:255],
         datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    return concept_id, True
