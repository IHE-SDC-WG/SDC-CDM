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
                sdcCdm.BridgeNaaccrSdcToOmop();
                Console.WriteLine("Bridge completed successfully!");

                // Now query the results to see what was actually stored
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("QUERYING RESULTS");
                Console.WriteLine(new string('=', 80));

                using var connection = sdcCdm.GetConnection();

                // Query report headers
                using var cmd = connection.CreateCommand();
                cmd.CommandText =
                    @"
                    SELECT 
                        sdc_report_id,
                        template_name,
                        template_version,
                        template_instance_guid,
                        report_template_version_id,
                        tumor_site,
                        procedure_type,
                        specimen_laterality
                    FROM sdc.sdc_report 
                    ORDER BY created_datetime DESC
                ";

                using var reader = cmd.ExecuteReader();
                Console.WriteLine("\nSDC Reports:");
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
                        $"{id} | {templateName.Substring(0, Math.Min(15, templateName.Length))}... | {templateVersion.Substring(0, Math.Min(15, templateVersion.Length))}... | {guid.Substring(0, 8)}... | {(reportTemplateVersionId ?? string.Empty).PadRight(Math.Min(20, (reportTemplateVersionId ?? string.Empty).Length)).Substring(0, Math.Min(20, (reportTemplateVersionId ?? string.Empty).Length))} | {tumorSite.Substring(0, Math.Min(12, tumorSite.Length))}... | {procedureType.Substring(0, Math.Min(10, procedureType.Length))}... | {specimenLaterality.Substring(0, Math.Min(10, specimenLaterality.Length))}..."
                    );
                }

                // Also check all columns to see the full picture
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("DETAILED COLUMN ANALYSIS");
                Console.WriteLine(new string('=', 80));

                using var detailCmd = connection.CreateCommand();
                detailCmd.CommandText =
                    "SELECT * FROM sdc.sdc_report ORDER BY created_datetime DESC LIMIT 1";

                using var detailReader = detailCmd.ExecuteReader();
                if (detailReader.Read())
                {
                    Console.WriteLine("\nAll columns in the most recent row:");
                    for (int i = 0; i < detailReader.FieldCount; i++)
                    {
                        var columnName = detailReader.GetName(i);
                        string value = detailReader.IsDBNull(i)
                            ? string.Empty
                            : (detailReader.GetValue(i)?.ToString() ?? string.Empty);
                        var displayValue =
                            value.Length > 50 ? value.Substring(0, 47) + "..." : value;
                        Console.WriteLine($"Column {i}: {columnName, -30} = '{displayValue}'");
                    }
                }

                // Validate three-schema linkage from raw NAACCR values through the note anchor.
                Console.WriteLine("\n" + new string('=', 80));
                Console.WriteLine("CHECKING THREE-SCHEMA LINKAGE");
                Console.WriteLine(new string('=', 80));

                using var qaCmd = connection.CreateCommand();
                qaCmd.CommandText =
                    @"
                    SELECT nv.naaccr_value_id, nv.report_accession, nv.item_num,
                           nv.value_code, nv.value_num, nv.value_unit_source,
                           n.note_id, m.measurement_id, m.value_as_number,
                           m.value_source_value, m.unit_source_value
                    FROM naaccr.naaccr_value nv
                    LEFT JOIN sdc.sdc_report sr
                      ON sr.sdc_report_id = nv.sdc_report_id
                    LEFT JOIN omop.note n
                      ON n.note_source_value = sr.report_accession
                     AND n.person_id = sr.person_id
                    LEFT JOIN omop.measurement m
                      ON m.measurement_event_id = n.note_id
                     AND m.meas_event_field_concept_id = 1147289
                     AND m.measurement_source_value = CAST(nv.item_num AS TEXT)
                    ORDER BY nv.naaccr_value_id, m.measurement_id
                    LIMIT 20;
                ";

                using var qaReader = qaCmd.ExecuteReader();
                Console.WriteLine(
                    "RawID | Accession | Item | RawCode | RawNum | RawUnits | NoteId | MeasID | MeasNum | MeasVal | MeasUnits"
                );
                Console.WriteLine(
                    "------+-----------+------+---------+--------+----------+--------+--------+---------+---------+----------"
                );
                while (qaReader.Read())
                {
                    var rawId = qaReader.GetInt64(0);
                    var accession = qaReader.IsDBNull(1) ? "" : qaReader.GetString(1);
                    var itemNum = qaReader.GetInt64(2);
                    var rawCode = qaReader.IsDBNull(3) ? "" : qaReader.GetString(3);
                    var rawNum = qaReader.IsDBNull(4) ? (double?)null : qaReader.GetDouble(4);
                    var rawUnits = qaReader.IsDBNull(5) ? "" : qaReader.GetString(5);
                    var noteId = qaReader.IsDBNull(6) ? (long?)null : qaReader.GetInt64(6);
                    var measId = qaReader.IsDBNull(7) ? (long?)null : qaReader.GetInt64(7);
                    var measNum = qaReader.IsDBNull(8) ? (double?)null : qaReader.GetDouble(8);
                    var measVal = qaReader.IsDBNull(9) ? "" : qaReader.GetString(9);
                    var measUnits = qaReader.IsDBNull(10) ? "" : qaReader.GetString(10);
                    Console.WriteLine(
                        $"{rawId} | {accession} | {itemNum} | {rawCode} | {rawNum?.ToString() ?? ""} | {rawUnits} | {noteId?.ToString() ?? ""} | {measId?.ToString() ?? ""} | {measNum?.ToString() ?? ""} | {measVal} | {measUnits}"
                    );
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
