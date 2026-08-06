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
    string? SdcOrder,
    string? SdcRepeatLevel,
    string? SdcComments
);

public interface ISdcCdm
{
    ILogger Logger { get; set; }

    long WriteTemplateSdcClass(
        string sdcformdesignid,
        string? baseuri = null,
        string? lineage = null,
        string? version = null,
        string? fulluri = null,
        string? formtitle = null,
        string? sdc_xml = null,
        string? doctype = null
    );

    long WriteTemplateInstanceClass(
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

    long WriteSdcObsClass(
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

    long? FindTemplateSdcClass(string formDesignId);

    long? FindTemplateInstanceClass(
        string instanceVersionGuid,
        string? instanceVersionDate = null
    );

    TemplateItem? WriteTemplateItem(in TemplateItemDTO templateItem);

    long? FindTemplateItem(string template_item_sdcid);

    TemplateInstanceRecord? GetTemplateInstanceRecord(long templateInstanceClassPk);

    List<SdcObsClass> GetSdcObsClasses(long templateInstanceClassPk);

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
    }

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
    }

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
}
