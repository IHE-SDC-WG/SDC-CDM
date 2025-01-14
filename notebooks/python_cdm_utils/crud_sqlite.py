import logging
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_template_sdc_class(
    cursor: sqlite3.Cursor,
    sdcformdesignid: str = None,
    baseuri: str = None,
    lineage: str = None,
    version: str = None,
    fulluri: str = None,
    formtitle: str = None,
    sdc_xml: str = None,
    doctype: str = None,
) -> dict[str, str]:
    new_entry = {
        "sdcformdesignid": sdcformdesignid,
        "baseuri": baseuri,
        "lineage": lineage,
        "version": version,
        "fulluri": fulluri,
        "formtitle": formtitle,
        "sdc_xml": sdc_xml,
        "doctype": doctype,
    }

    try:
        logger.info(f"Inserting new TemplateSdcClass: {new_entry}")
        cursor.execute(
            "INSERT INTO main.templatesdcclass (sdcformdesignid, baseuri, lineage, version, fulluri, formtitle, sdc_xml, doctype) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        logger.error("Failed to add new TemplateSdcClass:", exc_info=True)
        raise


def create_template_instance_class(
    cursor: sqlite3.Cursor,
    templatesdc_fk: int,
    template_instance_version_guid: str = None,
    template_instance_version_uri: str = None,
    instance_version_date: str = None,
    diag_report_props: str = None,
    surg_path_id: str = None,
    person_fk: int = None,
    encounter_fk: int = None,
    practitioner_fk: int = None,
    report_text: str = None,
) -> dict[str, str]:
    new_entry = {
        "templateinstanceversionguid": template_instance_version_guid,
        "templateinstanceversionuri": template_instance_version_uri,
        "templatesdcfk": templatesdc_fk,
        "instanceversiondate": instance_version_date,
        "diagreportprops": diag_report_props,
        "surgpathid": surg_path_id,
        "personfk": person_fk,
        "encounterfk": encounter_fk,
        "practitionerfk": practitioner_fk,
        "reporttext": report_text,
    }

    try:
        cursor.execute(
            "INSERT INTO templateinstanceclass (templateinstanceversionguid, templateinstanceversionuri, templatesdcfk, instanceversiondate, diagreportprops, surgpathid, personfk, encounterfk, practitionerfk, reporttext) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        logger.error("Failed to add new TemplateInstanceClass:", exc_info=True)
        raise


def create_sdc_obs_class(
    cursor: sqlite3.Cursor,
    template_instance_class_fk: int,
    parent_fk: int = None,
    parent_instance_guid: str = None,
    section_id: str = None,
    section_guid: str = None,
    q_text: str = None,
    q_instance_guid: str = None,
    q_id: str = None,
    li_text: str = None,
    li_id: str = None,
    li_instance_guid: str = None,
    li_parent_guid: str = None,
    response: str = None,
    units: str = None,
    units_system: str = None,
    datatype: str = None,
    response_int: str = None,
    response_float: str = None,
    response_datetime: str = None,
    reponse_string_nvarchar: str = None,
    obs_datetime: str = None,
    sdc_order: str = None,
    sdc_repeat_level: str = None,
    sdc_comments: str = None,
    person_fk: int = None,
    encounter_fk: int = None,
    practitioner_fk: int = None,
) -> dict[str, str]:
    new_entry = {
        "templateinstanceclassfk": template_instance_class_fk,
        # parentfk=parent_fk,
        "parentinstanceguid": parent_instance_guid,
        "section_id": section_id,
        "section_guid": section_guid,
        "q_text": q_text,
        "q_instanceguid": q_instance_guid,
        "q_id": q_id,
        "li_text": li_text,
        "li_id": li_id,
        "li_instanceguid": li_instance_guid,
        "li_parentguid": li_parent_guid,
        "response": response,
        "units": units,
        "units_system": units_system,
        "datatype": datatype,
        "response_int": response_int,
        "response_float": response_float,
        "response_datetime": response_datetime,
        "reponse_string_nvarchar": reponse_string_nvarchar,
        "obsdatetime": obs_datetime,
        "sdcorder": sdc_order,
        "sdcrepeatlevel": sdc_repeat_level,
        "sdccomments": sdc_comments,
        "personfk": person_fk,
        "encounterfk": encounter_fk,
        "practitionerfk": practitioner_fk,
    }

    try:
        cursor.execute(
            "INSERT INTO sdcobsclass (templateinstanceclassfk, parentinstanceguid, section_id, section_guid, q_text, q_instanceguid, q_id, li_text, li_id, li_instanceguid, li_parentguid, response, units, units_system, datatype, response_int, response_float, response_datetime, reponse_string_nvarchar, obsdatetime, sdcorder, sdcrepeatlevel, sdccomments, personfk, encounterfk, practitionerfk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(new_entry.values()),
        )
        cursor.execute("SELECT last_insert_rowid()")
        new_entry["pk"] = cursor.fetchone()[0]
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        logger.error("Failed to add new SdcObsClass:", exc_info=True)
        raise
