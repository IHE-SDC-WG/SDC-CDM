"""Report groups, retained versions, and explicit supersession.

A report group is one accession for one intake patient at one sending
facility; `report_loinc` distinguishes report types within it. Every loaded,
accessioned `sdc_report` becomes one version. The first version of each type is
selected, and only `supersede_report` moves selection. No function here writes
`sdc_report`, `naaccr_value`, or OMOP rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import SdcCdmError


class ReportVersionError(SdcCdmError):
    """Loaded reports lack the source links a version records."""


class SupersessionError(SdcCdmError):
    """A supersession request breaks the named rule; nothing was written."""

    def __init__(self, rule: str, detail: str):
        super().__init__(f"{rule}: {detail}")
        self.rule = rule


@dataclass(frozen=True)
class Supersession:
    predecessor_id: int
    successor_id: int
    report_group_id: int
    report_loinc: str


def is_accessioned(accession: str | None) -> bool:
    """Accession-less reports (NULL or '') form no group and get no version."""

    return bool(accession)


def _lock(backend: DatabaseBackend) -> str:
    """Table hint that holds a check-then-write read until commit.

    On SQL Server, UPDLOCK plus HOLDLOCK locks the key range a lookup found
    empty, so a concurrent transaction waits and then sees the committed row
    instead of inserting a duplicate. SQLite's BEGIN IMMEDIATE already
    serializes writers.
    """

    return " WITH (UPDLOCK, HOLDLOCK)" if backend.dialect == "sqlserver" else ""


def _group_id(backend: DatabaseBackend, person_id: int, sending_facility: str,
              accession: str) -> int:
    key = (person_id, sending_facility, accession)
    row = backend.fetch_one(
        f"SELECT report_group_id FROM naaccr.report_group{_lock(backend)} WHERE person_id = ? "
        "AND sending_facility = ? AND report_accession = ?", key,
    )
    if row is not None:
        return int(row[0])
    columns = "(person_id, sending_facility, report_accession)"
    if backend.dialect == "sqlite":
        sql = (f"INSERT INTO naaccr.report_group {columns} VALUES (?, ?, ?) "
               "RETURNING report_group_id")
    else:
        sql = (f"INSERT INTO naaccr.report_group {columns} "
               "OUTPUT INSERTED.report_group_id VALUES (?, ?, ?)")
    row = backend.fetch_one(sql, key)
    if row is None:
        raise RuntimeError(f"no report_group_id for accession {accession!r}")
    return int(row[0])


def record_report_version(
    backend: DatabaseBackend,
    *,
    sdc_report_id: int,
    person_id: int,
    sending_facility: str | None,
    accession: str,
    report_loinc: str | None,
    inbound_envelope_id: int,
    inbound_message_id: int,
) -> None:
    """Add one version inside the caller's transaction.

    Missing facility and LOINC use the stable empty key. The version is
    selected only when it is the first of its type in the group.
    """

    group_id = _group_id(backend, person_id, sending_facility or "", accession)
    report_type = report_loinc or ""
    has_type = backend.fetch_one(
        f"SELECT 1 FROM naaccr.report_version{_lock(backend)} "
        "WHERE report_group_id = ? AND report_loinc = ?",
        (group_id, report_type),
    )
    backend.execute_uncommitted(
        "INSERT INTO naaccr.report_version (report_group_id, report_loinc, sdc_report_id, "
        "inbound_envelope_id, inbound_message_id, is_selected) VALUES (?, ?, ?, ?, ?, ?)",
        (group_id, report_type, sdc_report_id, inbound_envelope_id, inbound_message_id,
         int(has_type is None)),
    )


# Accessioned reports without a version, oldest first, with every link a version
# records. A NULL envelope, message, or patient column means a broken link.
_UNVERSIONED = """
    SELECT r.sdc_report_id, r.report_accession, r.report_loinc,
           e.inbound_envelope_id, m.inbound_message_id, m.sending_facility, p.patient_id
    FROM sdc.sdc_report r
    LEFT JOIN intake.inbound_envelope e ON e.inbound_envelope_id = r.inbound_envelope_id
    LEFT JOIN intake.inbound_message m ON m.inbound_message_id = e.inbound_message_id
    LEFT JOIN intake.patient p ON p.patient_id = r.person_id
    WHERE r.report_accession IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM naaccr.report_version v WHERE v.sdc_report_id = r.sdc_report_id
      )
    ORDER BY r.sdc_report_id
"""


def backfill_report_versions(backend: DatabaseBackend) -> int:
    """Version every accessioned report that has none; return how many.

    Reports are taken in `sdc_report_id` order, so the first loaded version of
    each type is selected. Existing versions, and so any explicit selection,
    are left alone, which makes a rerun a no-op. If any candidate lacks a source
    link, nothing is written and the error names every such report.
    """

    with backend.transaction():
        rows = [row for row in backend.fetch_all(_UNVERSIONED) if is_accessioned(row[1])]
        broken = [int(row[0]) for row in rows if None in (row[3], row[4], row[6])]
        if broken:
            raise ReportVersionError(
                "cannot backfill report versions: sdc_report_id "
                + ", ".join(map(str, broken))
                + " lack an inbound envelope, raw message, or intake patient"
            )
        for report_id, accession, loinc, envelope_id, message_id, facility, person_id in rows:
            record_report_version(
                backend, sdc_report_id=int(report_id), person_id=int(person_id),
                sending_facility=facility, accession=accession, report_loinc=loinc,
                inbound_envelope_id=int(envelope_id), inbound_message_id=int(message_id),
            )
    return len(rows)


_VERSION = (
    "SELECT report_group_id, report_loinc, is_selected, predecessor_sdc_report_id "
    "FROM naaccr.report_version{lock} WHERE sdc_report_id = ?"
)


def _check_supersession(backend: DatabaseBackend, predecessor_id: int,
                        successor_id: int) -> tuple[int, str]:
    version = _VERSION.format(lock=_lock(backend))
    predecessor = backend.fetch_one(version, (predecessor_id,))
    successor = backend.fetch_one(version, (successor_id,))
    for report_id, row in ((predecessor_id, predecessor), (successor_id, successor)):
        if row is None:
            raise SupersessionError("unversioned_report", f"sdc_report {report_id} has no report version")
    if predecessor[0] != successor[0]:
        raise SupersessionError(
            "cross_group",
            f"sdc_report {predecessor_id} is in report group {predecessor[0]}, "
            f"sdc_report {successor_id} in {successor[0]}",
        )
    if predecessor[1] != successor[1]:
        raise SupersessionError(
            "cross_type",
            f"sdc_report {predecessor_id} has report type {predecessor[1]!r}, "
            f"sdc_report {successor_id} has {successor[1]!r}",
        )
    ancestor: int | None = predecessor_id
    seen: set[int] = set()
    while ancestor is not None and ancestor not in seen:
        if ancestor == successor_id:
            raise SupersessionError(
                "cycle",
                f"sdc_report {successor_id} is sdc_report {predecessor_id} or precedes it",
            )
        seen.add(ancestor)
        row = backend.fetch_one(version, (ancestor,))
        ancestor = None if row is None or row[3] is None else int(row[3])
    existing = backend.fetch_one(
        f"SELECT sdc_report_id FROM naaccr.report_version{_lock(backend)} "
        "WHERE predecessor_sdc_report_id = ?",
        (predecessor_id,),
    )
    if existing is not None:
        raise SupersessionError(
            "predecessor_has_successor",
            f"sdc_report {predecessor_id} is already superseded by sdc_report {existing[0]}",
        )
    if successor[3] is not None:
        raise SupersessionError(
            "successor_has_predecessor",
            f"sdc_report {successor_id} already supersedes sdc_report {successor[3]}",
        )
    if not predecessor[2]:
        raise SupersessionError(
            "predecessor_not_selected", f"sdc_report {predecessor_id} is not the selected version",
        )
    if successor[2]:
        raise SupersessionError(
            "successor_selected", f"sdc_report {successor_id} is already selected",
        )
    return int(predecessor[0]), str(predecessor[1])


def supersede_report(backend: DatabaseBackend, predecessor_id: int,
                     successor_id: int) -> Supersession:
    """Move selection from the predecessor to the successor and record the link.

    Every rule is checked before the first write, and both writes share one
    transaction, so a rejection or failure leaves every row unchanged.
    """

    with backend.transaction():
        group_id, report_type = _check_supersession(backend, predecessor_id, successor_id)
        backend.execute_uncommitted(
            "UPDATE naaccr.report_version SET is_selected = 0 WHERE sdc_report_id = ?",
            (predecessor_id,),
        )
        backend.execute_uncommitted(
            "UPDATE naaccr.report_version SET is_selected = 1, predecessor_sdc_report_id = ? "
            "WHERE sdc_report_id = ?",
            (predecessor_id, successor_id),
        )
    return Supersession(predecessor_id, successor_id, group_id, report_type)
