#!/usr/bin/env python3
"""Smoke tests for workbook-to-JSON NAACCR/OMOP mapping conversion."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from convert_naaccr_omop_maps import build_spec


spec = build_spec(REPO_ROOT / "NAACRToOMOPmaps")
items = spec["workflow_input"]["item_mappings"]
by_code = {mapping["concept_code"]: mapping for mapping in items}

merge = spec["workflow_input"]["naaccr_person_merge"]
assert merge["matched_rows"] == 142, merge
assert merge["unmatched_rows"] == 0, merge
assert sum(1 for mapping in items if mapping.get("person_mapping_applied")) == 142

sex = by_code["sex"]
assert sex["storage"] == "OMOP PERSON"
assert sex["omop_table"] == "PERSON"
assert sex["mapping_kind"] == "OMOP_CORE"
assert sex["proposed_extension_table"] is None

current_country = by_code["addrCurrentCountry"]
assert current_country["storage"] == "OMOP LOCATION"
assert current_country["omop_table"] == "LOCATION"
assert current_country["naaccr_person_column"] == "current_location_id"
assert current_country["proposed_extension_table"] is None

ethnicity_source = by_code["computedEthnicitySource"]
assert ethnicity_source["storage"] == "OMOP OBSERVATION"
assert ethnicity_source["omop_table"] == "OBSERVATION"
assert ethnicity_source["mapping_kind"] == "OMOP_OBSERVATION"

cause_of_death = by_code["causeOfDeath"]
assert cause_of_death["storage"] == "OMOP DEATH"
assert cause_of_death["omop_table"] == "DEATH"
assert cause_of_death["proposed_extension_table"] is None

vital_status = by_code["vitalStatus"]
assert vital_status["storage"] == "NAACCR_PERSON"
assert vital_status["mapping_kind"] == "NAACCR_PERSON"
assert vital_status["proposed_extension_table"] == "NAACCR_PERSON"
assert vital_status["proposed_extension_column"] == "vital_status"

for mapping in items:
    if mapping.get("person_mapping_applied") and mapping["storage"].startswith("OMOP "):
        assert mapping.get("proposed_extension_table") is None, mapping["concept_code"]

print("All converter merge assertions passed.")
