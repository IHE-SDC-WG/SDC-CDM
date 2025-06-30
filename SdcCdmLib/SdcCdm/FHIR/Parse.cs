using Hl7.Fhir.FhirPath;
using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;

public static class Parse
{
    private static T parseFromString<T>(string input, InputFileType fileType)
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

    public static IGrouping<string, string>[] getResourceTypesFromBundle(Bundle bundle)
    {
        var entries = bundle.Entry;
        var resourceTypes = entries.GroupBy(
            entry => entry.Resource.TypeName,
            entry => entry.Resource.Id
        );
        return resourceTypes.ToArray();
    }
}
