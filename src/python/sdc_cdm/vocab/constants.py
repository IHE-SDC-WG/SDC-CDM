"""Resolve repository-named OMOP constants against a loaded vocabulary."""

from __future__ import annotations

import csv
from dataclasses import dataclass

from sdc_cdm.cdm.tables import VOCABULARY_SCHEMA
from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.errors import VocabularyError
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.run_log import RunLog


CONSTANTS_PATH = "database/seed/concept_constants.csv"
_EXPECTED_HEADER = ("constant_name", "vocabulary_id", "concept_code")


@dataclass(frozen=True)
class ConstantSpec:
    constant_name: str
    vocabulary_id: str
    concept_code: str


@dataclass(frozen=True)
class ResolvedConstant:
    constant_name: str
    concept_id: int
    vocabulary_id: str
    concept_code: str


def read_constant_specs() -> tuple[ConstantSpec, ...]:
    path = repository_path(CONSTANTS_PATH)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise VocabularyError(f"{CONSTANTS_PATH} is empty") from exc
        if header != _EXPECTED_HEADER:
            raise VocabularyError(
                f"{CONSTANTS_PATH} header must be {','.join(_EXPECTED_HEADER)}"
            )
        specs: list[ConstantSpec] = []
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(_EXPECTED_HEADER) or any(value == "" for value in row):
                raise VocabularyError(
                    f"{CONSTANTS_PATH}:{line_number} must contain three "
                    "non-empty fields"
                )
            specs.append(ConstantSpec(*row))

    names = [spec.constant_name for spec in specs]
    if len(names) != len(set(names)):
        raise VocabularyError(
            f"{CONSTANTS_PATH} contains duplicate constant_name values"
        )
    return tuple(specs)


def valid_exact_candidates(
    backend: DatabaseBackend, spec: ConstantSpec
) -> list[tuple[object, ...]]:
    """Return valid, case-exact concept rows for one tracked pair."""

    concept = backend.qualified_name(VOCABULARY_SCHEMA, "concept")
    rows = backend.fetch_all(
        f"SELECT concept_id, concept_code, standard_concept, invalid_reason "
        f"FROM {concept} WHERE vocabulary_id = ? AND concept_code = ?",
        (spec.vocabulary_id, spec.concept_code),
    )
    return [
        tuple(row)
        for row in rows
        if str(row[1]) == spec.concept_code and row[3] is None
    ]


def _resolve_one(
    backend: DatabaseBackend, spec: ConstantSpec
) -> tuple[ResolvedConstant | None, str | None]:
    candidates = valid_exact_candidates(backend, spec)
    pair = (spec.vocabulary_id, spec.concept_code)
    if not candidates:
        return None, f"missing {pair!r}"
    if len(candidates) > 1:
        standard = [row for row in candidates if row[2] == "S"]
        if standard:
            candidates = standard
    if len(candidates) > 1:
        concept_ids = ", ".join(
            str(int(row[0]))
            for row in sorted(candidates, key=lambda row: int(row[0]))
        )
        return None, f"ambiguous {pair!r}; candidate concept_ids: {concept_ids}"
    return (
        ResolvedConstant(
            spec.constant_name,
            int(candidates[0][0]),
            spec.vocabulary_id,
            spec.concept_code,
        ),
        None,
    )


def resolve_constants(
    backend: DatabaseBackend,
) -> tuple[ResolvedConstant, ...]:
    """Resolve all tracked pairs and atomically replace etl.concept_constant."""

    run_log = RunLog(backend)
    run_id = run_log.start("constants resolve")
    try:
        resolved: list[ResolvedConstant] = []
        failures: list[str] = []
        for spec in read_constant_specs():
            constant, failure = _resolve_one(backend, spec)
            if failure is not None:
                failures.append(failure)
            else:
                assert constant is not None
                resolved.append(constant)

        if failures:
            raise VocabularyError(
                "Concept constant resolution failed:\n- "
                + "\n- ".join(failures)
                + "\nRun `sdc-cdm vocab load` with an Athena extract containing "
                "the required pairs, then rerun `sdc-cdm constants resolve`. "
                "etl.concept_constant was not modified."
            )

        with backend.transaction():
            backend.execute_uncommitted("DELETE FROM etl.concept_constant")
            backend.bulk_insert(
                "etl",
                "concept_constant",
                ("constant_name", "concept_id", "vocabulary_id", "concept_code"),
                (
                    (
                        constant.constant_name,
                        constant.concept_id,
                        constant.vocabulary_id,
                        constant.concept_code,
                    )
                    for constant in resolved
                ),
            )
        run_log.finish(run_id)
        return tuple(resolved)
    except Exception as exc:
        run_log.finish(run_id, error=str(exc))
        raise
