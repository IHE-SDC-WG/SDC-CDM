using System;
using System.IO;
using SdcCdm;
using SdcCdmInSqlite;
using Xunit;
using Xunit.Abstractions;

namespace SdcCdm.Tests
{
    public class VocabImporterTests
    {
        private readonly ITestOutputHelper output;

        public VocabImporterTests(ITestOutputHelper output)
        {
            this.output = output;
        }

        [Fact]
        public void ImportConceptCsv_ExecutesWithoutError()
        {
            // Arrange
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            sdcCdm.BuildSchema();
            string csvPath = Path.Combine(AppContext.BaseDirectory, "TestData", "CONCEPT.csv");
            
            // Act
            int recordsImported = CsvImporter.ImportConceptCsv(sdcCdm, csvPath, batchSize: 100);
            
            // Assert
            output.WriteLine($"Imported {recordsImported} concept records");
            Assert.True(recordsImported > 0, "Expected to import at least one concept record");
        }

        [Fact]
        public void ImportConceptCsv_WithInvalidPath_ThrowsFileNotFoundException()
        {
            // Arrange
            var sdcCdm = new SdcCdmInSqlite.SdcCdmInSqlite("SdcCdm.Tests", true);
            string nonExistentPath = Path.Combine(AppContext.BaseDirectory, "TestData", "NonExistent.csv");
            
            // Act & Assert
            Assert.Throws<FileNotFoundException>(() => 
                CsvImporter.ImportConceptCsv(sdcCdm, nonExistentPath));
        }
    }
}
