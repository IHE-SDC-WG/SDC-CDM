using System.Diagnostics;

namespace SdcCdm;

public static class NAACCRVolVImporter
{
    private static void ErrorCallback(string message)
    {
        Debug.Assert(message != null, "No message provided for error callback");
        throw new Exception(message);
    }

    public static void ImportNaaccrVolV(ISdcCdm sdcCdm, string hl7_message)
    {
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
        var lines = hl7_message.Split(new char[] { '\n' }, StringSplitOptions.RemoveEmptyEntries);

        // MSH segment
        var msh_segment = get_first_segment(lines, "MSH");
        if (msh_segment == null)
        {
            ErrorCallback("No MSH segment found");
            return;
        }
        var msh_segment_fields = msh_segment.Split('|');
        var message_type = get_field(msh_segment_fields, 9);
        if (message_type != "ORU^R01^ORU_R01")
        {
            ErrorCallback($"Unknown message type: {message_type}");
        }
        Debug.Print($"Message type: {message_type}");
        var message_profile = get_field(msh_segment_fields, 21).Trim();
        // if (message_profile != "VOL_V_40_ORU_R01^NAACCR_CP")
        // {
        //     ErrorCallback($"Unknown message profile: {message_profile}");
        // }
        // Debug.Print($"Message profile: {message_profile}");

        // Get Person data from the first PID segment
        var pid_segment = get_first_segment(lines, "PID");
        if (pid_segment == null)
        {
            ErrorCallback("No PID segment found");
            return;
        }
        var pid_segment_fields = pid_segment.Split('|');

        // OBR segment
        var obr_segment = get_first_segment(lines, "OBR");
        if (obr_segment == null)
        {
            ErrorCallback("No OBR segment found");
            return;
        }
        var obr_segment_fields = obr_segment.Split('|');
        var report_type = get_field(obr_segment_fields, 4);
        var valid_report_types = new[]
        {
            "60568-3^SYNOPTIC REPORT^LN",
            "35265-8^PATH REPORT ADDENDUM^LN",
        };
        if (!valid_report_types.Contains(report_type))
        {
            ErrorCallback($"Unknown report type: {report_type}");
        }

        // Extract person data
        var person_source_value = get_field(pid_segment_fields, 3);
        var person_name = get_field(pid_segment_fields, 5);
        var birth_date = get_field(pid_segment_fields, 7);
        var gender = get_field(pid_segment_fields, 8);

        // Parse birth date
        DateTime? birth_datetime = null;
        if (!string.IsNullOrEmpty(birth_date) && birth_date.Length >= 8)
        {
            try
            {
                var year = int.Parse(birth_date.Substring(0, 4));
                var month = int.Parse(birth_date.Substring(4, 2));
                var day = int.Parse(birth_date.Substring(6, 2));
                birth_datetime = new DateTime(year, month, day);
            }
            catch (Exception ex)
            {
                Debug.Print($"Error parsing birth date: {ex.Message}");
            }
        }

        // Create or find person
        var existingPersonId = sdcCdm.FindPersonByIdentifier(person_source_value);
        long? personId = null;

        if (existingPersonId == null)
        {
            // Create new person record
            var personDto = new ISdcCdm.PersonDTO
            {
                PersonSourceValue = person_source_value,
                YearOfBirth = birth_datetime?.Year ?? 1900,
                MonthOfBirth = birth_datetime?.Month,
                DayOfBirth = birth_datetime?.Day,
                BirthDatetime = birth_datetime,
                GenderConceptId =
                    gender == "M" ? 8507L
                    : gender == "F" ? 8532L
                    : 0L, // Male/Female/Unknown
                RaceConceptId = 0L, // Unknown
                EthnicityConceptId = 0L, // Unknown
            };
            var newPerson = sdcCdm.WritePerson(personDto);
            personId = newPerson?.PersonId;
        }
        else
        {
            personId = existingPersonId;
        }

        // Extract all OBX segments and look for ECP-specific ones
        var obx_segments = get_all_segments(lines, "OBX");
        if (obx_segments.Count < 6)
        {
            ErrorCallback("Not enough OBX segments for template metadata (need at least 6)");
            return;
        }

        Console.WriteLine($"Found {obx_segments.Count} total OBX segments");

        // Find ECP-specific OBX segments by looking for the Report Template Source
        var template_source = "";
        var template_id = "";
        var template_version = "";

        // Look for OBX segments with Report Template Source (60573-3)
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("60573-3")
                && (
                    obx_observation_id.Contains("Report Template Source")
                    || obx_observation_id.Contains("Report template source")
                )
            )
            {
                template_source = get_field(obx_fields, 5);
                Console.WriteLine($"Found Report Template Source at OBX[{i}]: {template_source}");
                break;
            }
        }

        // Look for OBX segments with Report Template ID (60572-5)
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("60572-5")
                && (
                    obx_observation_id.Contains("Report Template ID")
                    || obx_observation_id.Contains("Report template ID")
                )
            )
            {
                template_id = get_field(obx_fields, 5);
                Console.WriteLine($"Found Report Template ID at OBX[{i}]: {template_id}");
                break;
            }
        }

        // Look for OBX segments with Report Template Version ID (60574-1)
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("60574-1")
                && (
                    obx_observation_id.Contains("Report Template Version ID")
                    || obx_observation_id.Contains("Report template version ID")
                )
            )
            {
                template_version = get_field(obx_fields, 5);
                Console.WriteLine(
                    $"Found Report Template Version ID at OBX[{i}]: {template_version}"
                );
                break;
            }
        }

        // Parse additional metadata by looking for specific OBX segments
        var tumor_site = "";
        var procedure_type = "";
        var specimen_laterality = "";

        // Look for Tumor Site (usually contains "Tumor Site" in the observation ID)
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("Tumor Site")
                || obx_observation_id.Contains("22371.100004300")
                || obx_observation_id.Contains("2118.1000043")
            )
            {
                tumor_site = get_field(obx_fields, 5);
                Console.WriteLine($"Found Tumor Site at OBX[{i}]: {tumor_site}");
                break;
            }
        }

        // Look for Procedure (usually contains "Procedure" in the observation ID)
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("Procedure")
                || obx_observation_id.Contains("51121.100004300")
                || obx_observation_id.Contains("820603.1000043")
            )
            {
                procedure_type = get_field(obx_fields, 5);
                Console.WriteLine($"Found Procedure at OBX[{i}]: {procedure_type}");
                break;
            }
        }

        // Look for Specimen Laterality or Tumor Focality
        for (int i = 0; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_observation_id = get_field(obx_fields, 3);

            if (
                obx_observation_id.Contains("Tumor Focality")
                || obx_observation_id.Contains("8722.100004300")
                || obx_observation_id.Contains("Specimen Laterality")
                || obx_observation_id.Contains("52756.1000043")
            )
            {
                specimen_laterality = get_field(obx_fields, 5);
                Console.WriteLine($"Found Tumor Focality at OBX[{i}]: {specimen_laterality}");
                break;
            }
        }

        // Generate template instance GUID
        var template_instance_guid = Guid.NewGuid().ToString();

        // Create SDC template instance for ECP data
        var template_instance_id = sdcCdm.WriteSdcTemplateInstanceEcp(
            template_name: template_id,
            template_version: template_version,
            template_instance_guid: template_instance_guid,
            person_id: personId,
            report_template_source: template_source,
            report_template_id: template_id,
            report_template_version_id: template_version,
            tumor_site: tumor_site,
            procedure_type: procedure_type,
            specimen_laterality: specimen_laterality
        );

        // Process OBX segments for ECP data (starting from 4th OBX)
        for (int i = 3; i < obx_segments.Count; i++)
        {
            var obx_fields = obx_segments[i].Split('|');
            var obx_value_type = get_field(obx_fields, 2);
            var obx_observation_id = get_field(obx_fields, 3);
            var obx4_value_raw = get_field(obx_fields, 4);
            var obx4_value = string.IsNullOrWhiteSpace(obx4_value_raw) ? "N/A" : obx4_value_raw;
            var obx_value = get_field(obx_fields, 5);
            var obx_units = get_field(obx_fields, 6);

            // Debug logging for units extraction
            if (!string.IsNullOrEmpty(obx_units))
            {
                Console.WriteLine(
                    $"OBX[{i}] - Observation: {obx_observation_id} - Units: '{obx_units}'"
                );
            }

            // Skip narrative content (focus on structured ECP data)
            if (obx_value_type == "ST" && obx_value.Length > 200)
            {
                continue; // Skip long narrative text
            }

            // Parse question identifier from observation ID
            var question_parts = obx_observation_id.Split('^');
            var question_identifier =
                question_parts.Length > 0 ? question_parts[0] : obx_observation_id;
            var question_text = question_parts.Length > 1 ? question_parts[1] : "";

            // Determine response type and value
            string response_type = "text";
            string response_value = obx_value;
            double? numeric_value = null;

            switch (obx_value_type)
            {
                case "NM":
                    response_type = "numeric";
                    if (double.TryParse(obx_value, out double num_val))
                    {
                        numeric_value = num_val;
                    }
                    break;
                case "CWE":
                    response_type = "list_selection";
                    break;
                case "ST":
                    response_type = "text";
                    break;
                default:
                    response_type = "text";
                    break;
            }

            // Create measurement record with SDC-specific data
            var measurement_id = sdcCdm.WriteMeasurementWithSdcData(
                person_id: personId ?? 0,
                measurement_concept_id: 0, // Will be mapped to appropriate OMOP concept
                measurement_date: DateTime.Now.Date,
                measurement_type_concept_id: 32856, // Laboratory measurement
                value_as_number: numeric_value,
                value_as_string: response_value,
                unit_source_value: obx_units,
                measurement_source_value: obx_observation_id,
                // SDC-specific fields
                sdc_template_instance_guid: template_instance_guid,
                sdc_question_identifier: question_identifier,
                sdc_response_value: response_value,
                sdc_response_type: response_type,
                sdc_template_version: template_version,
                sdc_question_text: question_text,
                sdc_units: obx_units,
                sdc_datatype: obx_value_type,
                sdc_order: i - 2, // OBX sequence number
                obx4: obx4_value
            );
        }

        Debug.Print(
            $"Successfully imported NAACCR V2 message with {obx_segments.Count - 3} ECP data points"
        );
    }
}
