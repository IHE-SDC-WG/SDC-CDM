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
            INSERT INTO omop.concept 
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
        AttachSchemaDatabases(overwrite);

        Logger = _loggerFactory.CreateLogger<SdcCdmInSqlite>();
    }

    private readonly string dbFilePath;
    private readonly SqliteConnection connection;
    private readonly bool isMemoryDb;

    private void AttachSchemaDatabases(bool overwrite)
    {
        using var pragma = connection.CreateCommand();
        pragma.CommandText = "PRAGMA foreign_keys = ON;";
        pragma.ExecuteNonQuery();

        AttachSchemaDatabase("omop", overwrite);
        AttachSchemaDatabase("naaccr", overwrite);
        AttachSchemaDatabase("sdc", overwrite);
    }

    private void AttachSchemaDatabase(string schemaName, bool overwrite)
    {
        var dataSource = ":memory:";
        if (!isMemoryDb)
        {
            var directory = Path.GetDirectoryName(Path.GetFullPath(dbFilePath)) ?? ".";
            var fileName = Path.GetFileNameWithoutExtension(dbFilePath);
            dataSource = Path.Combine(directory, $"{fileName}.{schemaName}.db");
            if (overwrite && File.Exists(dataSource))
            {
                File.Delete(dataSource);
            }
        }

        using var cmd = connection.CreateCommand();
        cmd.CommandText = $"ATTACH DATABASE '{dataSource.Replace("'", "''")}' AS {schemaName};";
        cmd.ExecuteNonQuery();
    }

    public void BuildSchema()
    {
        // Get the current assembly
        var assembly = System.Reflection.Assembly.GetExecutingAssembly();

        // Determine the resource name prefix for files in the 'sqlite' folder.
        // This typically follows the pattern: "{DefaultNamespace}.database.ddl.sqlite."
        string resourcePrefix = "SdcCdmInSqlite.";

        // Debug: List all available resources
        var allResources = assembly.GetManifestResourceNames();
        Console.WriteLine($"All available resources ({allResources.Length}):");
        foreach (var resource in allResources)
        {
            Console.WriteLine($"  {resource}");
        }

        // Retrieve all resource names that match the .sql files in the desired folder.
        var sqlResourceNames = assembly
            .GetManifestResourceNames()
            .Where(name =>
                name.StartsWith(resourcePrefix, StringComparison.OrdinalIgnoreCase)
                && name.Contains(".database.schemas.", StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".sql", StringComparison.OrdinalIgnoreCase)
            )
            .OrderBy(name => name) // Sort them alphabetically
            .ToList();

        Console.WriteLine(
            $"\nFound {sqlResourceNames.Count} SQL scripts with prefix '{resourcePrefix}':"
        );
        foreach (var resource in sqlResourceNames)
        {
            Console.WriteLine($"  {resource}");
        }

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

        // If no SQL scripts were loaded, create a basic schema
        if (sqlResourceNames.Count == 0)
        {
            Console.WriteLine("No SQL scripts loaded, creating basic schema directly...");
            CreateBasicSchema();
        }

        // Insert essential concepts for basic functionality
        InsertEssentialConcepts();

        Logger.LogInformation("Finished building schema.");
    }

    private void CreateBasicSchema()
    {
        throw new InvalidOperationException("No embedded three-schema DDL resources were found.");
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
                INSERT INTO sdc.template_sdc 
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
                INSERT INTO sdc.template_instance 
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
        return WriteSdcFormAnswer(
            template_instance_id: template_instance_class_fk,
            parent_form_answer_id: parent_observation_id,
            section_sdcid: section_id,
            section_guid: section_guid,
            question_text: q_text,
            question_instance_guid: q_instance_guid,
            question_sdcid: q_id,
            list_item_id: li_id,
            list_item_text: li_text,
            list_item_instance_guid: li_instance_guid,
            list_item_parent_guid: li_parent_guid,
            units_system: units_system,
            datatype: datatype,
            sdc_order: sdc_order,
            response: response,
            units: units,
            response_int: response_int,
            response_float: response_float,
            response_datetime: response_datetime,
            reponse_string_nvarchar: reponse_string_nvarchar
        );
    }

    public ISdcCdm.Person? WritePerson(in ISdcCdm.PersonDTO dto)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO omop.person
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
              FROM sdc.template_sdc
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
            FROM sdc.template_instance
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
            FROM omop.person
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
                p.person_id, p.person_source_value
            FROM
                omop.person p
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
            FROM sdc.template_instance
            INNER JOIN sdc.template_sdc ON template_sdc.template_sdc_id = template_instance.template_sdc_id
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
                sdc_form_answer.sdc_form_answer_id,
                sdc_form_answer.template_instance_id,
                sdc_form_answer.section_sdcid,
                sdc_form_answer.section_guid,
                sdc_form_answer.question_text,
                sdc_form_answer.question_instance_guid,
                sdc_form_answer.question_sdcid,
                sdc_form_answer.list_item_text,
                sdc_form_answer.list_item_id,
                sdc_form_answer.list_item_instance_guid,
                sdc_form_answer.list_item_parent_guid,
                sdc_form_answer.response,
                sdc_form_answer.units,
                sdc_form_answer.units_system,
                sdc_form_answer.datatype,
                sdc_form_answer.response_int,
                sdc_form_answer.response_float,
                sdc_form_answer.response_datetime,
                sdc_form_answer.reponse_string_nvarchar,
                NULL AS obs_datetime,
                sdc_form_answer.sdc_order,
                sdc_form_answer.sdc_repeat_level,
                sdc_form_answer.sdc_comments
            FROM sdc.sdc_form_answer
            INNER JOIN sdc.template_instance ON template_instance.template_instance_id = sdc_form_answer.template_instance_id
            WHERE template_instance.template_instance_id = @templateinstanceclasspk
            ORDER BY sdc_form_answer.sdc_form_answer_id
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
                    reader.IsDBNull(16) ? null : reader.GetDouble(16),
                    reader.IsDBNull(17) ? null : reader.GetDateTimeOffset(17),
                    reader.IsDBNull(18) ? null : reader.GetString(18),
                    reader.IsDBNull(19) ? null : reader.GetDateTimeOffset(19),
                    reader.IsDBNull(20) ? null : reader.GetString(20),
                    reader.IsDBNull(21) ? null : reader.GetString(21),
                    reader.IsDBNull(22) ? null : reader.GetString(22)
                )
            );
        }
        reader.Close();
        return sdcObsClasses;
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
            INSERT INTO sdc.template_item 
            (template_sdc_id, parent_template_item_id, template_item_sdcid, type, visible_text, 
             invisible_text, min_card, must_implement, item_order)
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

    public long WriteSdcReport(
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
        string? specimen_laterality = null,
        string? report_accession = null,
        string? report_loinc = null,
        bool is_duplicate_accession = false,
        long? first_seen_report_id = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO sdc.sdc_report
            (template_name, template_version, template_instance_guid,
             person_id, visit_occurrence_id, provider_id, report_text, report_template_source,
             report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
             report_accession, report_loinc, is_duplicate_accession, first_seen_report_id,
             created_datetime, updated_datetime)
            VALUES
            (@templateName, @templateVersion, @templateInstanceGuid,
             @personId, @visitOccurrenceId, @providerId, @reportText,
             @reportTemplateSource, @reportTemplateId, @reportTemplateVersionId, @tumorSite,
             @procedureType, @specimenLaterality, @reportAccession, @reportLoinc, @isDuplicateAccession,
             @firstSeenReportId, datetime('now'), datetime('now'));
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
        cmd.Parameters.AddWithValue("@reportAccession", report_accession ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@reportLoinc", report_loinc ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@isDuplicateAccession", is_duplicate_accession ? 1 : 0);
        cmd.Parameters.AddWithValue("@firstSeenReportId", first_seen_report_id ?? (object)DBNull.Value);

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public long? FindFirstSdcReportByAccession(string report_accession)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT MIN(sdc_report_id)
            FROM sdc.sdc_report
            WHERE report_accession = @reportAccession;
        ";
        cmd.Parameters.AddWithValue("@reportAccession", report_accession);
        var result = cmd.ExecuteScalar();
        return result == null || result == DBNull.Value ? null : Convert.ToInt64(result);
    }

    public long WriteNaaccrValue(
        long person_id,
        string episode_key,
        int item_num,
        string? report_accession = null,
        string? schema_id_number = null,
        string? value_code = null,
        double? value_num = null,
        string? value_unit_source = null,
        DateTime? observation_date = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO naaccr.naaccr_value (
                person_id, episode_key, report_accession, schema_id_number, item_num,
                value_code, value_num, value_unit_source, observation_date
            ) VALUES (
                @personId, @episodeKey, @reportAccession, @schemaIdNumber, @itemNum,
                @valueCode, @valueNum, @valueUnitSource, @observationDate
            );
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@personId", person_id);
        cmd.Parameters.AddWithValue("@episodeKey", episode_key);
        cmd.Parameters.AddWithValue("@reportAccession", report_accession ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@schemaIdNumber", schema_id_number ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@itemNum", item_num);
        cmd.Parameters.AddWithValue("@valueCode", value_code ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@valueNum", value_num ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@valueUnitSource", value_unit_source ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@observationDate",
            observation_date?.ToString("yyyy-MM-dd") ?? (object)DBNull.Value
        );

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public long WriteSdcFormAnswer(
        long template_instance_id,
        long? parent_form_answer_id = null,
        string? section_sdcid = null,
        string? section_guid = null,
        string? question_text = null,
        string? question_instance_guid = null,
        string? question_sdcid = null,
        string? list_item_id = null,
        string? list_item_text = null,
        string? list_item_instance_guid = null,
        string? list_item_parent_guid = null,
        string? units_system = null,
        string? datatype = null,
        string? sdc_order = null,
        string? sdc_repeat_level = null,
        string? sdc_comments = null,
        string? response = null,
        string? units = null,
        long? response_int = null,
        double? response_float = null,
        DateTime? response_datetime = null,
        string? reponse_string_nvarchar = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO sdc.sdc_form_answer (
                template_instance_id, parent_form_answer_id,
                section_sdcid, section_guid, question_text, question_instance_guid, question_sdcid,
                list_item_id, list_item_text, list_item_instance_guid, list_item_parent_guid,
                units_system, response, units, response_int, response_float, response_datetime,
                reponse_string_nvarchar, datatype, sdc_order, sdc_repeat_level, sdc_comments
            ) VALUES (
                @template_instance_id, @parent_form_answer_id,
                @section_sdcid, @section_guid, @question_text, @question_instance_guid, @question_sdcid,
                @list_item_id, @list_item_text, @list_item_instance_guid, @list_item_parent_guid,
                @units_system, @response, @units, @response_int, @response_float, @response_datetime,
                @reponse_string_nvarchar, @datatype, @sdc_order, @sdc_repeat_level, @sdc_comments
            );
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@template_instance_id", template_instance_id);
        cmd.Parameters.AddWithValue(
            "@parent_form_answer_id",
            parent_form_answer_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@section_sdcid", section_sdcid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@section_guid", section_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@question_text", question_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@question_instance_guid",
            question_instance_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@question_sdcid", question_sdcid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@list_item_id", list_item_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@list_item_text", list_item_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@list_item_instance_guid",
            list_item_instance_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@list_item_parent_guid",
            list_item_parent_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@units_system", units_system ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@response", response ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@units", units ?? (object)DBNull.Value);
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
        cmd.Parameters.AddWithValue("@datatype", datatype ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdc_order", sdc_order ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdc_repeat_level", sdc_repeat_level ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdc_comments", sdc_comments ?? (object)DBNull.Value);

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public long WriteNote(
        long person_id,
        DateTime note_date,
        long note_type_concept_id,
        long note_class_concept_id,
        string note_text,
        string? note_title = null,
        long encoding_concept_id = 0,
        long language_concept_id = 0,
        long? provider_id = null,
        long? visit_occurrence_id = null,
        string? note_source_value = null,
        long? note_event_id = null,
        long? note_event_field_concept_id = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            INSERT INTO omop.note (
                person_id, note_date, note_type_concept_id, note_class_concept_id,
                note_title, note_text, encoding_concept_id, language_concept_id,
                provider_id, visit_occurrence_id, note_source_value,
                note_event_id, note_event_field_concept_id
            ) VALUES (
                @person_id, @note_date, @note_type_concept_id, @note_class_concept_id,
                @note_title, @note_text, @encoding_concept_id, @language_concept_id,
                @provider_id, @visit_occurrence_id, @note_source_value,
                @note_event_id, @note_event_field_concept_id
            );
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@person_id", person_id);
        cmd.Parameters.AddWithValue("@note_date", note_date);
        cmd.Parameters.AddWithValue("@note_type_concept_id", note_type_concept_id);
        cmd.Parameters.AddWithValue("@note_class_concept_id", note_class_concept_id);
        cmd.Parameters.AddWithValue("@note_title", note_title ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@note_text", note_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@encoding_concept_id", encoding_concept_id);
        cmd.Parameters.AddWithValue("@language_concept_id", language_concept_id);
        cmd.Parameters.AddWithValue("@provider_id", provider_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@visit_occurrence_id",
            visit_occurrence_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@note_source_value",
            note_source_value ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@note_event_id", note_event_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@note_event_field_concept_id",
            note_event_field_concept_id ?? (object)DBNull.Value
        );

        var result = cmd.ExecuteScalar();
        return result != null ? Convert.ToInt64(result) : -1;
    }

    public int BridgeNaaccrSdcToOmop()
    {
        var assembly = System.Reflection.Assembly.GetExecutingAssembly();
        var etlResources = assembly
            .GetManifestResourceNames()
            .Where(name =>
                name.Contains(".database.etl.sqlite.", StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".sql", StringComparison.OrdinalIgnoreCase)
            )
            .OrderBy(name => name)
            .ToList();

        if (etlResources.Count == 0)
        {
            throw new InvalidOperationException("No embedded SQLite ETL resources were found.");
        }

        var affectedRows = 0;
        foreach (var resourceName in etlResources)
        {
            using Stream? stream = assembly.GetManifestResourceStream(resourceName);
            if (stream == null)
            {
                throw new Exception($"Could not find SQL script {resourceName}.");
            }

            using StreamReader reader = new(stream);
            using var command = connection.CreateCommand();
            command.CommandText = reader.ReadToEnd();
            affectedRows += command.ExecuteNonQuery();
        }

        return affectedRows;
    }

    public ISdcCdm.SdcReportRecord? GetSdcReportRecord(long reportPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT sdc_report_id, template_name, template_version, template_instance_guid,
                   person_id, visit_occurrence_id, provider_id, report_text, report_template_source,
                   report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
                   report_accession, report_loinc, is_duplicate_accession, first_seen_report_id,
                   created_datetime, updated_datetime
            FROM sdc.sdc_report 
            WHERE sdc_report_id = @reportPk
        ";

        cmd.Parameters.AddWithValue("@reportPk", reportPk);

        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            return new ISdcCdm.SdcReportRecord(
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
                ReportAccession: reader.IsDBNull(14) ? null : reader.GetString(14),
                ReportLoinc: reader.IsDBNull(15) ? null : reader.GetString(15),
                IsDuplicateAccession: reader.GetInt64(16) != 0,
                FirstSeenReportId: reader.IsDBNull(17) ? null : reader.GetInt64(17),
                CreatedDatetime: reader.GetDateTime(18),
                UpdatedDatetime: reader.GetDateTime(19)
            );
        }
        return null;
    }

    public ISdcCdm.SdcReportRecord? FindSdcReportByGuid(string templateInstanceGuid)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT sdc_report_id, template_name, template_version, template_instance_guid,
                   person_id, visit_occurrence_id, provider_id, report_text, report_template_source,
                   report_template_id, report_template_version_id, tumor_site, procedure_type, specimen_laterality,
                   report_accession, report_loinc, is_duplicate_accession, first_seen_report_id,
                   created_datetime, updated_datetime
            FROM sdc.sdc_report 
            WHERE template_instance_guid = @templateInstanceGuid
        ";

        cmd.Parameters.AddWithValue("@templateInstanceGuid", templateInstanceGuid);

        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            return new ISdcCdm.SdcReportRecord(
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
                ReportAccession: reader.IsDBNull(14) ? null : reader.GetString(14),
                ReportLoinc: reader.IsDBNull(15) ? null : reader.GetString(15),
                IsDuplicateAccession: reader.GetInt64(16) != 0,
                FirstSeenReportId: reader.IsDBNull(17) ? null : reader.GetInt64(17),
                CreatedDatetime: reader.GetDateTime(18),
                UpdatedDatetime: reader.GetDateTime(19)
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
            new ConceptRecord
            {
                ConceptId = 45905771,
                ConceptName = "Observation recorded from EHR",
                DomainId = "Type Concept",
                VocabularyId = "Type Concept",
                ConceptClassId = "Type Concept",
                StandardConcept = "S",
                ConceptCode = "EHR_obs",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
            // Note type for the synoptic-report NOTE row (one per eCP report)
            new ConceptRecord
            {
                ConceptId = 32817,
                ConceptName = "EHR",
                DomainId = "Type Concept",
                VocabularyId = "Type Concept",
                ConceptClassId = "Type Concept",
                StandardConcept = "S",
                ConceptCode = "EHR",
                ValidStartDate = DateTime.Parse("1970-01-01"),
                ValidEndDate = DateTime.Parse("2099-12-31"),
                InvalidReason = null,
            },
            // CDM field concept for note.note_id, used as observation.obs_event_field_concept_id
            // when observation_event_id references the synoptic-report NOTE row.
            // TODO: confirm the exact field concept_id against the loaded OMOP vocabulary.
            new ConceptRecord
            {
                ConceptId = 1147289,
                ConceptName = "note.note_id",
                DomainId = "Metadata",
                VocabularyId = "CDM",
                ConceptClassId = "Field",
                StandardConcept = "S",
                ConceptCode = "note.note_id",
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
