from sqlalchemy.orm import Session
from models import TemplateSdcClass, TemplateInstanceClass, SdcObsClass
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_template_sdc_class(
    session: Session,
    sdcformdesignid: str = None,
    baseuri: str = None,
    lineage: str = None,
    version: str = None,
    fulluri: str = None,
    formtitle: str = None,
    sdc_xml: str = None,
    doctype: str = None,
) -> TemplateSdcClass:
    """
    Creates a new TemplateSdcClass record in the database.

    :param session: SQLAlchemy session object
    :param sdcformdesignid: (Optional) SDC Form Design ID as a string
    :param baseuri: (Optional) Base URI as a string
    :param lineage: (Optional) Lineage information as a string
    :param version: (Optional) Version information as a string
    :param fulluri: (Optional) Full URI as a string
    :param formtitle: (Optional) Form title as a string
    :param sdc_xml: (Optional) XML content as text
    :param doctype: (Optional) Document type as a string
    :return: The created TemplateSdcClass object
    """
    new_entry = TemplateSdcClass(
        pk=None,
        sdcformdesignid=sdcformdesignid,
        baseuri=baseuri,
        lineage=lineage,
        version=version,
        fulluri=fulluri,
        formtitle=formtitle,
        sdc_xml=sdc_xml,
        doctype=doctype,
    )

    try:
        session.add(new_entry)
        session.commit()
        session.refresh(new_entry)  # Refresh to get the generated PK
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        session.rollback()
        logger.error("Failed to add new TemplateSdcClass:", exc_info=True)
        raise


# Similarly, define create functions for other models


def create_template_instance_class(
    session: Session,
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
) -> TemplateInstanceClass:
    """
    Creates a new TemplateInstanceClass record in the database.

    :param session: SQLAlchemy session object
    :param templatesdc_fk: Foreign key to TemplateSdcClass
    :param template_instance_version_guid: (Optional) GUID as a string
    :param template_instance_version_uri: (Optional) URI as a string
    :param instance_version_date: (Optional) Date as a string
    :param diag_report_props: (Optional) Diagnostic report properties as text
    :param surg_path_id: (Optional) Surgery Pathology ID as integer
    :param person_fk: (Optional) Foreign key to Person
    :param encounter_fk: (Optional) Foreign key to Encounter
    :param practitioner_fk: (Optional) Foreign key to Practitioner
    :param report_text: (Optional) Report text as string
    :return: The created TemplateInstanceClass object
    """
    new_entry = TemplateInstanceClass(
        templateinstanceversionguid=template_instance_version_guid,
        templateinstanceversionuri=template_instance_version_uri,
        templatesdcfk=templatesdc_fk,
        instanceversiondate=instance_version_date,
        diagreportprops=diag_report_props,
        surgpathid=surg_path_id,
        personfk=person_fk,
        encounterfk=encounter_fk,
        practitionerfk=practitioner_fk,
        reporttext=report_text,
    )

    try:
        session.add(new_entry)
        session.commit()
        session.refresh(new_entry)
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        session.rollback()
        logger.error("Failed to add new TemplateInstanceClass:", exc_info=True)
        raise


def create_sdc_obs_class(
    session: Session,
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
) -> SdcObsClass:
    """
    Creates a new SdcObsClass record in the database.

    :param session: SQLAlchemy session object
    :param template_instance_class_fk: Foreign key to TemplateInstanceClass
    :param parent_fk: (Optional) Parent foreign key as integer
    :param parent_instance_guid: (Optional) Parent instance GUID as string
    :param section_id: (Optional) Section ID as integer
    :param section_guid: (Optional) Section GUID as string
    :param q_text: (Optional) Question text as string
    :param q_instance_guid: (Optional) Question instance GUID as string
    :param q_id: (Optional) Question ID as integer
    :param li_text: (Optional) List item text as string
    :param li_id: (Optional) List item ID as integer
    :param li_instance_guid: (Optional) List item instance GUID as string
    :param li_parent_guid: (Optional) List item parent GUID as string
    :param response: (Optional) Response as string
    :param units: (Optional) Units as string
    :param units_system: (Optional) Units system as string
    :param datatype: (Optional) Data type as string
    :param response_int: (Optional) Response integer
    :param response_float: (Optional) Response float
    :param response_datetime: (Optional) Response datetime as string
    :param reponse_string_nvarchar: (Optional) Response string
    :param obs_datetime: (Optional) Observation datetime as string
    :param sdc_order: (Optional) SDC order as integer
    :param sdc_repeat_level: (Optional) SDC repeat level as integer
    :param sdc_comments: (Optional) SDC comments as string
    :param person_fk: (Optional) Foreign key to Person
    :param encounter_fk: (Optional) Foreign key to Encounter
    :param practitioner_fk: (Optional) Foreign key to Practitioner
    :return: The created SdcObsClass object
    """
    new_entry = SdcObsClass(
        templateinstanceclassfk=template_instance_class_fk,
        # parentfk=parent_fk,
        parentinstanceguid=parent_instance_guid,
        section_id=section_id,
        section_guid=section_guid,
        q_text=q_text,
        q_instanceguid=q_instance_guid,
        q_id=q_id,
        li_text=li_text,
        li_id=li_id,
        li_instanceguid=li_instance_guid,
        li_parentguid=li_parent_guid,
        response=response,
        units=units,
        units_system=units_system,
        datatype=datatype,
        response_int=response_int,
        response_float=response_float,
        response_datetime=response_datetime,
        reponse_string_nvarchar=reponse_string_nvarchar,
        obsdatetime=obs_datetime,
        sdcorder=sdc_order,
        sdcrepeatlevel=sdc_repeat_level,
        sdccomments=sdc_comments,
        personfk=person_fk,
        encounterfk=encounter_fk,
        practitionerfk=practitioner_fk,
    )

    try:
        session.add(new_entry)
        session.commit()
        session.refresh(new_entry)
        logger.info(f"Successfully added: {new_entry}")
        return new_entry
    except Exception:
        session.rollback()
        logger.error("Failed to add new SdcObsClass:", exc_info=True)
        raise
