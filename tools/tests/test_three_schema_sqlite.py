import json
import sqlite3
import tempfile
from pathlib import Path

from sdc_cdm.naaccr.load import (
    VERSIONED_DELETE_ORDER,
    VERSIONED_FOREIGN_KEYS,
)


ROOT = Path(__file__).resolve().parents[2]


def _exec_script(conn: sqlite3.Connection, relative_path: str) -> None:
    conn.executescript((ROOT / relative_path).read_text())


def test_cross_dialect_schema_contracts() -> None:
    naaccr_ddls = [
        ROOT / "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql",
        ROOT / "database/schemas/naaccr/ddl/sqlserver/1_naaccr_sqlserver_ddl.sql",
    ]
    for ddl_path in naaccr_ddls:
        ddl = ddl_path.read_text().lower()
        assert "obx_sub_id" in ddl_path.read_text().lower()
        assert "value_text" in ddl

    sqlserver_maps = (
        ROOT
        / "database/schemas/naaccr/ddl/sqlserver/2_naaccr_concept_maps_sqlserver.sql"
    ).read_text()
    assert "target_domain_id NVARCHAR(20)" in sqlserver_maps
    assert "mapping_layer NVARCHAR(20) NOT NULL" in sqlserver_maps
    assert "CREATE OR ALTER VIEW naaccr.concept_map_coverage" in sqlserver_maps
    assert "CREATE OR ALTER VIEW naaccr.value_code_collision" in sqlserver_maps
    assert "domain_id NVARCHAR(20)" not in sqlserver_maps.replace("target_domain_id", "")

    # The NAACCR2026 supplement seeds vocabulary only; the map tables are owned by
    # manifest DDL and `maps build`. source_to_concept_map is still seeded.
    sqlserver_vocab = (
        ROOT
        / "database/schemas/naaccr/ddl/sqlserver/2_naaccr_omop_vocab_sqlserver.sql"
    ).read_text().lower()
    assert "naaccr_concept_map" not in sqlserver_vocab
    assert "naaccr_value_concept_map" not in sqlserver_vocab
    assert "source_to_concept_map" in sqlserver_vocab

    delete_position = {
        table: position for position, table in enumerate(VERSIONED_DELETE_ORDER)
    }
    for child, parents in VERSIONED_FOREIGN_KEYS.items():
        for parent in parents:
            assert delete_position[child] < delete_position[parent]

    sqlite_dictionary = naaccr_ddls[0].read_text().lower()
    sqlserver_dictionary = (
        ROOT / "database/schemas/naaccr/ddl/sqlserver/0_naaccr_dictionary_sqlserver.sql"
    ).read_text().lower()
    for ddl in (sqlite_dictionary, sqlserver_dictionary):
        assert "naaccr_item_allowed_code" in ddl
        assert "naaccr_item_registry_requirement" in ddl
        assert "alternate_names" in ddl
    assert "schema_selection_rule_id" in sqlserver_dictionary


def test_sqlite_three_schema_layout(tmp_path: Path) -> None:
    """OMOP-01: the attached-database layout. The bridge itself is covered by
    src/python/tests/test_bridge.py and test_validate.py."""
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
        "response_string",
    } <= form_answer_columns
    assert "report_id" not in form_answer_columns

    conn.executescript(
        """
        INSERT INTO naaccr.data_dictionary_version (algorithm, version)
        VALUES ('EOD', 'test');

        INSERT INTO naaccr.staging_schema (
            dd_version_id, schema_id_number, schema_id
        ) VALUES (1, 'test-schema', 'test-schema');

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

        INSERT INTO sdc.sdc_form_answer (question_sdcid, question_text, response)
        VALUES ('100.1', 'Question text', 'Answer text');
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
            ({dd}, '00460', 3827, 'input', 1),
            ({dd}, '00460', 3605, 'output', 0);

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
        "UPDATE naaccr.data_dictionary_version SET is_current = 0 "
        "WHERE algorithm = 'eod_public'"
    )
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
        "        FROM naaccr.data_dictionary_version "
        "        WHERE algorithm = 'eod_public' AND is_current = 1)"
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
    test_cross_dialect_schema_contracts()
    with tempfile.TemporaryDirectory() as temp_dir:
        test_sqlite_three_schema_layout_and_bridge(Path(temp_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        test_naaccr_dictionary_versioning_and_features(Path(temp_dir))
    print("three-schema sqlite tests passed")
