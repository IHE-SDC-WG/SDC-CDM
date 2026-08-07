using System.Globalization;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;

namespace SdcCdm;

public static class XmlFormImporter
{
    private static readonly XNamespace Sdc = "urn:ihe:qrph:sdc:2016";

    /// <summary>Imports an SDCFormSubmission XML form into the SDC CDM.</summary>
    public static void ProcessXmlForm(ISdcCdm sdcCdm, XElement sdcSubmissionPackage)
    {
        XElement formDesign =
            sdcSubmissionPackage.Element(Sdc + "FormDesign")
            ?? throw new Exception("No Form Design found in XML");
        string formDesignId =
            formDesign.Attribute("ID")?.Value
            ?? throw new Exception("No Form Design ID provided in XML");

        long templateSdcId =
            sdcCdm.FindTemplateSdcClass(formDesignId)
            ?? sdcCdm.WriteTemplateSdcClass(
                formDesignId,
                formDesign.Attribute("baseURI")?.Value ?? "UNKNOWN",
                formDesign.Attribute("lineage")?.Value ?? "UNKNOWN",
                formDesign.Attribute("version")?.Value ?? "UNKNOWN",
                formDesign.Attribute("fullURI")?.Value ?? "UNKNOWN",
                formDesign.Attribute("formTitle")?.Value ?? "UNKNOWN",
                formDesign.ToString(),
                "FD"
            );

        long templateInstanceId = sdcCdm.WriteTemplateInstanceClass(
            templateSdcId,
            sdcSubmissionPackage.Attribute("instanceID")?.Value,
            sdcSubmissionPackage.Attribute("instanceVersionURI")?.Value,
            sdcSubmissionPackage.Attribute("instanceVersion")?.Value
        );

        XElement body =
            formDesign.Element(Sdc + "Body") ?? throw new Exception("Body element not found.");
        foreach (XElement childItems in body.Elements(Sdc + "ChildItems"))
        {
            ProcessChildItems(sdcCdm, childItems, templateInstanceId);
        }
    }

    private static void ProcessChildItems(
        ISdcCdm sdcCdm,
        XElement childItems,
        long templateInstanceId,
        string? sectionId = null,
        string? sectionGuid = null,
        long? parentAnswerId = null
    )
    {
        foreach (XElement section in childItems.Elements(Sdc + "Section"))
        {
            string? nestedSectionGuid = section.Attribute("ID")?.Value;
            if (string.IsNullOrEmpty(nestedSectionGuid))
            {
                continue;
            }

            string? nestedSectionId = section.Attribute("title")?.Value;
            foreach (XElement nestedItems in section.Elements(Sdc + "ChildItems"))
            {
                ProcessChildItems(
                    sdcCdm,
                    nestedItems,
                    templateInstanceId,
                    nestedSectionId,
                    nestedSectionGuid,
                    parentAnswerId
                );
            }
        }

        if (string.IsNullOrEmpty(sectionGuid))
        {
            return;
        }

        foreach (XElement question in childItems.Elements(Sdc + "Question"))
        {
            ProcessQuestion(
                sdcCdm,
                question,
                templateInstanceId,
                sectionId,
                sectionGuid,
                parentAnswerId
            );
        }
    }

    private static void ProcessQuestion(
        ISdcCdm sdcCdm,
        XElement question,
        long templateInstanceId,
        string? sectionId,
        string sectionGuid,
        long? parentAnswerId
    )
    {
        string? questionId = question.Attribute("name")?.Value;
        string? questionGuid = question.Attribute("ID")?.Value;
        string? questionText = question.Attribute("title")?.Value;
        long? questionAnswerId = parentAnswerId;

        XElement? listField = question.Element(Sdc + "ListField");
        XElement? responseField = question.Element(Sdc + "ResponseField");
        if (listField is not null)
        {
            ProcessListField(
                sdcCdm,
                listField,
                templateInstanceId,
                sectionId,
                sectionGuid,
                questionText,
                questionId,
                questionGuid,
                parentAnswerId
            );
        }
        else if (responseField is not null)
        {
            questionAnswerId = ProcessResponseField(
                sdcCdm,
                responseField,
                templateInstanceId,
                sectionId,
                sectionGuid,
                questionText,
                questionId,
                questionGuid,
                parentAnswerId
            );
        }

        foreach (XElement nestedItems in question.Elements(Sdc + "ChildItems"))
        {
            ProcessChildItems(
                sdcCdm,
                nestedItems,
                templateInstanceId,
                sectionId,
                sectionGuid,
                questionAnswerId
            );
        }
    }

    private static void ProcessListField(
        ISdcCdm sdcCdm,
        XElement listField,
        long templateInstanceId,
        string? sectionId,
        string sectionGuid,
        string? questionText,
        string? questionId,
        string? questionGuid,
        long? parentAnswerId
    )
    {
        XElement? list = listField.Element(Sdc + "List");
        if (list is null)
        {
            return;
        }

        foreach (XElement listItem in list.Elements(Sdc + "ListItem"))
        {
            if (listItem.Attribute("selected")?.Value != "true")
            {
                continue;
            }

            string? listItemText = listItem.Attribute("title")?.Value;
            string? listItemId = listItem.Attribute("name")?.Value;
            string? listItemGuid = listItem.Attribute("ID")?.Value;
            XElement? responseField = listItem.Element(Sdc + "ListItemResponseField");
            long? listItemAnswerId;
            if (responseField is not null)
            {
                listItemAnswerId = ProcessResponseField(
                    sdcCdm,
                    responseField,
                    templateInstanceId,
                    sectionId,
                    sectionGuid,
                    questionText,
                    questionId,
                    questionGuid,
                    parentAnswerId,
                    listItemText,
                    listItemId,
                    listItemGuid
                );
            }
            else
            {
                listItemAnswerId = sdcCdm.WriteSdcObsClass(
                    templateInstanceId,
                    parentAnswerId,
                    sectionId,
                    sectionGuid,
                    questionText,
                    questionGuid,
                    questionId,
                    listItemText,
                    listItemId,
                    listItemGuid,
                    listItem.Attribute("order")?.Value
                );
            }

            foreach (XElement nestedItems in listItem.Elements(Sdc + "ChildItems"))
            {
                ProcessChildItems(
                    sdcCdm,
                    nestedItems,
                    templateInstanceId,
                    sectionId,
                    sectionGuid,
                    listItemAnswerId
                );
            }
        }
    }

    private static long? ProcessResponseField(
        ISdcCdm sdcCdm,
        XElement responseField,
        long templateInstanceId,
        string? sectionId,
        string sectionGuid,
        string? questionText,
        string? questionId,
        string? questionGuid,
        long? parentAnswerId,
        string? listItemText = null,
        string? listItemId = null,
        string? listItemGuid = null,
        string? listItemParentGuid = null
    )
    {
        XElement? unitsElement = responseField.Element(Sdc + "ResponseUnits");
        string? units = unitsElement?.Attribute("val")?.Value;
        string? unitsSystem = unitsElement?.Attribute("unitSystem")?.Value;
        XElement? response = responseField.Element(Sdc + "Response");
        XElement? typedValue = response
            ?.Elements()
            .FirstOrDefault(element =>
                element.Attribute("val") is not null
                && element.Name.LocalName is "string" or "integer" or "int" or "decimal"
            );

        if (typedValue is null && listItemId is null)
        {
            return null;
        }

        // `response` holds the raw source lexeme for every typed answer; the
        // response_string / response_int / response_float columns hold the parsed value
        // for the datatype named in `datatype`. A value that does not parse keeps its
        // lexeme in `response` and is logged, so one bad value cannot discard the form.
        string? value = typedValue?.Attribute("val")?.Value;
        string? responseString = null;
        long? responseInt = null;
        double? responseFloat = null;
        string? datatype = typedValue?.Name.LocalName;
        switch (datatype)
        {
            case "string":
                responseString = value;
                break;
            case "integer":
            case "int":
                if (
                    long.TryParse(
                        value,
                        NumberStyles.Integer,
                        CultureInfo.InvariantCulture,
                        out long parsedInt
                    )
                )
                {
                    responseInt = parsedInt;
                }
                else
                {
                    LogUnparseableValue(sdcCdm, questionId, datatype, value);
                }
                break;
            case "decimal":
                if (
                    double.TryParse(
                        value,
                        NumberStyles.Float,
                        CultureInfo.InvariantCulture,
                        out double parsedFloat
                    )
                )
                {
                    responseFloat = parsedFloat;
                }
                else
                {
                    LogUnparseableValue(sdcCdm, questionId, datatype, value);
                }
                break;
        }

        return sdcCdm.WriteSdcObsClass(
            templateInstanceId,
            parentAnswerId,
            sectionId,
            sectionGuid,
            questionText,
            questionGuid,
            questionId,
            listItemText,
            listItemId,
            listItemGuid,
            typedValue?.Attribute("order")?.Value ?? response?.Attribute("order")?.Value,
            response: value,
            units: units,
            units_system: unitsSystem,
            datatype: datatype,
            response_int: responseInt,
            response_float: responseFloat,
            response_string: responseString,
            li_parent_guid: listItemParentGuid
        );
    }

    private static void LogUnparseableValue(
        ISdcCdm sdcCdm,
        string? questionId,
        string datatype,
        string? value
    )
    {
        sdcCdm.Logger.LogWarning(
            "Question {QuestionId}: {Datatype} value {Value} did not parse; "
                + "the raw lexeme is kept in sdc_form_answer.response.",
            questionId ?? "(unnamed)",
            datatype,
            value ?? "(empty)"
        );
    }
}
