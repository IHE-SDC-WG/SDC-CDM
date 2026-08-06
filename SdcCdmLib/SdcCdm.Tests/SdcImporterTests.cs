using System.Xml.Linq;

namespace SdcCdm.Tests;

public class SdcImporterTests
{
    [Fact]
    public void ProcessXmlForm_ExecutesWithoutError()
    {
        using var store = new SdcSqliteStore("SdcCdm.Tests", inMemory: true);
        store.BuildSchema();
        string xmlPath = Path.Combine(AppContext.BaseDirectory, "TestData", "SDC_Form.xml");
        XElement submission = XElement.Load(xmlPath);

        XmlFormImporter.ProcessXmlForm(store, submission);

        using var command = store.GetConnection().CreateCommand();
        command.CommandText = "SELECT COUNT(*) FROM sdc.template_sdc";
        Assert.Equal(1L, command.ExecuteScalar());
    }
}
