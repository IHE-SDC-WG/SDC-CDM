using Microsoft.Extensions.Logging;

namespace SdcCdm;

public record SdcObsClass(
    long Pk,
    long TemplateInstanceClassFk,
    string? SectionId,
    string? SectionGuid,
    string? QText,
    string? QInstanceGuid,
    string? QId,
    string? LiText,
    string? LiId,
    string? LiInstanceGuid,
    string? LiParentGuid,
    string? Response,
    string? Units,
    string? UnitsSystem,
    string? Datatype,
    long? ResponseInt,
    double? ResponseFloat,
    DateTimeOffset? ResponseDatetime,
    string? ReponseStringNvarchar,
    DateTimeOffset? ObsDateTime,
    string? SdcOrder,
    string? SdcRepeatLevel,
    string? SdcComments
);

public interface ISdcCdm
{
    public ILogger Logger { get; set; }

    /// <summary>
    /// Inserts a concept record into the concept table.
    /// </summary>
    /// <param name="concept">The concept record to insert.</param>
    /// <returns>The ID of the inserted concept.</returns>
    long InsertConcept(ConceptRecord concept);
    public long WriteTemplateSdcClass(
        string sdcformdesignid,
        string? baseuri = null,
        string? lineage = null,
        string? version = null,
        string? fulluri = null,
        string? formtitle = null,
        string? sdc_xml = null,
        string? doctype = null
    );
    public long WriteTemplateInstanceClass(
        long templatesdc_fk,
        string? template_instance_version_guid = null,
        string? template_instance_version_uri = null,
        string? instance_version_date = null,
        string? diag_report_props = null,
        string? surg_path_id = null,
        string? person_fk = null,
        string? encounter_fk = null,
        string? practitioner_fk = null,
        string? report_text = null
    );
    public long WriteSdcObsClass(
        long template_instance_class_fk,
        long? parent_observation_id,
        string? section_id,
        string? section_guid,
        string? q_text,
        string? q_instance_guid,
        string? q_id,
        string? li_text,
        string? li_id,
        string? li_instance_guid,
        string? sdc_order,
        string? response = null,
        string? units = null,
        string? units_system = null,
        string? datatype = null,
        long? response_int = null,
        double? response_float = null,
        DateTime? response_datetime = null,
        string? reponse_string_nvarchar = null,
        string? li_parent_guid = null
    );

    public long? FindTemplateSdcClass(string formDesignId);

    public long? FindTemplateInstanceClass(
        string instanceVersionGuid,
        string? instanceVersionDate = null
    );

    public struct TemplateItemDTO
    {
        public long TemplateSdcId;
        public long? ParentTemplateItemId;
        public string TemplateItemSdcid;
        public string? Type;
        public string? VisibleText;
        public string? InvisibleText;
        public string? MinCard;
        public string? MustImplement;
        public string? ItemOrder;
    };

    public struct TemplateItem
    {
        public long TemplateItemId;
        public long TemplateSdcId;
        public long? ParentTemplateItemId;
        public string TemplateItemSdcid;
        public string? Type;
        public string? VisibleText;
        public string? InvisibleText;
        public string? MinCard;
        public string? MustImplement;
        public string? ItemOrder;
    };

    public TemplateItem? WriteTemplateItem(in TemplateItemDTO templateItem);
    public long? FindTemplateItem(string template_item_sdcid);

    public struct PersonDTO
    {
        public long GenderConceptId;
        public int YearOfBirth;
        public int? MonthOfBirth;
        public int? DayOfBirth;
        public DateTimeOffset? BirthDatetime;
        public long RaceConceptId;
        public long EthnicityConceptId;
        public long? LocationId;
        public long? ProviderId;
        public long? CareSiteId;
        public string? PersonSourceValue;
        public string? GenderSourceValue;
        public long? GenderSourceConceptId;
        public string? RaceSourceValue;
        public long? RaceSourceConceptId;
        public string? EthnicitySourceValue;
        public long? EthnicitySourceConceptId;
    };

    public struct Person
    {
        public long PersonId;
        public long GenderConceptId;
        public int YearOfBirth;
        public int? MonthOfBirth;
        public int? DayOfBirth;
        public DateTimeOffset? BirthDatetime;
        public long RaceConceptId;
        public long EthnicityConceptId;
        public long? LocationId;
        public long? ProviderId;
        public long? CareSiteId;
        public string? PersonSourceValue;
        public string? GenderSourceValue;
        public long? GenderSourceConceptId;
        public string? RaceSourceValue;
        public long? RaceSourceConceptId;
        public string? EthnicitySourceValue;
        public long? EthnicitySourceConceptId;
    };

    public Person? WritePerson(in PersonDTO person);
    public long? FindPerson(long personPk);
    public long? FindPersonByIdentifier(string identifier);

    public record TemplateInstanceRecord(
        long Pk,
        string? TemplateInstanceVersionGuid,
        string? TemplateInstanceVersionUri,
        long Templatesdcfk,
        string? InstanceVersionDate,
        string? DiagReportProps,
        string? SurgPathId,
        long? PersonFk,
        long? EncounterFk,
        long? PractitionerFk,
        string? ReportText
    );

    public TemplateInstanceRecord? GetTemplateInstanceRecord(long templateInstanceClassPk);

    public List<SdcObsClass> GetSdcObsClasses(long templateInstanceClassPk);

    // New methods for ECP data handling
    public long WriteSdcTemplateInstanceEcp(
        string template_name,
        string template_version,
        string template_instance_guid,
        long? person_id = null,
        long? visit_occurrence_id = null,
        long? provider_id = null,
        string? report_text = null,
        string? report_template_source = null,
        string? report_template_id = null,
        string? report_template_version_id = null,
        string? tumor_site = null,
        string? procedure_type = null,
        string? specimen_laterality = null
    );

    public long WriteMeasurementWithSdcData(
        long person_id,
        long measurement_concept_id,
        DateTime measurement_date,
        long measurement_type_concept_id,
        double? value_as_number = null,
        string? value_as_string = null,
        string? unit_source_value = null,
        string? measurement_source_value = null,
        // SDC-specific fields
        string? sdc_template_instance_guid = null,
        string? sdc_question_identifier = null,
        string? sdc_response_value = null,
        string? sdc_response_type = null,
        string? sdc_template_version = null,
        string? sdc_question_text = null,
        string? sdc_section_identifier = null,
        string? sdc_list_item_id = null,
        string? sdc_list_item_text = null,
        string? sdc_units = null,
        string? sdc_datatype = null,
        int? sdc_order = null,
        int? sdc_repeat_level = null,
        string? sdc_comments = null
    );

    public record SdcTemplateInstanceEcpRecord(
        long Pk,
        string TemplateName,
        string TemplateVersion,
        string TemplateInstanceGuid,
        long? PersonId,
        long? VisitOccurrenceId,
        long? ProviderId,
        string? ReportText,
        string? ReportTemplateSource,
        string? ReportTemplateId,
        string? ReportTemplateVersionId,
        string? TumorSite,
        string? ProcedureType,
        string? SpecimenLaterality,
        DateTime CreatedDatetime,
        DateTime UpdatedDatetime
    );

    public SdcTemplateInstanceEcpRecord? GetSdcTemplateInstanceEcpRecord(
        long templateInstanceEcpPk
    );
    public SdcTemplateInstanceEcpRecord? FindSdcTemplateInstanceEcpByGuid(
        string templateInstanceGuid
    );
}
