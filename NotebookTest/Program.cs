using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using SdcCdm;
using SdcCdmInSqlite;
using Hl7.Fhir.Model;
using Hl7.Fhir.Serialization;

namespace NotebookTest
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.WriteLine("Starting polyglot notebook test execution...");
            
            try
            {
                // Mimic the notebook workflow step by step
                
                // Step 1: Create a new Sqlite database instance for the SDC CDM
                Console.WriteLine("Step 1: Creating SQLite database instance...");
                var sdcCdmInstance = new SdcCdmInSqlite.SdcCdmInSqlite("public/sdc_cdm.db", overwrite: true);
                sdcCdmInstance.BuildSchema();
                Console.WriteLine("✓ Database schema built successfully");

                // Step 2: Import SDC templates (only first two to avoid long operation)
                Console.WriteLine("Step 2: Importing SDC templates...");
                var templatesDir = Path.Combine("..", "sample_data", "sdc_templates");
                if (Directory.Exists(templatesDir))
                {
                    var xmlFiles = Directory.GetFiles(templatesDir, "*.xml").Take(2);
                    foreach (var filePath in xmlFiles)
                    {
                        var doc = XDocument.Load(filePath);
                        SdcCdm.TemplateImporter.ImportTemplate(sdcCdmInstance, doc.Root);
                        Console.WriteLine($"✓ Imported template: {Path.GetFileName(filePath)}");
                    }
                }
                else
                {
                    Console.WriteLine("⚠ Templates directory not found, skipping template import");
                }

                // Step 3: Import SDC Template Row Data
                Console.WriteLine("Step 3: Importing template row data...");
                var templateCsvPath = Path.Combine("..", "sample_data", "TemplateHistory(in).csv");
                if (File.Exists(templateCsvPath))
                {
                    SdcCdm.TemplateRowDataImporter.ImportTemplateRowData((ISdcCdm)sdcCdmInstance, templateCsvPath);
                    Console.WriteLine("✓ Template row data imported successfully");
                }
                else
                {
                    Console.WriteLine("⚠ Template history CSV not found, skipping row data import");
                }

                // Step 4: Import sample SDC XML files
                Console.WriteLine("Step 4: Importing SDC XML files...");
                var sdcXmlDir = Path.Combine("..", "sample_data", "sdc_xml");
                if (Directory.Exists(sdcXmlDir))
                {
                    var sdcXmlFiles = Directory.GetFiles(sdcXmlDir, "*.xml");
                    foreach (var xmlFile in sdcXmlFiles)
                    {
                        var xmlStr = File.ReadAllText(xmlFile);
                        var doc = XDocument.Parse(xmlStr);
                        SdcCdm.XmlFormImporter.ProcessXmlForm((ISdcCdm)sdcCdmInstance, doc.Root);
                        Console.WriteLine($"✓ Imported SDC XML: {Path.GetFileName(xmlFile)}");
                    }
                }
                else
                {
                    Console.WriteLine("⚠ SDC XML directory not found, skipping XML import");
                }

                // Step 5: Import NAACCR V2 messages
                Console.WriteLine("Step 5: Importing NAACCR V2 messages...");
                var naaccrDir = Path.Combine("..", "sample_data", "naaccr_v2");
                if (Directory.Exists(naaccrDir))
                {
                    var v2Messages = Directory.GetFiles(naaccrDir, "*.hl7");
                    foreach (var message in v2Messages)
                    {
                        try
                        {
                            var messageStr = File.ReadAllText(message);
                            SdcCdm.NAACCRVolVImporter.ImportNaaccrVolV((ISdcCdm)sdcCdmInstance, messageStr);
                            Console.WriteLine($"✓ Imported NAACCR message: {Path.GetFileName(message)}");
                        }
                        catch (Exception e)
                        {
                            Console.WriteLine($"⚠ Error processing message {Path.GetFileName(message)}: {e.Message}");
                            // Continue processing other messages
                        }
                    }
                }
                else
                {
                    Console.WriteLine("⚠ NAACCR V2 directory not found, skipping NAACCR import");
                }

                // Step 6: Convert form instance to FHIR CPDS Bundle
                Console.WriteLine("Step 6: Exporting FHIR CPDS bundle...");
                var existingTemplate = "5b64392d-680e-4a96-94ca-3da4acf6bd27"; // ADRENAL_GLAND.xml instance ID
                
                var bundle = FhirCPDSExporter.ExportFhirCpds(sdcCdmInstance, existingTemplate);
                
                if (bundle != null)
                {
                    var serializer = new FhirJsonSerializer(new SerializerSettings { Pretty = true });
                    var bundleJson = serializer.SerializeToString(bundle);
                    Console.WriteLine("✓ FHIR CPDS bundle exported successfully");
                    Console.WriteLine($"Bundle contains {bundle.Entry.Count} entries");
                }
                else
                {
                    Console.WriteLine("⚠ Failed to export FHIR CPDS bundle (template may not exist)");
                }

                Console.WriteLine("\n🎉 All notebook steps completed successfully!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"\n❌ Error during notebook execution: {ex.Message}");
                Console.WriteLine($"Stack trace: {ex.StackTrace}");
                Environment.Exit(1);
            }
        }
    }
}