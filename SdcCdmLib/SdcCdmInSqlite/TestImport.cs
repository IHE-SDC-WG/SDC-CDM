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
