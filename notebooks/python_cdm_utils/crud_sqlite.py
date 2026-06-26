import logging
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# sdc.template_sdc
# ---------------------------------------------------------------------------
def create_template_sdc_class(
    cursor: sqlite3.Cursor,
    sdc_form_design_sdcid: str = None,
    base_uri: str = None,
    lineage: str = None,
    version: str = None,
    full_uri: str = None,
    form_title: str = None,
    sdc_xml: str = None,
    doc_type: str = None,
) -> dict:
    new_entry = {
        "sdc_form_design_sdcid": sdc_form_design_sdcid,
        "base_uri": base_uri,
        "lineage": lineage,
        "version": version,
        "full_uri": full_uri,
        "form_title": form_title,
        "sdc_xml": sdc_xml,
        "doc_type": doc_type,
    }
    try:
        cursor.execute(
            """
            INSERT INTO sdc.template_sdc (
                sdc_form_design_sdcid, base_uri, lineage, version,
                full_uri, form_title, sdc_xml, doc_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        return new_entry
    except Exception:
        logger.error("Failed to add new template_sdc:", exc_info=True)
        raise


def find_template_sdc_class(
    cursor: sqlite3.Cursor, sdc_form_design_sdcid: str
):
    """Return the template_sdc_id for a form-design id, or None if absent."""
    cursor.execute(
        "SELECT template_sdc_id FROM sdc.template_sdc WHERE sdc_form_design_sdcid = ?",
        (sdc_form_design_sdcid,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# sdc.template_instance
# ---------------------------------------------------------------------------
def create_template_instance_class(
    cursor: sqlite3.Cursor,
    template_sdc_id: int,
    template_instance_version_guid: str = None,
    template_instance_version_uri: str = None,
    instance_version_date: str = None,
    diag_report_props: str = None,
    surg_path_sdcid: str = None,
    person_id: int = None,
    visit_occurrence_id: int = None,
    provider_id: int = None,
    report_text: str = None,
) -> dict:
    new_entry = {
        "template_instance_version_guid": template_instance_version_guid,
        "template_instance_version_uri": template_instance_version_uri,
        "template_sdc_id": template_sdc_id,
        "instance_version_date": instance_version_date,
        "diag_report_props": diag_report_props,
        "surg_path_sdcid": surg_path_sdcid,
        "person_id": person_id,
        "visit_occurrence_id": visit_occurrence_id,
        "provider_id": provider_id,
        "report_text": report_text,
    }
    try:
        cursor.execute(
            """
            INSERT INTO sdc.template_instance (
                template_instance_version_guid, template_instance_version_uri,
                template_sdc_id, instance_version_date, diag_report_props,
                surg_path_sdcid, person_id, visit_occurrence_id, provider_id, report_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        return new_entry
    except Exception:
        logger.error("Failed to add new template_instance:", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# sdc.sdc_form_answer  (replaces the old create_sdc_obs_class)
# ---------------------------------------------------------------------------
def create_sdc_form_answer(
    cursor: sqlite3.Cursor,
    template_instance_id: int = None,
    report_id: int = None,
    parent_form_answer_id: int = None,
    section_sdcid: str = None,
    section_guid: str = None,
    question_text: str = None,
    question_instance_guid: str = None,
    question_sdcid: str = None,
    list_item_id: str = None,
    list_item_text: str = None,
    list_item_instance_guid: str = None,
    list_item_parent_guid: str = None,
    units_system: str = None,
    datatype: str = None,
    sdc_order: str = None,
    sdc_repeat_level: str = None,
    sdc_comments: str = None,
) -> dict:
    new_entry = {
        "report_id": report_id,
        "template_instance_id": template_instance_id,
        "parent_form_answer_id": parent_form_answer_id,
        "section_sdcid": section_sdcid,
        "section_guid": section_guid,
        "question_text": question_text,
        "question_instance_guid": question_instance_guid,
        "question_sdcid": question_sdcid,
        "list_item_id": list_item_id,
        "list_item_text": list_item_text,
        "list_item_instance_guid": list_item_instance_guid,
        "list_item_parent_guid": list_item_parent_guid,
        "units_system": units_system,
        "datatype": datatype,
        "sdc_order": sdc_order,
        "sdc_repeat_level": sdc_repeat_level,
        "sdc_comments": sdc_comments,
    }
    try:
        cursor.execute(
            """
            INSERT INTO sdc.sdc_form_answer (
                report_id, template_instance_id, parent_form_answer_id,
                section_sdcid, section_guid, question_text, question_instance_guid,
                question_sdcid, list_item_id, list_item_text, list_item_instance_guid,
                list_item_parent_guid, units_system, datatype, sdc_order,
                sdc_repeat_level, sdc_comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        return new_entry
    except Exception:
        logger.error("Failed to add new sdc_form_answer:", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# omop.person
# ---------------------------------------------------------------------------
def find_person_by_identifier(cursor: sqlite3.Cursor, person_source_value: str):
    """Return an existing person_id for a source identifier, or None."""
    cursor.execute(
        "SELECT person_id FROM omop.person WHERE person_source_value = ?",
        (person_source_value,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def create_person(
    cursor: sqlite3.Cursor,
    person_source_value: str = None,
    year_of_birth: int = 1900,
    month_of_birth: int = None,
    day_of_birth: int = None,
    birth_datetime: str = None,
    gender_concept_id: int = 0,
    race_concept_id: int = 0,
    ethnicity_concept_id: int = 0,
) -> int:
    cursor.execute(
        """
        INSERT INTO omop.person (
            gender_concept_id, year_of_birth, month_of_birth, day_of_birth,
            birth_datetime, race_concept_id, ethnicity_concept_id, person_source_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gender_concept_id,
            year_of_birth,
            month_of_birth,
            day_of_birth,
            birth_datetime,
            race_concept_id,
            ethnicity_concept_id,
            person_source_value,
        ),
    )
    cursor.execute("SELECT last_insert_rowid()")
    return cursor.fetchone()[0]


# ---------------------------------------------------------------------------
# sdc.sdc_report
# ---------------------------------------------------------------------------
def find_first_sdc_report_by_accession(
    cursor: sqlite3.Cursor, report_accession: str
):
    """Return the earliest sdc_report_id for an accession, or None."""
    if not report_accession:
        return None
    cursor.execute(
        """
        SELECT sdc_report_id FROM sdc.sdc_report
        WHERE report_accession = ?
        ORDER BY sdc_report_id
        LIMIT 1
        """,
        (report_accession,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def create_sdc_report(
    cursor: sqlite3.Cursor,
    template_name: str,
    template_version: str,
    template_instance_guid: str,
    person_id: int = None,
    report_text: str = None,
    report_template_source: str = None,
    report_template_id: str = None,
    report_template_version_id: str = None,
    tumor_site: str = None,
    procedure_type: str = None,
    specimen_laterality: str = None,
    report_accession: str = None,
    report_loinc: str = None,
    is_duplicate_accession: bool = False,
    first_seen_report_id: int = None,
) -> int:
    cursor.execute(
        """
        INSERT INTO sdc.sdc_report (
            template_name, template_version, template_instance_guid, person_id,
            report_text, report_template_source, report_template_id,
            report_template_version_id, tumor_site, procedure_type,
            specimen_laterality, report_accession, report_loinc,
            is_duplicate_accession, first_seen_report_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            template_name,
            template_version,
            template_instance_guid,
            person_id,
            report_text,
            report_template_source,
            report_template_id,
            report_template_version_id,
            tumor_site,
            procedure_type,
            specimen_laterality,
            report_accession,
            report_loinc,
            1 if is_duplicate_accession else 0,
            first_seen_report_id,
        ),
    )
    cursor.execute("SELECT last_insert_rowid()")
    return cursor.fetchone()[0]


# ---------------------------------------------------------------------------
# naaccr.naaccr_value
# ---------------------------------------------------------------------------
def create_naaccr_value(
    cursor: sqlite3.Cursor,
    person_id: int,
    episode_key: str,
    report_accession: str = None,
    item_num: int = None,
    value_code: str = None,
    value_num: float = None,
    value_unit_source: str = None,
    observation_date: str = None,
    schema_id_number: str = None,
) -> int:
    cursor.execute(
        """
        INSERT INTO naaccr.naaccr_value (
            person_id, episode_key, report_accession, schema_id_number,
            item_num, value_code, value_num, value_unit_source, observation_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            person_id,
            episode_key,
            report_accession,
            schema_id_number,
            item_num,
            value_code,
            value_num,
            value_unit_source,
            observation_date,
        ),
    )
    cursor.execute("SELECT last_insert_rowid()")
    return cursor.fetchone()[0]
