using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SdcCdmInSqlite.Entities;

[Table("person")]
public class PersonEntity
{
    [Key]
    [Column("person_id")]
    public long PersonId { get; set; }

    [Column("gender_concept_id")]
    public long GenderConceptId { get; set; }

    [Column("year_of_birth")]
    public int YearOfBirth { get; set; }

    [Column("month_of_birth")]
    public int? MonthOfBirth { get; set; }

    [Column("day_of_birth")]
    public int? DayOfBirth { get; set; }

    [Column("birth_datetime")]
    public DateTimeOffset? BirthDatetime { get; set; }

    [Column("race_concept_id")]
    public long RaceConceptId { get; set; }

    [Column("ethnicity_concept_id")]
    public long EthnicityConceptId { get; set; }

    [Column("location_id")]
    public long? LocationId { get; set; }

    [Column("provider_id")]
    public long? ProviderId { get; set; }

    [Column("care_site_id")]
    public long? CareSiteId { get; set; }

    [Column("person_source_value")]
    public string? PersonSourceValue { get; set; }

    [Column("gender_source_value")]
    public string? GenderSourceValue { get; set; }

    [Column("gender_source_concept_id")]
    public long? GenderSourceConceptId { get; set; }

    [Column("race_source_value")]
    public string? RaceSourceValue { get; set; }

    [Column("race_source_concept_id")]
    public long? RaceSourceConceptId { get; set; }

    [Column("ethnicity_source_value")]
    public string? EthnicitySourceValue { get; set; }

    [Column("ethnicity_source_concept_id")]
    public long? EthnicitySourceConceptId { get; set; }
}
