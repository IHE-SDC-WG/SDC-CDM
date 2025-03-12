namespace SdcCdm;

public static class NAACCRVolVImporter
{
    public static void ImportNaaccrVolV(
        ISdcCdm sdcCdm,
        string hl7_message,
        bool exit_on_error = true
    )
    {
        void print_extracted_var(string str) => Console.WriteLine($"! {str}");

        void hl7_error(string message)
        {
            Console.WriteLine($"Error: {message}");
            if (exit_on_error)
            {
                throw new Exception(message);
            }
        }

        string get_field(string[] fields, int index)
        {
            // If fields[0] == "MSH", use index-1, else index.
            // This is because MSH segments have a different indexing scheme.
            if (fields[0] == "MSH")
            {
                return (index - 1 >= 0 && index - 1 < fields.Length) ? fields[index - 1] : "";
            }
            else
            {
                return (index >= 0 && index < fields.Length) ? fields[index] : "";
            }
        }

        string? get_first_segment(IEnumerable<string> segments, string segment_name)
        {
            foreach (var segment in segments)
            {
                var fields = segment.Split('|');
                if (fields[0] == segment_name)
                {
                    return segment;
                }
            }
            return null;
        }

        List<string> get_all_segments(IEnumerable<string> segments, string segment_name)
        {
            var found_segments = new List<string>();
            foreach (var segment in segments)
            {
                var fields = segment.Split('|');
                if (fields[0] == segment_name)
                {
                    found_segments.Add(segment);
                }
            }
            return found_segments;
        }

        // Split the HL7 message into lines
        var lines = hl7_message.Split(new[] { '\n' }, StringSplitOptions.RemoveEmptyEntries);

        // MSH segment
        var msh_segment = get_first_segment(lines, "MSH");
        if (msh_segment == null)
        {
            hl7_error("No MSH segment found");
            return;
        }
        var msh_segment_fields = msh_segment.Split('|');
        var message_type = get_field(msh_segment_fields, 9);
        if (message_type != "ORU^R01^ORU_R01")
        {
            hl7_error($"Unknown message type: {message_type}");
        }
        Console.WriteLine($"Message type: {message_type}");
        var message_profile = get_field(msh_segment_fields, 21).Trim();
        if (message_profile != "VOL_V_40_ORU_R01^NAACCR_CP")
        {
            hl7_error($"Unknown message profile: {message_profile}");
        }
        Console.WriteLine($"Message profile: {message_profile}");

        // OBR segment
        var obr_segment = get_first_segment(lines, "OBR");
        if (obr_segment == null)
        {
            hl7_error("No OBR segment found");
            return;
        }
        var obr_segment_fields = obr_segment.Split('|');
        var report_type = get_field(obr_segment_fields, 4);
        if (report_type != "60568-3^SYNOPTIC REPORT^LN")
        {
            hl7_error($"Unknown report type: {report_type}");
        }
        Console.WriteLine($"Report type: {report_type}");

        // OBX segments
        var obx_segments = get_all_segments(lines, "OBX");
        if (obx_segments.Count < 3)
        {
            hl7_error("Not enough OBX segments found");
            return;
        }

        // First OBX
        var first_obx = obx_segments[0];
        var first_obx_fields = first_obx.Split('|');
        var observation_identifier = get_field(first_obx_fields, 3);
        if (observation_identifier != "60573-3^Report template source^LN")
        {
            hl7_error($"Unexpected observation identifier: {observation_identifier}");
        }
        Console.WriteLine($"First OBX identifier: {observation_identifier}");
        var document_source_style = get_field(first_obx_fields, 5);
        if (document_source_style != "CAP eCC")
        {
            hl7_error($"Unexpected document source style: {document_source_style}");
        }
        Console.WriteLine($"Document source style: {document_source_style}");

        // Second OBX
        var second_obx = obx_segments[1];
        var second_obx_fields = second_obx.Split('|');
        observation_identifier = get_field(second_obx_fields, 3);
        if (observation_identifier != "60572-5^Report template ID^LN")
        {
            hl7_error($"Unexpected observation identifier: {observation_identifier}");
        }
        var template_id = get_field(second_obx_fields, 5);
        var template_id_parts = template_id.Split('^');
        // Assuming template_id always has at least two parts
        var form_title = template_id_parts.Length > 1 ? template_id_parts[1] : "UNKNOWN_FORM_TITLE";
        Console.WriteLine($"Template ID: {template_id}");
        print_extracted_var($"Form Title: {form_title}");

        // Third OBX
        var third_obx = obx_segments[2];
        var third_obx_fields = third_obx.Split('|');
        observation_identifier = get_field(third_obx_fields, 3);
        if (observation_identifier != "60574-1^Report template version ID^LN")
        {
            hl7_error($"Unexpected observation identifier: {observation_identifier}");
        }
        var version_id = get_field(third_obx_fields, 5);
        print_extracted_var($"Version ID: {version_id}");

        // Insert into DB (template_sdc)
        var new_template_sdc_pk = sdcCdm.WriteTemplateSdcClass(
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            version_id ?? "UNKNOWN",
            "UNKNOWN",
            form_title,
            "UNKNOWN",
            "FD"
        );

        // Insert into DB (template_instance_class)
        var new_template_instance_class_pk = sdcCdm.WriteTemplateInstanceClass(new_template_sdc_pk);
        var new_template_instance_class_fk = new_template_instance_class_pk;

        // Build map of observations
        var obs_sub_id_map = new Dictionary<string, Dictionary<string, string?>>();

        var rest_of_obx_segments = obx_segments.Skip(3);
        foreach (var obx_segment in rest_of_obx_segments)
        {
            var obx_segment_fields = obx_segment.Split('|');
            var observation_data_type = get_field(obx_segment_fields, 2);
            observation_identifier = get_field(obx_segment_fields, 3);
            var obs_id_parts = observation_identifier.Split('^');
            var q_id = obs_id_parts.Length > 0 ? obs_id_parts[0] : null;
            var q_text = obs_id_parts.Length > 1 ? obs_id_parts[1] : null;
            Console.WriteLine($"Q ID: {q_id}");
            Console.WriteLine($"Q Text: {q_text}");

            var observation_sub_id = get_field(obx_segment_fields, 4);
            if (!string.IsNullOrEmpty(observation_sub_id))
            {
                var observation_value = get_field(obx_segment_fields, 5);
                var obs_val_parts = observation_value.Split('^');
                string? li_text = null;
                string? li_id = null;
                if (obs_val_parts.Length > 1)
                {
                    li_text = obs_val_parts[0];
                    li_id = obs_val_parts[1];
                }
                var observation_units = get_field(obx_segment_fields, 6);

                if (obs_sub_id_map.ContainsKey(observation_sub_id))
                {
                    Console.WriteLine(
                        $"@@@@@ Observation sub ID already exists: {observation_sub_id}"
                    );
                }
                else
                {
                    obs_sub_id_map[observation_sub_id] = new Dictionary<string, string?>
                    {
                        { "q_id", q_id },
                        { "q_text", q_text },
                        { "value", observation_value },
                        { "units", observation_units },
                    };
                }
                if (!string.IsNullOrEmpty(observation_units))
                {
                    Console.WriteLine($"Observation units: {observation_units}");
                }
                Console.WriteLine($"@@@ Observation sub ID: {observation_sub_id}");
            }
            else
            {
                var observation_value = get_field(obx_segment_fields, 5);
                string? response = null;
                string? li_text = null;
                string? li_id = null;
                if (observation_data_type == "ST")
                {
                    response =
                        observation_value.Length > 99 ? observation_value[..99] : observation_value;
                }
                else
                {
                    var obs_val_parts = observation_value.Split('^');
                    if (obs_val_parts.Length > 1)
                    {
                        li_text = obs_val_parts[0];
                        li_id = obs_val_parts[1];
                    }
                }

                sdcCdm.WriteSdcObsClass(
                    new_template_instance_class_fk,
                    parent_observation_id: null,
                    "UNKNOWN",
                    "UNKNOWN",
                    q_text,
                    "UNKNOWN",
                    q_id,
                    li_text,
                    li_id,
                    "UNKNOWN",
                    "UNKNOWN",
                    response
                );
            }
        }
    }
}
