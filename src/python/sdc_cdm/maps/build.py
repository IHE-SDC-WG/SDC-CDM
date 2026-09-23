"""Build stable NAACCR sources and layered standard targets in one transaction."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sdc_cdm.db.backend import DatabaseBackend
from sdc_cdm.db.bulk import suspend_constraints, verify_constraints
from sdc_cdm.db.errors import UsageError, VocabularyError
from sdc_cdm.db.paths import repository_path
from sdc_cdm.db.run_log import RunLog
from sdc_cdm.maps.allocation import LOCAL_VOCABULARY_ID, local_code, reserve
from sdc_cdm.maps.classes import class_definitions, concept_class_id
from sdc_cdm.maps.seeds import OVERRIDE_FILE, Seeds, read_seeds

# This is a provisional Athena matcher, separate from local concept codes. A
# bundle containing NAACCR must be measured before Athena value coverage is
# treated as accepted evidence.
ATHENA_VALUE_CODE_PATTERN = "{item_num}@{code}"
MAP_COLUMNS = (
    "source_concept_id", "concept_id", "target_domain_id", "concept_code",
    "concept_name", "mapping_layer", "created_at",
)


@dataclass(frozen=True)
class BuildReport:
    algorithm: str
    dd_version_id: int
    item_layers: dict[str, int]
    value_layers: dict[str, int]
    new_allocations: int
    reused_allocations: int
    layer1_ambiguous: int
    excluded_items: int


def current_generation(backend: DatabaseBackend, algorithm: str | None) -> tuple[str, int]:
    if not backend.table_exists("naaccr", "data_dictionary_version"):
        raise VocabularyError("rebuild required: missing NAACCR dictionary tables; re-run build")
    rows = backend.fetch_all(
        "SELECT algorithm, dd_version_id FROM naaccr.data_dictionary_version "
        "WHERE is_current = 1 ORDER BY algorithm"
    )
    if algorithm is not None:
        rows = [row for row in rows if row[0] == algorithm]
        if not rows:
            raise UsageError(f"no current NAACCR dictionary for algorithm {algorithm!r}")
    if len(rows) != 1:
        raise UsageError(
            "specify --algorithm when there is not exactly one current dictionary generation"
        )
    return str(rows[0][0]), int(rows[0][1])


def _columns(backend: DatabaseBackend, table: str) -> set[str]:
    if backend.dialect == "sqlite":
        return {str(row[1]) for row in backend.fetch_all(f'PRAGMA "naaccr".table_info("{table}")')}
    return {str(row[0]) for row in backend.fetch_all(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'naaccr' AND TABLE_NAME = ?", (table,),
    )}


def _preflight(backend: DatabaseBackend) -> None:
    required = {
        "naaccr_concept_map": {"item_num"} | set(MAP_COLUMNS),
        "naaccr_value_concept_map": {"item_num", "code"} | set(MAP_COLUMNS),
        "concept_map_build_state": {"singleton_id", "algorithm", "dd_version_id", "built_at"},
        "local_concept_allocation": {"concept_id", "concept_kind", "item_num", "code", "concept_code"},
    }
    for table, columns in required.items():
        if not backend.table_exists("naaccr", table) or not columns <= _columns(backend, table):
            raise VocabularyError(f"rebuild required: naaccr.{table} is missing Phase 2 columns; re-run build")
    if not backend.table_exists("omop", "concept") or not backend.fetch_one("SELECT 1 FROM omop.concept"):
        raise VocabularyError("maps build requires a loaded OMOP vocabulary; run vocab load first")
    for domain in ("Metadata", "Observation", "Meas Value"):
        if backend.fetch_one("SELECT 1 FROM omop.domain WHERE domain_id = ?", (domain,)) is None:
            raise VocabularyError(f"loaded OMOP vocabulary is missing domain {domain!r}")
    for class_id in ("Vocabulary", "Concept Class"):
        if backend.fetch_one("SELECT 1 FROM omop.concept_class WHERE concept_class_id = ?", (class_id,)) is None:
            raise VocabularyError(f"loaded OMOP vocabulary is missing concept class {class_id!r}")


def _items(backend: DatabaseBackend, generation: int) -> list[tuple[int, str, str, str]]:
    rows = backend.fetch_all(
        "SELECT item_num, name, section, parent_xml_element FROM naaccr.naaccr_item "
        "WHERE dd_version_id = ? AND year_retired IS NULL ORDER BY item_num", (generation,),
    )
    return [(int(row[0]), str(row[1] or ""), str(row[2] or ""), str(row[3] or "")) for row in rows]


def _values(backend: DatabaseBackend, generation: int) -> dict[tuple[int, str], str]:
    rows = backend.fetch_all(
        "SELECT item_num, code, description FROM naaccr.naaccr_item_allowed_code "
        "WHERE dd_version_id = ? ORDER BY item_num, code, code_seq", (generation,),
    )
    values: dict[tuple[int, str], str] = {}
    for row in rows:
        key = (int(row[0]), str(row[1]))
        description = str(row[2] or "")
        if key not in values or (not values[key] and description):
            values[key] = description
    return values


def _athena_targets(backend: DatabaseBackend) -> dict[str, list[tuple[int, str]]]:
    rows = backend.fetch_all(
        "SELECT source.concept_code, target.concept_id, target.domain_id "
        "FROM omop.concept source "
        "JOIN omop.concept_relationship rel ON rel.concept_id_1 = source.concept_id "
        "JOIN omop.concept target ON target.concept_id = rel.concept_id_2 "
        "WHERE source.vocabulary_id = 'NAACCR' AND source.invalid_reason IS NULL "
        "AND rel.relationship_id = 'Maps to' AND rel.invalid_reason IS NULL "
        "AND target.standard_concept = 'S' AND target.invalid_reason IS NULL "
        "AND source.valid_end_date >= ? AND rel.valid_end_date >= ? "
        "AND target.valid_end_date >= ? AND source.valid_start_date <= ? "
        "AND rel.valid_start_date <= ? AND target.valid_start_date <= ? "
        "ORDER BY source.concept_code, target.concept_id",
        (datetime.now(UTC).date().isoformat(),) * 6,
    )
    result: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for code, concept_id, domain in rows:
        pair = (int(concept_id), str(domain))
        if pair not in result[str(code)]:
            result[str(code)].append(pair)
    return result


def _insert_concept(
    backend: DatabaseBackend, concept_id: int, name: str, domain: str,
    class_id: str, concept_code: str,
) -> None:
    clean_name = " ".join(name.split())[:255] or concept_code
    existing = backend.fetch_one(
        "SELECT vocabulary_id, concept_code, domain_id, concept_class_id, "
        "standard_concept, invalid_reason, concept_name "
        "FROM omop.concept WHERE concept_id = ?", (concept_id,),
    )
    if existing is not None:
        if tuple(existing[:6]) != (LOCAL_VOCABULARY_ID, concept_code, domain, class_id, None, None):
            raise VocabularyError(f"local concept {concept_id} conflicts with omop.concept")
        if existing[6] != clean_name:
            backend.execute_uncommitted(
                "UPDATE omop.concept SET concept_name = ? WHERE concept_id = ?",
                (clean_name, concept_id),
            )
        return
    backend.execute_uncommitted(
        "INSERT INTO omop.concept "
        "(concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, "
        "standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason) "
        "VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)",
        (concept_id, clean_name, domain, LOCAL_VOCABULARY_ID, class_id,
         concept_code, "1970-01-01", "2099-12-31"),
    )


def _insert_vocabulary_and_classes(
    backend: DatabaseBackend, items: list[tuple[int, str, str, str]],
    allocation: Counter[str],
) -> None:
    vocab_id, fresh = reserve(backend, "vocabulary", name="Locally assigned NAACCR concepts")
    allocation["new" if fresh else "reused"] += 1
    existing = backend.fetch_one(
        "SELECT vocabulary_concept_id FROM omop.vocabulary WHERE vocabulary_id = ?",
        (LOCAL_VOCABULARY_ID,),
    )
    if existing is None:
        backend.execute_uncommitted(
            "INSERT INTO omop.vocabulary "
            "(vocabulary_id, vocabulary_name, vocabulary_reference, vocabulary_version, vocabulary_concept_id) "
            "VALUES (?, ?, ?, ?, 0)",
            (LOCAL_VOCABULARY_ID, "Local NAACCR source concepts", "SEER NAACCR dictionary", "1"),
        )
    elif int(existing[0]) not in (0, vocab_id):
        raise VocabularyError("NAACCR_LOCAL vocabulary concept ID conflicts with allocation")
    _insert_concept(backend, vocab_id, "Local NAACCR source vocabulary", "Metadata", "Vocabulary", local_code("vocabulary"))
    backend.execute_uncommitted(
        "UPDATE omop.vocabulary SET vocabulary_concept_id = ? WHERE vocabulary_id = ?",
        (vocab_id, LOCAL_VOCABULARY_ID),
    )
    for class_id, name in sorted(class_definitions(items).items()):
        concept_id, fresh = reserve(backend, "concept_class", code=class_id, name=name)
        allocation["new" if fresh else "reused"] += 1
        _insert_concept(backend, concept_id, name, "Metadata", "Concept Class", local_code("concept_class", code=class_id))
        existing = backend.fetch_one(
            "SELECT concept_class_concept_id, concept_class_name "
            "FROM omop.concept_class WHERE concept_class_id = ?",
            (class_id,),
        )
        if existing is None:
            backend.execute_uncommitted(
                "INSERT INTO omop.concept_class "
                "(concept_class_id, concept_class_name, concept_class_concept_id) VALUES (?, ?, ?)",
                (class_id, name[:255], concept_id),
            )
        elif int(existing[0]) != concept_id:
            raise VocabularyError(f"concept class {class_id} conflicts with local allocation")
        elif existing[1] != name[:255]:
            backend.execute_uncommitted(
                "UPDATE omop.concept_class SET concept_class_name = ? WHERE concept_class_id = ?",
                (name[:255], class_id),
            )


def _validate_override(
    backend: DatabaseBackend, target_id: int, supplied_domain: str | None,
    path: Path, line: int,
) -> str | None:
    if target_id == 0:
        if supplied_domain:
            raise VocabularyError(f"{path}:{line}: zero target cannot have target_domain_id")
        return None
    row = backend.fetch_one(
        "SELECT domain_id, standard_concept, invalid_reason, valid_start_date, valid_end_date "
        "FROM omop.concept WHERE concept_id = ?", (target_id,),
    )
    today = datetime.now(UTC).date().isoformat()
    if row is None or row[1] != "S" or row[2] is not None or str(row[3]) > today or str(row[4]) < today:
        raise VocabularyError(f"{path}:{line}: target {target_id} is not a valid standard OMOP concept")
    domain = str(row[0])
    if supplied_domain and supplied_domain != domain:
        raise VocabularyError(f"{path}:{line}: target_domain_id {supplied_domain!r} conflicts with {domain!r}")
    return domain


def _validate_rows(backend: DatabaseBackend, expected_items: int, expected_values: int) -> None:
    failures: list[str] = []
    for table, expected in (("naaccr_concept_map", expected_items), ("naaccr_value_concept_map", expected_values)):
        actual = int(backend.fetch_one(f"SELECT COUNT(*) FROM naaccr.{table}")[0])
        if actual != expected:
            failures.append(f"{table}: expected {expected} rows, got {actual}")
        bad = int(backend.fetch_one(
            f"SELECT COUNT(*) FROM naaccr.{table} m "
            "LEFT JOIN omop.concept source ON source.concept_id = m.source_concept_id "
            "LEFT JOIN omop.concept target ON target.concept_id = m.concept_id "
            "WHERE m.source_concept_id = 0 OR m.mapping_layer IS NULL "
            "OR source.concept_id IS NULL OR source.vocabulary_id <> 'NAACCR_LOCAL' "
            "OR (m.concept_id <> 0 AND "
            "(target.concept_id IS NULL OR target.standard_concept <> 'S' OR target.invalid_reason IS NOT NULL))"
        )[0])
        if bad:
            failures.append(f"{table}: {bad} invalid source, layer, or target rows")
    if failures:
        raise VocabularyError("concept map validation failed: " + "; ".join(failures))


def build_concept_maps(
    backend: DatabaseBackend, *, algorithm: str | None = None, csv_dir: Path | None = None,
) -> BuildReport:
    csv_dir = csv_dir or repository_path("database/seed")
    seeds: Seeds = read_seeds(csv_dir)
    run_log = RunLog(backend)
    run_id = run_log.start("maps build")
    try:
        _preflight(backend)
        selected_algorithm, generation = current_generation(backend, algorithm)
        all_items = _items(backend, generation)
        excluded = seeds.exclusions
        items = [item for item in all_items if item[0] not in excluded]
        item_keys = {item[0] for item in items}
        all_values = _values(backend, generation)
        values = {key: name for key, name in all_values.items() if key[0] in item_keys}
        override_path = csv_dir / OVERRIDE_FILE
        active_overrides = {}
        for override in seeds.overrides:
            if override.target_id is None:
                continue
            key = (override.item_num, override.code)
            if override.item_num not in item_keys or (override.code is not None and (override.item_num, override.code) not in values):
                raise VocabularyError(f"{override_path}:{override.line}: unknown current-generation item or value {key}")
            active_overrides[key] = override
        athena = _athena_targets(backend)
        allocations: Counter[str] = Counter()
        item_layers: Counter[str] = Counter()
        value_layers: Counter[str] = Counter()
        ambiguous = 0
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        item_rows: list[tuple[object, ...]] = []
        value_rows: list[tuple[object, ...]] = []
        with suspend_constraints(backend, "omop", ("concept", "vocabulary", "concept_class")):
            with backend.transaction():
                backend.execute_uncommitted("DELETE FROM naaccr.naaccr_value_concept_map")
                backend.execute_uncommitted("DELETE FROM naaccr.naaccr_concept_map")
                _insert_vocabulary_and_classes(backend, items, allocations)
                for item_num, name, section, parent in items:
                    local_id, fresh = reserve(backend, "item", item_num, name=name)
                    allocations["new" if fresh else "reused"] += 1
                    code = local_code("item", item_num)
                    _insert_concept(backend, local_id, name or f"NAACCR item {item_num}", "Observation", concept_class_id(section, parent), code)
                    candidates = athena.get(str(item_num), [])
                    ambiguous += len(candidates) > 1
                    target_id, domain = candidates[0] if candidates else (0, None)
                    layer = "athena_standard" if candidates else "local_mint"
                    override = active_overrides.get((item_num, None))
                    if override is not None:
                        target_id = override.target_id
                        assert target_id is not None
                        domain = _validate_override(backend, target_id, override.target_domain_id, override_path, override.line)
                        layer = "curated_override"
                    item_layers[layer] += 1
                    item_rows.append((item_num, local_id, target_id, domain, code, name or f"NAACCR item {item_num}", layer, now))
                for (item_num, raw_code), description in sorted(values.items()):
                    local_id, fresh = reserve(backend, "value", item_num, raw_code, description or raw_code)
                    allocations["new" if fresh else "reused"] += 1
                    code = local_code("value", item_num, raw_code)
                    name = description or raw_code
                    parent_item = next(item for item in items if item[0] == item_num)
                    _insert_concept(backend, local_id, name, "Meas Value", concept_class_id(parent_item[2], parent_item[3]), code)
                    athena_code = ATHENA_VALUE_CODE_PATTERN.format(item_num=item_num, code=raw_code)
                    candidates = athena.get(athena_code, [])
                    ambiguous += len(candidates) > 1
                    target_id, domain = candidates[0] if candidates else (0, None)
                    layer = "athena_standard" if candidates else "local_mint"
                    override = active_overrides.get((item_num, raw_code))
                    if override is not None:
                        target_id = override.target_id
                        assert target_id is not None
                        domain = _validate_override(backend, target_id, override.target_domain_id, override_path, override.line)
                        layer = "curated_override"
                    value_layers[layer] += 1
                    value_rows.append((item_num, raw_code, local_id, target_id, domain, code, name, layer, now))
                backend.bulk_insert(
                    "naaccr", "naaccr_concept_map", ("item_num",) + MAP_COLUMNS, item_rows,
                )
                backend.bulk_insert(
                    "naaccr", "naaccr_value_concept_map", ("item_num", "code") + MAP_COLUMNS, value_rows,
                )
                _validate_rows(backend, len(items), len(values))
                backend.execute_uncommitted("DELETE FROM naaccr.concept_map_build_state")
                backend.execute_uncommitted(
                    "INSERT INTO naaccr.concept_map_build_state "
                    "(singleton_id, algorithm, dd_version_id, built_at) VALUES (1, ?, ?, ?)",
                    (selected_algorithm, generation, now),
                )
                verify_constraints(backend, "omop", ("concept", "vocabulary", "concept_class"))
                verify_constraints(backend, "naaccr", (
                    "naaccr_concept_map", "naaccr_value_concept_map",
                    "local_concept_allocation", "concept_map_build_state",
                ))
        run_log.finish(run_id)
        return BuildReport(selected_algorithm, generation, dict(item_layers), dict(value_layers),
                           allocations["new"], allocations["reused"], ambiguous,
                           len({item[0] for item in all_items} & excluded))
    except Exception as exc:
        run_log.finish(run_id, error=str(exc))
        raise
