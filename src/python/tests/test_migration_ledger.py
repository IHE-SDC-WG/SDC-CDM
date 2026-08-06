from __future__ import annotations

import pytest

from sdc_cdm.db.errors import MigrationHashMismatch
from sdc_cdm.db.ledger import (
    MigrationDecision,
    MigrationRecord,
    decide_migration,
)


RECORD = MigrationRecord("database/example.sql", "a" * 64, None)


def test_unchanged_migration_is_skipped() -> None:
    assert decide_migration(
        RECORD,
        "a" * 64,
        reapply_on_change=False,
        accept_changed_hashes=False,
    ) is MigrationDecision.SKIP


def test_changed_handwritten_migration_is_reapplied() -> None:
    assert decide_migration(
        RECORD,
        "b" * 64,
        reapply_on_change=True,
        accept_changed_hashes=False,
    ) is MigrationDecision.REAPPLY


def test_changed_immutable_migration_fails_without_acceptance() -> None:
    with pytest.raises(MigrationHashMismatch, match="database/example.sql"):
        decide_migration(
            RECORD,
            "b" * 64,
            reapply_on_change=False,
            accept_changed_hashes=False,
        )


def test_changed_hash_can_be_accepted_without_reapply() -> None:
    assert decide_migration(
        RECORD,
        "b" * 64,
        reapply_on_change=False,
        accept_changed_hashes=True,
    ) is MigrationDecision.ACCEPT_HASH
