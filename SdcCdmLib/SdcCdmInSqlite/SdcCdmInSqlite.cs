using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using SdcCdm;
using SdcCdmInSqlite.Entities;

namespace SdcCdmInSqlite;

public class SdcCdmInSqlite : ISdcCdm
{
    /// <summary>
    /// Inserts a concept record into the concept table using Entity Framework Core.
    /// </summary>
    /// <param name="concept">The concept record to insert.</param>
    /// <returns>The ID of the inserted concept.</returns>
    public async Task<long> InsertConceptAsync(ConceptRecord concept)
    {
        var conceptEntity = new ConceptEntity
        {
            ConceptId = concept.ConceptId,
            ConceptName = concept.ConceptName,
            DomainId = concept.DomainId,
            VocabularyId = concept.VocabularyId,
            ConceptClassId = concept.ConceptClassId,
            StandardConcept = concept.StandardConcept,
            ConceptCode = concept.ConceptCode,
            ValidStartDate = concept.ValidStartDate,
            ValidEndDate = concept.ValidEndDate,
            InvalidReason = concept.InvalidReason,
        };

        _dbContext.Concepts.Add(conceptEntity);
        await _dbContext.SaveChangesAsync();

        return conceptEntity.ConceptId;
    }

    /// <summary>
    /// Inserts a concept record into the concept table.
    /// This is the synchronous version for backward compatibility.
    /// </summary>
    /// <param name="concept">The concept record to insert.</param>
    /// <returns>The ID of the inserted concept.</returns>
    public long InsertConcept(ConceptRecord concept)
    {
        return InsertConceptAsync(concept).GetAwaiter().GetResult();
    }

    private static readonly ILoggerFactory _loggerFactory = LoggerFactory.Create(builder =>
    {
        builder.AddConsole();
    });
    public ILogger Logger { get; set; }

    public SdcCdmInSqlite(string dbFilePath, bool inMemory = false, bool overwrite = false)
    {
        this.dbFilePath = dbFilePath;
        this.isMemoryDb = inMemory;
        string connectionString = new SqliteConnectionStringBuilder()
        {
            Mode = inMemory ? SqliteOpenMode.Memory : SqliteOpenMode.ReadWriteCreate,
            DataSource = dbFilePath,
        }.ToString();
        if (overwrite && !inMemory && File.Exists(dbFilePath))
        {
            File.Delete(dbFilePath);
        }
        this.connection = new(connectionString);
        connection.Open();

        // Initialize EF Core DbContext
        this._dbContext = new SdcCdmDbContext(connection);

        Logger = _loggerFactory.CreateLogger<SdcCdmInSqlite>();
    }

    private readonly string dbFilePath;
    private readonly SqliteConnection connection;
    private readonly bool isMemoryDb;
    private readonly SdcCdmDbContext _dbContext;

    public void BuildSchema()
    {
        // Get the current assembly
        var assembly = System.Reflection.Assembly.GetExecutingAssembly();

        // Determine the resource name prefix for files in the 'sqlite' folder.
        // This typically follows the pattern: "{DefaultNamespace}.database.ddl.sqlite."
        string resourcePrefix = "SdcCdmInSqlite.database.ddl.sqlite.";
        resourcePrefix = "";

        // Retrieve all resource names that match the .sql files in the desired folder.
        var sqlResourceNames = assembly
            .GetManifestResourceNames()
            .Where(name =>
                name.StartsWith(resourcePrefix, StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".sql", StringComparison.OrdinalIgnoreCase)
            )
            .OrderBy(name => name) // Sort them alphabetically
            .ToList();

        System.Diagnostics.Debug.WriteLine($"Found {sqlResourceNames.Count} SQL scripts.");

        foreach (var resourceName in sqlResourceNames)
        {
            // Extract a friendly file name (optional)
            string fileName = resourceName[resourcePrefix.Length..];

            Logger.LogTrace("Executing {fileName}...", fileName);

            // Read the embedded SQL script
            using (Stream? stream = assembly.GetManifestResourceStream(resourceName))
            {
                if (stream == null)
                {
                    throw new Exception(
                        $"Could not find SQL script {resourceName}, which is required for the database schema."
                    );
                }

                using StreamReader reader = new(stream);
                string sqlScript = reader.ReadToEnd();

                using var command = connection.CreateCommand();
                command.CommandText = sqlScript;
                command.ExecuteNonQuery();
            }

            Logger.LogTrace("Finished executing {fileName}.", fileName);
        }

        Logger.LogInformation("Finished building schema.");
    }

    /// <summary>
    /// Writes a template SDC class using Entity Framework Core.
    /// </summary>
    /// <param name="sdcformdesignid">The SDC form design ID.</param>
    /// <param name="baseuri">The base URI.</param>
    /// <param name="lineage">The lineage.</param>
    /// <param name="version">The version.</param>
    /// <param name="fulluri">The full URI.</param>
    /// <param name="formtitle">The form title.</param>
    /// <param name="sdc_xml">The SDC XML.</param>
    /// <param name="doctype">The document type.</param>
    /// <returns>The ID of the inserted template SDC.</returns>
    public async Task<long> WriteTemplateSdcClassAsync(
        string sdcformdesignid,
        string? baseuri = null,
        string? lineage = null,
        string? version = null,
        string? fulluri = null,
        string? formtitle = null,
        string? sdc_xml = null,
        string? doctype = null
    )
    {
        var templateSdcEntity = new TemplateSdcEntity
        {
            SdcFormDesignSdcid = sdcformdesignid,
            BaseUri = baseuri,
            Lineage = lineage,
            Version = version,
            FullUri = fulluri,
            FormTitle = formtitle,
            SdcXml = sdc_xml,
            DocType = doctype,
        };

        _dbContext.TemplateSdcs.Add(templateSdcEntity);
        await _dbContext.SaveChangesAsync();

        return templateSdcEntity.TemplateSdcId;
    }

    public long WriteTemplateSdcClass(
        string sdcformdesignid,
        string? baseuri,
        string? lineage,
        string? version,
        string? fulluri,
        string? formtitle,
        string? sdc_xml,
        string? doctype
    )
    {
        return WriteTemplateSdcClassAsync(
                sdcformdesignid,
                baseuri,
                lineage,
                version,
                fulluri,
                formtitle,
                sdc_xml,
                doctype
            )
            .GetAwaiter()
            .GetResult();
    }

    /// <summary>
    /// Writes a template instance class using Entity Framework Core.
    /// </summary>
    /// <param name="templatesdc_fk">The template SDC foreign key.</param>
    /// <param name="template_instance_version_guid">The template instance version GUID.</param>
    /// <param name="template_instance_version_uri">The template instance version URI.</param>
    /// <param name="instance_version_date">The instance version date.</param>
    /// <param name="diag_report_props">The diagnostic report properties.</param>
    /// <param name="surg_path_id">The surgical path ID.</param>
    /// <param name="person_fk">The person foreign key.</param>
    /// <param name="encounter_fk">The encounter foreign key.</param>
    /// <param name="practitioner_fk">The practitioner foreign key.</param>
    /// <param name="report_text">The report text.</param>
    /// <returns>The ID of the inserted template instance.</returns>
    public async Task<long> WriteTemplateInstanceClassAsync(
        long templatesdc_fk,
        string? template_instance_version_guid = null,
        string? template_instance_version_uri = null,
        string? instance_version_date = null,
        string? diag_report_props = null,
        string? surg_path_id = null,
        string? person_fk = null,
        string? encounter_fk = null,
        string? practitioner_fk = null,
        string? report_text = null
    )
    {
        var templateInstanceEntity = new TemplateInstanceEntity
        {
            TemplateSdcId = templatesdc_fk,
            TemplateInstanceVersionGuid = template_instance_version_guid,
            TemplateInstanceVersionUri = template_instance_version_uri,
            InstanceVersionDate = instance_version_date,
            DiagReportProps = diag_report_props,
            SurgPathSdcid = surg_path_id,
            PersonId = person_fk != null ? long.Parse(person_fk) : null,
            VisitOccurrenceId = encounter_fk != null ? long.Parse(encounter_fk) : null,
            ProviderId = practitioner_fk != null ? long.Parse(practitioner_fk) : null,
            ReportText = report_text,
        };

        _dbContext.TemplateInstances.Add(templateInstanceEntity);
        await _dbContext.SaveChangesAsync();

        return templateInstanceEntity.TemplateInstanceId;
    }

    public long WriteTemplateInstanceClass(
        long templatesdc_fk,
        string? template_instance_version_guid,
        string? template_instance_version_uri,
        string? instance_version_date,
        string? diag_report_props,
        string? surg_path_id,
        string? person_fk,
        string? encounter_fk,
        string? practitioner_fk,
        string? report_text
    )
    {
        return WriteTemplateInstanceClassAsync(
                templatesdc_fk,
                template_instance_version_guid,
                template_instance_version_uri,
                instance_version_date,
                diag_report_props,
                surg_path_id,
                person_fk,
                encounter_fk,
                practitioner_fk,
                report_text
            )
            .GetAwaiter()
            .GetResult();
    }

    /// <summary>
    /// Writes an SDC observation class using Entity Framework Core.
    /// </summary>
    /// <param name="template_instance_class_fk">The template instance class foreign key.</param>
    /// <param name="parent_observation_id">The parent observation ID.</param>
    /// <param name="section_id">The section ID.</param>
    /// <param name="section_guid">The section GUID.</param>
    /// <param name="q_text">The question text.</param>
    /// <param name="q_instance_guid">The question instance GUID.</param>
    /// <param name="q_id">The question ID.</param>
    /// <param name="li_text">The list item text.</param>
    /// <param name="li_id">The list item ID.</param>
    /// <param name="li_instance_guid">The list item instance GUID.</param>
    /// <param name="sdc_order">The SDC order.</param>
    /// <param name="response">The response.</param>
    /// <param name="units">The units.</param>
    /// <param name="units_system">The units system.</param>
    /// <param name="datatype">The data type.</param>
    /// <param name="response_int">The response integer.</param>
    /// <param name="response_float">The response float.</param>
    /// <param name="response_datetime">The response datetime.</param>
    /// <param name="reponse_string_nvarchar">The response string.</param>
    /// <param name="li_parent_guid">The list item parent GUID.</param>
    /// <returns>The ID of the inserted SDC observation.</returns>
    public async Task<long> WriteSdcObsClassAsync(
        long template_instance_class_fk,
        long? parent_observation_id = null,
        string? section_id = null,
        string? section_guid = null,
        string? q_text = null,
        string? q_instance_guid = null,
        string? q_id = null,
        string? li_text = null,
        string? li_id = null,
        string? li_instance_guid = null,
        string? sdc_order = null,
        string? response = null,
        string? units = null,
        string? units_system = null,
        string? datatype = null,
        long? response_int = null,
        double? response_float = null,
        DateTime? response_datetime = null,
        string? reponse_string_nvarchar = null,
        string? li_parent_guid = null
    )
    {
        var sdcObservationEntity = new SdcObservationEntity
        {
            TemplateInstanceId = template_instance_class_fk,
            ParentObservationId = parent_observation_id,
            ParentInstanceGuid = null, // Always null as per original implementation
            SectionSdcid = section_id,
            SectionGuid = section_guid,
            QuestionText = q_text,
            QuestionInstanceGuid = q_instance_guid,
            QuestionSdcid = q_id,
            ListItemText = li_text,
            ListItemId = li_id,
            ListItemInstanceGuid = li_instance_guid,
            ListItemParentGuid = li_parent_guid,
            Response = response,
            Units = units,
            UnitsSystem = units_system,
            Datatype = datatype,
            ResponseInt = response_int,
            ResponseFloat = response_float,
            ResponseDatetime = response_datetime,
            ReponseStringNvarchar = reponse_string_nvarchar,
            ObsDatetime = null, // Always null as per original implementation
            SdcOrder = sdc_order,
            SdcRepeatLevel = null, // Always null as per original implementation
            SdcComments = null, // Always null as per original implementation
        };

        _dbContext.SdcObservations.Add(sdcObservationEntity);
        await _dbContext.SaveChangesAsync();

        return sdcObservationEntity.SdcObservationId;
    }

    public long WriteSdcObsClass(
        long template_instance_class_fk,
        long? parent_observation_id,
        string? section_id,
        string? section_guid,
        string? q_text,
        string? q_instance_guid,
        string? q_id,
        string? li_text,
        string? li_id,
        string? li_instance_guid,
        string? sdc_order,
        string? response,
        string? units,
        string? units_system,
        string? datatype,
        long? response_int,
        double? response_float,
        DateTime? response_datetime,
        string? reponse_string_nvarchar,
        string? li_parent_guid
    )
    {
        return WriteSdcObsClassAsync(
                template_instance_class_fk,
                parent_observation_id,
                section_id,
                section_guid,
                q_text,
                q_instance_guid,
                q_id,
                li_text,
                li_id,
                li_instance_guid,
                sdc_order,
                response,
                units,
                units_system,
                datatype,
                response_int,
                response_float,
                response_datetime,
                reponse_string_nvarchar,
                li_parent_guid
            )
            .GetAwaiter()
            .GetResult();
    }

    public ISdcCdm.Person? WritePerson(in ISdcCdm.PersonDTO dto)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO main.person
                    (gender_concept_id, year_of_birth, month_of_birth, day_of_birth, birth_datetime,
                    race_concept_id, ethnicity_concept_id, location_id, provider_id, care_site_id,
                    person_source_value, gender_source_value, gender_source_concept_id,
                    race_source_value, race_source_concept_id, ethnicity_source_value, ethnicity_source_concept_id)
                VALUES
                    (@genderconceptid, @yearofbirth, @monthofbirth, @dayofbirth, @birthdatetime,
                    @raceconceptid, @ethnicityconceptid, @locationid, @providerid, @caresiteid,
                    @personsourcevalue, @gendersourcevalue, @gendersourceconceptid,
                    @racesourcevalue, @racesourceconceptid, @ethnicitysourcevalue, @ethnicitysourceconceptid)
                RETURNING 
                    person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth,
                    birth_datetime, race_concept_id, ethnicity_concept_id, location_id, provider_id,
                    care_site_id, person_source_value, gender_source_value, gender_source_concept_id,
                    race_source_value, race_source_concept_id, ethnicity_source_value, ethnicity_source_concept_id;
            ";

        cmd.Parameters.AddWithValue("@genderconceptid", dto.GenderConceptId);
        cmd.Parameters.AddWithValue("@yearofbirth", dto.YearOfBirth);
        cmd.Parameters.AddWithValue(
            "@monthofbirth",
            dto.MonthOfBirth.HasValue ? dto.MonthOfBirth.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@dayofbirth",
            dto.DayOfBirth.HasValue ? dto.DayOfBirth.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@birthdatetime",
            dto.BirthDatetime.HasValue ? dto.BirthDatetime.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue("@raceconceptid", dto.RaceConceptId);
        cmd.Parameters.AddWithValue("@ethnicityconceptid", dto.EthnicityConceptId);
        cmd.Parameters.AddWithValue(
            "@locationid",
            dto.LocationId.HasValue ? dto.LocationId.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@providerid",
            dto.ProviderId.HasValue ? dto.ProviderId.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@caresiteid",
            dto.CareSiteId.HasValue ? dto.CareSiteId.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@personsourcevalue",
            dto.PersonSourceValue != null ? dto.PersonSourceValue : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@gendersourcevalue",
            dto.GenderSourceValue != null ? dto.GenderSourceValue : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@gendersourceconceptid",
            dto.GenderSourceConceptId.HasValue ? dto.GenderSourceConceptId.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@racesourcevalue",
            dto.RaceSourceValue != null ? dto.RaceSourceValue : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@racesourceconceptid",
            dto.RaceSourceConceptId.HasValue ? dto.RaceSourceConceptId.Value : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@ethnicitysourcevalue",
            dto.EthnicitySourceValue != null ? dto.EthnicitySourceValue : DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@ethnicitysourceconceptid",
            dto.EthnicitySourceConceptId.HasValue
                ? dto.EthnicitySourceConceptId.Value
                : DBNull.Value
        );

        using var reader = cmd.ExecuteReader();
        if (!reader.Read())
            return null;

        // Reconstruct the Person record based on the data from the DB.
        var personId = reader.GetInt64(0);
        var genderConceptId = reader.GetInt64(1);
        var yearOfBirth = reader.GetInt32(2);
        int? monthOfBirth = reader.IsDBNull(3) ? null : reader.GetInt32(3);
        int? dayOfBirth = reader.IsDBNull(4) ? null : reader.GetInt32(4);
        DateTimeOffset? birthDatetime = reader.IsDBNull(5) ? null : reader.GetDateTime(5);
        var raceConceptId = reader.GetInt64(6);
        var ethnicityConceptId = reader.GetInt64(7);
        long? locationId = reader.IsDBNull(8) ? null : reader.GetInt64(8);
        long? providerId = reader.IsDBNull(9) ? null : reader.GetInt64(9);
        long? careSiteId = reader.IsDBNull(10) ? null : reader.GetInt64(10);
        string? personSourceValue = reader.IsDBNull(11) ? null : reader.GetString(11);
        string? genderSourceValue = reader.IsDBNull(12) ? null : reader.GetString(12);
        long? genderSourceConceptId = reader.IsDBNull(13) ? null : reader.GetInt64(13);
        string? raceSourceValue = reader.IsDBNull(14) ? null : reader.GetString(14);
        long? raceSourceConceptId = reader.IsDBNull(15) ? null : reader.GetInt64(15);
        string? ethnicitySourceValue = reader.IsDBNull(16) ? null : reader.GetString(16);
        long? ethnicitySourceConceptId = reader.IsDBNull(17) ? null : reader.GetInt64(17);

        return new()
        {
            PersonId = personId,
            GenderConceptId = genderConceptId,
            YearOfBirth = yearOfBirth,
            MonthOfBirth = monthOfBirth,
            DayOfBirth = dayOfBirth,
            BirthDatetime = birthDatetime,
            RaceConceptId = raceConceptId,
            EthnicityConceptId = ethnicityConceptId,
            LocationId = locationId,
            ProviderId = providerId,
            CareSiteId = careSiteId,
            PersonSourceValue = personSourceValue,
            GenderSourceValue = genderSourceValue,
            GenderSourceConceptId = genderSourceConceptId,
            RaceSourceValue = raceSourceValue,
            RaceSourceConceptId = raceSourceConceptId,
            EthnicitySourceValue = ethnicitySourceValue,
            EthnicitySourceConceptId = ethnicitySourceConceptId,
        };
    }

    public long? FindTemplateSdcClass(string formDesignId)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"SELECT template_sdc_id
              FROM template_sdc
              WHERE sdc_form_design_sdcid = @formDesignId";
        cmd.Parameters.AddWithValue("@formDesignId", formDesignId);
        using var reader = cmd.ExecuteReader();
        return reader.Read() ? reader.GetInt64(0) : null;
    }

    public long? FindTemplateInstanceClass(
        string instanceVersionGuid,
        string? instanceVersionDate = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT template_instance_id
            FROM template_instance
            WHERE template_instance_version_guid = @templateinstanceversionguid
            ";
        cmd.Parameters.AddWithValue(
            "@templateinstanceversionguid",
            instanceVersionGuid ?? (object)DBNull.Value
        );
        var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            long templateInstanceClassPk = reader.GetInt64(0);
            reader.Close();
            return templateInstanceClassPk;
        }
        reader.Close();
        return null;

        // TODO: Support searching by instanceVersionDate
    }

    /// <summary>
    /// Gets the underlying SQLite connection for direct database access.
    /// </summary>
    /// <returns>The SQLite connection.</returns>
    public SqliteConnection GetConnection() => connection;

    /// <summary>
    /// Finds a person by their primary key using Entity Framework Core.
    /// </summary>
    /// <param name="personPk">The person's primary key.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public async Task<long?> FindPersonAsync(long personPk)
    {
        var person = await _dbContext
            .Persons.Where(p => p.PersonId == personPk)
            .Select(p => new { p.PersonId })
            .FirstOrDefaultAsync();

        return person?.PersonId;
    }

    /// <summary>
    /// Finds a person by their primary key using Entity Framework Core.
    /// This is the synchronous version for backward compatibility.
    /// </summary>
    /// <param name="personPk">The person's primary key.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public long? FindPerson(long personPk)
    {
        return FindPersonAsync(personPk).GetAwaiter().GetResult();
    }

    /// <summary>
    /// Finds a person by their identifier using Entity Framework Core.
    /// </summary>
    /// <param name="identifier">The person's identifier.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public async Task<long?> FindPersonByIdentifierAsync(string identifier)
    {
        var person = await _dbContext
            .Persons.Where(p => p.PersonSourceValue == identifier)
            .Select(p => new { p.PersonId })
            .FirstOrDefaultAsync();

        return person?.PersonId;
    }

    /// <summary>
    /// Finds a person by their identifier using Entity Framework Core.
    /// This is the synchronous version for backward compatibility.
    /// </summary>
    /// <param name="identifier">The person's identifier.</param>
    /// <returns>The person ID if found, null otherwise.</returns>
    public long? FindPersonByIdentifier(string identifier)
    {
        return FindPersonByIdentifierAsync(identifier).GetAwaiter().GetResult();
    }

    /// <summary>
    /// Gets a person by their primary key and projects to a DTO using Entity Framework Core.
    /// This demonstrates how to use EF Core with DTOs to avoid exposing EF types.
    /// </summary>
    /// <param name="personPk">The person's primary key.</param>
    /// <returns>The person DTO if found, null otherwise.</returns>
    public async Task<ISdcCdm.Person?> GetPersonDtoAsync(long personPk)
    {
        var person = await _dbContext
            .Persons.Where(p => p.PersonId == personPk)
            .Select(p => new ISdcCdm.Person
            {
                PersonId = p.PersonId,
                GenderConceptId = p.GenderConceptId,
                YearOfBirth = p.YearOfBirth,
                MonthOfBirth = p.MonthOfBirth,
                DayOfBirth = p.DayOfBirth,
                BirthDatetime = p.BirthDatetime,
                RaceConceptId = p.RaceConceptId,
                EthnicityConceptId = p.EthnicityConceptId,
                LocationId = p.LocationId,
                ProviderId = p.ProviderId,
                CareSiteId = p.CareSiteId,
                PersonSourceValue = p.PersonSourceValue,
                GenderSourceValue = p.GenderSourceValue,
                GenderSourceConceptId = p.GenderSourceConceptId,
                RaceSourceValue = p.RaceSourceValue,
                RaceSourceConceptId = p.RaceSourceConceptId,
                EthnicitySourceValue = p.EthnicitySourceValue,
                EthnicitySourceConceptId = p.EthnicitySourceConceptId,
            })
            .FirstOrDefaultAsync();

        return person;
    }

    public ISdcCdm.TemplateInstanceRecord? GetTemplateInstanceRecord(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT
                template_instance.template_instance_id,
                template_instance_version_guid,
                template_instance_version_uri,
                template_instance.template_sdc_id,
                instance_version_date,
                diag_report_props,
                surg_path_sdcid,
                person_id,
                visit_occurrence_id,
                provider_id,
                report_text
            FROM template_instance
            INNER JOIN template_sdc ON template_sdc.template_sdc_id = template_instance.template_sdc_id
            WHERE template_instance.template_instance_id = @templateinstanceclasspk
            ";
        cmd.Parameters.AddWithValue("@templateinstanceclasspk", templateInstanceClassPk);
        var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            ISdcCdm.TemplateInstanceRecord record = new(
                reader.GetInt64(0),
                reader.IsDBNull(1) ? null : reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.GetInt64(3),
                reader.IsDBNull(4) ? null : reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetInt64(7),
                reader.IsDBNull(8) ? null : reader.GetInt64(8),
                reader.IsDBNull(9) ? null : reader.GetInt64(9),
                reader.IsDBNull(10) ? null : reader.GetString(10)
            );
            reader.Close();
            return record;
        }
        reader.Close();
        return null;
    }

    public List<SdcObsClass> GetSdcObsClasses(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT
                sdc_observation.sdc_observation_id,
                sdc_observation.template_instance_id,
                sdc_observation.section_sdcid,
                sdc_observation.section_guid,
                sdc_observation.question_text,
                sdc_observation.question_instance_guid,
                sdc_observation.question_sdcid,
                sdc_observation.list_item_text,
                sdc_observation.list_item_id,
                sdc_observation.list_item_instance_guid,
                sdc_observation.list_item_parent_guid,
                sdc_observation.response,
                sdc_observation.units,
                sdc_observation.units_system,
                sdc_observation.datatype,
                sdc_observation.response_int,
                sdc_observation.response_float,
                sdc_observation.response_datetime,
                sdc_observation.reponse_string_nvarchar,
                sdc_observation.obs_datetime,
                sdc_observation.sdc_order,
                sdc_observation.sdc_repeat_level,
                sdc_observation.sdc_comments
            FROM sdc_observation
            INNER JOIN template_instance ON template_instance.template_instance_id = sdc_observation.template_instance_id
            WHERE template_instance.template_instance_id = @templateinstanceclasspk
            ORDER BY sdc_observation.sdc_observation_id
            ";
        cmd.Parameters.AddWithValue("@templateinstanceclasspk", templateInstanceClassPk);
        var reader = cmd.ExecuteReader();
        List<SdcObsClass> sdcObsClasses = [];
        while (reader.Read())
        {
            sdcObsClasses.Add(
                new SdcObsClass(
                    reader.GetInt64(0),
                    reader.GetInt64(1),
                    reader.IsDBNull(2) ? null : reader.GetString(2),
                    reader.IsDBNull(3) ? null : reader.GetString(3),
                    reader.IsDBNull(4) ? null : reader.GetString(4),
                    reader.IsDBNull(5) ? null : reader.GetString(5),
                    reader.IsDBNull(6) ? null : reader.GetString(6),
                    reader.IsDBNull(7) ? null : reader.GetString(7),
                    reader.IsDBNull(8) ? null : reader.GetString(8),
                    reader.IsDBNull(9) ? null : reader.GetString(9),
                    reader.IsDBNull(10) ? null : reader.GetString(10),
                    reader.IsDBNull(11) ? null : reader.GetString(11),
                    reader.IsDBNull(12) ? null : reader.GetString(12),
                    reader.IsDBNull(13) ? null : reader.GetString(13),
                    reader.IsDBNull(14) ? null : reader.GetString(14),
                    reader.IsDBNull(15) ? null : reader.GetInt64(15),
                    reader.IsDBNull(16) ? null : reader.GetFloat(16),
                    reader.IsDBNull(17) ? null : reader.GetDateTimeOffset(17),
                    reader.IsDBNull(18) ? null : reader.GetString(18),
                    reader.IsDBNull(19) ? null : reader.GetDateTimeOffset(19),
                    reader.IsDBNull(20) ? null : reader.GetString(20),
                    reader.IsDBNull(21) ? null : reader.GetString(21),
                    reader.IsDBNull(22) ? null : reader.GetString(22)
                )
            );
            reader.Close();
            return sdcObsClasses;
        }
        reader.Close();
        throw new Exception("No template instance records found");
    }

    public long? FindTemplateItem(string template_item_sdcid)
    {
        throw new NotImplementedException();
    }

    /// <summary>
    /// Writes a template item using Entity Framework Core.
    /// </summary>
    /// <param name="templateItem">The template item DTO.</param>
    /// <returns>The template item if successful, null otherwise.</returns>
    public async Task<ISdcCdm.TemplateItem?> WriteTemplateItemAsync(
        ISdcCdm.TemplateItemDTO templateItem
    )
    {
        var templateItemEntity = new TemplateItemEntity
        {
            TemplateSdcId = templateItem.TemplateSdcId,
            ParentTemplateItemId = templateItem.ParentTemplateItemId,
            TemplateItemSdcid = templateItem.TemplateItemSdcid,
            Type = templateItem.Type,
            VisibleText = templateItem.VisibleText,
            InvisibleText = templateItem.InvisibleText,
            MinCardinality = templateItem.MinCard,
            MustImplement = templateItem.MustImplement,
            ItemOrder = templateItem.ItemOrder,
        };

        _dbContext.TemplateItems.Add(templateItemEntity);
        await _dbContext.SaveChangesAsync();

        return new ISdcCdm.TemplateItem
        {
            TemplateItemId = templateItemEntity.TemplateItemId,
            TemplateSdcId = templateItemEntity.TemplateSdcId,
            ParentTemplateItemId = templateItemEntity.ParentTemplateItemId,
            TemplateItemSdcid = templateItemEntity.TemplateItemSdcid,
            Type = templateItemEntity.Type,
            VisibleText = templateItemEntity.VisibleText,
            InvisibleText = templateItemEntity.InvisibleText,
            MinCard = templateItemEntity.MinCardinality,
            MustImplement = templateItemEntity.MustImplement,
            ItemOrder = templateItemEntity.ItemOrder,
        };
    }

    public ISdcCdm.TemplateItem? WriteTemplateItem(in ISdcCdm.TemplateItemDTO templateItem)
    {
        return WriteTemplateItemAsync(templateItem).GetAwaiter().GetResult();
    }
}
