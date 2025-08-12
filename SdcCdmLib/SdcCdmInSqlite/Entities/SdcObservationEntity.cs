using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("sdc_observation")]
public class SdcObservationEntity
{
    [Key]
    [Column("sdc_observation_id")]
    public long SdcObservationId { get; set; }

    [Column("template_instance_id")]
    public long TemplateInstanceId { get; set; }

    [Column("parent_observation_id")]
    public long? ParentObservationId { get; set; }

    [Column("parent_instance_guid")]
    public string? ParentInstanceGuid { get; set; }

    [Column("section_sdcid")]
    public string? SectionSdcid { get; set; }

    [Column("section_guid")]
    public string? SectionGuid { get; set; }

    [Column("question_text")]
    public string? QuestionText { get; set; }

    [Column("question_instance_guid")]
    public string? QuestionInstanceGuid { get; set; }

    [Column("question_sdcid")]
    public string? QuestionSdcid { get; set; }

    [Column("list_item_text")]
    public string? ListItemText { get; set; }

    [Column("list_item_id")]
    public string? ListItemId { get; set; }

    [Column("list_item_instance_guid")]
    public string? ListItemInstanceGuid { get; set; }

    [Column("list_item_parent_guid")]
    public string? ListItemParentGuid { get; set; }

    [Column("response")]
    public string? Response { get; set; }

    [Column("units")]
    public string? Units { get; set; }

    [Column("units_system")]
    public string? UnitsSystem { get; set; }

    [Column("datatype")]
    public string? Datatype { get; set; }

    [Column("response_int")]
    public long? ResponseInt { get; set; }

    [Column("response_float")]
    public double? ResponseFloat { get; set; }

    [Column("response_datetime")]
    public DateTime? ResponseDatetime { get; set; }

    [Column("reponse_string_nvarchar")]
    public string? ReponseStringNvarchar { get; set; }

    [Column("obs_datetime")]
    public DateTimeOffset? ObsDatetime { get; set; }

    [Column("sdc_order")]
    public string? SdcOrder { get; set; }

    [Column("sdc_repeat_level")]
    public string? SdcRepeatLevel { get; set; }

    [Column("sdc_comments")]
    public string? SdcComments { get; set; }

    // Navigation properties
    public virtual TemplateInstanceEntity TemplateInstance { get; set; } = null!;
    public virtual SdcObservationEntity? ParentObservation { get; set; }
}
