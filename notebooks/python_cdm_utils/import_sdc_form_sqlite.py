#!/usr/bin/env python3
"""Import an SDCFormSubmission XML form into the three-schema SDC CDM.

Ported from SdcCdmLib/SdcCdm/ImportXmlForm.cs. Writes form *structure* into
``sdc.template_instance`` and ``sdc.sdc_form_answer`` only -- answer values are
not stored on the SDC side (they live in ``naaccr.naaccr_value`` for NAACCR
feeds). ``sdc_form_answer.report_id`` is left null for form submissions.
"""

from lxml import etree
import logging
from python_cdm_utils.crud_sqlite import (
    create_template_sdc_class,
    find_template_sdc_class,
    create_template_instance_class,
    create_sdc_form_answer,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

NAMESPACES = {
    "sdc": "urn:ihe:qrph:sdc:2016",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}


def process_xml(xml_root, cursor):
    """
    :param xml_root: Root of the SDCFormSubmission XML tree (lxml Element)
    :param cursor: SQLite cursor to insert with
    """
    form_design = xml_root.find("sdc:FormDesign", NAMESPACES)
    if form_design is None:
        raise Exception("No Form Design found in XML")
    print(f"Form Design: {form_design}")

    sdc_form_design_id = form_design.get("ID")
    if not sdc_form_design_id:
        raise Exception("No Form Design ID provided in XML")

    # Find the template row for this form-design id; create one if missing.
    template_sdc_id = find_template_sdc_class(cursor, sdc_form_design_id)
    if template_sdc_id is None:
        template_sdc_id = create_template_sdc_class(
            cursor=cursor,
            sdc_form_design_sdcid=sdc_form_design_id,
            base_uri=form_design.get("baseURI") or "UNKNOWN",
            lineage=form_design.get("lineage") or "UNKNOWN",
            version=form_design.get("version") or "UNKNOWN",
            full_uri=form_design.get("fullURI") or "UNKNOWN",
            form_title=form_design.get("formTitle") or "UNKNOWN",
            sdc_xml=etree.tostring(form_design).decode("utf-8"),
            doc_type="FD",
        )["pk"]

    template_instance = create_template_instance_class(
        cursor=cursor,
        template_sdc_id=template_sdc_id,
        template_instance_version_guid=xml_root.get("instanceID"),
        template_instance_version_uri=xml_root.get("instanceVersionURI"),
        instance_version_date=xml_root.get("instanceVersion"),
    )
    template_instance_id = template_instance["pk"]

    body = form_design.find("sdc:Body", NAMESPACES)
    if body is None:
        raise Exception("Body element not found.")

    for child in body.findall("sdc:ChildItems", NAMESPACES):
        process_child_item(child, cursor, template_instance_id)


def process_child_item(
    child_item,
    cursor,
    template_instance_id,
    section_id=None,
    section_guid=None,
):
    for section in child_item.findall("sdc:Section", NAMESPACES):
        inner_section_guid = section.get("ID")
        if not inner_section_guid:
            continue
        inner_section_id = section.get("title")
        for child in section.findall("sdc:ChildItems", NAMESPACES):
            process_child_item(
                child,
                cursor,
                template_instance_id,
                inner_section_id,
                inner_section_guid,
            )

    # Questions are only emitted when inside a section (i.e. section_guid set).
    if not section_guid:
        return

    for question in child_item.findall("sdc:Question", NAMESPACES):
        process_question(
            question, cursor, template_instance_id, section_id, section_guid
        )


def process_question(
    question, cursor, template_instance_id, section_id, section_guid
):
    question_id = question.get("name")
    question_guid = question.get("ID")
    question_text = question.get("title")

    list_field = question.find("sdc:ListField", NAMESPACES)
    response_field = question.find("sdc:ResponseField", NAMESPACES)

    if list_field is not None:
        process_list_field(
            list_field,
            cursor,
            template_instance_id,
            section_id,
            section_guid,
            question_text,
            question_id,
            question_guid,
        )
    elif response_field is not None:
        process_response_field(
            response_field,
            cursor,
            template_instance_id,
            section_id,
            section_guid,
            question_text,
            question_id,
            question_guid,
        )
    else:
        print("Warning: No ListField or ResponseField found for Question")


def process_list_field(
    list_field,
    cursor,
    template_instance_id,
    section_id,
    section_guid,
    question_text,
    question_id,
    question_guid,
):
    list_elem = list_field.find("sdc:List", NAMESPACES)
    if list_elem is None:
        return
    for list_item in list_elem.findall("sdc:ListItem", NAMESPACES):
        # Only selected list items are captured (matches the C# importer).
        if list_item.get("selected") != "true":
            continue
        li_response_field = list_item.find("sdc:ListItemResponseField", NAMESPACES)
        if li_response_field is not None:
            process_response_field(
                li_response_field,
                cursor,
                template_instance_id,
                section_id,
                section_guid,
                question_text,
                question_id,
                question_guid,
                li_text=list_item.get("title"),
                li_id=list_item.get("name"),
                li_instance_guid=list_item.get("ID"),
            )
        else:
            create_sdc_form_answer(
                cursor=cursor,
                template_instance_id=template_instance_id,
                section_sdcid=section_id,
                section_guid=section_guid,
                question_text=question_text,
                question_instance_guid=question_guid,
                question_sdcid=question_id,
                list_item_text=list_item.get("title"),
                list_item_id=list_item.get("name"),
                list_item_instance_guid=list_item.get("ID"),
                sdc_order=list_item.get("order"),
            )


def process_response_field(
    response_field,
    cursor,
    template_instance_id,
    section_id,
    section_guid,
    question_text,
    question_id,
    question_guid,
    li_text=None,
    li_id=None,
    li_instance_guid=None,
    li_parent_guid=None,
):
    response_units_system = None
    response_units_elem = response_field.find("sdc:ResponseUnits", NAMESPACES)
    if response_units_elem is not None:
        response_units_system = response_units_elem.get("unitSystem")

    response = response_field.find("sdc:Response", NAMESPACES)
    if response is not None:
        create_sdc_form_answer(
            cursor=cursor,
            template_instance_id=template_instance_id,
            section_sdcid=section_id,
            section_guid=section_guid,
            question_text=question_text,
            question_instance_guid=question_guid,
            question_sdcid=question_id,
            list_item_text=li_text,
            list_item_id=li_id,
            list_item_instance_guid=li_instance_guid,
            list_item_parent_guid=li_parent_guid,
            units_system=response_units_system,
            sdc_order=response.get("order"),
        )
