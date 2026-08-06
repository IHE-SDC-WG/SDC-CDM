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

        Assert.NotNull(
            store.FindTemplateSdcClass("Adrenal.Bx.Res.120_3.004.001.REL_sdcFDF")
        );
    }
}
