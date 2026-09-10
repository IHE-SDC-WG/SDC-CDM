from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.naaccr.columns import (
    ALLOWED_CODE_COLUMNS,
    ALLOWED_CODE_FILE,
    SSDI_VERSION_FILE,
    VERSION_COLUMNS,
    VERSION_FILE,
)
from sdc_cdm.naaccr.csv_io import read_csv, write_csv
from sdc_cdm.naaccr.load import (
    SSDI_ITEM_COLUMNS,
    load_dictionary,
)
from sdc_cdm.naaccr.verify import CHECK_NAMES, verify_dictionary

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_CSV = ROOT / "sample_data/test-fixtures/naaccr-dict/csv"
BROKEN_CSV = ROOT / "sample_data/test-fixtures/naaccr-dict/broken_csv"


def _copy_fixture(
    tmp_path: Path,
    *,
    algorithm: str,
    version: str = "fixture-a",
    source: Path = FIXTURE_CSV,
) -> Path:
    target = tmp_path / f"csv-{version}"
    shutil.copytree(source, target)
    row = (algorithm, version, "25", "https://api.seer.cancer.gov/rest/naaccr/25")
    write_csv(target / VERSION_FILE, VERSION_COLUMNS, [row])
    write_csv(target / SSDI_VERSION_FILE, VERSION_COLUMNS, [row])
    return target


@contextmanager
def _backend(dialect: str, tmp_path: Path) -> Iterator[DatabaseBackend]:
    if dialect == "sqlite":
        backend: DatabaseBackend = SQLiteBackend(tmp_path / "dictionary.db")
    else:
        connection_string = os.environ.get("SDC_CDM_SQLSERVER_DSN")
        if not connection_string:
            pytest.skip("SDC_CDM_SQLSERVER_DSN is not set")
        backend = SqlServerBackend(connection_string)
    try:
        yield backend
    finally:
        backend.close()


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_fixture_loads_in_both_dialects_and_is_idempotent(
    dialect: str, tmp_path: Path
) -> None:
    algorithm = f"dict_test_{uuid.uuid4().hex}"
    csv_dir = _copy_fixture(tmp_path, algorithm=algorithm)
    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        first = load_dictionary(backend, csv_dir=csv_dir)
        second = load_dictionary(backend, csv_dir=csv_dir)

        assert second.dd_version_id == first.dd_version_id
        assert second.row_counts == first.row_counts
        assert second.row_counts["naaccr_item"] == 12
        assert second.row_counts["naaccr_item_allowed_code"] == 121
        assert second.row_counts["naaccr_item_registry_requirement"] == 36
        assert second.row_counts["schema_item"] == 2
        assert second.stub_item_count == 0
        assert (
            int(
                backend.fetch_one(
                    "SELECT COUNT(*) FROM naaccr.data_dictionary_version "
                    "WHERE algorithm = ? AND is_current = 1",
                    (algorithm,),
                )[0]
            )
            == 1
        )

        item = backend.qualified_name("naaccr", "naaccr_item")
        code = backend.qualified_name("naaccr", "naaccr_item_allowed_code")
        schema_item = backend.qualified_name("naaccr", "schema_item")
        assert (
            int(
                backend.fetch_one(
                    f"SELECT COUNT(*) FROM {item} WHERE dd_version_id = ?",
                    (first.dd_version_id,),
                )[0]
            )
            == 12
        )
        assert (
            int(
                backend.fetch_one(
                    f"SELECT COUNT(*) FROM {schema_item} si LEFT JOIN {item} ni "
                    "ON ni.dd_version_id = si.dd_version_id "
                    "AND ni.item_num = si.item_num "
                    "WHERE si.dd_version_id = ? AND ni.item_num IS NULL",
                    (first.dd_version_id,),
                )[0]
            )
            == 0
        )
        assert (
            int(
                backend.fetch_one(
                    f"SELECT COUNT(*) FROM {item} "
                    "WHERE dd_version_id = ? AND "
                    "((xml_id IS NULL AND year_retired IS NULL) OR "
                    "(xml_id IS NOT NULL AND year_retired IS NOT NULL))",
                    (first.dd_version_id,),
                )[0]
            )
            == 0
        )
        duplicate = backend.fetch_one(
            f"SELECT COUNT(*) FROM {code} WHERE dd_version_id = ? "
            "AND item_num = 1832 AND code = 'Custom codes for historic use only'",
            (first.dd_version_id,),
        )
        assert int(duplicate[0]) == 2
        collection = backend.fetch_one(
            "SELECT collect_status FROM "
            f"{backend.qualified_name('naaccr', 'naaccr_item_registry_requirement')} "
            "WHERE dd_version_id = ? AND item_num = 3827 "
            "AND registry_code = 'CCCR'",
            (first.dd_version_id,),
        )
        assert collection[0] == "Required, site specific; when available"
        metadata = backend.fetch_one(
            f"SELECT unit, decimal_places FROM {item} "
            "WHERE dd_version_id = ? AND item_num = 3827",
            (first.dd_version_id,),
        )
        assert tuple(metadata) == ("percent", 0)
        # The SQL Server drift fix is executable, not only a text assertion.
        backend.fetch_all(
            f"SELECT schema_selection_rule_id FROM "
            f"{backend.qualified_name('naaccr', 'schema_selection_rule')} WHERE 1 = 0"
        )


def test_broken_schema_item_fixture_fails_before_mutating_the_database(
    tmp_path: Path,
) -> None:
    with SQLiteBackend(tmp_path / "broken.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        valid = load_dictionary(backend, csv_dir=FIXTURE_CSV)
        before = backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.naaccr_item WHERE dd_version_id = ?",
            (valid.dd_version_id,),
        )[0]

        with pytest.raises(VocabularyError, match="999999"):
            load_dictionary(backend, csv_dir=BROKEN_CSV)

        assert (
            backend.fetch_one(
                "SELECT COUNT(*) FROM naaccr.naaccr_item WHERE dd_version_id = ?",
                (valid.dd_version_id,),
            )[0]
            == before
        )
        assert (
            backend.fetch_one(
                "SELECT is_current FROM naaccr.data_dictionary_version "
                "WHERE dd_version_id = ?",
                (valid.dd_version_id,),
            )[0]
            == 1
        )


def test_partial_ssdi_csv_set_is_rejected(tmp_path: Path) -> None:
    csv_dir = _copy_fixture(tmp_path, algorithm="partial_ssdi")
    (csv_dir / "schema_item.csv").unlink()

    with SQLiteBackend(tmp_path / "partial.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        with pytest.raises(
            VocabularyError, match="incomplete SSDI CSV set.*schema_item"
        ):
            load_dictionary(backend, csv_dir=csv_dir)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_failed_second_generation_rolls_back_current_flag_and_all_rows(
    dialect: str, tmp_path: Path
) -> None:
    algorithm = f"rollback_{uuid.uuid4().hex}"
    first_csv = _copy_fixture(tmp_path, algorithm=algorithm, version="a")
    second_csv = _copy_fixture(tmp_path, algorithm=algorithm, version="b")
    code_rows = read_csv(second_csv, ALLOWED_CODE_FILE, ALLOWED_CODE_COLUMNS)
    duplicate = dict(code_rows[0])
    code_rows.append(duplicate)
    write_csv(
        second_csv / ALLOWED_CODE_FILE,
        ALLOWED_CODE_COLUMNS,
        [tuple(row[column] for column in ALLOWED_CODE_COLUMNS) for row in code_rows],
    )

    with _backend(dialect, tmp_path) as backend:
        BuildRunner(load_manifest(), backend).run()
        generation_a = load_dictionary(backend, csv_dir=first_csv)

        with pytest.raises(VocabularyError, match="load failed"):
            load_dictionary(backend, csv_dir=second_csv)

        versions = backend.fetch_all(
            "SELECT version, is_current FROM naaccr.data_dictionary_version "
            "WHERE algorithm = ? ORDER BY version",
            (algorithm,),
        )
        assert [tuple(row) for row in versions] == [("a", 1)]
        assert (
            backend.fetch_one(
                "SELECT COUNT(*) FROM naaccr.naaccr_item WHERE dd_version_id = ?",
                (generation_a.dd_version_id,),
            )[0]
            == 12
        )


def test_ssdi_item_missing_only_from_dictionary_gets_a_counted_stub(
    tmp_path: Path,
) -> None:
    algorithm = f"stub_{uuid.uuid4().hex}"
    csv_dir = _copy_fixture(tmp_path, algorithm=algorithm)
    item_rows = read_csv(csv_dir, "naaccr_item.csv", SSDI_ITEM_COLUMNS)
    item_rows.append(
        {
            "item_num": "999998",
            "name": "Loud stub",
            "xml_id": "loudStub",
            "unit": "mm",
            "decimal_places": "1",
        }
    )
    write_csv(
        csv_dir / "naaccr_item.csv",
        SSDI_ITEM_COLUMNS,
        [tuple(row[column] for column in SSDI_ITEM_COLUMNS) for row in item_rows],
    )

    with SQLiteBackend(tmp_path / "stub.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        result = load_dictionary(backend, csv_dir=csv_dir)

        assert result.stub_item_count == 1
        assert result.stub_item_nums == (999998,)
        assert backend.fetch_one(
            "SELECT name, unit, decimal_places FROM naaccr.naaccr_item "
            "WHERE dd_version_id = ? AND item_num = 999998",
            (result.dd_version_id,),
        ) == ("Loud stub", "mm", 1)


def test_missing_ssdi_version_stamp_is_an_incomplete_set(tmp_path: Path) -> None:
    csv_dir = _copy_fixture(tmp_path, algorithm="missing_stamp")
    (csv_dir / SSDI_VERSION_FILE).unlink()

    with SQLiteBackend(tmp_path / "missing.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        with pytest.raises(
            VocabularyError, match="incomplete SSDI CSV set.*ssdi_version"
        ):
            load_dictionary(backend, csv_dir=csv_dir)


_STAGING_API = "https://api.seer.cancer.gov/rest/staging"


@pytest.mark.parametrize(
    "ssdi_row",
    (
        ("eod_public", "3.3", "26", f"{_STAGING_API}/eod_public/3.3"),
        ("tnm", "3.3", "25", f"{_STAGING_API}/tnm/3.3"),
        ("eod_public", "3.4", "25", f"{_STAGING_API}/eod_public/3.4"),
    ),
    ids=("naaccr_version", "algorithm", "staging_version"),
)
def test_mismatched_ssdi_generation_is_rejected_before_transaction(
    tmp_path: Path, ssdi_row: tuple[str, str, str, str]
) -> None:
    mismatched = tmp_path / "mismatched"
    shutil.copytree(FIXTURE_CSV, mismatched)
    write_csv(mismatched / SSDI_VERSION_FILE, VERSION_COLUMNS, [ssdi_row])

    with SQLiteBackend(tmp_path / "mismatch.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        valid = load_dictionary(backend, csv_dir=FIXTURE_CSV)
        before = backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.naaccr_item WHERE dd_version_id = ?",
            (valid.dd_version_id,),
        )[0]

        with pytest.raises(
            VocabularyError, match=r"ssdi_version\.csv generation .* does not match"
        ):
            load_dictionary(backend, csv_dir=mismatched)

        assert (
            backend.fetch_one(
                "SELECT COUNT(*) FROM naaccr.naaccr_item WHERE dd_version_id = ?",
                (valid.dd_version_id,),
            )[0]
            == before
        )
        assert (
            backend.fetch_one(
                "SELECT is_current FROM naaccr.data_dictionary_version "
                "WHERE dd_version_id = ?",
                (valid.dd_version_id,),
            )[0]
            == 1
        )
        assert (
            backend.fetch_one("SELECT COUNT(*) FROM naaccr.data_dictionary_version")[0]
            == 1
        )


def test_stale_sqlite_dictionary_shape_requests_a_rebuild(tmp_path: Path) -> None:
    with SQLiteBackend(tmp_path / "stale.db") as backend:
        backend.execute(
            "CREATE TABLE naaccr.naaccr_item ("
            "dd_version_id INTEGER NOT NULL, item_num INTEGER NOT NULL, "
            "PRIMARY KEY (dd_version_id, item_num))"
        )
        BuildRunner(load_manifest(), backend).run()

        with pytest.raises(VocabularyError, match="rebuild required:.*delete"):
            load_dictionary(backend, csv_dir=FIXTURE_CSV)


def test_counts_only_verification_reports_pass_and_first_failure(
    tmp_path: Path,
) -> None:
    with SQLiteBackend(tmp_path / "verify.db") as backend:
        BuildRunner(load_manifest(), backend).run()
        loaded = load_dictionary(backend, csv_dir=FIXTURE_CSV)
        section_rows = backend.fetch_all(
            "SELECT section, COUNT(*) FROM naaccr.naaccr_item "
            "WHERE dd_version_id = ? AND section IS NOT NULL GROUP BY section",
            (loaded.dd_version_id,),
        )
        expectation = {
            "algorithm": "eod_public",
            "version": "3.3",
            "naaccr_version": "25",
            "checks": dict(zip(CHECK_NAMES, (12, 9, 3, 0, 4, 121, 36, 0), strict=True)),
            "sections": {str(row[0]): int(row[1]) for row in section_rows},
        }
        path = tmp_path / "expect.json"
        path.write_text(json.dumps(expectation), encoding="utf-8")
        lines: list[str] = []

        passed = verify_dictionary(
            backend, expectation_path=path, print_line=lines.append
        )
        assert passed.passed
        assert lines[0] == "check | expected | actual | PASS/FAIL"
        assert all(line.endswith("PASS") for line in lines[1:])

        expectation["checks"]["item_count"] = 13
        path.write_text(json.dumps(expectation), encoding="utf-8")
        failed = verify_dictionary(
            backend, expectation_path=path, print_line=lambda _line: None
        )
        assert failed.failures[0] == "item_count"
