from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REMOVED_DIALECT = "post" + "gres"
REFERENCE_DIRECTORY = "database/schemas/omop/ddl/" + REMOVED_DIALECT + "ql"
THIS_TEST = "src/python/tests/test_no_" + REMOVED_DIALECT + ".py"


def _git_lines(*arguments: str) -> list[str]:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode in (0, 1), completed.stderr
    return [line for line in completed.stdout.splitlines() if line]


def test_removed_dialect_text_is_limited_to_declared_references() -> None:
    hits = _git_lines(
        "grep",
        "-I",
        "-i",
        "-n",
        REMOVED_DIALECT,
        "--",
        ".",
        f":(exclude){REFERENCE_DIRECTORY}",
        ":(exclude)database/schemas/omop/VENDORED.md",
        ":(exclude)database/manifest.json",
        ":(exclude)docs/REBUILD_PLAN.md",
    )

    assert hits == []


def test_only_four_vendored_reference_paths_remain() -> None:
    tracked_paths = _git_lines("ls-files")
    matching = [path for path in tracked_paths if REMOVED_DIALECT in path.lower()]
    matching = [path for path in matching if path != THIS_TEST]

    assert matching == [
        f"{REFERENCE_DIRECTORY}/1_OMOPCDM_{REMOVED_DIALECT}ql_5.4_ddl.sql",
        f"{REFERENCE_DIRECTORY}/2_OMOPCDM_{REMOVED_DIALECT}ql_5.4_primary_keys.sql",
        f"{REFERENCE_DIRECTORY}/3_OMOPCDM_{REMOVED_DIALECT}ql_5.4_constraints.sql",
        f"{REFERENCE_DIRECTORY}/4_OMOPCDM_{REMOVED_DIALECT}ql_5.4_indices.sql",
    ]
