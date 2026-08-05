using Hl7.Fhir.Model;
using static SdcCdm.ISdcCdm;

namespace SdcCdm.FHIR;

public static class Converters
{
    public static long GenderFHIRToOMOP(AdministrativeGender? gender)
    {
        switch (gender)
        {
            case AdministrativeGender.Male:
                return 0;
            case AdministrativeGender.Female:
                return 1;
            case AdministrativeGender.Other:
                return 2;
            case AdministrativeGender.Unknown:
            default:
                return 3;
        }
    }
}
