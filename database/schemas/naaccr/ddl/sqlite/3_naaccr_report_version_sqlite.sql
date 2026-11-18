PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- One accession for one intake patient at one sending facility. Versions of
-- every report type in the group hang off this row.
CREATE TABLE IF NOT EXISTS naaccr.report_group (
    report_group_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    -- logical reference to intake.patient.patient_id; not an enforced FK (cross-schema/attached-DB)
    person_id INTEGER NOT NULL,
    -- '' when the message names no sending facility
    sending_facility TEXT NOT NULL,
    report_accession TEXT NOT NULL CHECK (length(report_accession) > 0),
    created_datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (person_id, sending_facility, report_accession)
);

-- One row per loaded, accessioned sdc_report. The first version of each type is
-- selected; only an explicit supersession moves selection, and the successor
-- records its predecessor in the same group and type.
CREATE TABLE IF NOT EXISTS naaccr.report_version (
    report_version_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    report_group_id INTEGER NOT NULL REFERENCES report_group(report_group_id),
    -- the report type; '' when the OBR carries no report LOINC
    report_loinc TEXT NOT NULL,
    -- logical references to sdc.sdc_report, intake.inbound_envelope and
    -- intake.inbound_message; not enforced FKs (cross-schema/attached-DB)
    sdc_report_id INTEGER NOT NULL UNIQUE,
    inbound_envelope_id INTEGER NOT NULL,
    inbound_message_id INTEGER NOT NULL,
    is_selected INTEGER NOT NULL CHECK (is_selected IN (0, 1)),
    predecessor_sdc_report_id INTEGER NULL,
    created_datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (report_group_id, report_loinc, sdc_report_id),
    CHECK (predecessor_sdc_report_id IS NULL OR predecessor_sdc_report_id <> sdc_report_id),
    FOREIGN KEY (report_group_id, report_loinc, predecessor_sdc_report_id)
        REFERENCES report_version (report_group_id, report_loinc, sdc_report_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS naaccr.ux_report_version_selected
    ON report_version (report_group_id, report_loinc) WHERE is_selected = 1;
CREATE UNIQUE INDEX IF NOT EXISTS naaccr.ux_report_version_predecessor
    ON report_version (predecessor_sdc_report_id) WHERE predecessor_sdc_report_id IS NOT NULL;

-- Bridge script 4 provenance: the one thin primary-site condition of a selected
-- group. condition_occurrence_id is a logical reference into omop.condition_occurrence
-- (OMOP holds no crosswalk); the bridge owns only conditions named here.
-- naaccr_value_id is the chosen primary-site value, and condition_target records
-- why condition_concept_id is or is not a standard target.
CREATE TABLE IF NOT EXISTS naaccr.group_condition (
    report_group_id INTEGER NOT NULL PRIMARY KEY REFERENCES report_group(report_group_id),
    condition_occurrence_id INTEGER NOT NULL UNIQUE,
    naaccr_value_id INTEGER NOT NULL REFERENCES naaccr_value(naaccr_value_id),
    condition_target TEXT NOT NULL CHECK (condition_target IN (
        'mapped', 'no_map', 'no_target', 'other_domain', 'collision_suppressed'
    ))
);

-- Bridge script 4 provenance: one disease episode per (person, episode_key). The
-- key is the envelope's source tumor identity, else its accession hash, so it never
-- fits omop.episode.episode_source_value. The bridge owns only episodes named here,
-- and every omop.episode_event row of an owned episode.
CREATE TABLE IF NOT EXISTS naaccr.person_episode (
    episode_id INTEGER NOT NULL PRIMARY KEY,
    -- logical reference to intake.patient.patient_id (omop.person.person_id)
    person_id INTEGER NOT NULL,
    episode_key TEXT NOT NULL,
    UNIQUE (person_id, episode_key)
);

COMMIT;
