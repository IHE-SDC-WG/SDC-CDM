using Hl7.Fhir.Model;

namespace SdcCdm.FHIR;

public static class Importers
{
    public static void ImportFhir(ISdcCdm sdcCdm, string fhirString)
    {
        Resource resource = Parse.parseJSONStringToResourceType<Resource>(fhirString);
        Type resourceType = resource.GetType();

        Parse.InvokeGenericResourceParser(resourceType, resource);
    }
}
