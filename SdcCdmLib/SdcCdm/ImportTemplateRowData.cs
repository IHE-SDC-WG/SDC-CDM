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

        var ckeyToRowIdMap = new Dictionary<string, long>();

        // Print one record for debugging
        Console.WriteLine(records[0]);

        // Loop through each record
        string lastSdcId = string.Empty;
        long? lastSdcPk = null;
        var count = -1;
        var templatesCreated = 0;
        foreach (var record in records)
        {
            if (count % 1000 == 0)
            {
                Console.WriteLine(
                    $"Processed {count} records, created {templatesCreated} rows for missing templates"
                );
            }
            count += 1;
            long? templateSdcPk;
            var template = record.Template;
            var releaseKey = record.ReleaseKey;
            var version = record.Version;

            string sdcId = $"{template}.{releaseKey}_{version}_sdcFDF";

            if (sdcId.Equals(lastSdcId))
            {
                // This record is for the same template as the previous record,
                // so we can skip a search through the DB
                templateSdcPk = lastSdcPk;
            }
            else
            {
                templateSdcPk = sdcCdm.FindTemplateSdcClass(sdcId);
            }

            if (!templateSdcPk.HasValue)
            {
                // TODO: How can we gather more metadata about this template?
                templateSdcPk = sdcCdm.WriteTemplateSdcClass(
                    sdcId,
                    baseuri: null,
                    lineage: $"{template}.{releaseKey}",
                    version: version,
                    fulluri: null,
                    formtitle: null,
                    sdc_xml: null,
                    doctype: null
                );
                if (!templateSdcPk.HasValue)
                    throw new Exception($"Could not create template SDC record for {sdcId}");
                templatesCreated += 1;
            }

            long? parentTemplateItemId = null;
            if (ckeyToRowIdMap.TryGetValue(record.ParentCkey, out long value))
            {
                parentTemplateItemId = value;
            }
            var templateItem = sdcCdm.WriteTemplateItem(
                new()
                {
                    TemplateSdcId = templateSdcPk.Value,
                    ParentTemplateItemId = parentTemplateItemId,
                    TemplateItemSdcid = record.ItemCkey,
                    Type = record.ItemType,
                    VisibleText = record.AnswerVisTxt,
                    InvisibleText = record.AnswerReportTxt,
                    MinCard = record.MinCard,
                    MustImplement = record.MustImplement,
                    ItemOrder = record.ItemOrder,
                }
            );
            if (!templateItem.HasValue)
                throw new Exception($"Could not create template item record for {record.ItemCkey}");

            if (!ckeyToRowIdMap.ContainsKey(record.ItemCkey))
            {
                ckeyToRowIdMap[record.ItemCkey] = templateItem.Value.TemplateItemId;
            }
        }
    }
}
