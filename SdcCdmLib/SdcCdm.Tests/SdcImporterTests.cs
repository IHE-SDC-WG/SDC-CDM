using System;
using System.IO;
using System.Xml.Linq;
using SdcCdm;
using SdcCdmInSqlite;
using Xunit;

namespace SdcCdm.Tests
{
    public class SdcImporterTests
    {
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
            string hl7Path = Path.Combine(AppContext.BaseDirectory, "TestData", "NAACCR_VolV.hl7");
            string hl7Message = File.ReadAllText(hl7Path);

            // Act
            NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message, exit_on_error: false);

            // Assert
            Assert.True(true, "Expected ImportNaaccrVolV to execute without errors.");
        }
    }
}
