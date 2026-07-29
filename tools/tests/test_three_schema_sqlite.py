import json
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _exec_script(conn: sqlite3.Connection, relative_path: str) -> None:
    conn.executescript((ROOT / relative_path).read_text())


def test_cross_dialect_schema_and_docker_bootstrap() -> None:
    postgres_sdc = (
        ROOT / "database/schemas/sdc/ddl/postgresql/1_sdc_postgresql_ddl.sql"
    ).read_text()
    expected_sdc_tables = {
        "template_sdc",
        "template_item",
        "template_instance",
        "sdc_report",
        "sdc_form_answer",
        "template_term_map",
        "template_map_content",
        "sdc_specimen",
        "observation_specimens",
    }
    assert all(
        f"CREATE TABLE IF NOT EXISTS sdc.{table}" in postgres_sdc
        for table in expected_sdc_tables
    )
    assert "idx_sdc_report_accession" in postgres_sdc
    assert "idx_sdc_form_answer_instance_question" in postgres_sdc

    naaccr_ddls = [
        ROOT / "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql",
        ROOT / "database/schemas/naaccr/ddl/postgresql/1_naaccr_postgresql_ddl.sql",
        ROOT / "database/schemas/naaccr/ddl/sqlserver/1_naaccr_sqlserver_ddl.sql",
    ]
    for ddl_path in naaccr_ddls:
        ddl = ddl_path.read_text().lower()
        assert "obx_sub_id" in ddl_path.read_text().lower()
        assert "value_text" in ddl

    postgres_naaccr = naaccr_ddls[1].read_text()
    for index_name in (
        "idx_naaccr_value_person_episode",
        "idx_naaccr_value_report_item",
        "idx_naaccr_value_item_code",
        "idx_naaccr_value_sdc_report",
    ):
        assert index_name in postgres_naaccr

    sqlserver_vocab = (
        ROOT
        / "database/schemas/naaccr/ddl/sqlserver/2_naaccr_omop_vocab_sqlserver.sql"
    ).read_text()
    assert "COL_LENGTH('naaccr.NAACCR_CONCEPT_MAP', 'domain_id')" in sqlserver_vocab
    assert "domain_id NVARCHAR(20)" in sqlserver_vocab

    sqlserver_bridge = (
        ROOT / "database/etl/sqlserver/1_naaccr_sdc_to_omop.sql"
    ).read_text()
    assert ";WITH report_dates AS" in sqlserver_bridge
    assert "GROUP BY\n    sr.sdc_report_id" not in sqlserver_bridge
    assert "HASHBYTES('SHA2_256'" in sqlserver_bridge

    dockerfile = (ROOT / "database/Dockerfile").read_text().splitlines()
    copy_lines = [line for line in dockerfile if line.startswith("COPY ")]
    assert [line.split()[2] for line in copy_lines] == [
        "/docker-entrypoint-initdb.d/10_omop_ddl.sql",
        "/docker-entrypoint-initdb.d/20_omop_primary_keys.sql",
        "/docker-entrypoint-initdb.d/30_omop_constraints.sql",
        "/docker-entrypoint-initdb.d/40_omop_indices.sql",
        "/docker-entrypoint-initdb.d/50_naaccr_ddl.sql",
        "/docker-entrypoint-initdb.d/60_sdc_ddl.sql",
    ]
    assert all((ROOT / "database" / line.split()[1]).is_file() for line in copy_lines)

    ssdi_loader = (
        ROOT / "tools/ssdi-ts/src/load-3nf-to-sqlserver.ts"
    ).read_text()
    assert "transaction.begin(sql.ISOLATION_LEVEL.SERIALIZABLE)" in ssdi_loader
    assert "await transaction.commit()" in ssdi_loader
    assert "await transaction.rollback()" in ssdi_loader
    delete_order = [
        "naaccr.SCHEMA_INVOLVED_TABLE",
        "naaccr.SCHEMA_ITEM_CODE",
        "naaccr.SCHEMA_ITEM_REQUIREMENT",
        "naaccr.SCHEMA_ITEM",
        "naaccr.SCHEMA_SELECTION_RULE",
        "naaccr.STAGING_TABLE_ROW",
        "naaccr.STAGING_TABLE_COLUMN",
        "naaccr.STAGING_TABLE",
        "naaccr.NAACCR_ITEM",
        "naaccr.STAGING_SCHEMA",
    ]
    delete_block = ssdi_loader[
        ssdi_loader.index("const VERSIONED_DELETE_ORDER"):
        ssdi_loader.index("async function clearVersionedRows")
    ]
    assert [delete_block.index(f"'{table}'") for table in delete_order] == sorted(
        delete_block.index(f"'{table}'") for table in delete_order
    )


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
    requirement_fk_targets = {
        row[2]
        for row in conn.execute(
            "PRAGMA naaccr.foreign_key_list(schema_item_requirement)"
        )
    }

    assert {"sdc_report_id", "obx_sub_id", "value_text"} <= naaccr_value_columns
    # SQLite requires unqualified REFERENCES targets. For a table in an attached
    # database, these names resolve within that same attached database.
    assert {"registry", "schema_item"} <= requirement_fk_targets

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
            (32879, 'Registry', 'Type Concept', 'Type Concept', 'Type Concept', 'Registry', '1970-01-01', '2099-12-31'),
            (1147289, 'note.note_id', 'Metadata', 'CDM', 'Field', 'note.note_id', '1970-01-01', '2099-12-31');

        INSERT INTO naaccr.data_dictionary_version (algorithm, version)
        VALUES ('EOD', 'test');

        INSERT INTO naaccr.staging_schema (dd_version_id, schema_id_number)
        VALUES (1, 'test-schema');

        INSERT INTO naaccr.naaccr_item (dd_version_id, item_num, name)
        VALUES (1, 100, 'Test item');

        INSERT INTO naaccr.schema_item (dd_version_id, schema_id_number, item_num)
        VALUES (1, 'test-schema', 100);

        INSERT INTO naaccr.registry (code, name)
        VALUES ('TEST', 'Test registry');

        INSERT INTO naaccr.schema_item_requirement (
            dd_version_id, schema_id_number, item_num, registry_id, is_required
        )
        VALUES (1, 'test-schema', 100, 1, 1);

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
            -- Distinct values for the non-duplicate report.
            (1, 'episode-1', 1, 'ACC-1', 100, 'A', '2026-06-22'),
            (1, 'episode-1', 1, 'ACC-1', 200, 'B', '2026-06-22'),
            -- Identical values from one report are distinct source occurrences.
            (1, 'episode-1', 1, 'ACC-1', 400, 'D', '2026-06-22'),
            (1, 'episode-1', 1, 'ACC-1', 400, 'D', '2026-06-22'),
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

    try:
        conn.execute(
            """
            INSERT INTO naaccr.schema_item_requirement (
                dd_version_id, schema_id_number, item_num, registry_id, is_required
            )
            VALUES (1, 'test-schema', 100, 1, 0)
            """
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("duplicate schema item requirement was accepted")

    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")

    assert conn.execute("SELECT note_source_value FROM omop.note").fetchall() == [("ACC-1",)]
    assert conn.execute(
        """
        SELECT measurement_source_value, value_source_value, measurement_type_concept_id,
               measurement_event_id, meas_event_field_concept_id
        FROM omop.measurement
        ORDER BY measurement_id
        """
    ).fetchall() == [
        ("100", "A", 32879, 1, 1147289),
        ("200", "B", 32879, 1, 1147289),
        ("400", "D", 32879, 1, 1147289),
        ("400", "D", 32879, 1, 1147289),
    ]

    # Bug 1: the duplicate re-import's values were present before the first bridge, but
    # they point at the duplicate-flagged report and must not double-count.
    assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 4

    # Bug 2: accession-less reports (NULL and '') never bridge -- no note, no fan-out.
    assert conn.execute(
        "SELECT COUNT(*) FROM omop.note WHERE COALESCE(note_source_value, '') = ''"
    ).fetchone()[0] == 0

    for _ in range(2):
        _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")
        assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 4

    # A partial load is repaired per value rather than being blocked by the note-level anchor.
    conn.execute(
        "DELETE FROM omop.measurement WHERE measurement_source_value = '200'"
    )
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 3
    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 4
    assert conn.execute(
        "SELECT COUNT(*) FROM omop.measurement WHERE measurement_source_value = '200'"
    ).fetchone()[0] == 1

    conn.execute(
        """
        INSERT INTO naaccr.naaccr_value (
            person_id, episode_key, sdc_report_id, report_accession, item_num, value_code, observation_date
        ) VALUES (1, 'episode-1', 1, 'ACC-1', 300, 'C', '2026-06-22')
        """
    )
    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")

    assert conn.execute("SELECT COUNT(*) FROM omop.note").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 5
    assert conn.execute(
        "SELECT COUNT(*) FROM omop.measurement WHERE measurement_source_value = '300'"
    ).fetchone()[0] == 1

    _exec_script(conn, "database/etl/sqlite/1_naaccr_sdc_to_omop.sql")
    assert conn.execute("SELECT COUNT(*) FROM omop.measurement").fetchone()[0] == 5
    assert conn.execute(
        "SELECT COUNT(*) FROM omop.measurement WHERE measurement_type_concept_id <> 32879"
    ).fetchone()[0] == 0
    conn.close()


def test_naaccr_dictionary_versioning_and_features(tmp_path: Path) -> None:
    """SEER-derived schema features (gaps 1-5): version dimension, field metadata,
    staging-table catalog, staging outputs, and code validation."""
    conn = sqlite3.connect(tmp_path / "control.db")
    conn.executescript(f"ATTACH DATABASE '{tmp_path / 'naaccr.db'}' AS naaccr;")
    _exec_script(conn, "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql")

    def cols(table: str) -> set:
        return {row[1] for row in conn.execute(f"PRAGMA naaccr.table_info({table})")}

    # Gap #2: field metadata columns exist on naaccr_item.
    assert {"unit", "decimal_places", "data_type", "length", "section"} <= cols("naaccr_item")
    # Gap #4: item_role exists on schema_item.
    assert "item_role" in cols("schema_item")
    # Gap #1: dd_version_id stamp exists on naaccr_value.
    assert "dd_version_id" in cols("naaccr_value")
    # Gap #3: staging-table catalog tables exist.
    for t in ("staging_table", "staging_table_column", "staging_table_row", "schema_involved_table"):
        assert cols(t), f"missing table {t}"

    # Gap #1: create a version and scope everything to it.
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO naaccr.data_dictionary_version (algorithm, version, naaccr_version, source_api) "
        "VALUES ('eod_public', '3.3', '23', 'https://api.seer.cancer.gov/rest/staging/eod_public/3.3')"
    )
    dd = cur.lastrowid

    conn.executescript(
        f"""
        INSERT INTO naaccr.staging_schema (dd_version_id, schema_id_number, schema_id, schema_name)
        VALUES ({dd}, '00460', 'adrenal_gland', 'Adrenal Gland');

        -- an input item (with field metadata) and an output item.
        INSERT INTO naaccr.naaccr_item (dd_version_id, item_num, name, xml_id, unit, decimal_places, data_type, length, section)
        VALUES
            ({dd}, 3827, 'Adrenal Gland SSDI', 'ssdiAdrenal', NULL, NULL, 'digits', 3, 'Stage/Prognostic Factors'),
            ({dd}, 3605, 'Derived Summary Stage 2018', 'derivedSummaryStage2018', NULL, NULL, 'digits', 1, 'Stage/Prognostic Factors');

        INSERT INTO naaccr.schema_item (dd_version_id, schema_id_number, item_num, item_role, used_for_staging)
        VALUES
            ({dd}, '00460', 3827, 'input', 'true'),
            ({dd}, '00460', 3605, 'output', 'false');

        INSERT INTO naaccr.schema_item_code (dd_version_id, schema_id_number, item_num, code, description)
        VALUES
            ({dd}, '00460', 3827, '000', 'Not present'),
            ({dd}, '00460', 3827, '100', 'Present');

        INSERT INTO naaccr.staging_table (dd_version_id, table_key, name) VALUES ({dd}, 'ssdi_adrenal', 'SSDI Adrenal');
        INSERT INTO naaccr.staging_table_column (dd_version_id, table_key, col_index, col_key, col_name)
        VALUES ({dd}, 'ssdi_adrenal', 0, 'code', 'Code'), ({dd}, 'ssdi_adrenal', 1, 'description', 'Description');
        INSERT INTO naaccr.staging_table_row (dd_version_id, table_key, row_index, cells)
        VALUES ({dd}, 'ssdi_adrenal', 0, '["000","Not present"]'), ({dd}, 'ssdi_adrenal', 1, '["100","Present"]');
        INSERT INTO naaccr.schema_involved_table (dd_version_id, schema_id_number, table_key)
        VALUES ({dd}, '00460', 'ssdi_adrenal');

        -- a captured value stamped with the dictionary version it was coded against.
        INSERT INTO naaccr.naaccr_value
            (person_id, episode_key, report_accession, schema_id_number, item_num, value_code, observation_date, dd_version_id)
        VALUES
            (1, 'episode-1', 'ACC-1', '00460', 3827, '000', '2026-06-22', {dd}),
            (1, 'episode-1', 'ACC-1', '00460', 3827, '999', '2026-06-22', {dd});
        """
    )

    # Gap #2: field metadata round-trips.
    assert conn.execute(
        "SELECT data_type, length FROM naaccr.naaccr_item WHERE dd_version_id = ? AND item_num = 3827",
        (dd,),
    ).fetchone() == ("digits", 3)

    # Gap #4: exactly one output-role item in this schema.
    assert conn.execute(
        "SELECT COUNT(*) FROM naaccr.schema_item WHERE dd_version_id = ? AND item_role = 'output'",
        (dd,),
    ).fetchone()[0] == 1

    # Gap #1: the captured value carries its dictionary version.
    assert conn.execute(
        "SELECT dd_version_id FROM naaccr.naaccr_value WHERE report_accession = 'ACC-1'"
    ).fetchone()[0] == dd

    cur.execute(
        "INSERT INTO naaccr.data_dictionary_version (algorithm, version) "
        "VALUES ('eod_public', '3.4')"
    )
    dd2 = cur.lastrowid
    cur.execute(
        "INSERT INTO naaccr.naaccr_item "
        "(dd_version_id, item_num, name, xml_id) VALUES (?, 3827, 'Adrenal Gland SSDI vNext', 'ssdiAdrenal')",
        (dd2,),
    )
    version_scoped_rows = conn.execute(
        "SELECT COUNT(*) FROM naaccr.naaccr_value nv "
        "JOIN naaccr.naaccr_item ni "
        "  ON ni.item_num = nv.item_num "
        " AND ni.dd_version_id = COALESCE("
        "       nv.dd_version_id, "
        "       (SELECT MAX(dd_version_id) "
        "        FROM naaccr.data_dictionary_version WHERE is_current = 1)"
        "     ) "
        "WHERE nv.value_code = '000'"
    ).fetchone()[0]
    assert version_scoped_rows == 1

    # Code validation: a captured value_code validates against schema_item_code.
    def code_is_allowed(code: str) -> bool:
        return conn.execute(
            "SELECT COUNT(*) FROM naaccr.naaccr_value nv "
            "JOIN naaccr.schema_item_code sic "
            "  ON sic.dd_version_id = nv.dd_version_id "
            " AND sic.schema_id_number = nv.schema_id_number "
            " AND sic.item_num = nv.item_num "
            " AND sic.code = nv.value_code "
            "WHERE nv.value_code = ?",
            (code,),
        ).fetchone()[0] > 0

    assert code_is_allowed("000")   # present in schema_item_code
    assert not code_is_allowed("999")  # not an allowable code

    # Gap #3: staging-table row cells round-trip as JSON aligned to the columns.
    ncols = conn.execute(
        "SELECT COUNT(*) FROM naaccr.staging_table_column WHERE dd_version_id = ? AND table_key = 'ssdi_adrenal'",
        (dd,),
    ).fetchone()[0]
    for (cells,) in conn.execute(
        "SELECT cells FROM naaccr.staging_table_row WHERE dd_version_id = ? AND table_key = 'ssdi_adrenal'",
        (dd,),
    ):
        assert len(json.loads(cells)) == ncols

    conn.close()


if __name__ == "__main__":
    test_cross_dialect_schema_and_docker_bootstrap()
    with tempfile.TemporaryDirectory() as temp_dir:
        test_sqlite_three_schema_layout_and_bridge(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_naaccr_dictionary_versioning_and_features(Path(temp_dir))
    print("three-schema sqlite tests passed")
