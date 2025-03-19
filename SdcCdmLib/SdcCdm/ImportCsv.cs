using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using CsvHelper;
using CsvHelper.Configuration;

namespace SdcCdm;

/// <summary>
/// Provides functionality to import CSV data into SDC CDM database tables.
/// </summary>
public static class CsvImporter
{
    /// <summary>
    /// Imports concept data from a CSV file into the concept table.
    /// </summary>
    /// <param name="sdcCdm">The SDC CDM interface implementation.</param>
    /// <param name="csvFilePath">Path to the CSV file containing concept data.</param>
    /// <param name="batchSize">Number of records to process in each batch (default: 1000).</param>
    /// <param name="hasHeaderRow">Whether the CSV file has a header row (default: true).</param>
    /// <returns>The number of records successfully imported.</returns>
    /// <exception cref="FileNotFoundException">Thrown when the CSV file is not found.</exception>
    /// <exception cref="InvalidOperationException">Thrown when there's an error processing the CSV data.</exception>
    public static int ImportConceptCsv(
        ISdcCdm sdcCdm,
        string csvFilePath,
        int batchSize = 1000,
        bool hasHeaderRow = true
    )
    {
        if (!File.Exists(csvFilePath))
        {
            throw new FileNotFoundException($"CSV file not found: {csvFilePath}");
        }

        int recordsImported = 0;

        try
        {
            using var reader = new StreamReader(csvFilePath);
            var config = new CsvConfiguration(CultureInfo.InvariantCulture)
            {
                HasHeaderRecord = hasHeaderRow,
                MissingFieldFound = null,
            };

            using var csv = new CsvReader(reader, config);

            // Skip header if present
            if (hasHeaderRow)
            {
                csv.Read();
                csv.ReadHeader();
            }

            var batch = new List<ConceptRecord>();

            while (csv.Read())
            {
                try
                {
                    var record = new ConceptRecord
                    {
                        ConceptId = csv.TryGetField<int>(0, out var conceptId) ? conceptId : 0,
                        ConceptName = csv.TryGetField<string>(1, out var conceptName)
                            ? conceptName
                            : string.Empty,
                        DomainId = csv.TryGetField<string>(2, out var domainId)
                            ? domainId
                            : string.Empty,
                        VocabularyId = csv.TryGetField<string>(3, out var vocabularyId)
                            ? vocabularyId
                            : string.Empty,
                        ConceptClassId = csv.TryGetField<string>(4, out var conceptClassId)
                            ? conceptClassId
                            : string.Empty,
                        StandardConcept = csv.TryGetField<string>(5, out var standardConcept)
                            ? standardConcept
                            : null,
                        ConceptCode = csv.TryGetField<string>(6, out var conceptCode)
                            ? conceptCode
                            : string.Empty,
                        ValidStartDate = csv.TryGetField<DateTime>(7, out var validStartDate)
                            ? validStartDate
                            : DateTime.MinValue,
                        ValidEndDate = csv.TryGetField<DateTime>(8, out var validEndDate)
                            ? validEndDate
                            : DateTime.MaxValue,
                        InvalidReason = csv.TryGetField<string>(9, out var invalidReason)
                            ? invalidReason
                            : null,
                    };

                    batch.Add(record);

                    if (batch.Count >= batchSize)
                    {
                        ImportConceptBatch(sdcCdm, batch);
                        recordsImported += batch.Count;
                        batch.Clear();
                        Console.WriteLine($"Imported {recordsImported} concept records...");
                        return recordsImported;
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error processing record: {ex.Message}");
                }
            }

            // Import any remaining records
            if (batch.Count > 0)
            {
                ImportConceptBatch(sdcCdm, batch);
                recordsImported += batch.Count;
                Console.WriteLine($"Imported {recordsImported} concept records...");
            }

            Console.WriteLine($"Successfully imported {recordsImported} concept records.");
            return recordsImported;
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"Error importing concept CSV: {ex.Message}", ex);
        }
    }

    private static void ImportConceptBatch(ISdcCdm sdcCdm, List<ConceptRecord> batch)
    {
        foreach (var record in batch)
        {
            try
            {
                sdcCdm.InsertConcept(record);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error importing concept {record.ConceptId}: {ex.Message}");
            }
        }
    }
}

/// <summary>
/// Represents a record in the concept table.
/// </summary>
public class ConceptRecord
{
    public int ConceptId { get; set; }
    public string ConceptName { get; set; } = string.Empty;
    public string DomainId { get; set; } = string.Empty;
    public string VocabularyId { get; set; } = string.Empty;
    public string ConceptClassId { get; set; } = string.Empty;
    public string? StandardConcept { get; set; }
    public string ConceptCode { get; set; } = string.Empty;
    public DateTime ValidStartDate { get; set; }
    public DateTime ValidEndDate { get; set; }
    public string? InvalidReason { get; set; }
}
