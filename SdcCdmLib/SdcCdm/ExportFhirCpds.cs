using System.Text;
using Hl7.Fhir.Model;
using Hl7.Fhir.Utility;

namespace SdcCdm;

public static class FhirCPDSExporter
{
    public static Bundle? ExportFhirCpds(
        ISdcCdm sdcCdm,
        string instanceVersionGuid,
        string? instanceVersionDate = null
    )
    {
        // Find the relevant row in the TemplateInstanceClass table
        long? templateInstanceClassPk = sdcCdm.FindTemplateInstanceClass(
            instanceVersionGuid,
            instanceVersionDate
        );
        if (!templateInstanceClassPk.HasValue)
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
            return null;
        }
        long templateInstanceClassPkValue = templateInstanceClassPk.Value;
        Console.WriteLine($"Found TemplateInstanceClass: {templateInstanceClassPkValue}");

        TemplateInstanceRecord? record =
            sdcCdm.GetTemplateInstanceRecord(templateInstanceClassPkValue)
            ?? throw new Exception(
                $"Failed to retrieve TemplateInstanceRecord for template instance class {templateInstanceClassPkValue}"
            );

        // Create Bundle resources
        Bundle cpdsBundle = new()
        {
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-exchange-bundle",
                ],
            },
            Id = Guid.NewGuid().ToString(),
            Type = Bundle.BundleType.Transaction,
            TimestampElement = Instant.Now(),
            Entry = [],
        };

        // TODO: Use template_instance.person_id
        Patient? patient = FindExistingPatient(sdcCdm);
        if (patient == null)
        {
            Console.WriteLine("Generating new patient.");
            patient = GeneratePatient(sdcCdm, record.PersonFk);
        }
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(patient));

        // TODO: Use template_instance.visit_occurrence_id
        Encounter encounter = GenerateEncounter(sdcCdm, record.EncounterFk);
        encounter.Subject = new ResourceReference($"Patient/{patient.Id}");
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(encounter));

        // TODO: Use template_instance.provider_id
        Practitioner oncologist = GeneratePractitioner(sdcCdm, record.PractitionerFk, 0);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(oncologist));
        Practitioner pathologist = GeneratePractitioner(sdcCdm, null, 1);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(pathologist));

        // TODO: Use provider.care_site_id
        Organization oncologyCenter = GenerateOrganization(sdcCdm, null, 0);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(oncologyCenter));
        Organization pathologyLab = GenerateOrganization(sdcCdm, null, 1);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(pathologyLab));

        // TODO: Use provider.specialty_concept_id/specialty_source_concept_id?
        PractitionerRole oncologistRole = GeneratePractitionerRole(oncologist, oncologyCenter);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(oncologistRole));
        PractitionerRole pathologistRole = GeneratePractitionerRole(pathologist, pathologyLab);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(pathologistRole));

        // Create Observation(s)
        // Get all SdcObsClass records for the template instance
        List<SdcObsClass> sdcObsClasses = sdcCdm.GetSdcObsClasses(templateInstanceClassPkValue);
        List<Observation> observations = GenerateObservationGroups(sdcCdm, sdcObsClasses);
        foreach (Observation observation in observations)
        {
            cpdsBundle.Entry.Add(CreateEntryComponentForPost(observation));
        }

        // TODO: Gather all specimens by observation_specimens.sdc_observation_id
        Specimen specimen = GenerateSpecimen(sdcCdm, null);
        cpdsBundle.Entry.Add(CreateEntryComponentForPost(specimen));

        byte[]? reportTextBase64Bytes = null;
        if (!string.IsNullOrEmpty(record.ReportText))
        {
            byte[] reportTextBytes = Encoding.UTF8.GetBytes(record.ReportText);
            string reportTextBase64 = Convert.ToBase64String(reportTextBytes);
            reportTextBase64Bytes = Encoding.ASCII.GetBytes(reportTextBase64);
        }
        else
        {
            Console.WriteLine(
                "Warning: Cannot populate DiagnosticReport.presentedForm because no report text found for this template instance."
            );
        }
        // TODO: Add performer, resultsInterpreter, and specimen
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
            Identifier =
            [
                new() { System = "https://cap.org/eCC", Value = $"urn:uuid:{Guid.NewGuid()}" },
            ],
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
            Effective = FhirDateTime.Now(),
            Result =
            [
                .. observations
                    .FindAll(o =>
                        o.Meta.Profile.Any(p =>
                            p
                            == "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-grouper-observation"
                        )
                    )
                    .Select(o => new ResourceReference($"Observation/{o.Id}")),
            ],
            PresentedForm =
            [
                reportTextBase64Bytes.IsNullOrEmpty()
                    ? null
                    : new Attachment { ContentType = "text/xml", Data = reportTextBase64Bytes },
            ],
        };
        cpdsBundle.Entry.Insert(0, CreateEntryComponentForPost(diagnosticReport));

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
            DateElement = FhirDateTime.Now(),
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
        cpdsBundle.Entry.Insert(0, CreateEntryComponentForPost(composition));

        return cpdsBundle;
    }

    private static Bundle.EntryComponent CreateEntryComponentForPost(Resource resource)
    {
        return new()
        {
            Request = new Bundle.RequestComponent
            {
                Method = Bundle.HTTPVerb.POST,
                Url = $"{resource.TypeName}/{resource.Id}",
            },
            Resource = resource,
        };
    }

    private static Patient? FindExistingPatient(ISdcCdm sdcCdm)
    {
        // Hardcoded patient identifier for demonstration
        string hardcodedPatientIdentifier = "0000000011";

        // Implement the search logic here. This is a placeholder for the actual search.
        // For example, you might have a method like sdcCdm.FindPersonByIdentifier
        long? foundPersonPk = sdcCdm.FindPersonByIdentifier(hardcodedPatientIdentifier);

        if (foundPersonPk != null)
        {
            // Retrieve patient details using foundPersonPk
            // This is a placeholder for actual retrieval logic
            return new Patient
            {
                Id = foundPersonPk.ToString(),
                // Populate other necessary fields
            };
        }

        return null;
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

    private static PractitionerRole GeneratePractitionerRole(
        Practitioner practitioner,
        Organization organization
    )
    {
        // TODO: Set PractitionerRole code and specialty
        return new()
        {
            Id = Guid.NewGuid().ToString(),
            Meta = new Meta
            {
                Profile =
                [
                    "http://hl7.org/fhir/us/cancer-reporting/StructureDefinition/us-pathology-related-practitioner-role",
                ],
            },
            Practitioner = new ResourceReference($"Practitioner/{practitioner.Id}"),
            Organization = new ResourceReference($"Organization/{organization.Id}"),
            Telecom =
            [
                new() { System = ContactPoint.ContactPointSystem.Phone, Value = "000-000-0000" },
            ],
        };
    }

    private static List<Observation> GenerateObservationGroups(
        ISdcCdm sdcCdm,
        List<SdcObsClass> sdcObsClasses
    )
    {
        List<Observation> grouperObservations = [];
        List<Observation> allObservations = []; // Returned by this function
        foreach (SdcObsClass sdcObsClass in sdcObsClasses)
        {
            if (sdcObsClass.SectionGuid == null || sdcObsClass.QId == null)
            {
                // Skip this sdcObsClass in certain cases
                // TODO: Confirm this is the correct behavior
                continue;
            }
            // Check if a grouper observation exists for the current sdcObsClass.SectionGuid
            Observation? sectionGrouper = grouperObservations.Find(o =>
                o.Code.Coding.Any(c =>
                    c.Code == sdcObsClass.SectionGuid && c.System == "http://cap.org/eCC"
                )
            );
            if (sectionGrouper == null)
            {
                // No grouper observation exists for this section, so create one for it
                sectionGrouper = new()
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
                            Value = $"urn:uuid:{Guid.NewGuid()}",
                        },
                    ],
                    Status = ObservationStatus.Final,
                    // TODO: Confirm this is the correct way to set the code
                    Code = new CodeableConcept(
                        "http://cap.org/eCC",
                        sdcObsClass.SectionGuid,
                        sdcObsClass.SectionId
                    ),
                };
                grouperObservations.Add(sectionGrouper);
                allObservations.Add(sectionGrouper);
            }

            // Create a FHIR Observation for this SDC Observation
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
                    new() { System = "https://cap.org/eCC", Value = $"urn:uuid:{Guid.NewGuid()}" },
                ],
                Status = ObservationStatus.Final,
                Code = new CodeableConcept(
                    "http://cap.org/eCC",
                    sdcObsClass.QId,
                    sdcObsClass.QText
                ),
                // TODO: Set value depending on SDC Observation datatype
                Value = new FhirString(sdcObsClass.Response),
            };

            allObservations.Add(newObservation);

            sectionGrouper.HasMember.Add(new ResourceReference($"Observation/{newObservation.Id}"));
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
