using System.Diagnostics;

namespace SdcCdm.Hl7v2;

public class Hl7v2
{
    static string[] GetFields(string segment)
    {
        return segment.Split('|', StringSplitOptions.TrimEntries);
    }

    static string[] GetRepetitions(string field)
    {
        return field.Split('~', StringSplitOptions.TrimEntries);
    }

    static string[] GetComponents(string repetition)
    {
        return repetition.Split('^', StringSplitOptions.TrimEntries);
    }

    static string? GetField(string segment, int index)
    {
        Debug.Assert(index > 0);
        string[] fields = GetFields(segment);
        // If fields[0] == "MSH", use index-1, else index.
        // This is because MSH segments have a different indexing scheme.
        if (fields[0] == "MSH")
        {
            return (index - 1 >= 0 && index - 1 < fields.Length) ? fields[index - 1] : null;
        }
        else
        {
            return (index >= 0 && index < fields.Length) ? fields[index] : null;
        }
    }

    static string GetSegmentHeader(string segment)
    {
        return GetFields(segment)[0];
    }

    static string? GetComponent(string repetition, int index)
    {
        Debug.Assert(index > 0);
        var resolved_index = index - 1;
        string[] components = GetComponents(repetition);
        if (components[resolved_index] == "")
            return null;
        return components[resolved_index];
    }

    public static string? GetPatientSocialSecurityNumber(string pid_segment)
    {
        var PatientIdentifierList = GetField(pid_segment, 3);
        if (PatientIdentifierList == null)
            return null;

        var PatientIdentifiers = GetRepetitions(PatientIdentifierList);
        foreach (var PatientIdentifier in PatientIdentifiers)
        {
            var PatientIdentifierType = GetComponent(PatientIdentifier, 5);
            if (PatientIdentifierType == "SS")
            {
                return GetField(PatientIdentifier, 3);
            }
        }

        return null;
    }

    public static string? GetPatientMedicalRecordNumber(string pid_segment)
    {
        var PatientIdentifierList = GetField(pid_segment, 3);
        if (PatientIdentifierList == null)
            return null;

        var PatientIdentifiers = GetRepetitions(PatientIdentifierList);
        foreach (var PatientIdentifier in PatientIdentifiers)
        {
            var PatientIdentifierType = GetComponent(PatientIdentifier, 5);
            if (PatientIdentifierType == "MR")
            {
                return GetField(PatientIdentifier, 3);
            }
        }

        return null;
    }
}
