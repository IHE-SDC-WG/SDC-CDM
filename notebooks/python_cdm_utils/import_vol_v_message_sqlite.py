#!/usr/bin/env python3

import logging
from python_cdm_utils.crud_sqlite import (
    create_template_sdc_class,
    create_template_instance_class,
    create_sdc_obs_class,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def import_data_from_hl7(cursor, hl7_message, exit_on_error=True):
    def print_extracted_var(string):
        print(f"! {string}")

    def hl7_error(message):
        print(f"Error: {message}")
        if exit_on_error:
            exit()

    def get_field(fields, index):
        if fields[0] == "MSH":
            return fields[index - 1]
        else:
            return fields[index]

    def get_first_segment(segments, segment_name):
        for segment in segments:
            fields = segment.split("|")
            if fields[0] == segment_name:
                return segment

    def get_all_segments(segments, segment_name):
        found_segments = []
        for segment in segments:
            fields = segment.split("|")
            if fields[0] == segment_name:
                found_segments.append(segment)
        return found_segments

    # Split string into lines
    lines = hl7_message.split("\n")

    ## MSH segment
    msh_segment = get_first_segment(lines, "MSH")
    msh_segment_fields = msh_segment.split("|")
    message_type = get_field(msh_segment_fields, 9)
    if message_type != "ORU^R01^ORU_R01":
        hl7_error(f"Unknown message type: {message_type}")
    print(f"Message type: {message_type}")
    message_profile = get_field(msh_segment_fields, 21)
    if message_profile != "VOL_V_40_ORU_R01^NAACCR_CP":
        hl7_error(f"Unknown message profile: {message_profile}")
    print(f"Message profile: {message_profile}")

    ## OBR segment
    obr_segment = get_first_segment(lines, "OBR")
    obr_segment_fields = obr_segment.split("|")
    report_type = get_field(obr_segment_fields, 4)
    if report_type != "60568-3^SYNOPTIC REPORT^LN":
        hl7_error(f"Unknown report type: {report_type}")
    print(f"Report type: {report_type}")

    ## OBX segments
    obx_segments = get_all_segments(lines, "OBX")

    # Process first three segments
    first_obx = obx_segments[0]
    first_obx_fields = first_obx.split("|")
    observation_identifier = get_field(first_obx_fields, 3)
    if observation_identifier != "60573-3^Report template source^LN":
        hl7_error(f"Unexpected observation identifier: {observation_identifier}")
    print(f"First OBX identifier: {observation_identifier}")
    document_source_style = get_field(first_obx_fields, 5)
    if document_source_style != "CAP eCC":
        hl7_error(f"Unexpected document source style: {document_source_style}")
    print(f"Document source style: {document_source_style}")

    second_obx = obx_segments[1]
    second_obx_fields = second_obx.split("|")
    observation_identifier = get_field(second_obx_fields, 3)
    if observation_identifier != "60572-5^Report template ID^LN":
        hl7_error(f"Unexpected observation identifier: {observation_identifier}")
    template_id = get_field(second_obx_fields, 5)
    form_title = template_id.split("^")[1]
    print(f"Template ID: {template_id}")
    print_extracted_var(f"Form Title: {form_title}")

    third_obx = obx_segments[2]
    third_obx_fields = third_obx.split("|")
    observation_identifier = get_field(third_obx_fields, 3)
    if observation_identifier != "60574-1^Report template version ID^LN":
        hl7_error(f"Unexpected observation identifier: {observation_identifier}")
    version_id = get_field(third_obx_fields, 5)
    print_extracted_var(f"Version ID: {version_id}")

    new_template_sdc = create_template_sdc_class(
        cursor=cursor,
        version=version_id,
        formtitle=form_title,
    )

    new_template_instance_class = create_template_instance_class(
        cursor=cursor,
        templatesdc_fk=new_template_sdc["pk"],
        # TODO: Fill in TemplateInstanceClass fields
    )
    new_template_instance_class_fk = new_template_instance_class["pk"]

    # Build map of observations
    obs_sub_id_map = {}

    rest_of_obx_segments = obx_segments[3:]
    for obx_segment in rest_of_obx_segments:
        obx_segment_fields = obx_segment.split("|")
        observation_data_type = get_field(obx_segment_fields, 2)
        observation_identifier = get_field(obx_segment_fields, 3)
        obs_id_parts = observation_identifier.split("^")
        q_id = obs_id_parts[0]
        q_text = obs_id_parts[1]
        print(f"Q ID: {q_id}")
        print(f"Q Text: {q_text}")

        observation_sub_id = get_field(obx_segment_fields, 4)
        if observation_sub_id != "":
            observation_value = get_field(obx_segment_fields, 5)
            obs_val_parts = observation_value.split("^")
            if len(obs_val_parts) > 1:
                li_text = obs_val_parts[0]
                li_id = obs_val_parts[1]
            observation_units = get_field(obx_segment_fields, 6)
            if observation_units != "":
                print(f"Observation units: {observation_units}")
            print(f"@@@ Observation sub ID: {observation_sub_id}")
            if observation_sub_id in obs_sub_id_map:
                print(f"@@@@@ Observation sub ID already exists: {observation_sub_id}")
            else:
                obs_sub_id_map[observation_sub_id] = {
                    "q_id": q_id,
                    "q_text": q_text,
                    "value": observation_value,
                    "units": observation_units,
                }
        else:
            observation_value = get_field(obx_segment_fields, 5)
            response = None
            if observation_data_type == "ST":
                response = observation_value[0:99]
            else:
                obs_val_parts = observation_value.split("^")
                li_text = obs_val_parts[0]
                li_id = obs_val_parts[1]
            create_sdc_obs_class(
                cursor=cursor,
                template_instance_class_fk=new_template_instance_class_fk,
                q_text=q_text,
                q_id=q_id,
                li_text=li_text,
                li_id=li_id,
                response=response,
            )

    # # Iterate through observation map
    # for observation_sub_id, observation_data in obs_sub_id_map.items():
    #     create_sdc_obs_class(
    #         session=session,
    #         template_instance_class_fk=new_template_instance_class_fk,
    #         q_text=observation_data["q_text"],
    #         q_id=observation_data["q_id"],
    #         li_text=observation_data["li_text"],
    #         li_id=observation_data["li_id"],
    #         response=observation_data["response"],
    #         units=observation_data["units"],
    #         units_system=observation_data["units_system"],
    #         datatype=None,
    #         response_int=None,
    #         response_float=None,
    #         response_datetime=None,
    #         # reponse_string_nvarchar=response_string_val,
    #         # sdc_order=response.get("order"),
    #     )
