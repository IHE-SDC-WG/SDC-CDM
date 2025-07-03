using System.Reflection;
using Hl7.Fhir.FhirPath;
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

    // public static IGrouping<string, Base?[]>[] getResourceTypesFromBundle(Bundle bundle)
    // {
    //     var entries = bundle.Entry;
    //     var resourceTypes = entries.GroupBy(
    //         entry => entry.Resource.TypeName,
    //         entry => bundle.Select($"Bundle.entry.ofType({entry.Resource.TypeName})").ToArray()
    //     );
    //     return [.. resourceTypes];
    // }

    public static void ProcessBundle(Bundle bundle)
    {
        System.Diagnostics.Debug.WriteLine($"Handling {bundle.TypeName} with ID: {bundle.Id}");

        // Group entries by their resource type
        var groupedResources = bundle
            .Entry.Where(e => e.Resource != null)
            .GroupBy(e => e.Resource.GetType());

        foreach (var group in groupedResources)
        {
            Type resourceType = group.Key;
            System.Diagnostics.Debug.WriteLine(
                $"Processing {group.Count()} resource(s) of type: {resourceType.Name}"
            );

            // Dynamically invoke generic processing method
            MethodInfo method = typeof(Parse).GetMethod(
                nameof(ProcessResourceGroup),
                BindingFlags.NonPublic | BindingFlags.Static
            );
            MethodInfo generic = method.MakeGenericMethod(resourceType);
            generic.Invoke(null, new object[] { group.Select(e => e.Resource) });
        }
    }

    public static void InvokeGenericResourceParser(Type resourceType, Resource resource)
    {
        MethodInfo method = typeof(Parse).GetMethod(
            nameof(ProcessResource),
            BindingFlags.NonPublic | BindingFlags.Static
        );
        MethodInfo generic = method.MakeGenericMethod(resourceType);
        generic.Invoke(null, [resource]);
    }

    private static void ProcessResourceGroup<T>(IEnumerable<Resource> resources)
        where T : Resource
    {
        foreach (var resource in resources)
        {
            ProcessResource<T>(resource);
        }
    }

    private static void ProcessResource<T>(Resource resource)
        where T : Resource
    {
        var typedResource = resource as T;
        if (typedResource != null)
        {
            switch (typedResource)
            {
                case Observation o:
                    ProcessObservation(o);
                    break;
                case Composition c:
                case Patient p:
                case Practitioner pr:
                case Organization or:
                case Condition co:
                case MedicationStatement ms:
                case Medication m:
                case AllergyIntolerance a:
                    System.Diagnostics.Debug.WriteLine(
                        $" - Unhandled resourcetype {typeof(T).Name} with ID: {typedResource.Id}"
                    );
                    break;
                case Bundle b:
                    ProcessBundle(b);
                    return;
                default:
                    throw new NotImplementedException(
                        $" - Unhandled resourcetype {typeof(T).Name} with ID: {typedResource.Id}"
                    );
            }
        }
    }

    private static void ProcessObservation(Observation o)
    {
        System.Diagnostics.Debug.WriteLine($" - Handling {o.TypeName} with ID: {o.Id}");
        // o.TryDeriveResourceType

        // sdcCdm.WriteSdcObsClass


        return;
    }
}
