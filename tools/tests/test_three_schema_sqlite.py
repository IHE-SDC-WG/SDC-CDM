import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _exec_script(conn: sqlite3.Connection, relative_path: str) -> None:
    conn.executescript((ROOT / relative_path).read_text())


def test_sqlite_three_schema_layout_and_bridge(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "control.db")
    conn.executescript(
        f"""
        ATTACH DATABASE '{tmp_path / "omop.db"}' AS omop;
        ATTACH DATABASE '{tmp_path / "naaccr.db"}' AS naaccr;
        ATTACH DATABASE '{tmp_path / "sdc.db"}' AS sdc;
        """
    )

    _exec_script(conn, "database/schemas/omop/ddl/sqlite/1_OMOPCDM_sqlite_5.4_ddl.sql")
    _exec_script(conn, "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql")
    _exec_script(conn, "database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql")

    measurement_columns = {
        row[1] for row in conn.execute("PRAGMA omop.table_info(measurement)")
    }
    observation_columns = {
        row[1] for row in conn.execute("PRAGMA omop.table_info(observation)")
    }
    form_answer_columns = {
        row[1] for row in conn.execute("PRAGMA sdc.table_info(sdc_form_answer)")
    }
    naaccr_value_columns = {
        row[1] for row in conn.execute("PRAGMA naaccr.table_info(naaccr_value)")
    }

    assert "sdc_report_id" in naaccr_value_columns

    assert "sdc_form_answer_id" not in measurement_columns
    assert "sdc_form_answer_id" not in observation_columns
    assert not {c for c in measurement_columns if c.startswith("sdc_")}
    assert not {c for c in observation_columns if c.startswith("sdc_")}
    assert {
        "response",
        "units",
        "response_int",
        "response_float",
        "response_datetime",
        "reponse_string_nvarchar",
    } <= form_answer_columns
    assert "report_id" not in form_answer_columns

    conn.executescript(
        """
        INSERT INTO omop.concept (
            concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
            concept_code, valid_start_date, valid_end_date
        )
        VALUES
            (0, 'Unknown', 'Metadata', 'None', 'None', '0', '1970-01-01', '2099-12-31'),
            (32817, 'EHR', 'Type Concept', 'Type Concept', 'Type Concept', 'EHR', '1970-01-01', '2099-12-31'),
            (1147289, 'note.note_id', 'Metadata', 'CDM', 'Field', 'note.note_id', '1970-01-01', '2099-12-31');

        INSERT INTO omop.person (
            gender_concept_id, year_of_birth, race_concept_id, ethnicity_concept_id, person_source_value
        )
        VALUES (0, 1970, 0, 0, 'patient-1');

        INSERT INTO sdc.sdc_report (
            template_name, template_version, template_instance_guid, person_id,
            report_accession, report_text, is_duplicate_accession, first_seen_report_id
        )
        VALUES
            -- sdc_report_id 1: the one non-duplicate accessioned report.
            ('Adrenal', '1', 'report-guid-1', 1, 'ACC-1', 'Report text', 0, NULL),
            -- sdc_report_id 2: a re-import of ACC-1, flagged duplicate (Bug 1 regression).
            ('Adrenal', '1', 'report-guid-2', 1, 'ACC-1', 'Duplicate report text', 1, 1),
            -- sdc_report_id 3/4: accession-less reports, NULL and '' (Bug 2 regression).
            ('Adrenal', '1', 'report-guid-3', 1, NULL, 'No-accession report (NULL)', 0, NULL),
            ('Adrenal', '1', 'report-guid-4', 1, '', 'No-accession report (empty)', 0, NULL);

        INSERT INTO sdc.sdc_form_answer (question_sdcid, question_text, response)
        VALUES ('100.1', 'Question text', 'Answer text');

        INSERT INTO naaccr.naaccr_value (
            person_id, episode_key, sdc_report_id, report_accession, item_num, value_code, observation_date
        )
        VALUES
            -- Values for the non-duplicate report (should bridge to 2 measurements).
            (1, 'episode-1', 1, 'ACC-1', 100, 'A', '2026-06-22'),
            (1, 'episode-1', 1, 'ACC-1', 100, 'A', '2026-06-22'),
            -- Bug 1: values from the duplicate re-import, present before the first bridge.
            -- They point at the duplicate report (id 2) so they must never bridge.
            (1, 'episode-1', 2, 'ACC-1', 100, 'A', '2026-06-22'),
            (1, 'episode-1', 2, 'ACC-1', 100, 'A', '2026-06-22'),
            -- Bug 2: values on accession-less reports (NULL and '') must never bridge.
            (1, 'episode-1', 3, NULL, 100, 'A', '2026-06-22'),
            (1, 'episode-1', 4, '', 100, 'A', '2026-06-22');
        """
    )

    assert conn.execute(
        "SELECT response FROM sdc.sdc_form_answer"
    ).fetchall() == [("Answer text",)]

    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")

    assert conn.execute("SELECT note_source_value FROM omop.note").fetchall() == [("ACC-1",)]
    assert conn.execute(
        """
        SELECT measurement_source_value, value_source_value, measurement_event_id,
               meas_event_field_concept_id
        FROM omop.measurement
        ORDER BY measurement_id
        """
    ).fetchall() == [
        ("100", "A", 1, 1147289),
        ("100", "A", 1, 1147289),
    ]

    # Bug 1: the duplicate re-import's values were present before the first bridge, but
    # they point at the duplicate-flagged report and must not double-count.
    assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 2

    # Bug 2: accession-less reports (NULL and '') never bridge -- no note, no fan-out.
    assert conn.execute(
        "SELECT COUNT(*) FROM omop.note WHERE COALESCE(note_source_value, '') = ''"
    ).fetchone()[0] == 0

    for _ in range(2):
        _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")
        assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 2

    conn.execute(
        """
        INSERT INTO naaccr.naaccr_value (
            person_id, episode_key, sdc_report_id, report_accession, item_num, value_code, observation_date
        ) VALUES (1, 'episode-1', 1, 'ACC-1', 100, 'A', '2026-06-22')
        """
    )
    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")

    assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 2
    conn.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp_dir:
        test_sqlite_three_schema_layout_and_bridge(Path(temp_dir))
    print("three-schema sqlite tests passed")
