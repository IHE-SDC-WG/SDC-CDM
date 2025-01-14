using System.Xml.Linq;

namespace SdcCdm;

public static class XmlFormImporter
{
    public static void ProcessXmlForm(ISdcCdm sdcCdm, XElement sdcSubmissionPackage)
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";

        XElement formDesign =
            sdcSubmissionPackage.Element(sdc + "FormDesign")
            ?? throw new Exception("No Form Design found in XML");
        Console.WriteLine($"Form Design: {formDesign}");

        var new_template_sdc_pk = sdcCdm.WriteTemplateSdcClass(
            formDesign.Attribute("ID")?.Value ?? "UNKNOWN",
            formDesign.Attribute("baseURI")?.Value ?? "UNKNOWN",
            formDesign.Attribute("lineage")?.Value ?? "UNKNOWN",
            formDesign.Attribute("version")?.Value ?? "UNKNOWN",
            formDesign.Attribute("fullURI")?.Value ?? "UNKNOWN",
            formDesign.Attribute("formTitle")?.Value ?? "UNKNOWN",
            formDesign.ToString(),
            "FD"
        );

        var new_template_instance_class_pk = sdcCdm.WriteTemplateInstanceClass(
            new_template_sdc_pk,
            sdcSubmissionPackage.Attribute("instanceID")?.Value ?? null,
            sdcSubmissionPackage.Attribute("instanceVersionURI")?.Value ?? null,
            sdcSubmissionPackage.Attribute("instanceVersion")?.Value ?? null
        );

        XElement body =
            formDesign.Element(sdc + "Body") ?? throw new Exception("Body element not found.");

        IEnumerable<XElement> childItems =
            body.Elements(sdc + "ChildItems")
            ?? throw new Exception("No ChildItems found in Body.");

        foreach (XElement child in childItems)
        {
            ProcessChildItem(sdcCdm, child, new_template_instance_class_pk);
        }
    }

    private static void ProcessChildItem(
        ISdcCdm sdcCdm,
        XElement childItem,
        long template_instance_class_fk,
        string? section_id = null,
        string? section_guid = null
    )
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";

        var sections = childItem.Elements(sdc + "Section");
        foreach (XElement section in sections)
        {
            string? inner_section_id = section.Attribute("title")?.Value;
            if (string.IsNullOrEmpty(inner_section_id))
                continue;
            string? inner_section_guid = section.Attribute("ID")?.Value;
            if (string.IsNullOrEmpty(inner_section_guid))
                continue;

            IEnumerable<XElement> childItems =
                section.Elements(sdc + "ChildItems")
                ?? throw new Exception("ChildItems not found inside Section.");

            foreach (XElement child in childItems)
            {
                ProcessChildItem(
                    sdcCdm,
                    child,
                    template_instance_class_fk,
                    inner_section_id,
                    inner_section_guid
                );
            }
        }

        if (string.IsNullOrEmpty(section_id))
            return;
        if (string.IsNullOrEmpty(section_guid))
            return;

        var questions = childItem.Elements(sdc + "Question");
        foreach (XElement question in questions)
        {
            ProcessQuestion(sdcCdm, question, template_instance_class_fk, section_id, section_guid);
        }
    }

    private static void ProcessQuestion(
        ISdcCdm sdcCdm,
        XElement question,
        long template_instance_class_fk,
        string section_id,
        string section_guid
    )
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";

        string? question_id = question.Attribute("name")?.Value;
        string? question_guid = question.Attribute("ID")?.Value;
        string? question_text = question.Attribute("title")?.Value;

        XElement? listField = question.Element(sdc + "ListField");
        if (listField != null)
        {
            ProcessListField(
                sdcCdm,
                listField,
                template_instance_class_fk,
                section_id,
                section_guid,
                question_text,
                question_id,
                question_guid
            );
        }

        XElement? responseField = question.Element(sdc + "ResponseField");
        if (responseField != null)
        {
            ProcessResponseField(
                sdcCdm,
                responseField,
                template_instance_class_fk,
                section_id,
                section_guid,
                question_text,
                question_id,
                question_guid
            );
        }
    }

    private static void ProcessListField(
        ISdcCdm sdcCdm,
        XElement listField,
        long template_instance_class_fk,
        string section_id,
        string section_guid,
        string? question_text,
        string? question_id,
        string? question_guid
    )
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";

        XElement? listElem = listField.Element(sdc + "List");
        if (listElem != null)
        {
            foreach (XElement listItem in listElem.Elements(sdc + "ListItem"))
            {
                XElement? li_response_field = listItem.Element(sdc + "ListItemResponseField");
                if (li_response_field != null)
                {
                    ProcessResponseField(
                        sdcCdm,
                        li_response_field,
                        template_instance_class_fk,
                        section_id,
                        section_guid,
                        question_text,
                        question_id,
                        question_guid,
                        li_text: listItem.Attribute("title")?.Value,
                        li_id: listItem.Attribute("name")?.Value,
                        li_instance_guid: listItem.Attribute("ID")?.Value
                    );
                }
                else
                {
                    sdcCdm.WriteSdcObsClass(
                        template_instance_class_fk,
                        section_id,
                        section_guid,
                        question_text,
                        question_guid,
                        question_id,
                        listItem.Attribute("title")?.Value,
                        listItem.Attribute("name")?.Value,
                        listItem.Attribute("ID")?.Value,
                        listItem.Attribute("order")?.Value
                    );
                }
            }
        }
    }

    private static void ProcessResponseField(
        ISdcCdm sdcCdm,
        XElement responseField,
        long template_instance_class_fk,
        string section_id,
        string section_guid,
        string? question_text,
        string? question_id,
        string? question_guid,
        string? li_text = null,
        string? li_id = null,
        string? li_instance_guid = null,
        string? li_parent_guid = null
    )
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";

        string? response_units = null;
        string? response_units_system = null;

        XElement? response_units_elem = responseField.Element(sdc + "ResponseUnits");
        if (response_units_elem != null)
        {
            response_units = response_units_elem.Attribute("val")?.Value;
            response_units_system = response_units_elem.Attribute("unitSystem")?.Value;
        }

        XElement? response = responseField.Element(sdc + "Response");
        if (response != null)
        {
            XElement? response_string = response.Element(sdc + "string");
            string? response_string_val = response_string?.Attribute("val")?.Value;

            sdcCdm.WriteSdcObsClass(
                template_instance_class_fk,
                section_id,
                section_guid,
                question_text,
                question_guid,
                question_id,
                li_text,
                li_id,
                li_instance_guid,
                response.Attribute("order")?.Value,
                response: response.Attribute("val")?.Value,
                units: response_units,
                units_system: response_units_system,
                reponse_string_nvarchar: response_string_val,
                li_parent_guid: li_parent_guid
            );
        }
    }
}
