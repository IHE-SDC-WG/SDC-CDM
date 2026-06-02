from __future__ import annotations

from typing import Any, Optional


def _normalize_target(mapping: dict[str, Any]) -> str:
    omop_table = str(mapping.get("omop_table") or "").lower()
    mapping_kind = str(mapping.get("mapping_kind") or "").lower()

    if "observation" in omop_table:
        return "observation"
    if "measurement" in omop_table:
        return "measurement"
    if mapping_kind == "omop_core":
        return "omop_core"
    return "measurement"


def _index_mappings(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for mapping in spec.get("workflow_input", {}).get("item_mappings", []):
        concept_code = mapping.get("concept_code")
        if concept_code and concept_code not in index:
            index[concept_code] = mapping
    return index


def _row_date(item: dict[str, Any], source: dict[str, Any]) -> Optional[str]:
    return (
        item.get("observation_date")
        or source.get("observation_date")
        or source.get("episode", {}).get("episode_start_date")
    )


def _value_source_value(item: dict[str, Any]) -> Optional[str]:
    for key in ("value_source_value", "value", "value_code", "value_num"):
        if key in item:
            return str(item[key])
    return None


def _measurement_row(
    *,
    row_id: int,
    source: dict[str, Any],
    item: dict[str, Any],
    mapping: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    constants = workflow.get("constants", {})
    return {
        "measurement_id": row_id,
        "person_id": source["person"]["person_id"],
        "measurement_concept_id": mapping.get("concept_id") or 0,
        "measurement_date": _row_date(item, source),
        "measurement_datetime": None,
        "measurement_type_concept_id": constants.get("measurement_type_concept_id", 0),
        "operator_concept_id": None,
        "value_as_number": item.get("value_num"),
        "value_as_concept_id": None,
        "unit_concept_id": None,
        "range_low": None,
        "range_high": None,
        "provider_id": None,
        "visit_occurrence_id": None,
        "visit_detail_id": None,
        "measurement_source_value": mapping.get("concept_code"),
        "measurement_source_concept_id": mapping.get("concept_id"),
        "unit_source_value": item.get("unit_source_value"),
        "value_source_value": _value_source_value(item),
    }


def _observation_row(
    *,
    row_id: int,
    source: dict[str, Any],
    item: dict[str, Any],
    mapping: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    constants = workflow.get("constants", {})
    value = item.get("value")
    return {
        "observation_id": row_id,
        "person_id": source["person"]["person_id"],
        "observation_concept_id": mapping.get("concept_id") or 0,
        "observation_date": _row_date(item, source),
        "observation_datetime": None,
        "observation_type_concept_id": constants.get("observation_type_concept_id", 0),
        "value_as_number": item.get("value_num"),
        "value_as_string": str(value) if value is not None else None,
        "value_as_concept_id": None,
        "qualifier_concept_id": None,
        "unit_concept_id": None,
        "provider_id": None,
        "visit_occurrence_id": None,
        "visit_detail_id": None,
        "observation_source_value": mapping.get("concept_code"),
        "observation_source_concept_id": mapping.get("concept_id"),
        "unit_source_value": item.get("unit_source_value"),
        "qualifier_source_value": item.get("value_code"),
    }


def _extension_column_value(item: dict[str, Any]) -> Any:
    for key in ("value_num", "value", "value_code"):
        if key in item:
            return item[key]
    return None


def _add_extension_value(
    *,
    rows: dict[str, Any],
    source: dict[str, Any],
    mapping: dict[str, Any],
    item: dict[str, Any],
) -> None:
    table = mapping.get("proposed_extension_table")
    column = mapping.get("proposed_extension_column") or mapping.get("concept_code")
    if not table or not column:
        return

    if table not in rows["extension_tables"]:
        rows["extension_tables"][table] = {
            "person_id": source["person"]["person_id"],
            "episode_id": source["episode"]["episode_id"],
        }

    rows["extension_tables"][table][column] = _extension_column_value(item)


def _episode_row(source: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    constants = workflow.get("constants", {})
    episode = source["episode"]
    return {
        "episode_id": episode["episode_id"],
        "person_id": source["person"]["person_id"],
        "episode_concept_id": constants.get("episode_concept_id", 0),
        "episode_start_date": episode["episode_start_date"],
        "episode_start_datetime": None,
        "episode_end_date": episode.get("episode_end_date"),
        "episode_end_datetime": None,
        "episode_parent_id": episode.get("episode_parent_id"),
        "episode_number": episode.get("episode_number"),
        "episode_object_concept_id": constants.get("episode_object_concept_id", 0),
        "episode_type_concept_id": constants.get("episode_type_concept_id", 0),
        "episode_source_value": episode.get("episode_key"),
        "episode_source_concept_id": None,
    }


def map_naaccr_case_to_omop(
    *,
    source: dict[str, Any],
    mapping_spec: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    mappings = _index_mappings(mapping_spec)
    rows: dict[str, Any] = {
        "episode": [_episode_row(source, workflow)],
        "measurement": [],
        "observation": [],
        "episode_event": [],
        "extension_tables": {},
        "unmapped_items": [],
    }

    measurement_id = source.get("id_offsets", {}).get("measurement_id", 1)
    observation_id = source.get("id_offsets", {}).get("observation_id", 1)
    constants = workflow.get("constants", {})

    for item in source.get("items", []):
        mapping = mappings.get(item.get("concept_code"))
        if mapping is None:
            rows["unmapped_items"].append(item)
            continue

        _add_extension_value(rows=rows, source=source, mapping=mapping, item=item)
        target = _normalize_target(mapping)

        if target == "observation":
            observation = _observation_row(
                row_id=observation_id,
                source=source,
                item=item,
                mapping=mapping,
                workflow=workflow,
            )
            observation_id += 1
            rows["observation"].append(observation)
            rows["episode_event"].append(
                {
                    "episode_id": source["episode"]["episode_id"],
                    "event_id": observation["observation_id"],
                    "episode_event_field_concept_id": constants.get(
                        "field_observation_id", 1147165
                    ),
                }
            )
            continue

        if target == "omop_core":
            continue

        measurement = _measurement_row(
            row_id=measurement_id,
            source=source,
            item=item,
            mapping=mapping,
            workflow=workflow,
        )
        measurement_id += 1
        rows["measurement"].append(measurement)
        rows["episode_event"].append(
            {
                "episode_id": source["episode"]["episode_id"],
                "event_id": measurement["measurement_id"],
                "episode_event_field_concept_id": constants.get(
                    "field_measurement_id", 1147138
                ),
            }
        )

    return rows
