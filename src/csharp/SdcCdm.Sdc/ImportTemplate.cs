using System.Xml.Linq;
using Microsoft.Extensions.Logging;

namespace SdcCdm;

public static class TemplateImporter
{
    public static bool ImportTemplate(ISdcCdm sdcCdm, XElement xmlRoot)
    {
        XNamespace sdc = "urn:ihe:qrph:sdc:2016";
        var formDesign = xmlRoot.Element(sdc + "FormDesign") ?? xmlRoot;
        if (formDesign == null)
        {
            sdcCdm.Logger.LogWarning(
                "No Form Design found in {XmlName} while attempting to import template -- skipping import",
                xmlRoot.Name
            );
            return false;
        }

        sdcCdm.Logger.LogTrace("Imported template with form_design: {FormDesign}", formDesign);

        var sdcformdesignid = formDesign.Attribute("ID")?.Value;
        if (string.IsNullOrEmpty(sdcformdesignid))
        {
            sdcCdm.Logger.LogWarning("No Form Design ID found in {XmlName}", xmlRoot.Name);
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
