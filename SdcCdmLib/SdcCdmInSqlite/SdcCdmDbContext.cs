using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using SdcCdmInSqlite.Entities;

namespace SdcCdmInSqlite;

public class SdcCdmDbContext : DbContext
{
    private readonly SqliteConnection _connection;

    public SdcCdmDbContext(SqliteConnection connection)
    {
        _connection = connection;
    }

    public DbSet<PersonEntity> Persons { get; set; } = null!;

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        optionsBuilder.UseSqlite(_connection);
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Configure the Person entity
        modelBuilder.Entity<PersonEntity>(entity =>
        {
            entity.ToTable("person");
            entity.HasKey(e => e.PersonId);

            // Configure column mappings for snake_case
            entity.Property(e => e.PersonId).HasColumnName("person_id");
            entity.Property(e => e.GenderConceptId).HasColumnName("gender_concept_id");
            entity.Property(e => e.YearOfBirth).HasColumnName("year_of_birth");
            entity.Property(e => e.MonthOfBirth).HasColumnName("month_of_birth");
            entity.Property(e => e.DayOfBirth).HasColumnName("day_of_birth");
            entity.Property(e => e.BirthDatetime).HasColumnName("birth_datetime");
            entity.Property(e => e.RaceConceptId).HasColumnName("race_concept_id");
            entity.Property(e => e.EthnicityConceptId).HasColumnName("ethnicity_concept_id");
            entity.Property(e => e.LocationId).HasColumnName("location_id");
            entity.Property(e => e.ProviderId).HasColumnName("provider_id");
            entity.Property(e => e.CareSiteId).HasColumnName("care_site_id");
            entity.Property(e => e.PersonSourceValue).HasColumnName("person_source_value");
            entity.Property(e => e.GenderSourceValue).HasColumnName("gender_source_value");
            entity.Property(e => e.GenderSourceConceptId).HasColumnName("gender_source_concept_id");
            entity.Property(e => e.RaceSourceValue).HasColumnName("race_source_value");
            entity.Property(e => e.RaceSourceConceptId).HasColumnName("race_source_concept_id");
            entity.Property(e => e.EthnicitySourceValue).HasColumnName("ethnicity_source_value");
            entity
                .Property(e => e.EthnicitySourceConceptId)
                .HasColumnName("ethnicity_source_concept_id");
        });
    }
}
