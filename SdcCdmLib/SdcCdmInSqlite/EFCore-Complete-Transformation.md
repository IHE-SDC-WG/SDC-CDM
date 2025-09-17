# Complete EF Core Transformation for SDC CDM

This document provides a comprehensive overview of all SQL insert operations that have been transformed to use Entity Framework Core for better maintainability, type safety, and performance.

## Overview

All SQL insert operations in the `SdcCdmInSqlite` class have been transformed to use Entity Framework Core with the following benefits:

- **Strong typing**: Compile-time checking of queries and entity properties
- **LINQ support**: Write queries using C# LINQ syntax instead of raw SQL
- **Async/await**: Modern async programming patterns for better performance
- **DTO projection**: Return clean DTOs that don't expose EF types
- **Backward compatibility**: All existing synchronous methods still work
- **Snake_case mapping**: Proper mapping from database columns to C# properties

## Transformed Operations

### 1. Concept Operations

#### Original SQL (InsertConcept)

```sql
INSERT INTO main.concept
(concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
 standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
VALUES
(@conceptId, @conceptName, @domainId, @vocabularyId, @conceptClassId,
 @standardConcept, @conceptCode, @validStartDate, @validEndDate, @invalidReason);
SELECT last_insert_rowid();
```

#### EF Core Implementation

```csharp
public async Task<long> InsertConceptAsync(ConceptRecord concept)
{
    var conceptEntity = new ConceptEntity
    {
        ConceptId = concept.ConceptId,
        ConceptName = concept.ConceptName,
        DomainId = concept.DomainId,
        VocabularyId = concept.VocabularyId,
        ConceptClassId = concept.ConceptClassId,
        StandardConcept = concept.StandardConcept,
        ConceptCode = concept.ConceptCode,
        ValidStartDate = concept.ValidStartDate,
        ValidEndDate = concept.ValidEndDate,
        InvalidReason = concept.InvalidReason
    };

    _dbContext.Concepts.Add(conceptEntity);
    await _dbContext.SaveChangesAsync();

    return conceptEntity.ConceptId;
}
```

### 2. Template SDC Operations

#### Original SQL (WriteTemplateSdcClass)

```sql
INSERT INTO main.template_sdc
(sdc_form_design_sdcid, base_uri, lineage, version, full_uri, form_title, sdc_xml, doc_type)
VALUES (@sdcformdesignid, @baseuri, @lineage, @version, @fulluri, @formtitle, @sdc_xml, @doctype);
SELECT last_insert_rowid();
```

#### EF Core Implementation

```csharp
public async Task<long> WriteTemplateSdcClassAsync(
    string sdcformdesignid,
    string? baseuri = null,
    string? lineage = null,
    string? version = null,
    string? fulluri = null,
    string? formtitle = null,
    string? sdc_xml = null,
    string? doctype = null
)
{
    var templateSdcEntity = new TemplateSdcEntity
    {
        SdcFormDesignSdcid = sdcformdesignid,
        BaseUri = baseuri,
        Lineage = lineage,
        Version = version,
        FullUri = fulluri,
        FormTitle = formtitle,
        SdcXml = sdc_xml,
        DocType = doctype
    };

    _dbContext.TemplateSdcs.Add(templateSdcEntity);
    await _dbContext.SaveChangesAsync();

    return templateSdcEntity.TemplateSdcId;
}
```

### 3. Template Instance Operations

#### Original SQL (WriteTemplateInstanceClass)

```sql
INSERT INTO template_instance
(template_instance_version_guid, template_instance_version_uri, template_sdc_id,
 instance_version_date, diag_report_props, surg_path_sdcid, person_id,
 visit_occurrence_id, provider_id, report_text)
VALUES (@templateinstanceversionguid, @templateinstanceversionuri, @templatesdcfk,
 @instanceversiondate, @diagreportprops, @surgpathid, @personfk,
 @encounterfk, @practitionerfk, @reporttext);
SELECT last_insert_rowid();
```

#### EF Core Implementation

```csharp
public async Task<long> WriteTemplateInstanceClassAsync(
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
)
{
    var templateInstanceEntity = new TemplateInstanceEntity
    {
        TemplateSdcId = templatesdc_fk,
        TemplateInstanceVersionGuid = template_instance_version_guid,
        TemplateInstanceVersionUri = template_instance_version_uri,
        InstanceVersionDate = instance_version_date,
        DiagReportProps = diag_report_props,
        SurgPathSdcid = surg_path_id,
        PersonId = person_fk != null ? long.Parse(person_fk) : null,
        VisitOccurrenceId = encounter_fk != null ? long.Parse(encounter_fk) : null,
        ProviderId = practitioner_fk != null ? long.Parse(practitioner_fk) : null,
        ReportText = report_text
    };

    _dbContext.TemplateInstances.Add(templateInstanceEntity);
    await _dbContext.SaveChangesAsync();

    return templateInstanceEntity.TemplateInstanceId;
}
```

### 4. SDC Observation Operations

#### Original SQL (WriteSdcObsClass)

```sql
INSERT INTO sdc_observation
(template_instance_id, parent_observation_id, parent_instance_guid, section_sdcid,
 section_guid, question_text, question_instance_guid, question_sdcid, list_item_text,
 list_item_id, list_item_instance_guid, list_item_parent_guid, response, units,
 units_system, datatype, response_int, response_float, response_datetime,
 reponse_string_nvarchar, obs_datetime, sdc_order, sdc_repeat_level, sdc_comments)
VALUES (@templateinstanceclassfk, @parent_observation_id, @parentinstanceguid,
 @section_id, @section_guid, @q_text, @q_instanceguid, @q_id, @li_text, @li_id,
 @li_instanceguid, @li_parentguid, @response, @units, @units_system, @datatype,
 @response_int, @response_float, @response_datetime, @reponse_string_nvarchar,
 @obsdatetime, @sdcorder, @sdcrepeatlevel, @sdccomments);
SELECT last_insert_rowid();
```

#### EF Core Implementation

```csharp
public async Task<long> WriteSdcObsClassAsync(
    long template_instance_class_fk,
    long? parent_observation_id = null,
    string? section_id = null,
    string? section_guid = null,
    string? q_text = null,
    string? q_instance_guid = null,
    string? q_id = null,
    string? li_text = null,
    string? li_id = null,
    string? li_instance_guid = null,
    string? sdc_order = null,
    string? response = null,
    string? units = null,
    string? units_system = null,
    string? datatype = null,
    long? response_int = null,
    double? response_float = null,
    DateTime? response_datetime = null,
    string? reponse_string_nvarchar = null,
    string? li_parent_guid = null
)
{
    var sdcObservationEntity = new SdcObservationEntity
    {
        TemplateInstanceId = template_instance_class_fk,
        ParentObservationId = parent_observation_id,
        ParentInstanceGuid = null, // Always null as per original implementation
        SectionSdcid = section_id,
        SectionGuid = section_guid,
        QuestionText = q_text,
        QuestionInstanceGuid = q_instance_guid,
        QuestionSdcid = q_id,
        ListItemText = li_text,
        ListItemId = li_id,
        ListItemInstanceGuid = li_instance_guid,
        ListItemParentGuid = li_parent_guid,
        Response = response,
        Units = units,
        UnitsSystem = units_system,
        Datatype = datatype,
        ResponseInt = response_int,
        ResponseFloat = response_float,
        ResponseDatetime = response_datetime,
        ReponseStringNvarchar = reponse_string_nvarchar,
        ObsDatetime = null, // Always null as per original implementation
        SdcOrder = sdc_order,
        SdcRepeatLevel = null, // Always null as per original implementation
        SdcComments = null // Always null as per original implementation
    };

    _dbContext.SdcObservations.Add(sdcObservationEntity);
    await _dbContext.SaveChangesAsync();

    return sdcObservationEntity.SdcObservationId;
}
```

### 5. Template Item Operations

#### Original SQL (WriteTemplateItem)

```sql
INSERT INTO template_item
(template_sdc_id, parent_template_item_id, template_item_sdcid, type,
 visible_text, invisible_text, min_cardinality, must_implement, item_order)
VALUES (@templatesdcfk, @parenttemplateitemid, @templateitem_sdcid, @type,
 @visibletext, @invisibletext, @mincard, @mustimplement, @itemorder)
RETURNING template_item_id, template_sdc_id, parent_template_item_id,
 template_item_sdcid, type, visible_text, invisible_text,
 min_cardinality, must_implement, item_order;
```

#### EF Core Implementation

```csharp
public async Task<ISdcCdm.TemplateItem?> WriteTemplateItemAsync(ISdcCdm.TemplateItemDTO templateItem)
{
    var templateItemEntity = new TemplateItemEntity
    {
        TemplateSdcId = templateItem.TemplateSdcId,
        ParentTemplateItemId = templateItem.ParentTemplateItemId,
        TemplateItemSdcid = templateItem.TemplateItemSdcid,
        Type = templateItem.Type,
        VisibleText = templateItem.VisibleText,
        InvisibleText = templateItem.InvisibleText,
        MinCardinality = templateItem.MinCard,
        MustImplement = templateItem.MustImplement,
        ItemOrder = templateItem.ItemOrder
    };

    _dbContext.TemplateItems.Add(templateItemEntity);
    await _dbContext.SaveChangesAsync();

    return new ISdcCdm.TemplateItem
    {
        TemplateItemId = templateItemEntity.TemplateItemId,
        TemplateSdcId = templateItemEntity.TemplateSdcId,
        ParentTemplateItemId = templateItemEntity.ParentTemplateItemId,
        TemplateItemSdcid = templateItemEntity.TemplateItemSdcid,
        Type = templateItemEntity.Type,
        VisibleText = templateItemEntity.VisibleText,
        InvisibleText = templateItemEntity.InvisibleText,
        MinCard = templateItemEntity.MinCardinality,
        MustImplement = templateItemEntity.MustImplement,
        ItemOrder = templateItemEntity.ItemOrder
    };
}
```

## Entity Definitions

### ConceptEntity

```csharp
[Table("concept")]
public class ConceptEntity
{
    [Key]
    [Column("concept_id")]
    public int ConceptId { get; set; }

    [Column("concept_name")]
    public string ConceptName { get; set; } = string.Empty;

    // ... other properties with snake_case mapping
}
```

### TemplateSdcEntity

```csharp
[Table("template_sdc")]
public class TemplateSdcEntity
{
    [Key]
    [Column("template_sdc_id")]
    public long TemplateSdcId { get; set; }

    [Column("sdc_form_design_sdcid")]
    public string SdcFormDesignSdcid { get; set; } = string.Empty;

    // ... other properties with snake_case mapping
}
```

### TemplateInstanceEntity

```csharp
[Table("template_instance")]
public class TemplateInstanceEntity
{
    [Key]
    [Column("template_instance_id")]
    public long TemplateInstanceId { get; set; }

    [Column("template_instance_version_guid")]
    public string? TemplateInstanceVersionGuid { get; set; }

    // ... other properties with snake_case mapping and navigation properties
}
```

### SdcObservationEntity

```csharp
[Table("sdc_observation")]
public class SdcObservationEntity
{
    [Key]
    [Column("sdc_observation_id")]
    public long SdcObservationId { get; set; }

    [Column("template_instance_id")]
    public long TemplateInstanceId { get; set; }

    // ... other properties with snake_case mapping and navigation properties
}
```

### TemplateItemEntity

```csharp
[Table("template_item")]
public class TemplateItemEntity
{
    [Key]
    [Column("template_item_id")]
    public long TemplateItemId { get; set; }

    [Column("template_sdc_id")]
    public long TemplateSdcId { get; set; }

    // ... other properties with snake_case mapping and navigation properties
}
```

## DbContext Configuration

The `SdcCdmDbContext` includes all entities with proper snake_case column mapping:

```csharp
public class SdcCdmDbContext : DbContext
{
    public DbSet<PersonEntity> Persons { get; set; } = null!;
    public DbSet<ConceptEntity> Concepts { get; set; } = null!;
    public DbSet<TemplateSdcEntity> TemplateSdcs { get; set; } = null!;
    public DbSet<TemplateInstanceEntity> TemplateInstances { get; set; } = null!;
    public DbSet<SdcObservationEntity> SdcObservations { get; set; } = null!;
    public DbSet<TemplateItemEntity> TemplateItems { get; set; } = null!;

    // ... configuration with relationships and column mappings
}
```

## Usage Examples

### Async Operations (Recommended)

```csharp
// Insert concept
var conceptId = await sdcCdm.InsertConceptAsync(concept);

// Write template SDC
var templateSdcId = await sdcCdm.WriteTemplateSdcClassAsync(sdcformdesignid, baseuri, lineage);

// Write template instance
var templateInstanceId = await sdcCdm.WriteTemplateInstanceClassAsync(templateSdcId, versionGuid);

// Write SDC observation
var observationId = await sdcCdm.WriteSdcObsClassAsync(templateInstanceId, response);

// Write template item
var templateItem = await sdcCdm.WriteTemplateItemAsync(templateItemDto);
```

### Sync Operations (Backward Compatibility)

```csharp
// All existing synchronous methods still work
var conceptId = sdcCdm.InsertConcept(concept);
var templateSdcId = sdcCdm.WriteTemplateSdcClass(sdcformdesignid, baseuri, lineage);
var templateInstanceId = sdcCdm.WriteTemplateInstanceClass(templateSdcId, versionGuid);
var observationId = sdcCdm.WriteSdcObsClass(templateInstanceId, response);
var templateItem = sdcCdm.WriteTemplateItem(templateItemDto);
```

## Benefits Achieved

1. **Complete Type Safety**: All SQL operations now use strongly-typed entities
2. **Async Performance**: All operations support async/await for better scalability
3. **LINQ Support**: Complex queries can be built using C# LINQ syntax
4. **Maintainability**: Centralized entity definitions and consistent patterns
5. **Backward Compatibility**: All existing code continues to work unchanged
6. **Relationship Support**: Proper foreign key relationships between entities
7. **DTO Projection**: Clean separation between data access and business logic

## Migration Path

The implementation provides a smooth migration path:

- All existing synchronous methods continue to work
- New async methods are available for better performance
- Gradual migration is possible without breaking changes
- Raw SQL access is still available via `GetConnection()`

## Files Created/Modified

### New Files

- `Entities/ConceptEntity.cs`
- `Entities/TemplateSdcEntity.cs`
- `Entities/TemplateInstanceEntity.cs`
- `Entities/SdcObservationEntity.cs`
- `Entities/TemplateItemEntity.cs`
- `EFCore-Complete-Transformation.md`

### Modified Files

- `SdcCdmDbContext.cs` - Added all new entities and relationships
- `SdcCdmInSqlite.cs` - Added async EF Core methods for all insert operations

This completes the transformation of all SQL insert operations to use Entity Framework Core while maintaining full backward compatibility.
