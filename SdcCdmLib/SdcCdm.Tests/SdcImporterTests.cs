using System;
using System.Collections.Generic;
using System.IO;
using System.Xml.Linq;
using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;
using SdcCdm;
using SdcCdm.FHIR;
using SdcCdmInSqlite;
using Xunit;
using Xunit.Abstractions;

namespace SdcCdm.Tests
{
    public class SdcImporterTests
    {
        private readonly ITestOutputHelper _output;

        public SdcImporterTests(ITestOutputHelper output)
        {
            _output = output;
        }

        [Fact]
        public void ProcessXmlForm_ExecutesWithoutError()
        {
            // Arrange
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string xmlPath = Path.Combine(AppContext.BaseDirectory, "TestData", "SDC_Form.xml");
            XElement sdcSubmissionPackage = XElement.Load(xmlPath);

            // Act
            XmlFormImporter.ProcessXmlForm(sdcCdm, sdcSubmissionPackage);

            // Assert
            Assert.True(true, "Expected ProcessXmlForm to execute without errors.");
        }

        [Fact]
        public void ImportNaaccrVolV_ExecutesWithoutError()
        {
            // Arrange
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string hl7Path = Path.Combine(
                AppContext.BaseDirectory,
                "TestData",
                "HL7",
                "obx-Adrenal.hl7"
            );
            string hl7Message = File.ReadAllText(hl7Path);

            // Act
            NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);

            // Assert
            long? reportId = sdcCdm.FindFirstSdcReportByAccession("15SL-2");
            Assert.NotNull(reportId);
            var report = sdcCdm.GetSdcReportRecord(reportId.Value);
            Assert.NotNull(report);
            Assert.Equal("15SL-2", report.ReportAccession);
            Assert.Equal("129.1000043^ADRENAL GLAND^CAPECC", report.ReportTemplateId);
            Assert.Equal("CAP eCC", report.ReportTemplateSource);
            Assert.Equal("3.007.011.1000043", report.ReportTemplateVersionId);
        }

        [Fact]
        public void ImportAllHL7Files_ExecutesWithoutError()
        {
            // Arrange
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string hl7Directory = Path.Combine(AppContext.BaseDirectory, "TestData", "HL7");

            Assert.True(Directory.Exists(hl7Directory), $"Directory not found: {hl7Directory}");

            // Find all .hl7 files recursively
            var hl7Files = GetAllHL7Files(hl7Directory);
            _output.WriteLine($"Found {hl7Files.Count} HL7 files to process");
            Assert.NotEmpty(hl7Files);

            // Process each file
            int processedCount = 0;
            List<string> failedFiles = [];

            foreach (var hl7File in hl7Files)
            {
                try
                {
                    _output.WriteLine($"Processing file: {Path.GetFileName(hl7File)}");
                    string hl7Message = File.ReadAllText(hl7File);
                    NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);
                    processedCount++;
                }
                catch (Exception ex)
                {
                    _output.WriteLine($"Error processing {hl7File}: {ex.Message}");
                    failedFiles.Add(hl7File);
                }
            }

            // Assert
            _output.WriteLine(
                $"Successfully processed {processedCount} of {hl7Files.Count} HL7 files"
            );
            if (failedFiles.Count > 0)
            {
                _output.WriteLine("Failed files:");
                foreach (var file in failedFiles)
                {
                    _output.WriteLine($"  - {file}");
                }
            }

            Assert.Empty(failedFiles);
            Assert.Equal(2, hl7Files.Count);
            Assert.Equal(hl7Files.Count, processedCount);
            Assert.NotNull(sdcCdm.FindFirstSdcReportByAccession("15SL-2"));
            Assert.NotNull(sdcCdm.FindFirstSdcReportByAccession("24-11-000312"));
        }

        private static List<string> GetAllHL7Files(string directory)
        {
            var files = new List<string>();

            // Add files in current directory
            files.AddRange(Directory.GetFiles(directory, "*.hl7"));

            // Recursively add files from subdirectories
            foreach (var subDir in Directory.GetDirectories(directory))
            {
                files.AddRange(GetAllHL7Files(subDir));
            }

            return files;
        }

        [Fact]
        public void ImportFHIRIPSJSONToResource_ExecutesWithoutError()
        {
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string ipsFilePath = Path.Combine(
                AppContext.BaseDirectory,
                "TestData",
                "Bundle-IPS-examples-Bundle-01.json"
            );
            string ipsJsonString = File.ReadAllText(ipsFilePath);
            Importers.ImportFhir(sdcCdm, ipsJsonString);
            Assert.True(true, "Expected ImportFHIRIPSJSONToResource to execute without errors.");
        }
    }
}
