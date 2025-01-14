using System.Text;
using Hl7.Fhir.Model;
using Hl7.Fhir.Utility;

namespace SdcCdm;

public static class FhirCPDSExporter
{
    public static bool ExportFhirCpds(
        ISdcCdm sdcCdm,
        out Bundle? outCpdsBundle,
        string instanceVersionGuid,
        string? instanceVersionDate = null
    )
    {
        outCpdsBundle = null;
        Bundle cpdsBundle = new();
        // Find the relevant row in the TemplateInstanceClass table
        if (
            !sdcCdm.FindTemplateInstanceClass(
                instanceVersionGuid,
                out long templateInstanceClassPk,
                instanceVersionDate
            )
        )
        {
            if (string.IsNullOrEmpty(instanceVersionDate))
            {
                Console.WriteLine(
                    $@"Could not find requested TemplateInstanceClass in database.
                    instanceVersionGuid: {instanceVersionGuid}"
                );
            }
            else
            {
                Console.WriteLine(
                    $@"Could not find requested TemplateInstanceClass in database.
                    instanceVersionGuid: {instanceVersionGuid}, instanceVersionDate: {instanceVersionDate}"
                );
            }
            return false;
        }
        Console.WriteLine($"Found TemplateInstanceClass: {templateInstanceClassPk}");

        TemplateInstanceRecord record = sdcCdm.GetTemplateInstanceRecord(templateInstanceClassPk);

        cpdsBundle.Id = Guid.NewGuid().ToString();
        cpdsBundle.Type = Bundle.BundleType.Transaction;
        cpdsBundle.Entry = [];

        // Create Bundle resources
        Patient patient = GeneratePatient(sdcCdm, record.PersonFk);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Patient/{patient.Id}",
                },
                Resource = patient,
            }
        );

        Encounter encounter = GenerateEncounter(sdcCdm, record.EncounterFk);
        encounter.Subject = new ResourceReference($"Patient/{patient.Id}");
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Encounter/{encounter.Id}",
                },
                Resource = encounter,
            }
        );

        Practitioner oncologist = GeneratePractitioner(sdcCdm, record.PractitionerFk, 0);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Practitioner/{oncologist.Id}",
                },
                Resource = oncologist,
            }
        );
        Practitioner pathologist = GeneratePractitioner(sdcCdm, null, 1);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Practitioner/{pathologist.Id}",
                },
                Resource = pathologist,
            }
        );

        Organization oncologyCenter = GenerateOrganization(sdcCdm, null, 0);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Organization/{oncologyCenter.Id}",
                },
                Resource = oncologyCenter,
            }
        );
        Organization pathologyLab = GenerateOrganization(sdcCdm, null, 1);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Organization/{pathologyLab.Id}",
                },
                Resource = pathologyLab,
            }
        );

        PractitionerRole oncologistRole = new()
        {
            Id = Guid.NewGuid().ToString(),
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-related-practitioner-role",
                ],
            },
            Practitioner = new ResourceReference($"Practitioner/{oncologist.Id}"),
            Organization = new ResourceReference($"Organization/{oncologyCenter.Id}"),
            Telecom =
            [
                new() { System = ContactPoint.ContactPointSystem.Phone, Value = "000-000-0000" },
            ],
        };
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"PractitionerRole/{oncologistRole.Id}",
                },
                Resource = oncologistRole,
            }
        );
        PractitionerRole pathologistRole = new()
        {
            Id = Guid.NewGuid().ToString(),
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-related-practitioner-role",
                ],
            },
            Practitioner = new ResourceReference($"Practitioner/{pathologist.Id}"),
            Organization = new ResourceReference($"Organization/{pathologyLab.Id}"),
            Telecom =
            [
                new() { System = ContactPoint.ContactPointSystem.Phone, Value = "000-000-0001" },
            ],
        };
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"PractitionerRole/{pathologistRole.Id}",
                },
                Resource = pathologistRole,
            }
        );

        // Create Observation(s)
        // Get all SdcObsClass records for the template instance
        List<SdcObsClass> sdcObsClasses = sdcCdm.GetSdcObsClasses(templateInstanceClassPk);
        List<Observation> observations = GenerateObservationGroups(sdcCdm, sdcObsClasses);
        foreach (Observation observation in observations)
        {
            cpdsBundle.Entry.Add(
                new Bundle.EntryComponent
                {
                    Request = new Bundle.RequestComponent
                    {
                        Method = Bundle.HTTPVerb.POST,
                        Url = $"Observation/{observation.Id}",
                    },
                    Resource = observation,
                }
            );
        }

        // TODO: Gather all specimens from sdcObsClasses
        Specimen specimen = GenerateSpecimen(sdcCdm, null);
        cpdsBundle.Entry.Add(
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Specimen/{specimen.Id}",
                },
                Resource = specimen,
            }
        );

        byte[]? reportTextBase64Bytes = null;
        if (!string.IsNullOrEmpty(record.ReportText))
        {
            byte[] reportTextBytes = Encoding.UTF8.GetBytes(record.ReportText);
            string reportTextBase64 = Convert.ToBase64String(reportTextBytes);
            reportTextBase64Bytes = Encoding.ASCII.GetBytes(reportTextBase64);
        }
        DiagnosticReport diagnosticReport = new()
        {
            Id = Guid.NewGuid().ToString(),
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-diagnostic-report",
                ],
            },
            Status = DiagnosticReport.DiagnosticReportStatus.Final,
            Category =
            [
                new CodeableConcept(
                    "http://hl7.org/fhir/us/cancer-reporting/CodeSystem/us-pathology-codesystem",
                    "LP7839-6",
                    "Pathology"
                ),
            ],
            Code = new CodeableConcept("http://loinc.org", "60568-3", "Pathology synoptic report"),
            Subject = new ResourceReference($"Patient/{patient.Id}"),
            Encounter = new ResourceReference($"Encounter/{encounter.Id}"),
            Effective = new FhirDateTime(DateTime.Now.ToString("yyyy-MM-ddTHH:mm:sszzz")),
            Result = observations
                .FindAll(o =>
                    o.Meta.Profile.Any(p =>
                        p
                        == "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-grouper-observation"
                    )
                )
                .Select(o => new ResourceReference($"Observation/{o.Id}"))
                .ToList(),
            PresentedForm =
            [
                reportTextBase64Bytes.IsNullOrEmpty()
                    ? null
                    : new Attachment { ContentType = "text/xml", Data = reportTextBase64Bytes },
            ],
        };
        cpdsBundle.Entry.Insert(
            0,
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"DiagnosticReport/{diagnosticReport.Id}",
                },
                Resource = diagnosticReport,
            }
        );

        Composition composition = new()
        {
            Id = Guid.NewGuid().ToString(),
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-composition",
                ],
            },

            Type = new CodeableConcept("http://loinc.org", "11526-1", "Pathology Study"),
            Date = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:sszzz"),
            Subject = new ResourceReference($"Patient/{patient.Id}"),
            Author =
            [
                new ResourceReference($"PractitionerRole/{oncologistRole.Id}"),
                new ResourceReference($"PractitionerRole/{pathologistRole.Id}"),
            ],
            Title = "Surgical Pathology Cancer Case Summary",
            Section =
            [
                new Composition.SectionComponent
                {
                    Title = "Lab Report Section",
                    Code = new CodeableConcept(
                        "http://loinc.org",
                        "26436-6",
                        "Laboratory Studies (set)"
                    ),
                    Entry = [new ResourceReference($"DiagnosticReport/{diagnosticReport.Id}")],
                },
            ],
        };
        cpdsBundle.Entry.Insert(
            0,
            new Bundle.EntryComponent
            {
                Request = new Bundle.RequestComponent
                {
                    Method = Bundle.HTTPVerb.POST,
                    Url = $"Composition/{composition.Id}",
                },
                Resource = composition,
            }
        );

        outCpdsBundle = cpdsBundle;
        return true;
    }

    private static Patient GeneratePatient(ISdcCdm sdcCdm, long? personId)
    {
        Patient patient;
        if (personId != null)
        {
            // TODO: Build Patient resource from personId
            patient = new() { Id = Guid.NewGuid().ToString() };
        }
        else
        {
            // Use hardcoded patient data
            patient = new()
            {
                Id = Guid.NewGuid().ToString(),
                Meta = new Meta
                {
                    Profile = ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"],
                },
                Identifier = [new() { System = "urn:NPI", Value = "0000000011" }],
                Name = [new() { Family = "A", Given = ["Patient"] }],
                Gender = AdministrativeGender.Male,
            };
        }
        return patient;
    }

    private static Encounter GenerateEncounter(ISdcCdm sdcCdm, long? visitOccurrenceId)
    {
        Encounter encounter;
        if (visitOccurrenceId != null)
        {
            // TODO: Build Encounter resource from visitOccurrenceId
            encounter = new() { Id = Guid.NewGuid().ToString() };
        }
        else
        {
            // Use hardcoded encounter data
            encounter = new()
            {
                Id = Guid.NewGuid().ToString(),
                Meta = new Meta
                {
                    Profile = ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter"],
                },
                Identifier =
                [
                    new() { System = "http://example.org/hospital", Value = "OncEncounterA" },
                ],
                Status = Encounter.EncounterStatus.Finished,
                Class = new Coding(
                    "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "IMP",
                    "inpatient encounter"
                ),
                Type =
                [
                    new CodeableConcept(
                        "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "726007",
                        "Pathology consultation, comprehensive, records and specimen with report"
                    ),
                ],
            };
        }
        return encounter;
    }

    private static Practitioner GeneratePractitioner(
        ISdcCdm sdcCdm,
        long? providerId,
        int sampleNumber = 0
    )
    {
        Practitioner practitioner;
        if (providerId != null)
        {
            // TODO: Build Practitioner resource from providerId
            practitioner = new() { Id = Guid.NewGuid().ToString() };
        }
        else
        {
            // Use hardcoded practitioner data
            if (sampleNumber == 0)
            {
                practitioner = new()
                {
                    Id = Guid.NewGuid().ToString(),
                    Meta = new Meta
                    {
                        Profile =
                        [
                            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner",
                        ],
                    },
                    Identifier =
                    [
                        new() { System = "http://hl7.org/fhir/sid/us-npi", Value = "0000000021" },
                    ],
                    Name =
                    [
                        new()
                        {
                            Family = "Oncologist",
                            Given = ["John"],
                            Prefix = ["Dr."],
                        },
                    ],
                };
            }
            else if (sampleNumber == 1)
            {
                practitioner = new()
                {
                    Id = Guid.NewGuid().ToString(),
                    Meta = new Meta
                    {
                        Profile =
                        [
                            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner",
                        ],
                    },
                    Identifier =
                    [
                        new() { System = "http://hl7.org/fhir/sid/us-npi", Value = "0000000022" },
                    ],
                    Name =
                    [
                        new()
                        {
                            Family = "Pathologist",
                            Given = ["Jane"],
                            Prefix = ["Dr."],
                        },
                    ],
                };
            }
            else
            {
                throw new Exception("Invalid sample number");
            }
        }
        return practitioner;
    }

    private static Organization GenerateOrganization(
        ISdcCdm sdcCdm,
        long? careSiteId,
        int sampleNumber = 0
    )
    {
        Organization organization;
        if (careSiteId != null)
        {
            // TODO: Build Organization resource from careSiteId
            organization = new() { Id = Guid.NewGuid().ToString() };
        }
        else
        {
            // Use hardcoded organization data
            if (sampleNumber == 0)
            {
                organization = new()
                {
                    Id = Guid.NewGuid().ToString(),
                    Meta = new Meta
                    {
                        Profile =
                        [
                            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-organization",
                        ],
                    },
                    Active = true,
                    Name = "Oncology Center",
                };
            }
            else if (sampleNumber == 1)
            {
                organization = new()
                {
                    Id = Guid.NewGuid().ToString(),
                    Meta = new Meta
                    {
                        Profile =
                        [
                            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-organization",
                        ],
                    },
                    Active = true,
                    Name = "Pathology Lab",
                };
            }
            else
            {
                throw new Exception("Invalid sample number");
            }
        }
        return organization;
    }

    private static List<Observation> GenerateObservationGroups(
        ISdcCdm sdcCdm,
        List<SdcObsClass> sdcObsClasses
    )
    {
        List<Observation> grouperObservations = [];
        List<Observation> allObservations = [];
        foreach (SdcObsClass sdcObsClass in sdcObsClasses)
        {
            if (sdcObsClass.SectionGuid == null || sdcObsClass.QId == null)
            {
                // Skip this sdcObsClass in certain cases
                // TODO: Confirm this is the correct behavior
                continue;
            }
            // Check if a grouper observation exists for the current sdcObsClass.SectionGuid
            Observation? existingGrouper = grouperObservations.Find(o =>
                o.Code.Coding.Any(c =>
                    c.Code == sdcObsClass.SectionGuid && c.System == "http://cap.org/eCC"
                )
            );
            if (existingGrouper == null)
            {
                // Create a new grouper observation for this section
                existingGrouper = new()
                {
                    Id = Guid.NewGuid().ToString(),
                    Meta = new Meta
                    {
                        Profile =
                        [
                            "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-grouper-observation",
                        ],
                    },
                    Identifier =
                    [
                        new()
                        {
                            System = "https://cap.org/eCC",
                            Value = $"urn:uuid:{Guid.NewGuid().ToString()}",
                        },
                    ],
                    Status = ObservationStatus.Final,
                    Code = new CodeableConcept(
                        "http://cap.org/eCC",
                        sdcObsClass.SectionGuid,
                        sdcObsClass.SectionId
                    ),
                };
                grouperObservations.Add(existingGrouper);
                allObservations.Add(existingGrouper);
            }

            // Create Observation resource for this sdcObsClass
            Observation newObservation = new()
            {
                Id = Guid.NewGuid().ToString(),
                Meta = new Meta
                {
                    Profile =
                    [
                        "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/ihe-sdc-ecc-Observation",
                    ],
                },
                Identifier =
                [
                    new()
                    {
                        System = "https://cap.org/eCC",
                        Value = $"urn:uuid:{Guid.NewGuid().ToString()}",
                    },
                ],
                Status = ObservationStatus.Final,
                Code = new CodeableConcept(
                    "http://cap.org/eCC",
                    sdcObsClass.QId,
                    sdcObsClass.QText
                ),
            };

            // TODO: Add value depending on datatype
            if (sdcObsClass.ReponseStringNvarchar != null)
            {
                newObservation.Value = new FhirString(sdcObsClass.ReponseStringNvarchar);
            }

            allObservations.Add(newObservation);

            existingGrouper.HasMember.Add(
                new ResourceReference($"Observation/{newObservation.Id}")
            );
        }
        return allObservations;
    }

    private static Specimen GenerateSpecimen(ISdcCdm sdcCdm, long? specimenPk)
    {
        Specimen specimen;
        if (specimenPk != null)
        {
            // TODO: Build Specimen resource from specimenPk
            specimen = new() { Id = Guid.NewGuid().ToString() };
        }
        else
        {
            // Use hardcoded specimen data
            specimen = new()
            {
                Id = Guid.NewGuid().ToString(),
                Meta = new Meta
                {
                    Profile =
                    [
                        "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-specimen",
                    ],
                },
                Identifier =
                [
                    new()
                    {
                        System = "http://example.org/lis/specimen-identifier-provisioner",
                        Value = "specimen-id",
                    },
                ],
                AccessionIdentifier = new()
                {
                    System = "http://example.org/lis/specimen-identifier-provisioner",
                    Value = "specimen-id-X",
                },
                Status = Specimen.SpecimenStatus.Available,
                Type = new CodeableConcept(
                    "http://loinc.org",
                    "396525008",
                    "Specimen from adrenal gland obtained by needle biopsy (specimen)"
                ),
            };
        }
        return specimen;
    }
}
