using Microsoft.Data.Sqlite;
using SdcCdm;

namespace SdcCdmInSqlite;

public class SdcCdmInSqlite : ISdcCdm
{
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
            string fileName = resourceName.Substring(resourcePrefix.Length);

            Console.WriteLine($"Executing {fileName}...");

            // Read the embedded SQL script
            using (Stream? stream = assembly.GetManifestResourceStream(resourceName))
            {
                if (stream == null)
                {
                    throw new Exception(
                        $"Internal error - could not find SQL script {resourceName}."
                    );
                }

                using StreamReader reader = new(stream);
                string sqlScript = reader.ReadToEnd();

                // Assuming you have an open connection named 'connection'
                using var command = connection.CreateCommand();
                command.CommandText = sqlScript;
                command.ExecuteNonQuery();
            }

            Console.WriteLine($"Finished executing {fileName}.");
        }
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
        // Print data for debugging:
        Console.WriteLine(
            $"TemplateSdcClass: {sdcformdesignid}, {baseuri}, {lineage}, {version}, {fulluri}, {formtitle}, {sdc_xml}, {doctype}"
        );

        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO main.templatesdcclass 
                (sdcformdesignid, baseuri, lineage, version, fulluri, formtitle, sdc_xml, doctype)
                VALUES (@sdcformdesignid, @baseuri, @lineage, @version, @fulluri, @formtitle, @sdc_xml, @doctype);
                SELECT last_insert_rowid();
            ";

        cmd.Parameters.AddWithValue("@sdcformdesignid", sdcformdesignid);
        cmd.Parameters.AddWithValue("@baseuri", baseuri);
        cmd.Parameters.AddWithValue("@lineage", lineage);
        cmd.Parameters.AddWithValue("@version", version);
        cmd.Parameters.AddWithValue("@fulluri", fulluri);
        cmd.Parameters.AddWithValue("@formtitle", formtitle);
        cmd.Parameters.AddWithValue("@sdc_xml", sdc_xml);
        cmd.Parameters.AddWithValue("@doctype", doctype);

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
        // Print data for debugging:
        Console.WriteLine($"TemplateInstanceClass: {templatesdc_fk}");

        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO templateinstanceclass 
                (templateinstanceversionguid, templateinstanceversionuri, templatesdcfk, instanceversiondate, diagreportprops, surgpathid, personfk, encounterfk, practitionerfk, reporttext)
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
        // Print data for debugging:
        Console.WriteLine(
            $"SdcObsClass: {template_instance_class_fk}, {section_id}, {section_guid}, {q_text}, {q_instance_guid}, {q_id}, {li_text}, {li_id}, {li_instance_guid}, {sdc_order}, {response}, {units}, {units_system}, {datatype}, {response_int}, {response_float}, {response_datetime}, {reponse_string_nvarchar}, {li_parent_guid}"
        );

        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
                INSERT INTO sdcobsclass 
                (templateinstanceclassfk, parentinstanceguid, section_id, section_guid, q_text, q_instanceguid, q_id, li_text, li_id, li_instanceguid, li_parentguid, response, units, units_system, datatype, response_int, response_float, response_datetime, reponse_string_nvarchar, obsdatetime, sdcorder, sdcrepeatlevel, sdccomments, personfk, encounterfk, practitionerfk)
                VALUES (@templateinstanceclassfk, @parentinstanceguid, @section_id, @section_guid, @q_text, @q_instanceguid, @q_id, @li_text, @li_id, @li_instanceguid, @li_parentguid, @response, @units, @units_system, @datatype, @response_int, @response_float, @response_datetime, @reponse_string_nvarchar, @obsdatetime, @sdcorder, @sdcrepeatlevel, @sdccomments, @personfk, @encounterfk, @practitionerfk);
                SELECT last_insert_rowid();
            ";

        cmd.Parameters.AddWithValue("@templateinstanceclassfk", template_instance_class_fk);
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
        cmd.Parameters.AddWithValue("@personfk", DBNull.Value);
        cmd.Parameters.AddWithValue("@encounterfk", DBNull.Value);
        cmd.Parameters.AddWithValue("@practitionerfk", DBNull.Value);

        var pk = cmd.ExecuteScalar() ?? -1;
        return (long)pk;
    }

    public bool FindTemplateSdcClass(string formDesignId, out long primaryKey)
    {
        primaryKey = 0;
        return false;
    }

    public bool FindTemplateInstanceClass(
        string instanceVersionGuid,
        out long templateInstanceClassPk,
        string? instanceVersionDate = null
    )
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT pk
            FROM templateinstanceclass
            WHERE templateinstanceversionguid = @templateinstanceversionguid
            ";
        cmd.Parameters.AddWithValue(
            "@templateinstanceversionguid",
            instanceVersionGuid ?? (object)DBNull.Value
        );
        var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            templateInstanceClassPk = reader.GetInt64(0);
            reader.Close();
            return true;
        }
        reader.Close();
        templateInstanceClassPk = -1L;
        return false;

        // TODO: Support searching by instanceVersionDate
    }

    public bool FindPerson(long personPk, out long foundPersonPk)
    {
        foundPersonPk = -1L;
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
            foundPersonPk = reader.GetInt64(0);
            reader.Close();
            return true;
        }
        reader.Close();
        return false;
    }

    public TemplateInstanceRecord GetTemplateInstanceRecord(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT
                templateinstanceclass.pk,
                templateinstanceversionguid,
                templateinstanceversionuri,
                templatesdcfk,
                instanceversiondate,
                diagreportprops,
                surgpathid,
                personfk,
                encounterfk,
                practitionerfk,
                reporttext
            FROM templateinstanceclass
            INNER JOIN templatesdcclass ON templatesdcclass.pk = templateinstanceclass.templatesdcfk
            WHERE templateinstanceclass.pk = @templateinstanceclasspk
            ";
        cmd.Parameters.AddWithValue("@templateinstanceclasspk", templateInstanceClassPk);
        var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            TemplateInstanceRecord record = new(
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
        throw new Exception("No template instance record found");
    }

    public List<SdcObsClass> GetSdcObsClasses(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT
                sdcobsclass.pk,
                sdcobsclass.templateinstanceclassfk,
                sdcobsclass.section_id,
                sdcobsclass.section_guid,
                sdcobsclass.q_text,
                sdcobsclass.q_instanceguid,
                sdcobsclass.q_id,
                sdcobsclass.li_text,
                sdcobsclass.li_id,
                sdcobsclass.li_instanceguid,
                sdcobsclass.li_parentguid,
                sdcobsclass.response,
                sdcobsclass.units,
                sdcobsclass.units_system,
                sdcobsclass.datatype,
                sdcobsclass.response_int,
                sdcobsclass.response_float,
                sdcobsclass.response_datetime,
                sdcobsclass.reponse_string_nvarchar,
                sdcobsclass.obsdatetime,
                sdcobsclass.sdcorder,
                sdcobsclass.sdcrepeatlevel,
                sdcobsclass.sdccomments,
                sdcobsclass.personfk,
                sdcobsclass.encounterfk,
                sdcobsclass.practitionerfk
            FROM sdcobsclass
            INNER JOIN templateinstanceclass ON templateinstanceclass.pk = sdcobsclass.templateinstanceclassfk
            WHERE templateinstanceclass.pk = @templateinstanceclasspk
            ORDER BY sdcobsclass.pk
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
                    reader.IsDBNull(22) ? null : reader.GetString(22),
                    reader.IsDBNull(23) ? null : reader.GetInt64(23),
                    reader.IsDBNull(24) ? null : reader.GetInt64(24),
                    reader.IsDBNull(25) ? null : reader.GetInt64(25)
                )
            );
            reader.Close();
            return sdcObsClasses;
        }
        reader.Close();
        throw new Exception("No template instance records found");
    }
}
