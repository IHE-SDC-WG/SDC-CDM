using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("concept")]
public class ConceptEntity
{
    [Key]
    [Column("concept_id")]
    public int ConceptId { get; set; }

    [Column("concept_name")]
    public string ConceptName { get; set; } = string.Empty;

    [Column("domain_id")]
    public string DomainId { get; set; } = string.Empty;

    [Column("vocabulary_id")]
    public string VocabularyId { get; set; } = string.Empty;

    [Column("concept_class_id")]
    public string ConceptClassId { get; set; } = string.Empty;

    [Column("standard_concept")]
    public string? StandardConcept { get; set; }

    [Column("concept_code")]
    public string ConceptCode { get; set; } = string.Empty;

    [Column("valid_start_date")]
    public DateTime ValidStartDate { get; set; }

    [Column("valid_end_date")]
    public DateTime ValidEndDate { get; set; }

    [Column("invalid_reason")]
    public string? InvalidReason { get; set; }
}
