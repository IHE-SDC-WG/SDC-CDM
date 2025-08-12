using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using SdcCdm;

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

        Logger = _loggerFactory.CreateLogger<SdcCdmInSqlite>();
    }

    private readonly string dbFilePath;
    private readonly SqliteConnection connection;
    private readonly bool isMemoryDb;

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

        // Insert essential concepts for basic functionality
        InsertEssentialConcepts();

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

    public long? FindPerson(long personPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT person_id
            FROM person
            WHERE person_id = @personpk
            ";
        cmd.Parameters.AddWithValue("@personpk", personPk);
        var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            long foundPersonPk = reader.GetInt64(0);
            reader.Close();
            return foundPersonPk;
        }
        reader.Close();
        return null;
    }

    public long? FindPersonByIdentifier(string identifier)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT
                person.person_id, person.person_source_value
            FROM
                person
            WHERE
                person_source_value = @identifier
            ";
        cmd.Parameters.AddWithValue("@identifier", identifier);
        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            long foundPersonPk = reader.GetInt64(0);
            reader.Close();
            return foundPersonPk;
        }
        reader.Close();
        return null;
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
            INSERT INTO main.template_item 
            (template_sdc_id, parent_template_item_id, template_item_sdcid, type, visible_text, 
             invisible_text, min_cardinality, must_implement, item_order)
                VALUES 
            (@templateSdcId, @parentTemplateItemId, @templateItemSdcid, @type, @visibleText, 
             @invisibleText, @minCardinality, @mustImplement, @itemOrder);
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@templateSdcId", templateItem.TemplateSdcId);
        cmd.Parameters.AddWithValue(
            "@parentTemplateItemId",
            templateItem.ParentTemplateItemId ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@templateItemSdcid", templateItem.TemplateItemSdcid);
        cmd.Parameters.AddWithValue("@type", templateItem.Type ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@visibleText",
            templateItem.VisibleText ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@invisibleText",
            templateItem.InvisibleText ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@minCardinality",
            templateItem.MinCard ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@mustImplement",
            templateItem.MustImplement ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@itemOrder", templateItem.ItemOrder ?? (object)DBNull.Value);

        var result = cmd.ExecuteScalar();
        if (result == null)
            return null;

        var templateItemId = Convert.ToInt64(result);
        return new ISdcCdm.TemplateItem
        {
            TemplateItemId = templateItemId,
            TemplateSdcId = templateItem.TemplateSdcId,
            ParentTemplateItemId = templateItem.ParentTemplateItemId,
            TemplateItemSdcid = templateItem.TemplateItemSdcid,
            Type = templateItem.Type,
            VisibleText = templateItem.VisibleText,
            InvisibleText = templateItem.InvisibleText,
            MinCard = templateItem.MinCard,
            MustImplement = templateItem.MustImplement,
            ItemOrder = templateItem.ItemOrder,
        };
    }

    // New methods for ECP data handling
    public long WriteSdcTemplateInstanceEcp(
        string template_name,
        string template_version,
        string template_instance_guid,
        long? person_id = null,
        long? visit_occurrence_id = null,
        long? provider_id = null,
        string? report_text = null,
        string? report_template_source = null,
        string? report_template_id = null,
        string? report_template_version_id = null,
        string? tumor_site = null,
        string? procedure_type = null,
        string? specimen_laterality = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO main.sdc_template_instance_ecp 
            (template_name, template_version, template_lineage, template_base_uri, template_instance_guid, 
             template_instance_version_guid, template_instance_version_uri, instance_version_date,
             person_id, visit_occurrence_id, provider_id, report_text, report_template_source, 
             report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
             created_datetime, updated_datetime)
            VALUES 
            (@templateName, @templateVersion, NULL, NULL, @templateInstanceGuid, 
             NULL, NULL, NULL, @personId, @visitOccurrenceId, @providerId, @reportText, 
             @reportTemplateSource, @reportTemplateId, @reportTemplateVersionId, @tumorSite, 
             @procedureType, @specimenLaterality, julianday('now'), julianday('now'));
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@templateName", template_name);
        cmd.Parameters.AddWithValue("@templateVersion", template_version);
        cmd.Parameters.AddWithValue("@templateInstanceGuid", template_instance_guid);
        cmd.Parameters.AddWithValue("@personId", person_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@visitOccurrenceId",
            visit_occurrence_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@providerId", provider_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@reportText", report_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@reportTemplateSource",
            report_template_source ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@reportTemplateId",
            report_template_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@reportTemplateVersionId",
            report_template_version_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@tumorSite", tumor_site ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@procedureType", procedure_type ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@specimenLaterality",
            specimen_laterality ?? (object)DBNull.Value
        );

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public long WriteMeasurementWithSdcData(
        long person_id,
        long measurement_concept_id,
        DateTime measurement_date,
        long measurement_type_concept_id,
        double? value_as_number = null,
        string? value_as_string = null,
        string? unit_source_value = null,
        string? measurement_source_value = null,
        // SDC-specific fields
        string? sdc_template_instance_guid = null,
        string? sdc_question_identifier = null,
        string? sdc_response_value = null,
        string? sdc_response_type = null,
        string? sdc_template_version = null,
        string? sdc_question_text = null,
        string? sdc_section_identifier = null,
        string? sdc_list_item_id = null,
        string? sdc_list_item_text = null,
        string? sdc_units = null,
        string? sdc_datatype = null,
        int? sdc_order = null,
        int? sdc_repeat_level = null,
        string? sdc_comments = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                    INSERT INTO main.measurement
                    (person_id, measurement_concept_id, measurement_date, measurement_type_concept_id,
                     value_as_number, value_source_value, unit_source_value, measurement_source_value,
                     sdc_template_instance_guid, sdc_question_identifier, sdc_response_value, sdc_response_type,
                     sdc_template_version, sdc_question_text, sdc_section_identifier, sdc_list_item_id,
                     sdc_list_item_text, sdc_units, sdc_datatype, sdc_order, sdc_repeat_level, sdc_comments)
                    VALUES
                    (@personId, @measurementConceptId, @measurementDate, @measurementTypeConceptId,
                     @valueAsNumber, @valueAsString, @unitSourceValue, @measurementSourceValue,
                     @sdcTemplateInstanceGuid, @sdcQuestionIdentifier, @sdcResponseValue, @sdcResponseType,
                     @sdcTemplateVersion, @sdcQuestionText, @sdcSectionIdentifier, @sdcListItemId,
                     @sdcListItemText, @sdcUnits, @sdcDatatype, @sdcOrder, @sdcRepeatLevel, @sdcComments);
                    SELECT last_insert_rowid();
                ";

        cmd.Parameters.AddWithValue("@personId", person_id);
        cmd.Parameters.AddWithValue("@measurementConceptId", measurement_concept_id);
        cmd.Parameters.AddWithValue("@measurementDate", measurement_date);
        cmd.Parameters.AddWithValue("@measurementTypeConceptId", measurement_type_concept_id);
        cmd.Parameters.AddWithValue("@valueAsNumber", value_as_number ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@valueAsString", value_as_string ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@unitSourceValue", unit_source_value ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@measurementSourceValue",
            measurement_source_value ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@sdcTemplateInstanceGuid",
            sdc_template_instance_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@sdcQuestionIdentifier",
            sdc_question_identifier ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@sdcResponseValue",
            sdc_response_value ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@sdcResponseType", sdc_response_type ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@sdcTemplateVersion",
            sdc_template_version ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@sdcQuestionText", sdc_question_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@sdcSectionIdentifier",
            sdc_section_identifier ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@sdcListItemId", sdc_list_item_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcListItemText", sdc_list_item_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcUnits", sdc_units ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcDatatype", sdc_datatype ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcOrder", sdc_order ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcRepeatLevel", sdc_repeat_level ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdcComments", sdc_comments ?? (object)DBNull.Value);

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public ISdcCdm.SdcTemplateInstanceEcpRecord? GetSdcTemplateInstanceEcpRecord(
        long templateInstanceEcpPk
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT sdc_template_instance_ecp_id, template_name, template_version, template_instance_guid,
                   person_id, visit_occurrence_id, provider_id, report_text, report_template_source,
                   report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
                   created_datetime, updated_datetime
            FROM main.sdc_template_instance_ecp 
            WHERE sdc_template_instance_ecp_id = @templateInstanceEcpPk
        ";

        cmd.Parameters.AddWithValue("@templateInstanceEcpPk", templateInstanceEcpPk);

        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            return new ISdcCdm.SdcTemplateInstanceEcpRecord(
                Pk: reader.GetInt64(0),
                TemplateName: reader.GetString(1),
                TemplateVersion: reader.GetString(2),
                TemplateInstanceGuid: reader.GetString(3),
                PersonId: reader.IsDBNull(4) ? null : reader.GetInt64(4),
                VisitOccurrenceId: reader.IsDBNull(5) ? null : reader.GetInt64(5),
                ProviderId: reader.IsDBNull(6) ? null : reader.GetInt64(6),
                ReportText: reader.IsDBNull(7) ? null : reader.GetString(7),
                ReportTemplateSource: reader.IsDBNull(8) ? null : reader.GetString(8),
                ReportTemplateId: reader.IsDBNull(9) ? null : reader.GetString(9),
                ReportTemplateVersionId: reader.IsDBNull(10) ? null : reader.GetString(10),
                TumorSite: reader.IsDBNull(11) ? null : reader.GetString(11),
                ProcedureType: reader.IsDBNull(12) ? null : reader.GetString(12),
                SpecimenLaterality: reader.IsDBNull(13) ? null : reader.GetString(13),
                CreatedDatetime: reader.GetDateTime(14),
                UpdatedDatetime: reader.GetDateTime(15)
            );
        }
        return null;
    }

    public ISdcCdm.SdcTemplateInstanceEcpRecord? FindSdcTemplateInstanceEcpByGuid(
        string templateInstanceGuid
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT sdc_template_instance_ecp_id, template_name, template_version, template_instance_guid,
                   person_id, visit_occurrence_id, provider_id, report_text, report_template_source,
                   report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
                   created_datetime, updated_datetime
            FROM main.sdc_template_instance_ecp 
            WHERE template_instance_guid = @templateInstanceGuid
        ";

        cmd.Parameters.AddWithValue("@templateInstanceGuid", templateInstanceGuid);

        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            return new ISdcCdm.SdcTemplateInstanceEcpRecord(
                Pk: reader.GetInt64(0),
                TemplateName: reader.GetString(1),
                TemplateVersion: reader.GetString(2),
                TemplateInstanceGuid: reader.GetString(3),
                PersonId: reader.IsDBNull(4) ? null : reader.GetInt64(4),
                VisitOccurrenceId: reader.IsDBNull(5) ? null : reader.GetInt64(5),
                ProviderId: reader.IsDBNull(6) ? null : reader.GetInt64(6),
                ReportText: reader.IsDBNull(7) ? null : reader.GetString(7),
                ReportTemplateSource: reader.IsDBNull(8) ? null : reader.GetString(8),
                ReportTemplateId: reader.IsDBNull(9) ? null : reader.GetString(9),
                ReportTemplateVersionId: reader.IsDBNull(10) ? null : reader.GetString(10),
                TumorSite: reader.IsDBNull(11) ? null : reader.GetString(11),
                ProcedureType: reader.IsDBNull(12) ? null : reader.GetString(12),
                SpecimenLaterality: reader.IsDBNull(13) ? null : reader.GetString(13),
                CreatedDatetime: reader.GetDateTime(14),
                UpdatedDatetime: reader.GetDateTime(15)
            );
        }
        return null;
    }

    // Method to get the database connection for testing purposes
    public Microsoft.Data.Sqlite.SqliteConnection GetConnection()
    {
        return connection;
    }

    private void InsertEssentialConcepts()
    {
        // Insert essential concepts that are commonly referenced
        var essentialConcepts = new[]
        {
            new ConceptRecord
            {
                ConceptId = 8507,
                ConceptName = "MALE",
                DomainId = "Gender",
                VocabularyId = "Gender",
                ConceptClassId = "Gender",
                StandardConcept = "S",
                ConceptCode = "M",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
            new ConceptRecord
            {
                ConceptId = 8532,
                ConceptName = "FEMALE",
                DomainId = "Gender",
                VocabularyId = "Gender",
                ConceptClassId = "Gender",
                StandardConcept = "S",
                ConceptCode = "F",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
            new ConceptRecord
            {
                ConceptId = 0,
                ConceptName = "UNKNOWN",
                DomainId = "Gender",
                VocabularyId = "Gender",
                ConceptClassId = "Gender",
                StandardConcept = "S",
                ConceptCode = "U",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
            new ConceptRecord
            {
                ConceptId = 32856,
                ConceptName = "Laboratory measurement",
                DomainId = "Measurement",
                VocabularyId = "Measurement Type",
                ConceptClassId = "Measurement Type",
                StandardConcept = "S",
                ConceptCode = "LAB",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
        };

        foreach (var concept in essentialConcepts)
        {
            try
            {
                InsertConcept(concept);
            }
            catch (Exception ex)
            {
                // Concept might already exist, ignore the error
                Logger.LogDebug(
                    "Could not insert concept {ConceptId}: {Message}",
                    concept.ConceptId,
                    ex.Message
                );
            }
        }
    }
}
