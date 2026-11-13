from __future__ import annotations

import dataclasses

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
        ]
        assert manifest.validate[dialect] == ()
        listed = {entry.path for entry in entries}
        for path in (REPO_ROOT / "database" / "etl" / dialect).glob("*.sql"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            assert (relative in listed) != (relative in excluded), relative
        for entry in entries:
            assert set(entry.constants) <= tracked
            assert all((REPO_ROOT / "database" / "seed" / seed).is_file()
                       for seed in entry.seeds)


def test_an_undeclared_etl_script_is_rejected() -> None:
    manifest = load_manifest()
    old_bridge = "database/etl/sqlite/1_naaccr_sdc_to_omop.sql"
    unlisted = dataclasses.replace(manifest, excluded=tuple(
        exclusion for exclusion in manifest.excluded if exclusion.path != old_bridge
    ))
    with pytest.raises(ManifestError, match=f"SQL files omitted from manifest: {old_bridge}"):
        validate_manifest_files(unlisted)
