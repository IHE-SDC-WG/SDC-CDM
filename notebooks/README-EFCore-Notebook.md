# Using Entity Framework Core in SDC CDM Notebooks

This document explains how to use the Entity Framework Core integration in .NET Interactive notebooks.

## Overview

The SDC CDM library now includes Entity Framework Core integration that provides:

- Strong typing for all database operations
- Async/await support for better performance
- LINQ query capabilities
- Backward compatibility with existing code

## Required NuGet Packages

When using the SDC CDM library in notebooks, you need to include the following NuGet packages:

```csharp
#r "nuget:Microsoft.Data.Sqlite,9.0.0"
#r "nuget:Microsoft.EntityFrameworkCore,8.0.0"
#r "nuget:Microsoft.EntityFrameworkCore.Sqlite,8.0.0"
#r "nuget:Microsoft.EntityFrameworkCore.Design,8.0.0"
#r "nuget:Microsoft.Extensions.Logging,9.0.4"
```

## Basic Setup

```csharp
// Reference the SDC CDM libraries
#r "../SdcCdmLib/SdcCdm/bin/Debug/net8.0/SdcCdm.dll"
#r "../SdcCdmLib/SdcCdmInSqlite/bin/Debug/net8.0/SdcCdmInSqlite.dll"

using SdcCdm;
using SdcCdmInSqlite;

// Create a new database instance
var sdcCdmInstance = new SdcCdmInSqlite("public/sdc_cdm.db", overwrite: true);
sdcCdmInstance.BuildSchema();
```

## Using EF Core Operations

### Person Operations

```csharp
// Create a person DTO
var personDto = new ISdcCdm.PersonDTO
{
    GenderConceptId = 8507, // Male
    YearOfBirth = 1980,
    PersonSourceValue = "TEST_PERSON_001"
};

// Write person (sync - backward compatibility)
var person = sdcCdmInstance.WritePerson(personDto);

// Find person by ID (async - recommended)
var foundPersonId = await sdcCdmInstance.FindPersonAsync(person?.PersonId ?? 0);

// Find person by identifier (async - recommended)
var foundPersonByIdentifier = await sdcCdmInstance.FindPersonByIdentifierAsync("TEST_PERSON_001");

// Get complete person DTO (async - recommended)
var personDtoResult = await sdcCdmInstance.GetPersonDtoAsync(person?.PersonId ?? 0);
```

### Concept Operations

```csharp
// Create a concept record
var conceptRecord = new ConceptRecord
{
    ConceptId = 999999,
    ConceptName = "Test Concept",
    DomainId = "Test Domain",
    VocabularyId = "Test Vocabulary",
    ConceptClassId = "Test Class",
    StandardConcept = "S",
    ConceptCode = "TEST001",
    ValidStartDate = DateTime.Now,
    ValidEndDate = DateTime.MaxValue
};

// Insert concept (async - recommended)
var conceptId = await sdcCdmInstance.InsertConceptAsync(conceptRecord);

// Insert concept (sync - backward compatibility)
var conceptIdSync = sdcCdmInstance.InsertConcept(conceptRecord);
```

### Template SDC Operations

```csharp
// Write template SDC (async - recommended)
var templateSdcId = await sdcCdmInstance.WriteTemplateSdcClassAsync(
    sdcformdesignid: "TEST_TEMPLATE_001",
    baseuri: "http://test.org",
    lineage: "Test Lineage",
    version: "1.0",
    formtitle: "Test Template"
);

// Write template SDC (sync - backward compatibility)
var templateSdcIdSync = sdcCdmInstance.WriteTemplateSdcClass(
    "TEST_TEMPLATE_001", "http://test.org", "Test Lineage", "1.0",
    null, "Test Template", null, null
);
```

### Template Instance Operations

```csharp
// Write template instance (async - recommended)
var templateInstanceId = await sdcCdmInstance.WriteTemplateInstanceClassAsync(
    templatesdc_fk: templateSdcId,
    template_instance_version_guid: Guid.NewGuid().ToString(),
    template_instance_version_uri: "http://test.org/instance/1",
    person_fk: person?.PersonId.ToString()
);

// Write template instance (sync - backward compatibility)
var templateInstanceIdSync = sdcCdmInstance.WriteTemplateInstanceClass(
    templateSdcId, Guid.NewGuid().ToString(), "http://test.org/instance/1",
    null, null, null, person?.PersonId.ToString(), null, null, null
);
```

### SDC Observation Operations

```csharp
// Write SDC observation (async - recommended)
var observationId = await sdcCdmInstance.WriteSdcObsClassAsync(
    template_instance_class_fk: templateInstanceId,
    q_text: "What is your favorite color?",
    q_id: "FAVORITE_COLOR",
    response: "Blue",
    datatype: "string"
);

// Write SDC observation (sync - backward compatibility)
var observationIdSync = sdcCdmInstance.WriteSdcObsClass(
    templateInstanceId, null, null, null, "What is your favorite color?",
    null, "FAVORITE_COLOR", null, null, null, null, "Blue", null, null,
    "string", null, null, null, null, null
);
```

### Template Item Operations

```csharp
// Create template item DTO
var templateItemDto = new ISdcCdm.TemplateItemDTO
{
    TemplateSdcId = templateSdcId,
    TemplateItemSdcid = "TEST_ITEM_001",
    Type = "question",
    VisibleText = "Test Question",
    MinCard = "1",
    MustImplement = "true",
    ItemOrder = "1"
};

// Write template item (async - recommended)
var templateItem = await sdcCdmInstance.WriteTemplateItemAsync(templateItemDto);

// Write template item (sync - backward compatibility)
var templateItemSync = sdcCdmInstance.WriteTemplateItem(templateItemDto);
```

## Benefits of Using EF Core

### 1. Strong Typing

- Compile-time checking of property names
- IntelliSense support in IDEs
- Refactoring support

### 2. Async/Await Support

- Better performance for I/O operations
- Non-blocking operations
- Modern C# programming patterns

### 3. LINQ Support

- Write queries using C# syntax instead of SQL strings
- Type-safe query building
- Easy to compose complex queries

### 4. Maintainability

- Centralized entity definitions
- Easy to add new queries
- Consistent patterns across the codebase

## Migration Path

The implementation provides a smooth migration path:

- All existing synchronous methods continue to work
- New async methods are available for better performance
- Gradual migration is possible without breaking changes
- Raw SQL access is still available via `GetConnection()`

## Example Notebooks

- `try_sdc_cdm_dotnet.dib` - Original notebook with EF Core packages added
- `test_efcore.dib` - Test notebook demonstrating all EF Core operations

## Troubleshooting

### Missing EF Core Assemblies

If you get an error like:

```
Could not load file or assembly 'Microsoft.EntityFrameworkCore, Version=8.0.0.0'
```

Make sure you have included all the required NuGet packages:

```csharp
#r "nuget:Microsoft.EntityFrameworkCore,8.0.0"
#r "nuget:Microsoft.EntityFrameworkCore.Sqlite,8.0.0"
#r "nuget:Microsoft.EntityFrameworkCore.Design,8.0.0"
```

### Build Errors

If you get build errors, make sure the SDC CDM libraries are built:

```powershell
dotnet build ../SdcCdmLib
```

### Database Connection Issues

If you have database connection issues, make sure the database file path is correct and the directory exists:

```csharp
var sdcCdmInstance = new SdcCdmInSqlite("public/sdc_cdm.db", overwrite: true);
```

## Performance Considerations

- Use async methods for better performance in I/O operations
- Consider using batch operations for large datasets
- Use LINQ queries for complex data retrieval
- Take advantage of EF Core's change tracking for efficient updates

## Best Practices

1. **Use async methods** when possible for better performance
2. **Keep backward compatibility** by maintaining sync methods
3. **Use DTOs** to avoid exposing EF types to calling code
4. **Leverage LINQ** for complex queries instead of raw SQL
5. **Use proper error handling** with try-catch blocks
6. **Test thoroughly** before migrating production code
