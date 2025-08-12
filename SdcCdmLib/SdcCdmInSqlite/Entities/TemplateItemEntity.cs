using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("template_item")]
public class TemplateItemEntity
{
    [Key]
    [Column("template_item_id")]
    public long TemplateItemId { get; set; }

    [Column("template_sdc_id")]
    public long TemplateSdcId { get; set; }

    [Column("parent_template_item_id")]
    public long? ParentTemplateItemId { get; set; }

    [Column("template_item_sdcid")]
    public string TemplateItemSdcid { get; set; } = string.Empty;

    [Column("type")]
    public string? Type { get; set; }

    [Column("visible_text")]
    public string? VisibleText { get; set; }

    [Column("invisible_text")]
    public string? InvisibleText { get; set; }

    [Column("min_cardinality")]
    public string? MinCardinality { get; set; }

    [Column("must_implement")]
    public string? MustImplement { get; set; }

    [Column("item_order")]
    public string? ItemOrder { get; set; }

    // Navigation properties
    public virtual TemplateSdcEntity TemplateSdc { get; set; } = null!;
    public virtual TemplateItemEntity? ParentTemplateItem { get; set; }
}
