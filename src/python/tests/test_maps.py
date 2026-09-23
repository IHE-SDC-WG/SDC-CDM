from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from sdc_cdm.cli.build import BuildRunner
from sdc_cdm.cli.main import main
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.manifest import load_manifest
from sdc_cdm.db.sqlite_backend import SQLiteBackend
from sdc_cdm.db.sqlserver_backend import SqlServerBackend
from sdc_cdm.maps.allocation import LOCAL_RANGE
from sdc_cdm.maps.build import build_concept_maps
from sdc_cdm.maps.coverage import report_coverage
from sdc_cdm.maps.seeds import EXCLUSION_COLUMNS, OVERRIDE_COLUMNS
from sdc_cdm.naaccr.csv_io import write_csv
from sdc_cdm.naaccr.load import load_dictionary
from vocab_fixture import _write_extract

ROOT = Path(__file__).resolve().parents[3]
DICTIONARY = ROOT / "sample_data/test-fixtures/naaccr-dict/csv"


@contextmanager
def _backend(dialect: str, tmp_path: Path) -> Iterator[DatabaseBackend]:
    if dialect == "sqlite":
        backend: DatabaseBackend = SQLiteBackend(tmp_path / "maps.db")
    else:
        connection_string = os.environ.get("SDC_CDM_MAPS_SQLSERVER_CONNECTION_STRING")
        if not connection_string:
            pytest.skip("SDC_CDM_MAPS_SQLSERVER_CONNECTION_STRING is not set")
        backend = SqlServerBackend(connection_string)
    try:
        yield backend
    finally:
        backend.close()


def _seed_dir(tmp_path: Path, *, override_rows: list[tuple[object, ...]] | None = None,
              exclusion_rows: list[tuple[object, ...]] | None = None) -> Path:
    directory = tmp_path / "seeds"
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(directory / "concept_map_overrides.csv", OVERRIDE_COLUMNS, override_rows or [])
    write_csv(directory / "naaccr_item_exclusions.csv", EXCLUSION_COLUMNS, exclusion_rows or [])
    return directory


def _prepare(backend: DatabaseBackend, tmp_path: Path) -> None:
    BuildRunner(load_manifest(), backend).run()
    if backend.fetch_one("SELECT 1 FROM omop.concept") is None:
        vocab = tmp_path / "vocab"
        _write_extract(vocab)
        from sdc_cdm.vocab.loader import load_vocab
        load_vocab(backend, vocab, "\t")
    if backend.fetch_one(
        "SELECT 1 FROM naaccr.data_dictionary_version WHERE is_current = 1"
    ) is None:
        load_dictionary(backend, csv_dir=DICTIONARY)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_local_sources_athena_targets_rebuild_and_coverage(
    dialect: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend(dialect, tmp_path) as backend:
        _prepare(backend, tmp_path)
        first = build_concept_maps(backend, csv_dir=seeds)
        assert first.item_layers["athena_standard"] == 1
        assert first.value_layers["athena_standard"] == 1
        assert first.layer1_ambiguous == 1
        assert first.new_allocations > 2  # vocabulary and multiple class rows
        class_count = backend.fetch_one(
            "SELECT COUNT(*) FROM naaccr.local_concept_allocation WHERE concept_kind = 'concept_class'"
        )[0]
        assert class_count > 1
        item = backend.fetch_one(
            "SELECT source_concept_id, concept_id FROM naaccr.naaccr_concept_map WHERE item_num = 3827"
        )
        value = backend.fetch_one(
            "SELECT source_concept_id, concept_id FROM naaccr.naaccr_value_concept_map "
            "WHERE item_num = 3605 AND code = '1'"
        )
        assert LOCAL_RANGE[0] <= item[0] <= LOCAL_RANGE[1] and item[1] == 9001
        assert LOCAL_RANGE[0] <= value[0] <= LOCAL_RANGE[1] and value[1] == 9002
        backend.execute("DELETE FROM naaccr.naaccr_value_concept_map WHERE item_num = 3605 AND code = '1'")
        second = build_concept_maps(backend, csv_dir=seeds)
        assert second.new_allocations == 0
        assert backend.fetch_one(
            "SELECT source_concept_id FROM naaccr.naaccr_value_concept_map "
            "WHERE item_num = 3605 AND code = '1'"
        )[0] == value[0]
        coverage = report_coverage(backend, csv_dir=seeds)
        assert coverage.checks["item_total"] == 9  # three dictionary items are retired
        assert coverage.checks["value_total"] < 121  # repeated allowed codes collapse
        assert coverage.checks["value_athena_standard"] == 1
        expected = tmp_path / "expect.json"
        expected.write_text(json.dumps({
            "algorithm": coverage.algorithm, "naaccr_version": "25",
            "checks": {"item_total": 1, "value_total": coverage.checks["value_total"]},
        }))
        comparison = report_coverage(backend, csv_dir=seeds, expectation_path=expected)
        assert comparison.comparisons == (
            ("item_total", 1, 9, False),
            ("value_total", coverage.checks["value_total"], coverage.checks["value_total"], True),
        )
        assert comparison.failures == ("item_total: expected 1, got 9",)
        if dialect == "sqlite":
            assert main([
                "maps", "coverage", "--dialect", "sqlite", "--db", str(tmp_path / "maps.db"),
                "--seed-dir", str(seeds), "--expect", str(expected),
            ]) == 1
            output = capsys.readouterr()
            assert "check | expected | actual | PASS/FAIL" in output.out
            assert "item_total | 1 | 9 | FAIL" in output.out
            assert (
                f"value_total | {coverage.checks['value_total']} | "
                f"{coverage.checks['value_total']} | PASS"
            ) in output.out
            assert "maps coverage FAIL: item_total: expected 1, got 9" in output.err
            expected.write_text(json.dumps({
                "algorithm": coverage.algorithm, "naaccr_version": "25",
                "checks": {"item_total": coverage.checks["item_total"]},
            }))
            assert main([
                "maps", "coverage", "--dialect", "sqlite", "--db", str(tmp_path / "maps.db"),
                "--seed-dir", str(seeds), "--expect", str(expected),
            ]) == 0
            output = capsys.readouterr()
            assert "item_total | 9 | 9 | PASS" in output.out
            assert "maps coverage PASS" in output.out


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_coverage_requires_matching_build_and_current_generation(dialect: str, tmp_path: Path) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend(dialect, tmp_path) as backend:
        _prepare(backend, tmp_path)
        first = build_concept_maps(backend, algorithm="eod_public", csv_dir=seeds)
        original_count = backend.fetch_one("SELECT COUNT(*) FROM naaccr.naaccr_concept_map")[0]
        assert original_count > 0
        assert tuple(backend.fetch_one(
            "SELECT algorithm, dd_version_id FROM naaccr.concept_map_build_state"
        )[:2]) == ("eod_public", first.dd_version_id)

        # A second current algorithm can share item numbers with the global map tables.
        backend.execute(
            "INSERT INTO naaccr.data_dictionary_version "
            "(algorithm, version, naaccr_version, is_current) VALUES (?, ?, ?, 1)",
            ("other", "1", "25"),
        )
        other = int(backend.fetch_one(
            "SELECT dd_version_id FROM naaccr.data_dictionary_version "
            "WHERE algorithm = 'other' AND version = '1'"
        )[0])
        backend.execute(
            "INSERT INTO naaccr.naaccr_item "
            "(dd_version_id, item_num, name, section, parent_xml_element) "
            "VALUES (?, 3827, 'Other algorithm item', 'Stage/Prognostic Factors', 'Tumor')",
            (other,),
        )
        try:
            with pytest.raises(VocabularyError, match="recorded build is eod_public/"):
                report_coverage(backend, algorithm="other", csv_dir=seeds)
            assert backend.fetch_one(
                "SELECT COUNT(*) FROM naaccr.concept_map_coverage WHERE algorithm = 'other'"
            )[0] == 0
            assert report_coverage(backend, algorithm="eod_public", csv_dir=seeds).checks["item_total"] == 9

            build_concept_maps(backend, algorithm="other", csv_dir=seeds)
            assert report_coverage(backend, algorithm="other", csv_dir=seeds).checks["item_total"] == 1
            with pytest.raises(VocabularyError, match="recorded build is other/"):
                report_coverage(backend, algorithm="eod_public", csv_dir=seeds)
            assert backend.fetch_one(
                "SELECT COUNT(*) FROM naaccr.concept_map_coverage WHERE algorithm = 'eod_public'"
            )[0] == 0

            build_concept_maps(backend, algorithm="eod_public", csv_dir=seeds)
            backend.execute(
                "UPDATE naaccr.data_dictionary_version SET is_current = 0 "
                "WHERE algorithm = 'eod_public' AND dd_version_id = ?", (first.dd_version_id,),
            )
            backend.execute(
                "INSERT INTO naaccr.data_dictionary_version "
                "(algorithm, version, naaccr_version, is_current) VALUES (?, ?, ?, 1)",
                ("eod_public", "next", "26"),
            )
            newer = int(backend.fetch_one(
                "SELECT dd_version_id FROM naaccr.data_dictionary_version "
                "WHERE algorithm = 'eod_public' AND version = 'next'"
            )[0])
            try:
                with pytest.raises(VocabularyError, match="maps coverage requires maps build"):
                    report_coverage(backend, algorithm="eod_public", csv_dir=seeds)
                assert backend.fetch_one(
                    "SELECT COUNT(*) FROM naaccr.concept_map_coverage WHERE algorithm = 'eod_public'"
                )[0] == 0
            finally:
                backend.execute(
                    "UPDATE naaccr.data_dictionary_version SET is_current = 0 "
                    "WHERE dd_version_id = ?", (newer,),
                )
                backend.execute(
                    "UPDATE naaccr.data_dictionary_version SET is_current = 1 "
                    "WHERE dd_version_id = ?", (first.dd_version_id,),
                )
                backend.execute(
                    "DELETE FROM naaccr.data_dictionary_version WHERE dd_version_id = ?", (newer,),
                )

            backend.execute("DELETE FROM naaccr.concept_map_build_state")
            with pytest.raises(VocabularyError, match="recorded build is none"):
                report_coverage(backend, algorithm="eod_public", csv_dir=seeds)
            build_concept_maps(backend, algorithm="eod_public", csv_dir=seeds)

            bad_seeds = _seed_dir(
                tmp_path / "bad", override_rows=[
                    (3827, "", 999999999, "", "invalid target", "tester", "2026-09-23"),
                ],
            )
            with pytest.raises(VocabularyError, match="not a valid standard OMOP concept"):
                build_concept_maps(backend, algorithm="eod_public", csv_dir=bad_seeds)
            assert tuple(backend.fetch_one(
                "SELECT algorithm, dd_version_id FROM naaccr.concept_map_build_state"
            )[:2]) == ("eod_public", first.dd_version_id)
            assert backend.fetch_one("SELECT COUNT(*) FROM naaccr.naaccr_concept_map")[0] == original_count
            assert report_coverage(backend, algorithm="eod_public", csv_dir=seeds).checks["item_total"] == 9
        finally:
            backend.execute(
                "DELETE FROM naaccr.naaccr_item WHERE dd_version_id = ?", (other,),
            )
            backend.execute(
                "DELETE FROM naaccr.data_dictionary_version WHERE dd_version_id = ?", (other,),
            )


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_coverage_expectation_requires_matching_naaccr_version(dialect: str, tmp_path: Path) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend(dialect, tmp_path) as backend:
        _prepare(backend, tmp_path)
        build_concept_maps(backend, algorithm="eod_public", csv_dir=seeds)
        expected = tmp_path / "expect.json"
        expected.write_text(json.dumps({"algorithm": "eod_public", "checks": {"item_total": 9}}))
        with pytest.raises(VocabularyError, match="must contain naaccr_version"):
            report_coverage(backend, algorithm="eod_public", csv_dir=seeds, expectation_path=expected)
        expected.write_text(json.dumps({
            "algorithm": "eod_public", "naaccr_version": "26", "checks": {"item_total": 9},
        }))
        with pytest.raises(VocabularyError, match="expected NAACCR version 26, found 25"):
            report_coverage(backend, algorithm="eod_public", csv_dir=seeds, expectation_path=expected)
        expected.write_text(json.dumps({
            "algorithm": "eod_public", "naaccr_version": "25", "checks": {"item_total": 9},
        }))
        assert report_coverage(
            backend, algorithm="eod_public", csv_dir=seeds, expectation_path=expected,
        ).comparisons == (("item_total", 9, 9, True),)


@pytest.mark.parametrize("dialect", ("sqlite", "sqlserver"))
def test_target_only_override_exclusion_and_long_value_code(dialect: str, tmp_path: Path) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend(dialect, tmp_path) as backend:
        _prepare(backend, tmp_path)
        build_concept_maps(backend, csv_dir=seeds)
        original_source = backend.fetch_one(
            "SELECT source_concept_id FROM naaccr.naaccr_concept_map WHERE item_num = 3827"
        )[0]
        write_csv(
            seeds / "concept_map_overrides.csv", OVERRIDE_COLUMNS,
            [(3827, "", 0, "", "reviewed", "tester", "2026-09-23"),
             (3605, "1", 9003, "Meas Value", "reviewed", "tester", "2026-09-23")],
        )
        write_csv(
            seeds / "naaccr_item_exclusions.csv", EXCLUSION_COLUMNS,
            [(102, "Country", "not mapped")],
        )
        long_code = "X" * 200
        generation = backend.fetch_one(
            "SELECT dd_version_id FROM naaccr.data_dictionary_version WHERE is_current = 1"
        )[0]
        backend.execute(
            "INSERT INTO naaccr.naaccr_item_allowed_code "
            "(dd_version_id, item_num, code_seq, code, description) VALUES (?, ?, ?, ?, ?)",
            (generation, 3605, 900, long_code, "Long value"),
        )
        report = build_concept_maps(backend, csv_dir=seeds)
        assert report.excluded_items == 1
        assert report.item_layers["curated_override"] == 1
        assert report.value_layers["curated_override"] == 1
        assert tuple(backend.fetch_one(
            "SELECT concept_id, mapping_layer, source_concept_id "
            "FROM naaccr.naaccr_concept_map WHERE item_num = 3827"
        )[:3]) == (0, "curated_override", original_source)
        assert backend.fetch_one(
            "SELECT concept_id FROM naaccr.naaccr_value_concept_map WHERE item_num = 3605 AND code = '1'"
        )[0] == 9003
        assert backend.fetch_one(
            "SELECT 1 FROM naaccr.naaccr_concept_map WHERE item_num = 102"
        ) is None
        allocation = backend.fetch_one(
            "SELECT concept_code FROM naaccr.local_concept_allocation "
            "WHERE concept_kind = 'value' AND item_num = 3605 AND code = ?",
            (long_code,),
        )
        assert allocation is not None and len(allocation[0]) <= 50


def test_seed_error_uses_physical_line_after_multiline_field(tmp_path: Path) -> None:
    seeds = _seed_dir(
        tmp_path,
        override_rows=[(3827, "", "", "", "a\nmultiline note", "", ""),
                       (999999, "", 9001, "", "unknown", "", "")],
    )
    with _backend("sqlite", tmp_path) as backend:
        _prepare(backend, tmp_path)
        with pytest.raises(VocabularyError, match=r"concept_map_overrides.csv:4: unknown"):
            build_concept_maps(backend, csv_dir=seeds)


def test_old_sqlite_missing_map_table_requests_rebuild(tmp_path: Path) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend("sqlite", tmp_path) as backend:
        _prepare(backend, tmp_path)
        backend.execute("DROP TABLE naaccr.naaccr_concept_map")
        with pytest.raises(VocabularyError, match="rebuild required"):
            build_concept_maps(backend, csv_dir=seeds)


def test_old_sqlite_missing_build_state_requests_rebuild(tmp_path: Path) -> None:
    seeds = _seed_dir(tmp_path)
    with _backend("sqlite", tmp_path) as backend:
        _prepare(backend, tmp_path)
        backend.execute("DROP TABLE naaccr.concept_map_build_state")
        with pytest.raises(VocabularyError, match="rebuild required"):
            build_concept_maps(backend, csv_dir=seeds)
        with pytest.raises(VocabularyError, match="rebuild required"):
            report_coverage(backend, csv_dir=seeds)
