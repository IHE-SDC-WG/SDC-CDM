SELECT [concept_id]
      , [concept_name]
      , [vocabulary_id]
      , [concept_class_id]
      , [concept_code]
      , [domain_id]
      -- , [valid_start_date]
      -- , [valid_end_date]
FROM [NAACCRDDPRD].[dbo].[CONCEPT]
WHERE valid_end_date > GETDATE()

AND
(
      -- [vocabulary_id] NOT LIKE '%NAACCR2026%' 
      -- AND
      [concept_name] LIKE '%term%'
)
-- (
--        [vocabulary_id] LIKE '%DEMOGRAPHIC%' OR
--        [vocabulary_id] = 'FOLLOW_UP_RECURRENCE' OR
--        [vocabulary_id] LIKE '%CONFIDENTIAL%' OR
      --  [vocabulary_id] LIKE '%HOSPITAL%'
--   )
ORDER BY [vocabulary_id], [concept_class_id]