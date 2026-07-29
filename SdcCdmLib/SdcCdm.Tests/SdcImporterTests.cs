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

            var connection = sdcCdm.GetConnection();
            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = """
                    SELECT COUNT(*), MIN(observation_date), MAX(observation_date)
                    FROM naaccr.naaccr_value
                    WHERE sdc_report_id = @reportId
                    """;
                cmd.Parameters.AddWithValue("@reportId", reportId.Value);
                using var reader = cmd.ExecuteReader();
                Assert.True(reader.Read());
                Assert.Equal(19, reader.GetInt32(0));
                Assert.Equal("2023-10-05", reader.GetString(1));
                Assert.Equal("2023-10-05", reader.GetString(2));
            }

            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = """
                    SELECT obx_sub_id, value_code, value_num, value_text
                    FROM naaccr.naaccr_value
                    WHERE sdc_report_id = @reportId AND item_num = 2129
                    """;
                cmd.Parameters.AddWithValue("@reportId", reportId.Value);
                using var reader = cmd.ExecuteReader();
                Assert.True(reader.Read());
                Assert.Equal("2131", reader.GetString(0));
                Assert.Equal("2131.1000043", reader.GetString(1));
                Assert.Equal(10.0, reader.GetDouble(2));
                Assert.True(reader.IsDBNull(3));
                Assert.False(reader.Read());
            }

            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = """
                    SELECT value_code, value_text
                    FROM naaccr.naaccr_value
                    WHERE sdc_report_id = @reportId AND item_num = 820404
                    """;
                cmd.Parameters.AddWithValue("@reportId", reportId.Value);
                using var reader = cmd.ExecuteReader();
                Assert.True(reader.Read());
                Assert.Equal("45594.1000043", reader.GetString(0));
                Assert.Equal(
                    "Capsular invasion and sinusoidal vascular invasion identified",
                    reader.GetString(1)
                );
                Assert.False(reader.Read());
            }

            sdcCdm.BridgeNaaccrSdcToOmop();
            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = """
                    SELECT COUNT(*), MIN(measurement_date), MAX(measurement_date)
                    FROM omop.measurement
                    """;
                using var reader = cmd.ExecuteReader();
                Assert.True(reader.Read());
                Assert.Equal(19, reader.GetInt32(0));
                Assert.Equal("2023-10-05", reader.GetString(1));
                Assert.Equal("2023-10-05", reader.GetString(2));
            }

            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = """
                    SELECT measurement_source_value, value_as_number, value_source_value
                    FROM omop.measurement
                    WHERE measurement_source_value IN ('2129', '820404')
                    ORDER BY measurement_source_value
                    """;
                using var reader = cmd.ExecuteReader();
                Assert.True(reader.Read());
                Assert.Equal("2129", reader.GetString(0));
                Assert.Equal(10.0, reader.GetDouble(1));
                Assert.Equal("2131.1000043", reader.GetString(2));
                Assert.True(reader.Read());
                Assert.Equal("820404", reader.GetString(0));
                Assert.True(reader.IsDBNull(1));
                Assert.Equal(
                    "Capsular invasion and sinusoidal vascular invasion identified",
                    reader.GetString(2)
                );
                Assert.False(reader.Read());
            }
        }

        [Fact]
        public void ImportNaaccrVolV_BlankNarrativeUsesBridgeFallback()
        {
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string hl7Path = Path.Combine(
                AppContext.BaseDirectory,
                "TestData",
                "HL7",
                "24-11-000312-2.txt.hl7"
            );

            NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, File.ReadAllText(hl7Path));
            var reportId = sdcCdm.FindFirstSdcReportByAccession("24-11-000312");
            Assert.NotNull(reportId);
            Assert.Null(sdcCdm.GetSdcReportRecord(reportId.Value)?.ReportText);

            sdcCdm.BridgeNaaccrSdcToOmop();
            using var cmd = sdcCdm.GetConnection().CreateCommand();
            cmd.CommandText = """
                SELECT note_text
                FROM omop.note
                WHERE note_source_value = '24-11-000312'
                """;
            Assert.Equal("Synoptic report", cmd.ExecuteScalar());
        }

        [Fact]
        public void ImportNaaccrVolV_MissingObxDateFallsBackToObrDate()
        {
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string hl7Path = Path.Combine(
                AppContext.BaseDirectory,
                "TestData",
                "HL7",
                "obx-Adrenal.hl7"
            );
            string hl7Message = File.ReadAllText(hl7Path).Replace("20231005152616", "");

            NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);
            using var cmd = sdcCdm.GetConnection().CreateCommand();
            cmd.CommandText = """
                SELECT MIN(observation_date), MAX(observation_date)
                FROM naaccr.naaccr_value
                """;
            using var reader = cmd.ExecuteReader();
            Assert.True(reader.Read());
            Assert.Equal("2021-02-23", reader.GetString(0));
            Assert.Equal("2021-02-23", reader.GetString(1));
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
