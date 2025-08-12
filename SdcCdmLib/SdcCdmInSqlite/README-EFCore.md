# Entity Framework Core Integration for SDC CDM

This document describes the Entity Framework Core integration that provides strong typing, modular design, and better maintainability for SQL queries in the SDC CDM project.

## Overview

The EF Core integration provides:

- **Strong typing**: Compile-time checking of queries and entity properties
- **LINQ support**: Write queries using C# LINQ syntax instead of raw SQL
- **Async/await support**: Modern async programming patterns
- **DTO projection**: Return clean DTOs instead of exposing EF types
- **Backward compatibility**: Existing synchronous methods still work

## Architecture

### Entities

- `PersonEntity`: Maps to the `person` table with snake_case column mapping
- Located in `Entities/PersonEntity.cs`

### DbContext

- `SdcCdmDbContext`: EF Core DbContext that uses the existing SQLite connection
- Configured to map snake_case columns to C# properties
- Located in `SdcCdmDbContext.cs`

### Updated Methods

The following methods have been updated to use EF Core:

1. **FindPerson(long personPk)**

   - Original SQL: `SELECT person_id FROM person WHERE person_id = @personpk`
   - EF Core equivalent: `await _dbContext.Persons.Where(p => p.PersonId == personPk).Select(p => new { p.PersonId }).FirstOrDefaultAsync()`

2. **FindPersonByIdentifier(string identifier)**

   - Original SQL: `SELECT person.person_id, person.person_source_value FROM person WHERE person_source_value = @identifier`
   - EF Core equivalent: `await _dbContext.Persons.Where(p => p.PersonSourceValue == identifier).Select(p => new { p.PersonId }).FirstOrDefaultAsync()`

3. **New: GetPersonDtoAsync(long personPk)**
   - Demonstrates DTO projection to avoid exposing EF types
   - Returns `ISdcCdm.Person` struct

## Usage Examples

### Basic Person Lookup

```csharp
// Async version (recommended)
var personId = await sdcCdm.FindPersonAsync(12345);

// Sync version (backward compatibility)
var personId = sdcCdm.FindPerson(12345);
```

### Person Lookup by Identifier

```csharp
// Async version (recommended)
var personId = await sdcCdm.FindPersonByIdentifierAsync("PATIENT_001");

// Sync version (backward compatibility)
var personId = sdcCdm.FindPersonByIdentifier("PATIENT_001");
```

### Getting Complete Person DTO

```csharp
// Get full person data projected to DTO
var person = await sdcCdm.GetPersonDtoAsync(12345);
if (person != null)
{
    Console.WriteLine($"Person: {person.PersonId}, Birth Year: {person.YearOfBirth}");
}
```

### Using the Demo Class

```csharp
var demo = new EFCoreDemo(sdcCdm);

// Find person
var personId = await demo.FindPersonAsync(12345);

// Find by identifier
var personId2 = await demo.FindPersonByIdentifierAsync("PATIENT_001");

// Get complete person DTO
var person = await demo.GetPersonDtoAsync(12345);

// Use raw connection for custom queries
var exists = await demo.CheckPersonExistsUsingRawConnection(12345);
```

## Benefits

### 1. Strong Typing

- Compile-time checking of property names
- IntelliSense support in IDEs
- Refactoring support

### 2. LINQ Queries

- Write queries in C# instead of SQL strings
- Type-safe query building
- Easy to compose complex queries

### 3. Async/Await

- Better performance for I/O operations
- Non-blocking operations
- Modern C# programming patterns

### 4. DTO Projection

- Clean separation between data access and business logic
- No dependency on EF types in calling code
- Easy to evolve the data model

### 5. Maintainability

- Centralized entity definitions
- Easy to add new queries
- Consistent patterns across the codebase

## Migration Path

The implementation maintains backward compatibility:

- All existing synchronous methods still work
- New async methods are available for better performance
- Gradual migration is possible

## Future Enhancements

1. **Add more entities**: Map other tables (concept, template_sdc, etc.)
2. **Repository pattern**: Abstract data access behind repositories
3. **Unit of Work**: Add transaction support
4. **Query specifications**: Add reusable query patterns
5. **Performance optimization**: Add query caching and optimization

## Dependencies

- Microsoft.EntityFrameworkCore (8.0.0)
- Microsoft.EntityFrameworkCore.Sqlite (8.0.0)
- Microsoft.EntityFrameworkCore.Design (8.0.0)

These packages are already added to the project file.
