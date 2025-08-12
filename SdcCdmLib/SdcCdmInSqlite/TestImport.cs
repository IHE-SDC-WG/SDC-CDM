using System;
using System.IO;
using SdcCdm;

namespace SdcCdmInSqlite
{
    class TestImport
    {
        static void Main(string[] args)
        {
            Console.WriteLine("Testing NAACCR Import Functionality");
            Console.WriteLine("==================================");

            // Create a test database
            var dbPath = "test_import.db";

            // Remove existing database if it exists
            if (File.Exists(dbPath))
            {
                File.Delete(dbPath);
                Console.WriteLine($"Removed existing database: {dbPath}");
            }

            // Create new database instance
            var sdcCdm = new SdcCdmInSqlite(dbPath, overwrite: true);

            // Build the schema
            Console.WriteLine("Building database schema...");
            sdcCdm.BuildSchema();
            Console.WriteLine("Schema built successfully!");

            // Test with the Thyroid HL7 file
            var hl7FilePath = "../../sample_data/naaccr_v2/24-11-000312-2.txt.hl7";

            if (!File.Exists(hl7FilePath))
            {
                Console.WriteLine($"HL7 file not found: {hl7FilePath}");
                Console.WriteLine("Current directory: " + Directory.GetCurrentDirectory());
                Console.WriteLine("Available files:");
                foreach (var file in Directory.GetFiles("."))
                {
                    Console.WriteLine($"  {file}");
                }
                return;
            }

            try
            {
                Console.WriteLine($"\nImporting HL7 file: {hl7FilePath}");
                var hl7Message = File.ReadAllText(hl7FilePath);
                Console.WriteLine($"File size: {hl7Message.Length} characters");

                // Import the NAACCR V2 message
                NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);
                Console.WriteLine("Import completed successfully!");

                // Now query the results to see what was actually stored
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("QUERYING RESULTS");
                Console.WriteLine(new string('=', 80));

                using var connection = sdcCdm.GetConnection();

                // Query template instances
                using var cmd = connection.CreateCommand();
                cmd.CommandText =
                    @"
                    SELECT 
                        sdc_template_instance_ecp_id,
                        template_name,
                        template_version,
                        template_instance_guid,
                        report_template_version_id,
                        tumor_site,
                        procedure_type,
                        specimen_laterality
                    FROM sdc_template_instance_ecp 
                    ORDER BY created_datetime DESC
                ";

                using var reader = cmd.ExecuteReader();
                Console.WriteLine("\nTemplate Instances:");
                Console.WriteLine(
                    "ID | Template Name | Version | GUID | Report Template Version ID | Tumor Site | Procedure | Laterality"
                );
                Console.WriteLine(
                    "---+----------------+---------+------+---------------------------+------------+-----------+-----------"
                );

                while (reader.Read())
                {
                    var id = reader.GetInt64(0);
                    var templateName = reader.GetString(1);
                    var templateVersion = reader.GetString(2);
                    var guid = reader.GetString(3);
                    var reportTemplateVersionId = reader.IsDBNull(4) ? "NULL" : reader.GetString(4);
                    var tumorSite = reader.IsDBNull(5) ? "NULL" : reader.GetString(5);
                    var procedureType = reader.IsDBNull(6) ? "NULL" : reader.GetString(6);
                    var specimenLaterality = reader.IsDBNull(7) ? "NULL" : reader.GetString(7);

                    Console.WriteLine(
                        $"{id} | {templateName.Substring(0, Math.Min(15, templateName.Length))}... | {templateVersion.Substring(0, Math.Min(15, templateVersion.Length))}... | {guid.Substring(0, 8)}... | {reportTemplateVersionId.Substring(0, Math.Min(20, reportTemplateVersionId.Length))}... | {tumorSite.Substring(0, Math.Min(12, tumorSite.Length))}... | {procedureType.Substring(0, Math.Min(10, procedureType.Length))}... | {specimenLaterality.Substring(0, Math.Min(10, specimenLaterality.Length))}..."
                    );
                }

                // Also check all columns to see the full picture
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("DETAILED COLUMN ANALYSIS");
                Console.WriteLine(new string('=', 80));

                using var detailCmd = connection.CreateCommand();
                detailCmd.CommandText =
                    "SELECT * FROM sdc_template_instance_ecp ORDER BY created_datetime DESC LIMIT 1";

                using var detailReader = detailCmd.ExecuteReader();
                if (detailReader.Read())
                {
                    Console.WriteLine("\nAll columns in the most recent row:");
                    for (int i = 0; i < detailReader.FieldCount; i++)
                    {
                        var columnName = detailReader.GetName(i);
                        var value = detailReader.IsDBNull(i)
                            ? "NULL"
                            : detailReader.GetValue(i).ToString();
                        var displayValue =
                            value.Length > 50 ? value.Substring(0, 47) + "..." : value;
                        Console.WriteLine($"Column {i}: {columnName, -30} = '{displayValue}'");
                    }
                }

                // Check if sdc_units are being stored in the measurement table
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("CHECKING SDC_UNITS IN MEASUREMENT TABLE");
                Console.WriteLine(new string('=', 80));

                using var unitsCmd = connection.CreateCommand();
                unitsCmd.CommandText =
                    "SELECT sdc_question_identifier, sdc_question_text, sdc_response_value, sdc_response_type, sdc_units, sdc_order FROM measurement WHERE sdc_template_instance_guid IS NOT NULL AND sdc_units IS NOT NULL ORDER BY sdc_order";

                using var unitsReader = unitsCmd.ExecuteReader();
                if (unitsReader.HasRows)
                {
                    Console.WriteLine("\nMeasurements with units found:");
                    Console.WriteLine("Question ID | Question | Response | Type | Units | Order");
                    Console.WriteLine("------------|----------|----------|------|-------|------");

                    while (unitsReader.Read())
                    {
                        var questionId = unitsReader.GetString(0);
                        var questionText = unitsReader.IsDBNull(1)
                            ? "N/A"
                            : unitsReader.GetString(1);
                        var response = unitsReader.IsDBNull(2) ? "N/A" : unitsReader.GetString(2);
                        var type = unitsReader.IsDBNull(3) ? "N/A" : unitsReader.GetString(3);
                        var units = unitsReader.GetString(4);
                        var order = unitsReader.IsDBNull(5) ? 0 : unitsReader.GetInt64(5);

                        Console.WriteLine(
                            $"{questionId.Substring(0, Math.Min(12, questionId.Length))}... | {questionText.Substring(0, Math.Min(10, questionText.Length))}... | {response.Substring(0, Math.Min(10, response.Length))}... | {type} | {units} | {order}"
                        );
                    }
                }
                else
                {
                    Console.WriteLine(
                        "\nNo measurements with units found. Checking all measurements:"
                    );

                    using var allUnitsCmd = connection.CreateCommand();
                    allUnitsCmd.CommandText =
                        "SELECT sdc_question_identifier, sdc_response_type, sdc_units FROM measurement WHERE sdc_template_instance_guid IS NOT NULL ORDER BY sdc_order LIMIT 10";

                    using var allUnitsReader = allUnitsCmd.ExecuteReader();
                    Console.WriteLine("Question ID | Response Type | Units");
                    Console.WriteLine("------------|---------------|-------");

                    while (allUnitsReader.Read())
                    {
                        var questionId = allUnitsReader.GetString(0);
                        var responseType = allUnitsReader.GetString(1);
                        var units = allUnitsReader.IsDBNull(2)
                            ? "NULL"
                            : allUnitsReader.GetString(2);

                        Console.WriteLine(
                            $"{questionId.Substring(0, Math.Min(12, questionId.Length))}... | {responseType} | {units}"
                        );
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error during import: {ex.Message}");
                Console.WriteLine($"Stack trace: {ex.StackTrace}");
            }

            Console.WriteLine("\nTest completed!");
        }
    }
}
