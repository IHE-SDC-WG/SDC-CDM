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
COLLISION_COLUMNS = {
    "algorithm",
    "dd_version_id",
    "item_num",
    "code",
    "schema_count",
    "description_count",
    "obsolete_count",
    "description_min",
    "description_max",
    "source_concept_id",
    "concept_id",
    "mapping_layer",
}
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
            "concept_map_build_state",
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
        assert {"singleton_id", "algorithm", "dd_version_id", "built_at"} <= _columns(
            backend, "concept_map_build_state"
        )
        assert _columns(backend, "value_code_collision") == COLLISION_COLUMNS

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

        assert backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.concept_map_coverage WHERE algorithm = ?",
            (algorithm,),
        )[0] == 0
        backend.execute("DELETE FROM naaccr.concept_map_build_state")
        backend.execute(
            "INSERT INTO naaccr.concept_map_build_state "
            "(singleton_id, algorithm, dd_version_id, built_at) VALUES (1, ?, ?, ?)",
            (algorithm, dd_version_id, created_at),
        )

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


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_value_code_collision_view(dialect: str, tmp_path: Path) -> None:
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()

        token = uuid.uuid4().hex[:6]
        algorithm = f"collision_{token}"
        base = 1_000_000 + int(token, 16)
        colliding, single, old_only = base + 1, base + 2, base + 3
        local_id = 2_100_000_000 + base
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        def add_generation(
            version: str,
            is_current: int,
            codes: list[tuple[str, int, str, str | None]],
        ) -> int:
            dd_version_id = _insert_id(
                backend,
                "INSERT INTO naaccr.data_dictionary_version "
                "(algorithm, version, is_current) VALUES (?, ?, ?)",
                "INSERT INTO naaccr.data_dictionary_version "
                "(algorithm, version, is_current) "
                "OUTPUT INSERTED.dd_version_id VALUES (?, ?, ?)",
                (algorithm, version, is_current),
            )
            for item_num in (colliding, single, old_only):
                backend.execute(
                    "INSERT INTO naaccr.naaccr_item (dd_version_id, item_num, name) "
                    "VALUES (?, ?, ?)",
                    (dd_version_id, item_num, f"Item {item_num}"),
                )
            schema_items = sorted({(schema, item_num) for schema, item_num, _, _ in codes})
            for schema in sorted({schema for schema, _ in schema_items}):
                backend.execute(
                    "INSERT INTO naaccr.staging_schema "
                    "(dd_version_id, schema_id_number, schema_id) VALUES (?, ?, ?)",
                    (dd_version_id, schema, f"schema_{schema}"),
                )
            for schema, item_num in schema_items:
                backend.execute(
                    "INSERT INTO naaccr.schema_item "
                    "(dd_version_id, schema_id_number, item_num) VALUES (?, ?, ?)",
                    (dd_version_id, schema, item_num),
                )
            for schema, item_num, code, description in codes:
                backend.execute(
                    "INSERT INTO naaccr.schema_item_code "
                    "(dd_version_id, schema_id_number, item_num, code, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (dd_version_id, schema, item_num, code, description),
                )
            return dd_version_id

        # The superseded generation goes in first: only one row per algorithm may be current.
        old_id = add_generation(
            "old",
            0,
            [
                ("S1", colliding, "1", "Old Alpha"),
                ("S4", colliding, "1", "Old Gamma"),
                ("S1", old_only, "9", "First"),
                ("S2", old_only, "9", "Second"),
            ],
        )
        current_id = add_generation(
            "current",
            1,
            [
                ("S1", colliding, "1", "Alpha"),
                ("S2", colliding, "1", "Beta"),
                ("S3", colliding, "1", "Alpha"),
                ("S1", colliding, "2", "Live meaning"),
                ("S2", colliding, "2", "**OBSOLETE** - Please use 600"),
                ("S1", colliding, "3", "Same"),
                ("S2", colliding, "3", "  same "),
                ("S1", colliding, "4", None),
                ("S2", colliding, "4", "Named"),
                ("S1", colliding, "5", " A"),
                ("S2", colliding, "5", "0"),
                ("S3", colliding, "5", "a"),
                ("S4", colliding, "5", "   "),
                ("S1", single, "1", "Only"),
            ],
        )

        backend.execute(
            "INSERT INTO naaccr.local_concept_allocation "
            "(concept_id, concept_kind, item_num, code, concept_code, concept_name, "
            "allocated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (local_id, "value", colliding, "1", f"{colliding}^1", "Alpha", created_at),
        )
        backend.execute(
            "INSERT INTO naaccr.naaccr_value_concept_map "
            "(item_num, code, source_concept_id, concept_id, target_domain_id, "
            "concept_code, concept_name, mapping_layer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                colliding,
                "1",
                local_id,
                0,
                "Meas Value",
                f"{colliding}^1",
                "Alpha",
                "local_mint",
                created_at,
            ),
        )

        assert backend.fetch_one(
            "SELECT source_concept_id FROM naaccr.value_code_collision "
            "WHERE algorithm = ? AND item_num = ? AND code = '1'",
            (algorithm, colliding),
        )[0] is None
        backend.execute("DELETE FROM naaccr.concept_map_build_state")
        backend.execute(
            "INSERT INTO naaccr.concept_map_build_state "
            "(singleton_id, algorithm, dd_version_id, built_at) VALUES (1, ?, ?, ?)",
            (algorithm, old_id, created_at),
        )
        assert backend.fetch_one(
            "SELECT source_concept_id FROM naaccr.value_code_collision "
            "WHERE algorithm = ? AND item_num = ? AND code = '1'",
            (algorithm, colliding),
        )[0] is None
        backend.execute(
            "UPDATE naaccr.concept_map_build_state SET dd_version_id = ? "
            "WHERE singleton_id = 1", (current_id,),
        )

        rows = [
            tuple(row)
            for row in backend.fetch_all(
                "SELECT dd_version_id, item_num, code, schema_count, description_count, "
                "obsolete_count, description_min, description_max, source_concept_id, "
                "concept_id, mapping_layer "
                "FROM naaccr.value_code_collision WHERE algorithm = ? "
                "ORDER BY item_num, code",
                (algorithm,),
            )
        ]
        assert [row[:6] + row[8:] for row in rows] == [
            (current_id, colliding, "1", 3, 2, 0, local_id, 0, "local_mint"),
            (current_id, colliding, "2", 2, 2, 1, None, None, None),
            (current_id, colliding, "5", 4, 2, 0, None, None, None),
        ]
        # Collation decides whether "*" sorts before letters, so compare as a set. Samples are
        # trimmed originals of two distinct normalized meanings; SQL Server's case-insensitive
        # collation may return either "A" or "a" for code 5, so that row compares case-folded.
        assert [set(row[6:8]) for row in rows[:2]] == [
            {"Alpha", "Beta"},
            {"Live meaning", "**OBSOLETE** - Please use 600"},
        ]
        assert {sample.upper() for sample in rows[2][6:8]} == {"0", "A"}
