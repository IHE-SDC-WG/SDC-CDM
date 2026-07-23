using System.IO;
using System.Xml.Linq;
using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;
using Xunit.Abstractions;

namespace SdcCdm.Tests;

public class FhirCpdsExporterTests(ITestOutputHelper output)
{
    private readonly ITestOutputHelper _output = output;

    [Fact]
    public void ExportFhirCpds_GivenInvalidSdcCdm_ShouldReturnFalse()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new("SdcCdm.Tests", true);
        sdcCdm.BuildSchema();
        string invalidTemplateId = "invalid-template-id";

        // Act
        var bundle = FhirCPDSExporter.ExportFhirCpds(sdcCdm, invalidTemplateId);

        // Assert
        Assert.Null(bundle);
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
        var bundle = FhirCPDSExporter.ExportFhirCpds(sdcCdm, existingTemplate);

        // Assert
        Assert.NotNull(bundle);

        // Use FhirJsonSerializer to convert the bundle to a JSON string
        var serializer = new FhirJsonSerializer(new SerializerSettings { Pretty = true });
        string bundleJson = serializer.SerializeToString(bundle);
        _output.WriteLine(bundleJson);
    }

    [Fact]
    public void ImportTemplateRowData_GivenTrackedFixture_ShouldCreateTemplate()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new("SdcCdm.Tests", true);
        sdcCdm.BuildSchema();
        string csvPath = Path.Combine(
            AppContext.BaseDirectory,
            "TestData",
            "TemplateHistory-small.csv"
        );

        // Act
        SdcCdm.TemplateRowDataImporter.ImportTemplateRowData(sdcCdm, csvPath);

        // Assert
        Assert.NotNull(
            sdcCdm.FindTemplateSdcClass("Adrenal.Bx.Res.120_3.004.001.REL_sdcFDF")
        );
    }
}
