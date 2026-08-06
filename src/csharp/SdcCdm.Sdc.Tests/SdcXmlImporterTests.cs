using System.Xml.Linq;
using Microsoft.Data.Sqlite;

namespace SdcCdm.Tests;

public class SdcXmlImporterTests
{
    private static readonly XNamespace Sdc = "urn:ihe:qrph:sdc:2016";

    [Fact]
    public void ImportTemplateThenProcessXmlForm_WritesOneTemplateAndOneInstance()
    {
        using var store = CreateStore();
        XElement submission = LoadSubmission();

        Assert.True(TemplateImporter.ImportTemplate(store, submission));
        XmlFormImporter.ProcessXmlForm(store, submission);

        Assert.Equal(1L, Scalar(store, "SELECT COUNT(*) FROM sdc.template_sdc"));
        Assert.Equal(1L, Scalar(store, "SELECT COUNT(*) FROM sdc.template_instance"));
        using var command = store.GetConnection().CreateCommand();
        command.CommandText =
            "SELECT sdc_form_design_sdcid, lineage, version, form_title " + "FROM sdc.template_sdc";
        using var reader = command.ExecuteReader();
        Assert.True(reader.Read());
        Assert.Equal("Breast.Invasive.Res.189_4.002.001.REL_sdcFDF", reader.GetString(0));
        Assert.Equal("Breast.Invasive.Res.189", reader.GetString(1));
        Assert.Equal("4.002.001.REL", reader.GetString(2));
        Assert.Equal("INVASIVE CARCINOMA OF THE BREAST: Resection", reader.GetString(3));

        using var instanceCommand = store.GetConnection().CreateCommand();
        instanceCommand.CommandText =
            "SELECT template_instance_version_guid, instance_version_date "
            + "FROM sdc.template_instance";
        using var instanceReader = instanceCommand.ExecuteReader();
        Assert.True(instanceReader.Read());
        Assert.Equal("f1076104-28b1-4dca-87e9-d8e0b77f8219", instanceReader.GetString(0));
        Assert.Equal("2023-12-15T14:11:27", instanceReader.GetString(1));
    }

    [Fact]
    public void ProcessXmlForm_PersistsEverySelectedListItemIncludingNestedItems()
    {
        using var store = CreateStore();
        XElement submission = LoadSubmission();
        var expected = submission
            .Descendants(Sdc + "ListItem")
            .Where(item => item.Attribute("selected")?.Value == "true")
            .Select(item =>
                (Id: item.Attribute("name")?.Value, Text: item.Attribute("title")?.Value)
            )
            .OrderBy(item => item.Id)
            .ToList();
        Assert.Equal(12, expected.Count);

        XmlFormImporter.ProcessXmlForm(store, submission);

        using var command = store.GetConnection().CreateCommand();
        command.CommandText =
            "SELECT list_item_id, list_item_text FROM sdc.sdc_form_answer "
            + "WHERE list_item_id IS NOT NULL ORDER BY list_item_id";
        using var reader = command.ExecuteReader();
        List<(string? Id, string? Text)> actual = [];
        while (reader.Read())
        {
            actual.Add((reader.GetString(0), reader.GetString(1)));
        }

        Assert.Equal(expected, actual);
        Assert.Equal(13L, Scalar(store, "SELECT COUNT(*) FROM sdc.sdc_form_answer"));
    }

    [Fact]
    public void ProcessXmlForm_PersistsTypedValuesFromResponseChildren()
    {
        using var store = CreateStore();

        XmlFormImporter.ProcessXmlForm(store, LoadSubmission());

        using var integerCommand = store.GetConnection().CreateCommand();
        integerCommand.CommandText =
            "SELECT response_int, datatype FROM sdc.sdc_form_answer "
            + "WHERE list_item_id = 'LI_40253'";
        using var integerReader = integerCommand.ExecuteReader();
        Assert.True(integerReader.Read());
        Assert.Equal(1L, integerReader.GetInt64(0));
        Assert.Equal("integer", integerReader.GetString(1));

        using var stringCommand = store.GetConnection().CreateCommand();
        stringCommand.CommandText =
            "SELECT response, response_string, units, datatype FROM sdc.sdc_form_answer "
            + "WHERE question_sdcid = 'Q_16451'";
        using var stringReader = stringCommand.ExecuteReader();
        Assert.True(stringReader.Read());
        Assert.Equal("10", stringReader.GetString(0));
        Assert.Equal("10", stringReader.GetString(1));
        Assert.Equal("mm", stringReader.GetString(2));
        Assert.Equal("string", stringReader.GetString(3));
    }

    [Fact]
    public void ProcessXmlForm_KeepsTheRawLexemeInResponseForEveryTypedAnswer()
    {
        using var store = CreateStore();

        XmlFormImporter.ProcessXmlForm(store, LoadSubmission());

        // `datatype` names which typed column holds the parsed value; `response`
        // holds the source lexeme regardless, so it is never null for an answered
        // question. Only selected list items without a response field lack one.
        Assert.Equal(
            0L,
            Scalar(
                store,
                "SELECT COUNT(*) FROM sdc.sdc_form_answer "
                    + "WHERE datatype IS NOT NULL AND response IS NULL"
            )
        );
        Assert.Equal(
            "1",
            ScalarValue(
                store,
                "SELECT response FROM sdc.sdc_form_answer WHERE list_item_id = 'LI_40253'"
            )
        );
    }

    [Fact]
    public void ProcessXmlForm_KeepsUnparseableNumericsInsteadOfFailingTheSubmission()
    {
        using var store = CreateStore();
        XElement submission = XElement.Parse(
            """
            <SDCSubmissionPackage xmlns="urn:ihe:qrph:sdc:2016" instanceID="bad-values">
              <FormDesign ID="bad-form" baseURI="test" lineage="bad" version="1" fullURI="bad:1" formTitle="Bad values">
                <Body>
                  <ChildItems>
                    <Section ID="section-1" title="Section 1">
                      <ChildItems>
                        <Question name="Q_blank_int" ID="q-blank-int" title="Blank integer">
                          <ResponseField><Response><integer val="" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_bad_decimal" ID="q-bad-decimal" title="Non-numeric decimal">
                          <ResponseField><Response><decimal val="not a number" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_good" ID="q-good" title="Good">
                          <ResponseField><Response><integer val="42" /></Response></ResponseField>
                        </Question>
                      </ChildItems>
                    </Section>
                  </ChildItems>
                </Body>
              </FormDesign>
            </SDCSubmissionPackage>
            """
        );

        XmlFormImporter.ProcessXmlForm(store, submission);

        // The malformed values must not discard the rest of the submission.
        Assert.Equal(3L, Scalar(store, "SELECT COUNT(*) FROM sdc.sdc_form_answer"));
        Assert.Equal(
            42L,
            ScalarValue(
                store,
                "SELECT response_int FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_good'"
            )
        );
        Assert.Null(
            ScalarValue(
                store,
                "SELECT response_int FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_blank_int'"
            )
        );
        Assert.Equal(
            "not a number",
            ScalarValue(
                store,
                "SELECT response FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_bad_decimal'"
            )
        );
        Assert.Null(
            ScalarValue(
                store,
                "SELECT response_float FROM sdc.sdc_form_answer "
                    + "WHERE question_sdcid = 'Q_bad_decimal'"
            )
        );
    }

    [Fact]
    public void ProcessXmlForm_RoutesStringIntegerIntAndDecimalAndSkipsUnansweredValues()
    {
        using var store = CreateStore();
        XElement submission = XElement.Parse(
            """
            <SDCSubmissionPackage xmlns="urn:ihe:qrph:sdc:2016" instanceID="typed-values">
              <FormDesign ID="typed-form" baseURI="test" lineage="typed" version="1" fullURI="typed:1" formTitle="Typed values">
                <Body>
                  <ChildItems>
                    <Section ID="section-1" title="Section 1">
                      <ChildItems>
                        <Question name="Q_string" ID="q-string" title="String">
                          <ResponseField><Response><string val="alpha" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_integer" ID="q-integer" title="Integer">
                          <ResponseField><Response><integer val="7" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_int" ID="q-int" title="Int alias">
                          <ResponseField><Response><int val="8" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_decimal" ID="q-decimal" title="Decimal">
                          <ResponseField><Response><decimal val="1.25" /></Response></ResponseField>
                        </Question>
                        <Question name="Q_unanswered" ID="q-unanswered" title="Unanswered">
                          <ResponseField><Response><string /></Response></ResponseField>
                        </Question>
                      </ChildItems>
                    </Section>
                  </ChildItems>
                </Body>
              </FormDesign>
            </SDCSubmissionPackage>
            """
        );

        XmlFormImporter.ProcessXmlForm(store, submission);

        Assert.Equal(4L, Scalar(store, "SELECT COUNT(*) FROM sdc.sdc_form_answer"));
        Assert.Equal(
            "alpha",
            ScalarValue(
                store,
                "SELECT response FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_string'"
            )
        );
        Assert.Equal(
            7L,
            ScalarValue(
                store,
                "SELECT response_int FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_integer'"
            )
        );
        Assert.Equal(
            8L,
            ScalarValue(
                store,
                "SELECT response_int FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_int'"
            )
        );
        Assert.Equal(
            1.25,
            ScalarValue(
                store,
                "SELECT response_float FROM sdc.sdc_form_answer WHERE question_sdcid = 'Q_decimal'"
            )
        );
    }

    private static SdcSqliteStore CreateStore()
    {
        var store = new SdcSqliteStore("SdcCdm.Tests", inMemory: true);
        store.BuildSchema();
        return store;
    }

    private static XElement LoadSubmission()
    {
        string path = Path.Combine(AppContext.BaseDirectory, "TestData", "SDC_Form.xml");
        return XElement.Load(path);
    }

    private static long Scalar(SdcSqliteStore store, string sql) =>
        Convert.ToInt64(ScalarValue(store, sql));

    /// <summary>Returns the first column of the first row, with SQL NULL as null.</summary>
    private static object? ScalarValue(SdcSqliteStore store, string sql)
    {
        using SqliteCommand command = store.GetConnection().CreateCommand();
        command.CommandText = sql;
        object? value = command.ExecuteScalar();
        return value is DBNull ? null : value;
    }
}
