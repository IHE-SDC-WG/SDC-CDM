using System.Reflection;
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

    public static IGrouping<string, Base?[]>[] getResourceTypesFromBundle(Bundle bundle)
    {
        var entries = bundle.Entry;
        var resourceTypes = entries.GroupBy(
            entry => entry.Resource.TypeName,
            entry => bundle.Select($"Bundle.entry.ofType({entry.Resource.TypeName})").ToArray()
        );
        return [.. resourceTypes];
    }

    public static List<string> ProcessBundle(Bundle bundle)
    {
        // Group entries by their resource type
        List<string> outputArray = new List<string>();
        var groupedResources = bundle
            .Entry.Where(e => e.Resource != null)
            .GroupBy(e => e.Resource.GetType());

        foreach (var group in groupedResources)
        {
            Type resourceType = group.Key;
            outputArray.Add(
                $"Processing {group.Count()} resource(s) of type: {resourceType.Name}"
            );

            // Dynamically invoke generic processing method
            MethodInfo method = typeof(Parse).GetMethod(
                nameof(ProcessGroup),
                BindingFlags.NonPublic | BindingFlags.Static
            );
            MethodInfo generic = method.MakeGenericMethod(resourceType);
            generic.Invoke(null, new object[] { group.Select(e => e.Resource), outputArray });
        }
        return outputArray;
    }

    private static List<string> ProcessGroup<T>(IEnumerable<Resource> resources, List<string> outputArray)
        where T : Resource
    {
        foreach (var resource in resources)
        {
            var typedResource = resource as T;
            if (typedResource != null)
            {
                // Custom logic based on type T
                outputArray.Add($" - Handling {typeof(T).Name} with ID: {typedResource.Id}");
            }
        }
        return outputArray;
    }
}
