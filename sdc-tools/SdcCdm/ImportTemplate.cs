using System.Xml.Linq;

namespace SdcCdm;

public static class TemplateImporter
{
    public static bool ImportTemplate(ISdcCdm sdcCdm, XElement xmlRoot)
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";
        var formDesign = xmlRoot.Element(sdc + "FormDesign") ?? xmlRoot;
        if (formDesign == null)
        {
            Console.WriteLine($"No Form Design found in {xmlRoot.Name}");
            return false;
        }

        Console.WriteLine($"Form Design: {formDesign}");

        var sdcformdesignid = formDesign.Attribute("ID")?.Value;
        if (string.IsNullOrEmpty(sdcformdesignid))
        {
            Console.WriteLine($"No Form Design ID found in {xmlRoot.Name}");
            return false;
        }
        var baseuri = formDesign.Attribute("baseURI")?.Value;
        var lineage = formDesign.Attribute("lineage")?.Value;
        var version = formDesign.Attribute("version")?.Value;
        var fulluri = formDesign.Attribute("fullURI")?.Value;
        var formtitle = formDesign.Attribute("formTitle")?.Value;
        var sdc_xml = formDesign.Value;
        var doctype = "FD";

        sdcCdm.WriteTemplateSdcClass(
            sdcformdesignid,
            baseuri,
            lineage,
            version,
            fulluri,
            formtitle,
            sdc_xml,
            doctype
        );

        return true;
    }
}
