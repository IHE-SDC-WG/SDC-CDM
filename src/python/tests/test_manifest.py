from __future__ import annotations

from pathlib import Path

import pytest

from sdc_cdm.db.errors import ManifestError
from sdc_cdm.db.manifest import (
    SCHEMA_ORDER,
    SUPPORTED_DIALECTS,
    load_manifest,
    validate_manifest_files,
)
from sdc_cdm.db.paths import REPO_ROOT
from sdc_cdm.vocab.constants import read_constant_specs


def test_manifest_has_one_explicit_order_per_dialect() -> None:
    manifest = load_manifest()

    assert manifest.manifest_version == 1
    assert tuple(manifest.build) == SUPPORTED_DIALECTS
    for dialect in SUPPORTED_DIALECTS:
        entries = manifest.entries_for(dialect)
        positions = [SCHEMA_ORDER.index(entry.schema) for entry in entries]
        assert positions == sorted(positions)
        assert entries[0].schema == "etl"
        assert entries[1].schema == "intake"
        assert [entry.schema for entry in entries if entry.schema == "omop"]
        assert entries[-1].schema == "sdc"


def test_manifest_exclusions_are_reasoned() -> None:
    manifest = load_manifest()

    assert manifest.excluded
    assert all(exclusion.reason.strip() for exclusion in manifest.excluded)
    removed_dialect = "post" + "gresql"
    assert sum(removed_dialect in exclusion.path for exclusion in manifest.excluded) == 4


def test_bridge_entries_are_ordered_and_every_etl_script_is_declared() -> None:
    """BRIDGE-03: the runner's order is the manifest's, never a directory glob."""
    manifest = load_manifest()
    excluded = {exclusion.path for exclusion in manifest.excluded}
    tracked = {spec.constant_name for spec in read_constant_specs()}
    for dialect in SUPPORTED_DIALECTS:
        entries = manifest.bridge_entries_for(dialect)
        assert [entry.path for entry in entries] == [
            f"database/etl/{dialect}/1_person_and_period.sql",
            f"database/etl/{dialect}/2_note.sql",
            f"database/etl/{dialect}/3_measurement_observation.sql",
            f"database/etl/{dialect}/4_condition_and_episode.sql",
        ]
        validate = manifest.validate_entries_for(dialect)
        assert [entry.path for entry in validate] == [f"database/etl/{dialect}/9_validate.sql"]
        assert validate[0].seeds == ("validate_thresholds.csv",)
        assert validate[0].tables == ()
        listed = {entry.path for entry in (*entries, *validate)}
        for path in (REPO_ROOT / "database" / "etl" / dialect).glob("*.sql"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            assert (relative in listed) != (relative in excluded), relative
        for entry in (*entries, *validate):
            assert set(entry.constants) <= tracked
            assert all((REPO_ROOT / "database" / "seed" / seed).is_file()
                       for seed in entry.seeds)


def test_an_undeclared_etl_script_is_rejected(monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:
    """MANIFEST-01: an ETL file that is neither listed nor excluded fails the load."""
    etl = tmp_path / "database" / "etl" / "sqlite"
    etl.mkdir(parents=True)
    (etl / "8_unlisted.sql").write_text("SELECT 1;\n", encoding="utf-8")
    manifest = load_manifest()
    declared = {
        entry.path
        for dialect in SUPPORTED_DIALECTS
        for entry in (*manifest.entries_for(dialect), *manifest.bridge[dialect],
                      *manifest.validate[dialect])
    } | {exclusion.path for exclusion in manifest.excluded}
    for path in declared:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / path).read_bytes())
    monkeypatch.setattr("sdc_cdm.db.manifest.REPO_ROOT", tmp_path)
    with pytest.raises(
        ManifestError,
        match="SQL files omitted from manifest: database/etl/sqlite/8_unlisted.sql",
    ):
        validate_manifest_files(manifest)
