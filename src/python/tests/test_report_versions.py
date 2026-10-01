"""BRIDGE-01/02: report groups, retained versions, and explicit supersession."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.hl7v2 import parse_hl7
from sdc_cdm.intake import ingest_message, load_message
from sdc_cdm.reports import ReportVersionError, SupersessionError, supersede_report


NARRATIVE = "35265-8"
SYNOPTIC = "60569-1"
DIALECTS = pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))

# Every version in the test's own groups, keyed by group identity rather than
# report_group_id so a backfill can be compared with the load that it replays.
VERSIONS = (
    "SELECT v.sdc_report_id, g.person_id, g.sending_facility, g.report_accession, "
    "v.report_loinc, v.is_selected, v.predecessor_sdc_report_id, "
    "v.inbound_envelope_id, v.inbound_message_id "
    "FROM naaccr.report_version v "
    "JOIN naaccr.report_group g ON g.report_group_id = v.report_group_id "
    "WHERE g.report_accession LIKE ? ORDER BY v.sdc_report_id"
)


def _backend(dialect: str, tmp_path: Path) -> DatabaseBackend:
    if dialect == "sqlite":
        return SQLiteBackend(tmp_path / "versions.db")
    connection_string = os.environ.get("SDC_CDM_SQLSERVER_CONNECTION_STRING")
    if not connection_string:
        pytest.skip("SDC_CDM_SQLSERVER_CONNECTION_STRING is not set")
    return SqlServerBackend(connection_string)


def _target(backend: DatabaseBackend, tmp_path: Path) -> list[str]:
    if backend.dialect == "sqlite":
        return ["--dialect", "sqlite", "--db", str(tmp_path / "versions.db")]
    return ["--dialect", "sqlserver", "--connection-string",
            os.environ["SDC_CDM_SQLSERVER_CONNECTION_STRING"]]


class _Lab:
    """Sends synthetic HL7 for one test; identifiers are unique per test run."""

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend
        self.token = uuid.uuid4().hex[:12]
        self.algorithm = f"TEST_VERSIONS_{self.token}"
        self.sent = 0
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version (algorithm, version) VALUES (?, ?)",
            (self.algorithm, "1"),
        )

    def message(self, reports: list[tuple[str, str]], *, patient: str = "P",
                facility: str = "LAB", accession: str | None = "A") -> bytes:
        self.sent += 1
        accession_value = f"{accession}-{self.token}" if accession else ""
        lines = [
            f"MSH|^~\\&|SYNTH|{facility}-{self.token}|SDC|TEST|202609241200||"
            f"ORU^R01^ORU_R01|{self.token}-{self.sent}|P|2.5.1",
            f"PID|1||{patient}-{self.token}^^^SYNTHLAB^MR||Example^Synthetic||1957|F",
            f"ORC|RE||{accession_value}",
        ]
        for ordinal, (loinc, content) in enumerate(reports, 1):
            lines.append(f"OBR|{ordinal}||{accession_value}|{loinc}^REPORT^LN|||2026092412")
            if loinc == NARRATIVE:
                lines.append(f"OBX|1|TX|22637-3^Path report.final diagnosis^LN|1|{content}")
            else:
                lines.append(f"OBX|1|NM|20791.100004300^Tumor Size^CAPECP||{content}|cm")
        return ("\n".join(lines) + "\n").encode()

    def load(self, raw: bytes) -> list[int]:
        """Ingest and load bytes; return the new sdc_report_ids in OBR order."""
        message_id = ingest_message(self.backend, raw, parse_hl7, parser_name="test",
                                    parser_version="1").inbound_message_id
        load_message(self.backend, message_id, algorithm=self.algorithm)
        return [int(row[0]) for row in self.backend.fetch_all(
            "SELECT l.sdc_report_id FROM intake.envelope_load l "
            "JOIN intake.inbound_envelope e ON e.inbound_envelope_id = l.inbound_envelope_id "
            "WHERE e.inbound_message_id = ? ORDER BY e.ordinal", (message_id,),
        )]

    def send(self, reports: list[tuple[str, str]], **identity: str | None) -> list[int]:
        return self.load(self.message(reports, **identity))

    def versions(self) -> list[tuple]:
        return [
            (int(row[0]), int(row[1]), row[2], row[3], row[4], int(row[5]),
             None if row[6] is None else int(row[6]), int(row[7]), int(row[8]))
            for row in self.backend.fetch_all(VERSIONS, (f"%{self.token}",))
        ]

    def selected(self) -> set[int]:
        return {row[0] for row in self.versions() if row[5]}

    def snapshot(self) -> tuple:
        """Every row a supersession or backfill could touch, plus source counts."""
        groups = self.backend.fetch_all(
            "SELECT report_group_id, person_id, sending_facility, report_accession "
            "FROM naaccr.report_group WHERE report_accession LIKE ? ORDER BY report_group_id",
            (f"%{self.token}",),
        )
        counts = [
            self.backend.fetch_one(f"SELECT COUNT(*) FROM {table}")[0]
            for table in ("sdc.sdc_report", "naaccr.naaccr_value", "omop.note",
                          "omop.measurement")
        ]
        return self.versions(), [tuple(row) for row in groups], counts


def _history(lab: _Lab) -> dict[str, list[int]]:
    """One group with two changed versions, an exact resend, and look-alike groups."""
    first = lab.send([(NARRATIVE, "first diagnosis"), (SYNOPTIC, "1.20")])
    changed_bytes = lab.message([(NARRATIVE, "corrected diagnosis"), (SYNOPTIC, "1.30")])
    changed = lab.load(changed_bytes)
    return {
        "first": first,
        "changed": changed,
        "resend": lab.load(changed_bytes),
        "other_patient": lab.send([(SYNOPTIC, "1.20")], patient="Q"),
        "other_facility": lab.send([(SYNOPTIC, "1.20")], facility="ELSEWHERE"),
        "no_accession": lab.send([(SYNOPTIC, "1.20")], accession=None),
    }


def _assert_history_versions(lab: _Lab, ids: dict[str, list[int]]) -> None:
    (n1, s1), (n2, s2) = ids["first"], ids["changed"]
    (other_patient,), (other_facility,) = ids["other_patient"], ids["other_facility"]
    versions = {row[0]: row for row in lab.versions()}
    assert sorted(versions) == sorted((n1, s1, n2, s2, other_patient, other_facility))
    assert lab.selected() == {n1, s1, other_patient, other_facility}
    assert {report: versions[report][4] for report in (n1, s1, n2, s2)} == {
        n1: NARRATIVE, s1: SYNOPTIC, n2: NARRATIVE, s2: SYNOPTIC,
    }
    group_of = {report: versions[report][1:4] for report in versions}
    assert len(set(group_of.values())) == 3
    assert len({group_of[report] for report in (n1, s1, n2, s2)}) == 1
    assert group_of[other_patient][0] != group_of[s1][0]
    assert group_of[other_patient][1:] == group_of[s1][1:]
    assert group_of[other_facility][1] == f"ELSEWHERE-{lab.token}"
    assert group_of[other_facility][::2] == group_of[s1][::2]
    assert all(row[6] is None for row in versions.values())
    links = {
        int(row[0]): (int(row[1]), int(row[2]))
        for row in lab.backend.fetch_all(
            "SELECT r.sdc_report_id, e.inbound_envelope_id, e.inbound_message_id "
            "FROM sdc.sdc_report r JOIN intake.inbound_envelope e "
            "ON e.inbound_envelope_id = r.inbound_envelope_id "
            "WHERE r.report_accession LIKE ?", (f"%{lab.token}",),
        )
    }
    assert {report: row[7:] for report, row in versions.items()} == links


@DIALECTS
def test_loads_version_reports_and_keep_the_first_of_each_type_selected(
    dialect: str, tmp_path: Path
) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        lab = _Lab(backend)
        ids = _history(lab)
        assert ids["resend"] == []
        (no_accession,) = ids["no_accession"]
        assert backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.report_version WHERE sdc_report_id = ?",
            (no_accession,),
        )[0] == 0
        _assert_history_versions(lab, ids)


@DIALECTS
def test_backfill_replays_load_selection_without_rewriting_sources(
    dialect: str, tmp_path: Path
) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        lab = _Lab(backend)
        ids = _history(lab)
        at_load = lab.versions()
        reports = sorted(report for group in ids.values() for report in group)
        markers = ", ".join("?" for _ in reports)
        sources = (
            f"SELECT * FROM sdc.sdc_report WHERE sdc_report_id IN ({markers}) "
            "ORDER BY sdc_report_id",
            f"SELECT * FROM naaccr.naaccr_value WHERE sdc_report_id IN ({markers}) "
            "ORDER BY naaccr_value_id",
        )
        before = [[tuple(row) for row in backend.fetch_all(sql, reports)] for sql in sources]
        counts = lab.snapshot()[2]

        # A database whose reports were loaded before report versions existed.
        groups = "SELECT report_group_id FROM naaccr.report_group WHERE report_accession LIKE ?"
        backend.execute(f"DELETE FROM naaccr.report_version WHERE report_group_id IN ({groups})",
                        (f"%{lab.token}",))
        backend.execute("DELETE FROM naaccr.report_group WHERE report_accession LIKE ?",
                        (f"%{lab.token}",))
        assert lab.versions() == []

        runner = BuildRunner(load_manifest(), backend)
        runner.run()
        assert runner.backfilled_report_versions == len(at_load) == 6
        assert lab.versions() == at_load
        _assert_history_versions(lab, ids)
        assert [[tuple(row) for row in backend.fetch_all(sql, reports)]
                for sql in sources] == before
        assert lab.snapshot()[2] == counts

        rerun = BuildRunner(load_manifest(), backend)
        rerun.run()
        assert rerun.backfilled_report_versions == 0
        assert lab.versions() == at_load


@DIALECTS
def test_backfill_names_reports_missing_source_links_and_writes_nothing(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        lab = _Lab(backend)
        (loaded,) = lab.send([(SYNOPTIC, "1.20")])
        envelope_id, person_id = backend.fetch_one(
            "SELECT inbound_envelope_id, person_id FROM sdc.sdc_report WHERE sdc_report_id = ?",
            (loaded,),
        )
        backend.execute("DELETE FROM naaccr.report_version WHERE sdc_report_id = ?", (loaded,))
        columns = ("template_name, template_version, template_instance_guid, person_id, "
                   "report_accession, report_loinc, inbound_envelope_id")
        insert = (f"INSERT INTO sdc.sdc_report ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?)"
                  if dialect == "sqlite" else
                  f"INSERT INTO sdc.sdc_report ({columns}) OUTPUT INSERTED.sdc_report_id "
                  "VALUES (?, ?, ?, ?, ?, ?, ?)")
        broken = []
        for suffix, person, envelope in (
            ("no-envelope", person_id, None),
            ("dangling-envelope", person_id, 2_000_000_000),
            ("no-patient", 2_000_000_000, envelope_id),
        ):
            parameters = ("t", "1", f"{lab.token}-{suffix}", person,
                          f"A-{lab.token}", SYNOPTIC, envelope)
            broken.append(int(backend.execute(insert, parameters)
                              if dialect == "sqlite"
                              else backend.execute(insert, parameters, return_scalar=True)))
        try:
            before = lab.snapshot()
            with pytest.raises(ReportVersionError) as error:
                BuildRunner(load_manifest(), backend).run()
            listed = f"sdc_report_id {', '.join(map(str, broken))} lack"
            assert listed in str(error.value)
            assert main(["build", *_target(backend, tmp_path)]) == 1
            assert listed in capsys.readouterr().err
            assert lab.snapshot() == before
            assert lab.versions() == []
        finally:
            markers = ", ".join("?" for _ in broken)
            backend.execute(f"DELETE FROM sdc.sdc_report WHERE sdc_report_id IN ({markers})",
                            broken)
        runner = BuildRunner(load_manifest(), backend)
        runner.run()
        assert [row[0] for row in lab.versions()] == [loaded]
        assert lab.selected() == {loaded}


@DIALECTS
def test_invalid_supersessions_name_their_rule_and_change_nothing(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        lab = _Lab(backend)
        n1, s1 = lab.send([(NARRATIVE, "first diagnosis"), (SYNOPTIC, "1.20")])
        (s2,) = lab.send([(SYNOPTIC, "1.30")])
        (s3,) = lab.send([(SYNOPTIC, "1.40")])
        (other_group,) = lab.send([(SYNOPTIC, "1.20")], patient="Q")
        (no_accession,) = lab.send([(SYNOPTIC, "1.20")], accession=None)

        def assert_rejected(rule: str, predecessor: int, successor: int) -> None:
            before = lab.snapshot()
            with pytest.raises(SupersessionError) as error:
                supersede_report(backend, predecessor, successor)
            assert error.value.rule == rule
            code = main(["reports", "supersede", str(predecessor), str(successor),
                         *_target(backend, tmp_path)])
            assert code == 1
            assert f"error: {rule}:" in capsys.readouterr().err
            assert lab.snapshot() == before

        assert_rejected("unversioned_report", s1, no_accession)
        assert_rejected("unversioned_report", no_accession, s2)
        assert_rejected("cross_group", s1, other_group)
        assert_rejected("cross_type", n1, s2)
        assert_rejected("predecessor_not_selected", s2, s3)

        supersede_report(backend, s1, s2)
        assert lab.selected() == {n1, s2, other_group}

        assert_rejected("cycle", s2, s1)
        assert_rejected("cycle", s2, s2)
        assert_rejected("predecessor_has_successor", s1, s3)
        assert_rejected("successor_has_predecessor", s3, s2)


@DIALECTS
def test_supersession_chain_advances_selection_one_version_at_a_time(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        lab = _Lab(backend)
        n1, s1 = lab.send([(NARRATIVE, "first diagnosis"), (SYNOPTIC, "1.20")])
        (s2,) = lab.send([(SYNOPTIC, "1.30")])
        (s3,) = lab.send([(SYNOPTIC, "1.40")])
        counts = lab.snapshot()[2]

        def links() -> dict[int, int | None]:
            return {row[0]: row[6] for row in lab.versions()}

        assert lab.selected() == {n1, s1}
        result = supersede_report(backend, s1, s2)
        assert (result.predecessor_id, result.successor_id, result.report_loinc) == (
            s1, s2, SYNOPTIC)
        assert lab.selected() == {n1, s2}
        assert links() == {n1: None, s1: None, s2: s1, s3: None}

        assert main(["reports", "supersede", str(s2), str(s3),
                     *_target(backend, tmp_path)]) == 0
        assert f"sdc_report {s3} supersedes {s2}" in capsys.readouterr().out
        assert lab.selected() == {n1, s3}
        assert links() == {n1: None, s1: None, s2: s1, s3: s2}
        # Supersession moves selection only: no source or OMOP row changes.
        assert lab.snapshot()[2] == counts

        # A later receipt and a rebuild's backfill keep the explicit selection.
        (s4,) = lab.send([(SYNOPTIC, "1.50")])
        runner = BuildRunner(load_manifest(), backend)
        runner.run()
        assert runner.backfilled_report_versions == 0
        assert lab.selected() == {n1, s3}
        assert links() == {n1: None, s1: None, s2: s1, s3: s2, s4: None}
