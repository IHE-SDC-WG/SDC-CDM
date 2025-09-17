# EF Core Transformation: Before and After

This document shows how the original SQL query has been transformed to use Entity Framework Core for better maintainability and type safety.

## Original SQL Query (Before)

```csharp
public long? FindPerson(long personPk)
{
    using var cmd = connection.CreateCommand();
    cmd.CommandText =
        @"
        SELECT person_id
        FROM person
        WHERE person_id = @personpk
        ";
    cmd.Parameters.AddWithValue("@personpk", personPk);
    var reader = cmd.ExecuteReader();
    if (reader.Read())
    {
        long foundPersonPk = reader.GetInt64(0);
        reader.Close();
        return foundPersonPk;
    }
    reader.Close();
    return null;
}
```

## EF Core Implementation (After)

### 1. Entity Definition

```csharp
[Table("person")]
public class PersonEntity
{
    [Key]
    [Column("person_id")]
    public long PersonId { get; set; }

    [Column("gender_concept_id")]
    public long GenderConceptId { get; set; }

    // ... other properties with snake_case mapping
}
```

### 2. DbContext Configuration

```csharp
public class SdcCdmDbContext : DbContext
{
    public DbSet<PersonEntity> Persons { get; set; } = null!;

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        optionsBuilder.UseSqlite(_connection);
    }
}
```

### 3. Async EF Core Query

```csharp
public async Task<long?> FindPersonAsync(long personPk)
{
    var person = await _dbContext.Persons
        .Where(p => p.PersonId == personPk)
        .Select(p => new { p.PersonId })
        .FirstOrDefaultAsync();

    return person?.PersonId;
}
```

### 4. DTO Projection

```csharp
public async Task<ISdcCdm.Person?> GetPersonDtoAsync(long personPk)
{
    var person = await _dbContext.Persons
        .Where(p => p.PersonId == personPk)
        .Select(p => new ISdcCdm.Person
        {
            PersonId = p.PersonId,
            GenderConceptId = p.GenderConceptId,
            YearOfBirth = p.YearOfBirth,
            // ... other properties
        })
        .FirstOrDefaultAsync();

    return person;
}
```

## Key Improvements

### 1. **Strong Typing**

- **Before**: String-based SQL with manual parameter binding
- **After**: Compile-time checked LINQ queries with IntelliSense

### 2. **Type Safety**

- **Before**: Manual casting with `reader.GetInt64(0)`
- **After**: Strongly-typed properties with automatic mapping

### 3. **Async Support**

- **Before**: Synchronous database operations
- **After**: Modern async/await patterns for better performance

### 4. **Maintainability**

- **Before**: SQL strings scattered throughout code
- **After**: Centralized entity definitions and LINQ queries

### 5. **DTO Projection**

- **Before**: Direct database result exposure
- **After**: Clean DTOs that hide EF implementation details

### 6. **Backward Compatibility**

- **Before**: Only synchronous methods
- **After**: Both sync and async methods available

## Usage Comparison

### Before (Raw SQL)

```csharp
var personId = sdcCdm.FindPerson(12345);
```

### After (EF Core)

```csharp
// Async version (recommended)
var personId = await sdcCdm.FindPersonAsync(12345);

// Sync version (backward compatibility)
var personId = sdcCdm.FindPerson(12345);

// Full DTO projection
var person = await sdcCdm.GetPersonDtoAsync(12345);
```

## Benefits Summary

1. **Compile-time Safety**: No more runtime SQL errors
2. **IntelliSense Support**: Full IDE assistance for queries
3. **Refactoring Support**: Easy to rename properties and queries
4. **Performance**: Async operations for better scalability
5. **Maintainability**: Centralized entity definitions
6. **Testability**: Easier to mock and test
7. **Type Safety**: No more manual casting or null checking
8. **LINQ Power**: Complex queries with C# syntax

## Migration Path

The implementation provides a smooth migration path:

- Existing code continues to work unchanged
- New code can use async methods for better performance
- Gradual migration is possible without breaking changes
- Raw SQL access is still available via `GetConnection()`
