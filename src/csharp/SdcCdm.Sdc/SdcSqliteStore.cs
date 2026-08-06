using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;

namespace SdcCdm;

public sealed class SdcSqliteStore : ISdcCdm, IDisposable
{
    private static readonly ILoggerFactory LoggerFactory =
        Microsoft.Extensions.Logging.LoggerFactory.Create(builder => builder.AddConsole());

    private readonly SqliteConnection connection;

    public ILogger Logger { get; set; }

    public SdcSqliteStore(string dbFilePath, bool inMemory = false, bool overwrite = false)
    {
        string connectionString = new SqliteConnectionStringBuilder
        {
            Mode = inMemory ? SqliteOpenMode.Memory : SqliteOpenMode.ReadWriteCreate,
            DataSource = dbFilePath,
        }.ToString();
        if (overwrite && !inMemory && File.Exists(dbFilePath))
        {
            File.Delete(dbFilePath);
        }

        connection = new SqliteConnection(connectionString);
        connection.Open();
        connection.ExecuteNonQuery("PRAGMA foreign_keys = ON;");

        string sdcDataSource;
        if (inMemory)
        {
            sdcDataSource = ":memory:";
        }
        else
        {
            string directory = Path.GetDirectoryName(Path.GetFullPath(dbFilePath)) ?? ".";
            string fileName = Path.GetFileNameWithoutExtension(dbFilePath);
            sdcDataSource = Path.Combine(directory, $"{fileName}.sdc.db");
            if (overwrite && File.Exists(sdcDataSource))
            {
                File.Delete(sdcDataSource);
            }
        }

        using (var command = connection.CreateCommand())
        {
            command.CommandText = $"ATTACH DATABASE '{sdcDataSource.Replace("'", "''")}' AS sdc;";
            command.ExecuteNonQuery();
        }

        Logger = LoggerFactory.CreateLogger<SdcSqliteStore>();
    }

    public void BuildSchema()
    {
        var assembly = typeof(SdcSqliteStore).Assembly;
        string? resourceName = assembly
            .GetManifestResourceNames()
            .SingleOrDefault(name =>
                name.EndsWith("1_sdc_sqlite_ddl.sql", StringComparison.OrdinalIgnoreCase)
            );
        if (resourceName is null)
        {
            throw new InvalidOperationException("The embedded SDC SQLite DDL was not found.");
        }

        using Stream stream =
            assembly.GetManifestResourceStream(resourceName)
            ?? throw new InvalidOperationException(
                $"The embedded resource {resourceName} was not found."
            );
        using StreamReader reader = new(stream);
        using var command = connection.CreateCommand();
        command.CommandText = reader.ReadToEnd();
        command.ExecuteNonQuery();
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

        return (long)(cmd.ExecuteScalar() ?? -1L);
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
                (template_instance_version_guid, template_instance_version_uri, template_sdc_id,
                 instance_version_date, diag_report_props, surg_path_sdcid, person_id,
                 visit_occurrence_id, provider_id, report_text)
                VALUES (@templateinstanceversionguid, @templateinstanceversionuri, @templatesdcfk,
                        @instanceversiondate, @diagreportprops, @surgpathid, @personfk,
                        @encounterfk, @practitionerfk, @reporttext);
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

        return (long)(cmd.ExecuteScalar() ?? -1L);
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
        string? response_string,
        string? li_parent_guid
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
                response_string, datatype, sdc_order
            ) VALUES (
                @template_instance_id, @parent_form_answer_id,
                @section_sdcid, @section_guid, @question_text, @question_instance_guid, @question_sdcid,
                @list_item_id, @list_item_text, @list_item_instance_guid, @list_item_parent_guid,
                @units_system, @response, @units, @response_int, @response_float, @response_datetime,
                @response_string, @datatype, @sdc_order
            );
            SELECT last_insert_rowid();
        ";

        cmd.Parameters.AddWithValue("@template_instance_id", template_instance_class_fk);
        cmd.Parameters.AddWithValue(
            "@parent_form_answer_id",
            parent_observation_id ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@section_sdcid", section_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@section_guid", section_guid ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@question_text", q_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@question_instance_guid",
            q_instance_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue("@question_sdcid", q_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@list_item_id", li_id ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@list_item_text", li_text ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue(
            "@list_item_instance_guid",
            li_instance_guid ?? (object)DBNull.Value
        );
        cmd.Parameters.AddWithValue(
            "@list_item_parent_guid",
            li_parent_guid ?? (object)DBNull.Value
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
        cmd.Parameters.AddWithValue("@response_string", response_string ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@datatype", datatype ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@sdc_order", sdc_order ?? (object)DBNull.Value);

        return Convert.ToInt64(cmd.ExecuteScalar());
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
        cmd.Parameters.AddWithValue("@templateinstanceversionguid", instanceVersionGuid);
        object? result = cmd.ExecuteScalar();
        return result is null ? null : Convert.ToInt64(result);
    }

    public ISdcCdm.TemplateInstanceRecord? GetTemplateInstanceRecord(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT template_instance_id, template_instance_version_guid,
                   template_instance_version_uri, template_sdc_id, instance_version_date,
                   diag_report_props, surg_path_sdcid, person_id, visit_occurrence_id,
                   provider_id, report_text
            FROM sdc.template_instance
            WHERE template_instance_id = @templateinstanceclasspk
            ";
        cmd.Parameters.AddWithValue("@templateinstanceclasspk", templateInstanceClassPk);
        using var reader = cmd.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new ISdcCdm.TemplateInstanceRecord(
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
    }

    public List<SdcObsClass> GetSdcObsClasses(long templateInstanceClassPk)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            @"
            SELECT sdc_form_answer_id, template_instance_id, section_sdcid, section_guid,
                   question_text, question_instance_guid, question_sdcid, list_item_text,
                   list_item_id, list_item_instance_guid, list_item_parent_guid, response,
                   units, units_system, datatype, response_int, response_float,
                   response_datetime, response_string, sdc_order,
                   sdc_repeat_level, sdc_comments
            FROM sdc.sdc_form_answer
            WHERE template_instance_id = @templateinstanceclasspk
            ORDER BY sdc_form_answer_id
            ";
        cmd.Parameters.AddWithValue("@templateinstanceclasspk", templateInstanceClassPk);
        using var reader = cmd.ExecuteReader();
        List<SdcObsClass> rows = [];
        while (reader.Read())
        {
            rows.Add(
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
                    reader.IsDBNull(19) ? null : reader.GetString(19),
                    reader.IsDBNull(20) ? null : reader.GetString(20),
                    reader.IsDBNull(21) ? null : reader.GetString(21)
                )
            );
        }
        return rows;
    }

    public long? FindTemplateItem(string template_item_sdcid)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText =
            "SELECT template_item_id FROM sdc.template_item WHERE template_item_sdcid = @sdcid";
        cmd.Parameters.AddWithValue("@sdcid", template_item_sdcid);
        object? result = cmd.ExecuteScalar();
        return result is null ? null : Convert.ToInt64(result);
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

        long templateItemId = Convert.ToInt64(cmd.ExecuteScalar());
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

    public SqliteConnection GetConnection() => connection;

    public void Dispose() => connection.Dispose();
}

internal static class SqliteConnectionExtensions
{
    public static void ExecuteNonQuery(this SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.ExecuteNonQuery();
    }
}
