using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("template_instance")]
public class TemplateInstanceEntity
{
    [Key]
    [Column("template_instance_id")]
    public long TemplateInstanceId { get; set; }

    [Column("template_instance_version_guid")]
    public string? TemplateInstanceVersionGuid { get; set; }

    [Column("template_instance_version_uri")]
    public string? TemplateInstanceVersionUri { get; set; }

    [Column("template_sdc_id")]
    public long TemplateSdcId { get; set; }

    [Column("instance_version_date")]
    public string? InstanceVersionDate { get; set; }

    [Column("diag_report_props")]
    public string? DiagReportProps { get; set; }

    [Column("surg_path_sdcid")]
    public string? SurgPathSdcid { get; set; }

    [Column("person_id")]
    public long? PersonId { get; set; }

    [Column("visit_occurrence_id")]
    public long? VisitOccurrenceId { get; set; }

    [Column("provider_id")]
    public long? ProviderId { get; set; }

    [Column("report_text")]
    public string? ReportText { get; set; }

    // Navigation properties
    public virtual TemplateSdcEntity TemplateSdc { get; set; } = null!;
    public virtual PersonEntity? Person { get; set; }
}
