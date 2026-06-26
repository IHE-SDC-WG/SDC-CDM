import sqlite3
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

    assert "sdc_form_answer_id" not in measurement_columns
    assert "sdc_form_answer_id" not in observation_columns
    assert not {c for c in measurement_columns if c.startswith("sdc_")}
    assert not {c for c in observation_columns if c.startswith("sdc_")}

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
            template_name, template_version, template_instance_guid, person_id, report_accession, report_text
        )
        VALUES ('Adrenal', '1', 'report-guid-1', 1, 'ACC-1', 'Report text');

        INSERT INTO sdc.sdc_form_answer (report_id, question_sdcid, question_text)
        VALUES (1, '100.1', 'Question text');

        INSERT INTO naaccr.naaccr_value (
            person_id, episode_key, report_accession, item_num, value_code, observation_date
        )
        VALUES (1, 'episode-1', 'ACC-1', 100, 'A', '2026-06-22');
        """
    )

    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")

    assert conn.execute("SELECT note_source_value FROM omop.note").fetchall() == [("ACC-1",)]
    assert conn.execute(
        "SELECT measurement_source_value, value_source_value, measurement_event_id FROM omop.measurement"
    ).fetchall() == [("100", "A", 1)]
