using System.Reflection;
using Hl7.Fhir.Model;
using Hl7.Fhir.Utility;

namespace SdcCdm.FHIR;

public static class Importers
{
    public static void ImportFhir(ISdcCdm sdcCdm, string fhirString)
    {
        Resource resource = Parse.parseJSONStringToResourceType<Resource>(fhirString);
        Type resourceType = resource.GetType();

        InvokeGenericResourceImporter(resourceType, resource);
    }

    private static void InvokeGenericResourceImporter(Type resourceType, Resource resource)
    {
        MethodInfo method = typeof(Importers).GetMethod(
            nameof(ImportResource),
            BindingFlags.NonPublic | BindingFlags.Static
        );
        MethodInfo generic = method.MakeGenericMethod(resourceType);
        generic.Invoke(null, [resource]);
    }

    private static void ImportResource<T>(Resource resource)
        where T : Resource
    {
        var typedResource = resource as T;
        if (typedResource != null)
        {
            switch (typedResource)
            {
                case Observation o:
                    ImportFhirObservation(o);
                    break;
                case Patient p:
                    ImportFhirPatient(p);
                    break;
                case Composition c:
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
                    ImportBundle(b);
                    return;
                default:
                    throw new NotImplementedException(
                        $" - Unhandled resourcetype {typeof(T).Name} with ID: {typedResource.Id}"
                    );
            }
        }
    }

    private static void ImportFhirObservation(Observation o)
    {
        System.Diagnostics.Debug.WriteLine($" - Handling {o.TypeName} with ID: {o.Id}");
        // o.TryDeriveResourceType

        // sdcCdm.WriteSdcObsClass


        return;
    }

    private static void ImportFhirPatient(Patient p)
    {
        System.Diagnostics.Debug.WriteLine($" - Handling {p.TypeName} with ID: {p.Id}");

        AdministrativeGender? gender = p.Gender;
        string birthdate = p.BirthDate;
        string? race;
        string? ethnicity;
        List<Address> address = p.Address;
        List<ResourceReference> generalPractitioner = p.GeneralPractitioner;
        ResourceReference managingOrganization = p.ManagingOrganization;
        // var personsourcevalue;
        // var gendersourcevalue;
        // var gendersourceconceptid;
        // var racesourcevalue;
        // var racesourceconceptid;
        // var ehtnicitysourcevalue;
        // var ehtnicitysourceconceptid;

        ISdcCdm.PersonDTO person = new ISdcCdm.PersonDTO
        {
            GenderConceptId = Converters.GenderFHIRToOMOP(gender),
            YearOfBirth = 5,
            MonthOfBirth = 6,
        };

        return;
    }

    private static void ImportBundle(Bundle bundle)
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
            MethodInfo method = typeof(Importers).GetMethod(
                nameof(ImportResourceGroup),
                BindingFlags.NonPublic | BindingFlags.Static
            );
            MethodInfo generic = method.MakeGenericMethod(resourceType);
            generic.Invoke(null, new object[] { group.Select(e => e.Resource) });
        }
    }

    private static void ImportResourceGroup<T>(IEnumerable<Resource> resources)
        where T : Resource
    {
        foreach (var resource in resources)
        {
            ImportResource<T>(resource);
        }
    }
}
