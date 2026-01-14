
-- Reconstruct original CSV outputs from 3NF tables
-- Target: Microsoft SQL Server


-- 1) Schema CSV (schema-file.csv)
SELECT
  s.schema_id_number         AS [Schema ID Number],
  s.schema_id                AS [Schema ID],
  ISNULL(s.schema_name,'')   AS [Schema Name],
  ISNULL(r.site,'')          AS [Site],
  ISNULL(r.histology,'')     AS [Histology],
  ISNULL(r.behavior,'')      AS [Behavior],
  ISNULL(r.sex_at_birth,'')  AS [Sex],
  ISNULL(r.discriminator_1,'') AS [SD1],
  ISNULL(r.discriminator_2,'') AS [SD2],
  ISNULL(r.year_dx,'')       AS [Year DX]
FROM cap.STAGING_SCHEMA s
JOIN cap.SCHEMA_SELECTION_RULE r
  ON s.schema_id_number = r.schema_id_number
ORDER BY
  TRY_CAST(s.schema_id_number AS INT),
  r.site,
  r.histology,
  r.behavior,
  r.sex_at_birth,
  r.discriminator_1,
  r.discriminator_2,
  r.year_dx;



-- 2) SSDI List CSV (ssdi-list-file.csv)
SELECT
  s.schema_id_number                    AS [Schema ID Number],
  CAST(si.item_num AS VARCHAR)          AS [NAACCR Item Num],
  ISNULL(ni.name,'')                    AS [NAACCR Item Name],
  ISNULL(ni.xml_id,'')                  AS [NAACCR XML ID],
  CASE WHEN ISNULL(req.seer_required,0) = 1 THEN 'SEER REQ' ELSE 'NOT SEER REQ' END AS [Is SEER Required],
  CASE WHEN ISNULL(req.npcr_required,0) = 1 THEN 'NPCR REQ' ELSE 'NOT NPCR REQ' END AS [Is NPCR Required],
  CASE WHEN ISNULL(req.coc_required,0)  = 1 THEN 'COC REQ'  ELSE 'NOT COC REQ'  END AS [Is COC Required],
  CASE WHEN ISNULL(req.cccr_required,0) = 1 THEN 'CCCR REQ' ELSE 'NOT CCCR REQ' END AS [Is CCCR Required],
  CASE WHEN si.used_for_staging = 1 THEN 'true' ELSE 'false' END  AS [Is Required For Staging],
  ISNULL(si.default_value,'')           AS [Default Value],
  ISNULL(si.description,'')             AS [Description],
  ISNULL(si.rationale,'')               AS [Rationale],
  ISNULL(si.additional_info,'')         AS [Additional Info],
  ISNULL(si.table_notes,'')             AS [Table Notes],
  ISNULL(si.coding_guidelines,'')       AS [Coding Guidelines]
FROM cap.SCHEMA_ITEM si
JOIN cap.STAGING_SCHEMA s
  ON s.schema_id_number = si.schema_id_number
LEFT JOIN cap.NAACCR_ITEM ni
  ON ni.item_num = si.item_num
LEFT JOIN (
  SELECT
    sir.schema_id_number,
    sir.item_num,
    MAX(CASE WHEN reg.code = 'SEER'  AND sir.is_required = 1 THEN 1 ELSE 0 END) AS seer_required,
    MAX(CASE WHEN reg.code = 'NPCR'  AND sir.is_required = 1 THEN 1 ELSE 0 END) AS npcr_required,
    MAX(CASE WHEN reg.code = 'COC'   AND sir.is_required = 1 THEN 1 ELSE 0 END) AS coc_required,
    MAX(CASE WHEN reg.code = 'CCCR'  AND sir.is_required = 1 THEN 1 ELSE 0 END) AS cccr_required
  FROM cap.SCHEMA_ITEM_REQUIREMENT sir
  JOIN cap.REGISTRY reg ON reg.id = sir.registry_id
  GROUP BY sir.schema_id_number, sir.item_num
) req
  ON req.schema_id_number = si.schema_id_number
 AND req.item_num         = si.item_num
ORDER BY TRY_CAST(s.schema_id_number AS INT), si.item_num;



-- 3) SSDI Code CSV (ssdi-code-file.csv)
SELECT
  schema_id_number          AS [Schema ID Number],
  CAST(item_num AS VARCHAR) AS [NAACCR Item Num],
  ISNULL(code,'')           AS [Code],
  ISNULL(description,'')    AS [Description]
FROM cap.SCHEMA_ITEM_CODE
ORDER BY TRY_CAST(schema_id_number AS INT), item_num, code;
