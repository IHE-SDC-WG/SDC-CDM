import sys
import argparse
from lxml import etree
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import logging
from crud import (
    create_template_sdc_class,
    create_template_instance_class,
    create_sdc_obs_class,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Process an XML file and import data into the database."
    )
    parser.add_argument("xml_file", help="Path to the XML file to process")
    return parser.parse_args()


def process_xml(xml_file, session):
    """
    :param xml_file: The path to the XML file to process.
    :param session: The SQLAlchemy database session.
    """
    try:
        tree = etree.parse(xml_file)
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"Error parsing XML file: {e}")
        sys.exit(1)
    assert root is not None

    namespaces = {
        "sdc": "urn:ihe:qrph:sdc:2016",  # Default namespace with a custom prefix 'sdc'
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsd": "http://www.w3.org/2001/XMLSchema",
    }

    form_design = root.find("sdc:FormDesign", namespaces)
    if form_design is None:
        form_design = root
    print(f"Form Design: {form_design}")
    if form_design is not None:
        new_template_sdc = create_template_sdc_class(
            session=session,
            sdcformdesignid=form_design.get("ID"),
            baseuri=form_design.get("baseURI"),
            lineage=form_design.get("lineage"),
            version=form_design.get("version"),
            fulluri=form_design.get("fullURI"),
            formtitle=form_design.get("formTitle"),
            sdc_xml=etree.tostring(form_design).decode("utf-8"),
            doctype="FD",  # TODO: Parse from fullURI
        )

        new_template_instance_class = create_template_instance_class(
            session=session,
            templatesdc_fk=new_template_sdc.pk,
            # TODO: Fill in TemplateInstanceClass fields
        )

        body = form_design.find("sdc:Body", namespaces)
        assert body is not None
        child_items = body.findall("sdc:ChildItems", namespaces)
        assert child_items is not None
        for child in child_items:
            process_child_item(
                child, session, namespaces, new_template_instance_class.pk
            )


def process_child_item(
    child_item,
    session,
    namespaces,
    template_instance_class_fk,
    section_id=None,
    section_guid=None,
):
    sections = child_item.findall("sdc:Section", namespaces)
    for section in sections:
        section_id = section.get("name")
        section_guid = section.get("ID")
        child_items = section.findall("sdc:ChildItems", namespaces)
        assert child_items is not None
        for child in child_items:
            process_child_item(
                child,
                session,
                namespaces,
                template_instance_class_fk,
                section_id,
                section_guid,
            )
    questions = child_item.findall("sdc:Question", namespaces)
    for question in questions:
        process_question(
            question,
            session,
            namespaces,
            template_instance_class_fk,
            section_id,
            section_guid,
        )


def process_question(
    question, session, namespaces, template_instance_class_fk, section_id, section_guid
):
    question_id = question.get("name")
    question_guid = question.get("ID")
    question_text = question.get("title")
    listfield = question.find("sdc:ListField", namespaces)
    if listfield is not None:
        process_list_field(
            listfield,
            session,
            namespaces,
            template_instance_class_fk,
            section_id,
            section_guid,
            question_text,
            question_id,
            question_guid,
        )
    responsefield = question.find("sdc:ResponseField", namespaces)
    if responsefield is not None:
        process_response_field(
            responsefield,
            session,
            namespaces,
            template_instance_class_fk,
            section_id,
            section_guid,
            question_text,
            question_id,
            question_guid,
        )


def process_list_field(
    list_field,
    session,
    namespaces,
    template_instance_class_fk,
    section_id,
    section_guid,
    question_text,
    question_id,
    question_guid,
):
    list_elem = list_field.find("sdc:List", namespaces)
    if list_elem is not None:
        list_items = list_elem.findall("sdc:ListItem", namespaces)
        for list_item in list_items:
            li_response_field = list_item.find("sdc:ListItemResponseField", namespaces)
            if li_response_field is not None:
                process_response_field(
                    li_response_field,
                    session,
                    namespaces,
                    template_instance_class_fk,
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
                create_sdc_obs_class(
                    session=session,
                    template_instance_class_fk=template_instance_class_fk,
                    section_id=section_id,
                    section_guid=section_guid,
                    q_text=question_text,
                    q_instance_guid=question_guid,
                    q_id=question_id,
                    li_text=list_item.get("title"),
                    li_id=list_item.get("name"),
                    li_instance_guid=list_item.get("ID"),
                    sdc_order=list_item.get("order"),
                )


def process_response_field(
    response_field,
    session,
    namespaces,
    template_instance_class_fk,
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
    # Get units
    response_units = None
    response_units_system = None
    response_units_elem = response_field.find("sdc:ResponseUnits", namespaces)
    if response_units_elem is not None:
        response_units = response_units_elem.get("val")
        response_units_system = response_units_elem.get("unitSystem")
    response = response_field.find("sdc:Response", namespaces)
    if response is not None:
        response_string = response.find("sdc:string", namespaces)
        response_string_val = None
        if response_string is not None:
            response_string_val = response_string.get("val")
        create_sdc_obs_class(
            session=session,
            template_instance_class_fk=template_instance_class_fk,
            section_id=section_id,
            section_guid=section_guid,
            q_text=question_text,
            q_instance_guid=question_guid,
            q_id=question_id,
            li_text=li_text,
            li_id=li_id,
            li_instance_guid=li_instance_guid,
            li_parent_guid=li_parent_guid,
            response=response.get("val"),
            units=response_units,
            units_system=response_units_system,
            datatype=None,
            response_int=None,
            response_float=None,
            response_datetime=None,
            reponse_string_nvarchar=response_string_val,
            sdc_order=response.get("order"),
        )


def main(xml_file):
    try:
        db_user = os.environ.get("DB_USER", "postgres")
        db_password = os.environ.get("DB_PASSWORD")
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", "5432")
        db_name = os.environ.get("DB_NAME", "postgres")
        if (db_password is None) or (db_password == ""):
            print("DB_PASSWORD environment variable must be set")
            sys.exit(1)
        assert db_user != "" and db_host != "" and db_port != "" and db_name != ""
        db_url = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        sys.exit(1)
    assert session is not None

    try:
        process_xml(xml_file, session)
    except Exception as e:
        print("An error occurred while processing XML:", e)
    finally:
        session.commit()
        session.close()


if __name__ == "__main__":
    args = parse_arguments()
    assert args.xml_file is not None
    main(args.xml_file)
