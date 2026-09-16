from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlscript import split_script
from sdc_cdm.db.sqlserver_backend import SqlServerBackend

MAP_CONTRACT = {
    "source_concept_id",
    "concept_id",
    "target_domain_id",
    "concept_code",
    "concept_name",
    "mapping_layer",
    "created_at",
}
ALLOCATION_CONTRACT = {
    "concept_id",
    "concept_kind",
    "item_num",
    "code",
    "concept_code",
    "concept_name",
    "allocated_at",
}
COVERAGE_COLUMNS = {"algorithm", "scope", "section", "mapping_layer", "item_count"}
NAACCR_DDL = {
    "sqlite": "database/schemas/naaccr/ddl/sqlite/1_naaccr_sqlite_ddl.sql",
    "sqlserver": "database/schemas/naaccr/ddl/sqlserver/2_naaccr_concept_maps_sqlserver.sql",
}


@contextmanager
def _backend(dialect: str, tmp_path: Path) -> Iterator[DatabaseBackend]:
    if dialect == "sqlite":
        backend: DatabaseBackend = SQLiteBackend(tmp_path / "maps.db")
    else:
        connection_string = os.environ.get("SDC_CDM_SQLSERVER_CONNECTION_STRING")
        if not connection_string:
            pytest.skip("SDC_CDM_SQLSERVER_CONNECTION_STRING is not set")
        backend = SqlServerBackend(connection_string)
    try:
        yield backend
    finally:
        backend.close()


def _insert_id(
    backend: DatabaseBackend,
    sqlite_sql: str,
    sqlserver_sql: str,
    parameters: tuple[object, ...],
) -> int:
    if backend.dialect == "sqlite":
        return int(backend.execute(sqlite_sql, parameters))
    return int(backend.execute(sqlserver_sql, parameters, return_scalar=True))


def _columns(backend: DatabaseBackend, name: str) -> set[str]:
    if backend.dialect == "sqlite":
        rows = backend.fetch_all(f'PRAGMA "naaccr".table_info("{name}")')
        return {str(row[1]) for row in rows}
    rows = backend.fetch_all(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'naaccr' AND TABLE_NAME = ?",
        (name,),
    )
    return {str(row[0]) for row in rows}


def _reapply_naaccr_ddl(backend: DatabaseBackend) -> None:
    sql = repository_path(NAACCR_DDL[backend.dialect]).read_text(encoding="utf-8")
    backend.execute_units(split_script(backend.dialect, sql).executable)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_concept_map_ddl_and_coverage_view(dialect: str, tmp_path: Path) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        # The naaccr DDL is reapplied on change, so it must be re-runnable as-is.
        _reapply_naaccr_ddl(backend)

        for table in (
            "naaccr_concept_map",
            "naaccr_value_concept_map",
            "local_concept_allocation",
        ):
            assert backend.table_exists("naaccr", table), table
        assert MAP_CONTRACT | {"item_num"} <= _columns(backend, "naaccr_concept_map")
        assert MAP_CONTRACT | {"item_num", "code"} <= _columns(
            backend, "naaccr_value_concept_map"
        )
        assert ALLOCATION_CONTRACT <= _columns(backend, "local_concept_allocation")
        assert "domain_id" not in _columns(backend, "naaccr_concept_map")
        assert _columns(backend, "concept_map_coverage") == COVERAGE_COLUMNS

        # Unique names and ids keep reruns against a persistent SQL Server database
        # collision-free; the maps carry no algorithm key.
        token = uuid.uuid4().hex[:6]
        algorithm = f"coverage_{token}"
        base = 1_000_000 + int(token, 16)
        mapped, unmapped, retired = base + 1, base + 2, base + 3
        local_id = 2_100_000_000 + base
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        dd_version_id = _insert_id(
            backend,
            "INSERT INTO naaccr.data_dictionary_version (algorithm, version) "
            "VALUES (?, ?)",
            "INSERT INTO naaccr.data_dictionary_version (algorithm, version) "
            "OUTPUT INSERTED.dd_version_id VALUES (?, ?)",
            (algorithm, "test"),
        )
        for item_num, year_retired in ((mapped, None), (unmapped, None), (retired, 2018)):
            backend.execute(
                "INSERT INTO naaccr.naaccr_item "
                "(dd_version_id, item_num, name, section, year_retired) "
                "VALUES (?, ?, ?, ?, ?)",
                (dd_version_id, item_num, f"Item {item_num}", "Demographic", year_retired),
            )
        for item_num, code_seq, code in (
            (mapped, 1, "A"),
            (mapped, 2, "B"),
            (unmapped, 1, "X"),
            (retired, 1, "Z"),
        ):
            backend.execute(
                "INSERT INTO naaccr.naaccr_item_allowed_code "
                "(dd_version_id, item_num, code_seq, code) VALUES (?, ?, ?, ?)",
                (dd_version_id, item_num, code_seq, code),
            )

        backend.execute(
            "INSERT INTO naaccr.naaccr_concept_map "
            "(item_num, source_concept_id, concept_id, target_domain_id, concept_code, "
            "concept_name, mapping_layer, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mapped,
                base + 10,
                0,
                "Measurement",
                str(mapped),
                "Mapped item",
                "athena_standard",
                created_at,
            ),
        )
        backend.execute(
            "INSERT INTO naaccr.local_concept_allocation "
            "(concept_id, concept_kind, item_num, code, concept_code, concept_name, "
            "allocated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (local_id, "value", mapped, "A", f"{mapped}^A", "A", created_at),
        )
        backend.execute(
            "INSERT INTO naaccr.naaccr_value_concept_map "
            "(item_num, code, source_concept_id, concept_id, target_domain_id, "
            "concept_code, concept_name, mapping_layer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mapped, "A", local_id, 0, "Meas Value", f"{mapped}^A", "A", "local_mint", created_at),
        )

        # Contract checks: local ids stay in range and source concepts are never zero.
        with pytest.raises(Exception):
            backend.execute(
                "INSERT INTO naaccr.local_concept_allocation "
                "(concept_id, concept_kind, item_num, code, concept_code, allocated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (2_000_000_000 + base, "item", unmapped, "", f"{unmapped}", created_at),
            )
        with pytest.raises(Exception):
            backend.execute(
                "INSERT INTO naaccr.naaccr_concept_map "
                "(item_num, source_concept_id, concept_id, mapping_layer, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (unmapped, 0, 0, "local_mint", created_at),
            )
        with pytest.raises(Exception):
            backend.execute(
                "INSERT INTO naaccr.naaccr_concept_map "
                "(item_num, source_concept_id, concept_id, mapping_layer, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (unmapped, base + 11, 0, "guess", created_at),
            )

        stored = backend.fetch_one(
            "SELECT created_at FROM naaccr.naaccr_concept_map WHERE item_num = ?",
            (mapped,),
        )[0]
        assert stored == created_at

        rows = backend.fetch_all(
            "SELECT scope, section, mapping_layer, item_count "
            "FROM naaccr.concept_map_coverage WHERE algorithm = ? "
            "ORDER BY scope, mapping_layer",
            (algorithm,),
        )
        assert [tuple(row) for row in rows] == [
            ("item", "Demographic", "athena_standard", 1),
            ("item", "Demographic", "unmapped", 1),
            ("value", "Demographic", "local_mint", 1),
            ("value", "Demographic", "unmapped", 2),
        ]
