using Microsoft.Extensions.Logging;

namespace SdcCdmInSqlite;

/// <summary>
/// Simple test class to demonstrate EF Core functionality.
/// This shows how the original SQL query has been replaced with strongly-typed LINQ.
/// </summary>
public class EFCoreTest
{
    public static async Task RunDemo()
    {
        // Create an in-memory database for testing
        var sdcCdm = new SdcCdmInSqlite(":memory:", inMemory: true);

        // Build the schema
        sdcCdm.BuildSchema();

        // Create demo instance
        var demo = new EFCoreDemo(sdcCdm);

        Console.WriteLine("=== EF Core Demo ===");
        Console.WriteLine();

        // Test 1: Find person that doesn't exist
        Console.WriteLine("Test 1: Finding non-existent person...");
        var personId = await demo.FindPersonAsync(999);
        Console.WriteLine($"Result: {personId}");
        Console.WriteLine();

        // Test 2: Find person by identifier that doesn't exist
        Console.WriteLine("Test 2: Finding person by non-existent identifier...");
        var personId2 = await demo.FindPersonByIdentifierAsync("NON_EXISTENT");
        Console.WriteLine($"Result: {personId2}");
        Console.WriteLine();

        // Test 3: Check if person exists using raw connection
        Console.WriteLine("Test 3: Checking person existence using raw connection...");
        var exists = await demo.CheckPersonExistsUsingRawConnection(999);
        Console.WriteLine($"Exists: {exists}");
        Console.WriteLine();

        Console.WriteLine("=== Demo Complete ===");
        Console.WriteLine();
        Console.WriteLine("Key Benefits Demonstrated:");
        Console.WriteLine("1. Strong typing - compile-time checking of property names");
        Console.WriteLine("2. LINQ queries - C# syntax instead of SQL strings");
        Console.WriteLine("3. Async/await - modern async programming patterns");
        Console.WriteLine("4. DTO projection - clean separation from EF types");
        Console.WriteLine("5. Backward compatibility - existing sync methods still work");
    }
}
