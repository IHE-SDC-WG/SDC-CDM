namespace SdcCdm.Tests;

public class TemplateRowDataImporterTests
{
    [Fact]
    public void ImportTemplateRowData_GivenTrackedFixture_ShouldCreateTemplate()
    {
        using var store = new SdcSqliteStore("SdcCdm.Tests", inMemory: true);
        store.BuildSchema();
        string csvPath = Path.Combine(
            AppContext.BaseDirectory,
            "TestData",
            "TemplateHistory-small.csv"
        );

        TemplateRowDataImporter.ImportTemplateRowData(store, csvPath);

        Assert.NotNull(store.FindTemplateSdcClass("Adrenal.Bx.Res.120_3.004.001.REL_sdcFDF"));
        using var command = store.GetConnection().CreateCommand();
        command.CommandText =
            "SELECT lineage, version FROM sdc.template_sdc "
            + "WHERE sdc_form_design_sdcid = 'Adrenal.Bx.Res.120_3.004.001.REL_sdcFDF'";
        using var reader = command.ExecuteReader();
        Assert.True(reader.Read());
        Assert.Equal("Adrenal.Bx.Res.120", reader.GetString(0));
        Assert.Equal("3.004.001.REL", reader.GetString(1));
        Assert.True(reader.Read() is false);
    }
}
