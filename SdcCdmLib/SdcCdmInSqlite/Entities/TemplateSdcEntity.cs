using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("template_sdc")]
public class TemplateSdcEntity
{
    [Key]
    [Column("template_sdc_id")]
    public long TemplateSdcId { get; set; }

    [Column("sdc_form_design_sdcid")]
    public string SdcFormDesignSdcid { get; set; } = string.Empty;

    [Column("base_uri")]
    public string? BaseUri { get; set; }

    [Column("lineage")]
    public string? Lineage { get; set; }

    [Column("version")]
    public string? Version { get; set; }

    [Column("full_uri")]
    public string? FullUri { get; set; }

    [Column("form_title")]
    public string? FormTitle { get; set; }

    [Column("sdc_xml")]
    public string? SdcXml { get; set; }

    [Column("doc_type")]
    public string? DocType { get; set; }
}
