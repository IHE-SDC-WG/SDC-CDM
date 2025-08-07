using System;
using System.IO;
using SdcCdm;

namespace SdcCdmInSqlite;

public class Program
{
    public static void Main(string[] args)
    {
        Console.WriteLine("OMOP SDC MVP - ECP Data Import Test");
        Console.WriteLine("=====================================");

        // Create a test database
        var dbPath = "test_ecp.db";
        if (File.Exists(dbPath))
        {
            File.Delete(dbPath);
        }

        var sdcCdm = new SdcCdmInSqlite(dbPath, overwrite: true);

        // Build the schema
        Console.WriteLine("Building database schema...");
        sdcCdm.BuildSchema();

        // Read the sample NAACCR V2 message
        var sampleDataPath = "../../../SDC-CDM/sample_data/naaccr_v2/obx-Adrenal.hl7";
        if (!File.Exists(sampleDataPath))
        {
            Console.WriteLine($"Sample data file not found: {sampleDataPath}");
            return;
        }

        var hl7Message = File.ReadAllText(sampleDataPath);
        Console.WriteLine($"Read HL7 message from: {sampleDataPath}");
        Console.WriteLine($"Message length: {hl7Message.Length} characters");

        try
        {
            // Import the NAACCR V2 message
            Console.WriteLine("\nImporting NAACCR V2 message...");
            NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);
            Console.WriteLine("Import completed successfully!");

            // Query the imported data
            Console.WriteLine("\nQuerying imported data...");

            // Get all template instances
            using (var cmd1 = sdcCdm.GetConnection().CreateCommand())
            {
                cmd1.CommandText =
                    @"
                    SELECT 
                        sdc_template_instance_ecp_id,
                        template_name,
                        template_version,
                        template_instance_guid,
                        tumor_site,
                        procedure_type,
                        specimen_laterality,
                        created_datetime
                    FROM sdc_template_instance_ecp
                    ORDER BY created_datetime DESC
                ";

                using var reader = cmd1.ExecuteReader();
                Console.WriteLine("\nTemplate Instances:");
                Console.WriteLine(
                    "ID\tTemplate Name\tVersion\tGUID\tTumor Site\tProcedure\tLaterality"
                );
                Console.WriteLine(
                    "--\t-------------\t-------\t----\t----------\t---------\t----------"
                );

                while (reader.Read())
                {
                    var id = reader.GetInt64(0);
                    var name = reader.GetString(1);
                    var version = reader.GetString(2);
                    var guid = reader.GetString(3);
                    var tumorSite = reader.IsDBNull(4) ? "N/A" : reader.GetString(4);
                    var procedure = reader.IsDBNull(5) ? "N/A" : reader.GetString(5);
                    var laterality = reader.IsDBNull(6) ? "N/A" : reader.GetString(6);
                    var created = reader.GetDateTime(7);

                    Console.WriteLine(
                        $"{id}\t{name}\t{version}\t{guid.Substring(0, 8)}...\t{tumorSite}\t{procedure}\t{laterality}"
                    );
                }
            }

            // Get measurement count
            using (var cmdCount = sdcCdm.GetConnection().CreateCommand())
            {
                cmdCount.CommandText =
                    @"
                    SELECT COUNT(*) as measurement_count
                    FROM measurement 
                    WHERE sdc_template_instance_guid IS NOT NULL
                ";

                var measurementCount = cmdCount.ExecuteScalar();
                Console.WriteLine($"\nTotal ECP measurements imported: {measurementCount}");
            }

            // Get measurements by response type
            using (var cmd2 = sdcCdm.GetConnection().CreateCommand())
            {
                cmd2.CommandText =
                    @"
                    SELECT 
                        sdc_response_type,
                        COUNT(*) as count
                    FROM measurement 
                    WHERE sdc_template_instance_guid IS NOT NULL
                    GROUP BY sdc_response_type
                    ORDER BY count DESC
                ";

                Console.WriteLine("\nMeasurements by Response Type:");
                Console.WriteLine("Type\t\tCount");
                Console.WriteLine("----\t\t-----");

                using var reader2 = cmd2.ExecuteReader();
                while (reader2.Read())
                {
                    var responseType = reader2.GetString(0);
                    var count = reader2.GetInt64(1);
                    Console.WriteLine($"{responseType}\t\t{count}");
                }
            }

            // Show sample measurements
            using (var cmd3 = sdcCdm.GetConnection().CreateCommand())
            {
                cmd3.CommandText =
                    @"
                    SELECT 
                        sdc_question_identifier,
                        sdc_question_text,
                        sdc_response_value,
                        sdc_response_type,
                        sdc_units,
                        sdc_order
                    FROM measurement 
                    WHERE sdc_template_instance_guid IS NOT NULL
                    ORDER BY sdc_order
                    LIMIT 10
                ";

                Console.WriteLine("\nSample Measurements:");
                Console.WriteLine("Question ID\tQuestion Text\tResponse\tType\tUnits\tOrder");
                Console.WriteLine("-----------\t-------------\t--------\t----\t-----\t-----");

                using var reader3 = cmd3.ExecuteReader();
                while (reader3.Read())
                {
                    var questionId = reader3.GetString(0);
                    var questionText = reader3.IsDBNull(1) ? "N/A" : reader3.GetString(1);
                    var response = reader3.IsDBNull(2) ? "N/A" : reader3.GetString(2);
                    var type = reader3.IsDBNull(3) ? "N/A" : reader3.GetString(3);
                    var units = reader3.IsDBNull(4) ? "N/A" : reader3.GetString(4);
                    var order = reader3.IsDBNull(5) ? 0 : reader3.GetInt64(5);

                    Console.WriteLine(
                        $"{questionId}\t{questionText}\t{response}\t{type}\t{units}\t{order}"
                    );
                }
            }

            Console.WriteLine("\nTest completed successfully!");
            Console.WriteLine($"Database file: {Path.GetFullPath(dbPath)}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error during import: {ex.Message}");
            Console.WriteLine($"Stack trace: {ex.StackTrace}");
        }
    }
}
