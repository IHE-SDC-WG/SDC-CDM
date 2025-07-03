using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;

public static class Parse
{
    public static T ParseFromString<T>(string input, InputFileType fileType)
        where T : Resource
    {
        switch (fileType)
        {
            case InputFileType.XML:
                throw new NotImplementedException("XML File Types not yet implemented");
            case InputFileType.JSON:
            default:
                return parseJSONStringToResourceType<T>(input);
        }
    }

    public static T parseJSONStringToResourceType<T>(string JSONString)
        where T : Resource
    {
        var parser = new FhirJsonParser();
        var parsedResource = parser.Parse<T>(JSONString);
        return parsedResource;
    }
}
