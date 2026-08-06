from __future__ import annotations

from sdc_cdm.db.manifest import SCHEMA_ORDER, SUPPORTED_DIALECTS, load_manifest


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
    assert any("postgresql" in exclusion.path for exclusion in manifest.excluded)
