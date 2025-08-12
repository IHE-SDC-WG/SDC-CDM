using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using SdcCdm;
using SdcCdmInSqlite.Entities;

namespace SdcCdmInSqlite;

public class SdcCdmInSqlite : ISdcCdm
{
    /// <summary>
    /// Inserts a concept record into the concept table.
    /// </summary>
    /// <param name="concept">The concept record to insert.</param>
    /// <returns>The ID of the inserted concept.</returns>
    public long InsertConcept(ConceptRecord concept)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO main.concept 
            (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, 
             standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
            VALUES 
            (@conceptId, @conceptName, @domainId, @vocabularyId, @conceptClassId, 
             @standardConcept, @conceptCode, @validStartDate, @validEndDate, @invalidReason);
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@conceptId", concept.ConceptId);
        cmd.Parameters.AddWithValue("@conceptName", concept.ConceptName);
        cmd.Parameters.AddWithValue("@domainId", concept.DomainId);
        cmd.Parameters.AddWithValue("@vocabularyId", concept.VocabularyId);
        cmd.Parameters.AddWithValue("@conceptClassId", concept.ConceptClassId);
        cmd.Parameters.AddWithValue(
            "@standardConcept",
            concept.StandardConcept ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@conceptCode", concept.ConceptCode);
        cmd.Parameters.AddWithValue("@validStartDate", concept.ValidStartDate);
        cmd.Parameters.AddWithValue("@validEndDate", concept.ValidEndDate);
        cmd.Parameters.AddWithValue(
            "@invalidReason",
            concept.InvalidReason ?? (object)DBNull.Value
        );

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
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
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO main.template_sdc 
                (sdc_form_design_sdcid, base_uri, lineage, version, full_uri, form_title, sdc_xml, doc_type)
                VALUES (@sdcformdesignid, @baseuri, @lineage, @version, @fulluri, @formtitle, @sdc_xml, @doctype);
                SELECT last_insert_rowid();
            ";

        cmd.Parameters.AddWithValue("@sdcformdesignid", sdcformdesignid);
        cmd.Parameters.AddWithValue("@baseuri", baseuri ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@lineage", lineage ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@version", version ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@fulluri", fulluri ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@formtitle", formtitle ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdc_xml", sdc_xml ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@doctype", doctype ?? (object)DBNull.Value);

        var pk = cmd.ExecuteScalar() ?? -1;
        return (long)pk;
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
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO template_instance 
                (template_instance_version_guid, template_instance_version_uri, template_sdc_id, instance_version_date, diag_report_props, surg_path_sdcid, person_id, visit_occurrence_id, provider_id, report_text)
                VALUES (@templateinstanceversionguid, @templateinstanceversionuri, @templatesdcfk, @instanceversiondate, @diagreportprops, @surgpathid, @personfk, @encounterfk, @practitionerfk, @reporttext);
                SELECT last_insert_rowid();
            ";

        cmd.Parameters.AddWithValue(
            "@templateinstanceversionguid",
            template_instance_version_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@templateinstanceversionuri",
            template_instance_version_uri ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@templatesdcfk", templatesdc_fk);
        cmd.Parameters.AddWithValue(
            "@instanceversiondate",
            instance_version_date ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@diagreportprops", diag_report_props ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@surgpathid", surg_path_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@personfk", person_fk ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@encounterfk", encounter_fk ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@practitionerfk", practitioner_fk ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@reporttext", report_text ?? (object)DBNull.Value);

        var pk = cmd.ExecuteScalar() ?? -1L;
        return (long)pk;
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
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO sdc_observation 
                (template_instance_id, parent_observation_id, parent_instance_guid, section_sdcid, section_guid, question_text, question_instance_guid, question_sdcid, list_item_text, list_item_id, list_item_instance_guid, list_item_parent_guid, response, units, units_system, datatype, response_int, response_float, response_datetime, reponse_string_nvarchar, obs_datetime, sdc_order, sdc_repeat_level, sdc_comments)
                VALUES (@templateinstanceclassfk, @parent_observation_id, @parentinstanceguid, @section_id, @section_guid, @q_text, @q_instanceguid, @q_id, @li_text, @li_id, @li_instanceguid, @li_parentguid, @response, @units, @units_system, @datatype, @response_int, @response_float, @response_datetime, @reponse_string_nvarchar, @obsdatetime, @sdcorder, @sdcrepeatlevel, @sdccomments);
                SELECT last_insert_rowid();
            ";

        cmd.Parameters.AddWithValue("@templateinstanceclassfk", template_instance_class_fk);
        cmd.Parameters.AddWithValue(
            "@parent_observation_id",
            parent_observation_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@parentinstanceguid", DBNull.Value);
        cmd.Parameters.AddWithValue("@section_id", section_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@section_guid", section_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@q_text", q_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@q_instanceguid", q_instance_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@q_id", q_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@li_text", li_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@li_id", li_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@li_instanceguid", li_instance_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@li_parentguid", li_parent_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@response", response ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@units", units ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@units_system", units_system ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@datatype", datatype ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@response_int", response_int ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@response_float", response_float ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@response_datetime",
            response_datetime ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@reponse_string_nvarchar",
            reponse_string_nvarchar ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@obsdatetime", DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcorder", sdc_order ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcrepeatlevel", DBNull.Value);
        cmd.Parameters.AddWithValue("@sdccomments", DBNull.Value);

        var pk = cmd.ExecuteScalar() ?? -1;
        return (long)pk;
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

    public ISdcCdm.TemplateItem? WriteTemplateItem(in ISdcCdm.TemplateItemDTO templateItem)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO template_item
                    (template_sdc_id, parent_template_item_id,
                    template_item_sdcid, type, visible_text, invisible_text,
                    min_cardinality, must_implement, item_order)
                VALUES 
                    (@templatesdcfk, @parenttemplateitemid, 
                    @templateitem_sdcid, @type, @visibletext, @invisibletext, 
                    @mincard, @mustimplement, @itemorder)
                RETURNING
                    template_item_id, template_sdc_id, parent_template_item_id, 
                    template_item_sdcid, type, visible_text, invisible_text, 
                    min_cardinality, must_implement, item_order;
            ";

        cmd.Parameters.AddWithValue("@templatesdcfk", templateItem.TemplateSdcId);
        cmd.Parameters.AddWithValue(
            "@parenttemplateitemid",
            templateItem.ParentTemplateItemId ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@templateitem_sdcid", templateItem.TemplateItemSdcid);
        cmd.Parameters.AddWithValue("@type", templateItem.Type ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@visibletext",
            templateItem.VisibleText ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@invisibletext",
            templateItem.InvisibleText ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@mincard", templateItem.MinCard ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@mustimplement",
            templateItem.MustImplement ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@itemorder", templateItem.ItemOrder ?? (object)DBNull.Value);

        using var reader = cmd.ExecuteReader();
        if (!reader.Read())
            return null;

        // Reconstruct the template item record based on the data from the DB.
        var templateItemId = reader.GetInt64(0);
        var templateSdcId = reader.GetInt64(1);
        long? parentTemplateItemId = reader.IsDBNull(2) ? null : reader.GetInt64(2);
        var templateItemSdcid = reader.GetString(3);
        var type = reader.IsDBNull(4) ? null : reader.GetString(4);
        var visibleText = reader.IsDBNull(5) ? null : reader.GetString(5);
        var invisibleText = reader.IsDBNull(6) ? null : reader.GetString(6);
        var minCard = reader.IsDBNull(7) ? null : reader.GetString(7);
        var mustImplement = reader.IsDBNull(8) ? null : reader.GetString(8);
        var itemOrder = reader.IsDBNull(9) ? null : reader.GetString(9);

        return new()
        {
            TemplateItemId = templateItemId,
            TemplateSdcId = templateSdcId,
            ParentTemplateItemId = parentTemplateItemId,
            TemplateItemSdcid = templateItemSdcid,
            Type = type,
            VisibleText = visibleText,
            InvisibleText = invisibleText,
            MinCard = minCard,
            MustImplement = mustImplement,
            ItemOrder = itemOrder,
        };
    }
}
