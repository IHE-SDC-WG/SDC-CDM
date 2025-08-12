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
    public DbSet<ConceptEntity> Concepts { get; set; } = null!;
    public DbSet<TemplateSdcEntity> TemplateSdcs { get; set; } = null!;
    public DbSet<TemplateInstanceEntity> TemplateInstances { get; set; } = null!;
    public DbSet<SdcObservationEntity> SdcObservations { get; set; } = null!;
    public DbSet<TemplateItemEntity> TemplateItems { get; set; } = null!;

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

        // Configure the Concept entity
        modelBuilder.Entity<ConceptEntity>(entity =>
        {
            entity.ToTable("concept");
            entity.HasKey(e => e.ConceptId);

            entity.Property(e => e.ConceptId).HasColumnName("concept_id");
            entity.Property(e => e.ConceptName).HasColumnName("concept_name");
            entity.Property(e => e.DomainId).HasColumnName("domain_id");
            entity.Property(e => e.VocabularyId).HasColumnName("vocabulary_id");
            entity.Property(e => e.ConceptClassId).HasColumnName("concept_class_id");
            entity.Property(e => e.StandardConcept).HasColumnName("standard_concept");
            entity.Property(e => e.ConceptCode).HasColumnName("concept_code");
            entity.Property(e => e.ValidStartDate).HasColumnName("valid_start_date");
            entity.Property(e => e.ValidEndDate).HasColumnName("valid_end_date");
            entity.Property(e => e.InvalidReason).HasColumnName("invalid_reason");
        });

        // Configure the TemplateSdc entity
        modelBuilder.Entity<TemplateSdcEntity>(entity =>
        {
            entity.ToTable("template_sdc");
            entity.HasKey(e => e.TemplateSdcId);

            entity.Property(e => e.TemplateSdcId).HasColumnName("template_sdc_id");
            entity.Property(e => e.SdcFormDesignSdcid).HasColumnName("sdc_form_design_sdcid");
            entity.Property(e => e.BaseUri).HasColumnName("base_uri");
            entity.Property(e => e.Lineage).HasColumnName("lineage");
            entity.Property(e => e.Version).HasColumnName("version");
            entity.Property(e => e.FullUri).HasColumnName("full_uri");
            entity.Property(e => e.FormTitle).HasColumnName("form_title");
            entity.Property(e => e.SdcXml).HasColumnName("sdc_xml");
            entity.Property(e => e.DocType).HasColumnName("doc_type");
        });

        // Configure the TemplateInstance entity
        modelBuilder.Entity<TemplateInstanceEntity>(entity =>
        {
            entity.ToTable("template_instance");
            entity.HasKey(e => e.TemplateInstanceId);

            entity.Property(e => e.TemplateInstanceId).HasColumnName("template_instance_id");
            entity
                .Property(e => e.TemplateInstanceVersionGuid)
                .HasColumnName("template_instance_version_guid");
            entity
                .Property(e => e.TemplateInstanceVersionUri)
                .HasColumnName("template_instance_version_uri");
            entity.Property(e => e.TemplateSdcId).HasColumnName("template_sdc_id");
            entity.Property(e => e.InstanceVersionDate).HasColumnName("instance_version_date");
            entity.Property(e => e.DiagReportProps).HasColumnName("diag_report_props");
            entity.Property(e => e.SurgPathSdcid).HasColumnName("surg_path_sdcid");
            entity.Property(e => e.PersonId).HasColumnName("person_id");
            entity.Property(e => e.VisitOccurrenceId).HasColumnName("visit_occurrence_id");
            entity.Property(e => e.ProviderId).HasColumnName("provider_id");
            entity.Property(e => e.ReportText).HasColumnName("report_text");

            // Configure relationships
            entity
                .HasOne(e => e.TemplateSdc)
                .WithMany()
                .HasForeignKey(e => e.TemplateSdcId)
                .OnDelete(DeleteBehavior.Restrict);

            entity
                .HasOne(e => e.Person)
                .WithMany()
                .HasForeignKey(e => e.PersonId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        // Configure the SdcObservation entity
        modelBuilder.Entity<SdcObservationEntity>(entity =>
        {
            entity.ToTable("sdc_observation");
            entity.HasKey(e => e.SdcObservationId);

            entity.Property(e => e.SdcObservationId).HasColumnName("sdc_observation_id");
            entity.Property(e => e.TemplateInstanceId).HasColumnName("template_instance_id");
            entity.Property(e => e.ParentObservationId).HasColumnName("parent_observation_id");
            entity.Property(e => e.ParentInstanceGuid).HasColumnName("parent_instance_guid");
            entity.Property(e => e.SectionSdcid).HasColumnName("section_sdcid");
            entity.Property(e => e.SectionGuid).HasColumnName("section_guid");
            entity.Property(e => e.QuestionText).HasColumnName("question_text");
            entity.Property(e => e.QuestionInstanceGuid).HasColumnName("question_instance_guid");
            entity.Property(e => e.QuestionSdcid).HasColumnName("question_sdcid");
            entity.Property(e => e.ListItemText).HasColumnName("list_item_text");
            entity.Property(e => e.ListItemId).HasColumnName("list_item_id");
            entity.Property(e => e.ListItemInstanceGuid).HasColumnName("list_item_instance_guid");
            entity.Property(e => e.ListItemParentGuid).HasColumnName("list_item_parent_guid");
            entity.Property(e => e.Response).HasColumnName("response");
            entity.Property(e => e.Units).HasColumnName("units");
            entity.Property(e => e.UnitsSystem).HasColumnName("units_system");
            entity.Property(e => e.Datatype).HasColumnName("datatype");
            entity.Property(e => e.ResponseInt).HasColumnName("response_int");
            entity.Property(e => e.ResponseFloat).HasColumnName("response_float");
            entity.Property(e => e.ResponseDatetime).HasColumnName("response_datetime");
            entity.Property(e => e.ReponseStringNvarchar).HasColumnName("reponse_string_nvarchar");
            entity.Property(e => e.ObsDatetime).HasColumnName("obs_datetime");
            entity.Property(e => e.SdcOrder).HasColumnName("sdc_order");
            entity.Property(e => e.SdcRepeatLevel).HasColumnName("sdc_repeat_level");
            entity.Property(e => e.SdcComments).HasColumnName("sdc_comments");

            // Configure relationships
            entity
                .HasOne(e => e.TemplateInstance)
                .WithMany()
                .HasForeignKey(e => e.TemplateInstanceId)
                .OnDelete(DeleteBehavior.Restrict);

            entity
                .HasOne(e => e.ParentObservation)
                .WithMany()
                .HasForeignKey(e => e.ParentObservationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        // Configure the TemplateItem entity
        modelBuilder.Entity<TemplateItemEntity>(entity =>
        {
            entity.ToTable("template_item");
            entity.HasKey(e => e.TemplateItemId);

            entity.Property(e => e.TemplateItemId).HasColumnName("template_item_id");
            entity.Property(e => e.TemplateSdcId).HasColumnName("template_sdc_id");
            entity.Property(e => e.ParentTemplateItemId).HasColumnName("parent_template_item_id");
            entity.Property(e => e.TemplateItemSdcid).HasColumnName("template_item_sdcid");
            entity.Property(e => e.Type).HasColumnName("type");
            entity.Property(e => e.VisibleText).HasColumnName("visible_text");
            entity.Property(e => e.InvisibleText).HasColumnName("invisible_text");
            entity.Property(e => e.MinCardinality).HasColumnName("min_cardinality");
            entity.Property(e => e.MustImplement).HasColumnName("must_implement");
            entity.Property(e => e.ItemOrder).HasColumnName("item_order");

            // Configure relationships
            entity
                .HasOne(e => e.TemplateSdc)
                .WithMany()
                .HasForeignKey(e => e.TemplateSdcId)
                .OnDelete(DeleteBehavior.Restrict);

            entity
                .HasOne(e => e.ParentTemplateItem)
                .WithMany()
                .HasForeignKey(e => e.ParentTemplateItemId)
                .OnDelete(DeleteBehavior.Restrict);
        });
    }
}
