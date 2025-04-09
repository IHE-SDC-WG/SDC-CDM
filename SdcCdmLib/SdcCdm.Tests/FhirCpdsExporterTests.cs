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
    public void SampleTest()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new("SdcCdm.Tests", true);
        sdcCdm.BuildSchema();
        string xmlPath = Path.Combine(
            AppContext.BaseDirectory,
            "TestData",
            "Adrenal.Bx.Res.129_3.007.011.REL_sdcFDF.xml"
        );
        XElement sdcSubmissionPackage = XElement.Load(xmlPath);
        XmlFormImporter.ProcessXmlForm(sdcCdm, sdcSubmissionPackage);

        // Act
        SdcCdm.TemplateRowDataImporter.ImportTemplateRowData(
            (ISdcCdm)sdcCdm,
            Path.Combine(AppContext.BaseDirectory, "TestData", "TemplateHistory(in).csv")
        );

        // Assert
        Assert.False(false, "Expected ExportFhirCpds to return false for the given template.");
    }

    [Fact]
    public void ExportCPDSForHIMSS()
    {
        // Arrange
        SdcCdmInSqlite.SdcCdmInSqlite sdcCdm = new(
            "/workspaces/SDC-CDM/notebooks/public/SdcCdm.Tests.db"
        );
        sdcCdm.BuildSchema();
        string xmlPath = Path.Combine(AppContext.BaseDirectory, "TestData", "freds_form.xml");
        string templatePath = Path.Combine(
            AppContext.BaseDirectory,
            "TestData",
            "STUB_RadOnc.619_1.000.000.AUTH_sdcFDF.xml"
        );
        XElement sdcSubmissionPackage = XElement.Load(xmlPath);
        XElement sdcTemplate = XElement.Load(templatePath);
        TemplateImporter.ImportTemplate(sdcCdm, sdcTemplate);
        XmlFormImporter.ProcessXmlForm(sdcCdm, sdcSubmissionPackage);
        string existingTemplate = "aa65c1b9-a43f-4c75-9cd6-285e774bd00c";

        // Act
        var bundle = FhirCPDSExporter.ExportFhirCpds(sdcCdm, existingTemplate);

        // Assert
        Assert.NotNull(bundle);

        // Use FhirJsonSerializer to convert the bundle to a JSON string
        var serializer = new FhirJsonSerializer(new SerializerSettings { Pretty = true });
        string bundleJson = serializer.SerializeToString(bundle);
        _output.WriteLine(bundleJson);
    }
}
