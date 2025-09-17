using Microsoft.Extensions.Logging;
using SdcCdm;

namespace SdcCdmInSqlite;

/// <summary>
/// Demo class showing how to use Entity Framework Core with the SDC CDM database.
/// This demonstrates the benefits of strong typing, LINQ queries, and async operations.
/// </summary>
public class EFCoreDemo
{
    private readonly SdcCdmInSqlite _sdcCdm;

    public EFCoreDemo(SdcCdmInSqlite sdcCdm)
    {
        _sdcCdm = sdcCdm;
    }

    /// <summary>
    /// Demonstrates finding a person using EF Core with async/await.
    /// </summary>
    /// <param name="personId">The person ID to find.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public async Task<long?> FindPersonAsync(long personId)
    {
        // This is the EF Core equivalent of the original SQL query:
        // SELECT person_id FROM person WHERE person_id = @personpk

        var result = await _sdcCdm.FindPersonAsync(personId);

        _sdcCdm.Logger.LogInformation("Found person with ID: {PersonId}", result);

        return result;
    }

    /// <summary>
    /// Demonstrates finding a person by identifier using EF Core with async/await.
    /// </summary>
    /// <param name="identifier">The person identifier to find.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public async Task<long?> FindPersonByIdentifierAsync(string identifier)
    {
        // This is the EF Core equivalent of the original SQL query:
        // SELECT person.person_id, person.person_source_value
        // FROM person WHERE person_source_value = @identifier

        var result = await _sdcCdm.FindPersonByIdentifierAsync(identifier);

        _sdcCdm.Logger.LogInformation(
            "Found person with identifier '{Identifier}': {PersonId}",
            identifier,
            result
        );

        return result;
    }

    /// <summary>
    /// Demonstrates getting a complete person DTO using EF Core.
    /// This shows how to project to a DTO to avoid exposing EF types.
    /// </summary>
    /// <param name="personId">The person ID to retrieve.</param>
    /// <returns>The person DTO if found, null otherwise.</returns>
    public async Task<ISdcCdm.Person?> GetPersonDtoAsync(long personId)
    {
        // This demonstrates projection to a DTO using EF Core
        var person = await _sdcCdm.GetPersonDtoAsync(personId);

        if (person.HasValue)
        {
            _sdcCdm.Logger.LogInformation(
                "Retrieved person: {PersonId}, Birth Year: {YearOfBirth}, Source: {SourceValue}",
                person.Value.PersonId,
                person.Value.YearOfBirth,
                person.Value.PersonSourceValue
            );
        }

        return person;
    }

    /// <summary>
    /// Demonstrates how to use the underlying connection for custom queries
    /// while still having access to EF Core for other operations.
    /// </summary>
    /// <param name="personId">The person ID to check.</param>
    /// <returns>True if the person exists.</returns>
    public async Task<bool> CheckPersonExistsUsingRawConnection(long personId)
    {
        // Get the connection from the SDC CDM instance
        using var connection = _sdcCdm.GetConnection();
        using var command = connection.CreateCommand();

        command.CommandText = "SELECT COUNT(*) FROM person WHERE person_id = @personId";
        command.Parameters.AddWithValue("@personId", personId);

        var count = await command.ExecuteScalarAsync();
        return Convert.ToInt32(count) > 0;
    }
}
