using System.Globalization;
using System.IO;
using System.Linq;
using CsvHelper;
using CsvHelper.Configuration;

namespace SdcCdm;

public static class TemplateRowDataImporter
{
    class TemplateRowData
    {
        public required string ProtocolName { get; set; }
        public required string Template { get; set; }
        public required string WebPostingDate { get; set; }
        public required string ReleaseKey { get; set; }
        public required string ProtocolVersion { get; set; }
        public required string AccreditationDate { get; set; }
        public required string Version { get; set; }
        public required string ParentCkey { get; set; }
        public required string ParentMin { get; set; }
        public required string ParentMI { get; set; }
        public required string ParentItemType { get; set; }
        public required string ParentQuestVisibleTxt { get; set; }
        public required string ParentQuestReportTxt { get; set; }
        public required string ParentInvisQuestion { get; set; }
        public required string ItemCkey { get; set; }
        public required string ItemType { get; set; }
        public required string AnswerVisTxt { get; set; }
        public required string AnswerReportTxt { get; set; }
        public required string ItemInivisibleText { get; set; }
        public required string MinCard { get; set; }
        public required string MustImplement { get; set; }
        public required string ItemOrder { get; set; }
    }

    public static void ImportTemplateRowData(ISdcCdm sdcCdm, string csvFilePath)
    {
        var config = new CsvConfiguration(CultureInfo.InvariantCulture) { HasHeaderRecord = true };

        using var reader = new StreamReader(csvFilePath);
        using var csv = new CsvReader(reader, config);
        var records = csv.GetRecords<TemplateRowData>().ToList();

        // Print one record for debugging
        Console.WriteLine(records[0]);

        // Loop through each record
        foreach (var record in records)
        {
            // Find the TemplateSdcClass record
            long? templateSdcPk = sdcCdm.FindTemplateSdcClass(record.ProtocolName);
            if (templateSdcPk == null)
            {
                Console.WriteLine($"TemplateSdcClass not found: {record.ProtocolName}");
                continue;
            }

            sdcCdm.WriteTemplateItem(
                new()
                {
                    TemplateSdcId = record.ProtocolName,
                    ParentTemplateItemId = record.ParentCkey,
                    TemplateItemSdcid = record.ItemCkey,
                    Type = record.ItemType,
                    VisibleText = record.AnswerVisTxt,
                    InvisibleText = record.AnswerReportTxt,
                    MinCard = record.MinCard,
                    MustImplement = record.MustImplement,
                    ItemOrder = record.ItemOrder,
                }
            );
        }
    }
}
