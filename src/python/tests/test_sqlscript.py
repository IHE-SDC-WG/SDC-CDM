from __future__ import annotations

from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlscript import split_sqlite_script, split_sqlserver_script


def test_sqlite_splitter_strips_commented_transaction_control() -> None:
    result = split_sqlite_script(
        """
        PRAGMA foreign_keys = ON;
        BEGIN TRANSACTION;
        CREATE TABLE example (value TEXT DEFAULT 'COMMIT;');
        -- HINT DISTRIBUTE ON RANDOM
        COMMIT;
        """
    )

    assert result.stripped_transaction_control == 2
    assert len(result.executable) == 2
    assert result.executable[0].startswith("PRAGMA")
    assert "CREATE TABLE" in result.executable[1]


def test_sqlserver_splitter_removes_go_and_preserves_batches() -> None:
    result = split_sqlserver_script(
        """
        EXEC('CREATE SCHEMA naaccr');
        GO
        CREATE TABLE naaccr.example (id INT);
        go
        """
    )

    assert result.stripped_batch_separators == 2
    assert len(result.executable) == 2
    assert result.executable[0].startswith("EXEC")
    assert result.executable[1].startswith("CREATE TABLE")


def test_real_manifest_script_counts_are_pinned() -> None:
    expected = {
        "sqlite": {
            "database/schemas/etl/ddl/sqlite/1_etl_sqlite_ddl.sql": (5, 2),
            "database/schemas/intake/ddl/sqlite/1_intake_sqlite_ddl.sql": (7, 2),
            "database/schemas/omop/ddl/sqlite/1_OMOPCDM_sqlite_5.4_ddl.sql": (40, 2),
            "database/schemas/omop/ddl/sqlite/2_OMOPCDM_sqlite_5.4_primary_keys.sql": (0, 0),
            "database/schemas/omop/ddl/sqlite/3_OMOPCDM_sqlite_5.4_constraints.sql": (0, 0),
            "database/schemas/omop/ddl/sqlite/4_OMOPCDM_sqlite_5.4_indices.sql": (70, 0),
            "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql": (20, 2),
            "database/schemas/sdc/ddl/sqlite/1_sdc_sqlite_ddl.sql": (12, 2),
        },
        "sqlserver": {
            "database/schemas/etl/ddl/sqlserver/1_etl_sqlserver_ddl.sql": (4, 4),
            "database/schemas/intake/ddl/sqlserver/1_intake_sqlserver_ddl.sql": (4, 4),
            "database/schemas/omop/ddl/sqlserver/1_OMOPCDM_sqlserver_5.4_ddl.sql": (2, 1),
            "database/schemas/omop/ddl/sqlserver/2_OMOPCDM_sqlserver_5.4_primary_keys.sql": (1, 0),
            "database/schemas/omop/ddl/sqlserver/3_OMOPCDM_sqlserver_5.4_constraints.sql": (1, 0),
            "database/schemas/omop/ddl/sqlserver/4_OMOPCDM_sqlserver_5.4_indices.sql": (1, 0),
            "database/schemas/naaccr/ddl/sqlserver/0_naaccr_dictionary_sqlserver.sql": (1, 0),
            "database/schemas/naaccr/ddl/sqlserver/1_naaccr_sqlserver_ddl.sql": (2, 2),
            "database/schemas/sdc/ddl/sqlserver/1_sdc_sqlserver_ddl.sql": (10, 10),
        },
    }

    manifest = load_manifest()
    actual: dict[str, dict[str, tuple[int, int]]] = {"sqlite": {}, "sqlserver": {}}
    for dialect in actual:
        for entry in manifest.entries_for(dialect):
            sql = repository_path(entry.path).read_text(encoding="utf-8")
            result = (
                split_sqlite_script(sql)
                if dialect == "sqlite"
                else split_sqlserver_script(sql)
            )
            stripped = (
                result.stripped_transaction_control
                if dialect == "sqlite"
                else result.stripped_batch_separators
            )
            actual[dialect][entry.path] = (len(result.executable), stripped)

    assert actual == expected
