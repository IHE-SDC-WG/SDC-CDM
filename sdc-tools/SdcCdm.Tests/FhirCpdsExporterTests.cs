using System.IO;
using System.Xml.Linq;
using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;
using Xunit.Abstractions;

namespace SdcCdm.Tests;

public class FhirCpdsExporterTests
{
    private readonly ITestOutputHelper _output;

    public FhirCpdsExporterTests(ITestOutputHelper output)
    {
        _output = output;
    }

    [Fact]
    public void ExportFhirCpds_GivenInvalidSdcCdm_ShouldReturnFalse()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new("SdcCdm.Tests", true);
        sdcCdm.BuildSchema();
        string invalidTemplateId = "invalid-template-id";

        // Act
        bool result = FhirCPDSExporter.ExportFhirCpds(sdcCdm, out _, invalidTemplateId);

        // Assert
        Assert.False(result, "Expected ExportFhirCpds to return false for the given template.");
    }

    [Fact]
    public void ExportFhirCpds_GivenValidSdcCdm_ShouldReturnTrue()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new("SdcCdm.Tests", true);
        sdcCdm.BuildSchema();
        string xmlPath = Path.Combine(AppContext.BaseDirectory, "TestData", "ADRENAL_GLAND.xml");
        XElement sdcSubmissionPackage = XElement.Load(xmlPath);
        XmlFormImporter.ProcessXmlForm(sdcCdm, sdcSubmissionPackage);
        string existingTemplate = "5b64392d-680e-4a96-94ca-3da4acf6bd27";

        // Act
        bool result = FhirCPDSExporter.ExportFhirCpds(sdcCdm, out Bundle? bundle, existingTemplate);

        // Use FhirJsonSerializer to convert the bundle to a JSON string
        if (bundle != null)
        {
            var serializer = new FhirJsonSerializer(new SerializerSettings { Pretty = true });
            string bundleJson = serializer.SerializeToString(bundle);
            _output.WriteLine(bundleJson);
        }
        else
        {
            _output.WriteLine("Bundle is null");
        }

        // Assert
        Assert.True(result, "Expected ExportFhirCpds to return true for the given template.");
    }
}
