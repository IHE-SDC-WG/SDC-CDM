/*
  TypeScript port of CreateSSDIFile.java
  - Generates the original three flat CSVs: schema-file.csv, ssdi-list-file.csv, ssdi-code-file.csv
  - With SSDI_OUTPUT_3NF=1, generates the 3NF CSVs loaded into the naaccr schema:
      data_dictionary_version.csv, staging_schema.csv, schema_selection_rule.csv,
      naaccr_item.csv, schema_item.csv, registry.csv, schema_item_requirement.csv,
      schema_item_code.csv, staging_table.csv, staging_table_column.csv,
      staging_table_row.csv, schema_involved_table.csv
  - Uses SEER Staging REST API documented at /v3/api-docs
  - Reads API key from env var SEER_API_KEY
*/

import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';

type StagingColumnDefinition = { key?: string; name?: string; type?: string; source?: string };
type StagingTable = {
  id: string;
  algorithm: string;
  version: string;
  name?: string;
  title?: string;
  subtitle?: string;
  description?: string;
  notes?: string;
  rationale?: string;
  additional_info?: string;
  coding_guidelines?: string;
  footnotes?: string;
  definition: StagingColumnDefinition[];
  extra_input?: string[];
  rows: string[][];
};

type StagingMetadata = { name: string; start?: number; end?: number };

type StagingSchemaInput = {
  key: string;
  name: string;
  description?: string;
  naaccr_item?: number;
  naaccr_xml_id?: string;
  default?: string;
  table?: string;
  used_for_staging?: boolean;
  unit?: string;
  decimal_places?: number;
  metadata?: StagingMetadata[];
  default_table?: string;
};

type StagingSchemaOutput = {
  key: string;
  name?: string;
  description?: string;
  naaccr_item?: number;
  naaccr_xml_id?: string;
  table?: string;
  default?: string;
  metadata?: StagingMetadata[];
};

type StagingSchema = {
  id: string;
  algorithm: string;
  version: string;
  name?: string;
  title?: string;
  schema_selection_table?: string;
  inputs: StagingSchemaInput[];
  outputs: StagingSchemaOutput[];
};

type SchemaProjection = { id: string; name?: string; title?: string; schema_num?: number };

const BASE = 'https://api.seer.cancer.gov';
const API_KEY = process.env.SEER_API_KEY || '';

const ALGORITHM = process.env.SSDI_ALGORITHM || 'eod_public';
const VERSION = process.env.SSDI_VERSION || '3.3';
// Optional: NAACCR data-dictionary version label recorded alongside the staging version.
const NAACCR_VERSION = process.env.SSDI_NAACCR_VERSION || '';
const OUT_DIR = process.env.SSDI_OUT_DIR || 'out-egs';
const OUTPUT_3NF = (process.env.SSDI_OUTPUT_3NF || '').toLowerCase() === 'true' || process.env.SSDI_OUTPUT_3NF === '1';

async function apiGet<T>(path: string): Promise<T> {
  const url = `${BASE}${path}`;
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (API_KEY) headers['X-SEERAPI-Key'] = API_KEY;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText} ${text}`);
  }
  return res.json() as Promise<T>;
}

function writeCsvLine(values: unknown[]): string {
  if (!values) return '';
  const parts: string[] = [];
  for (const v of values) {
    // Preserve column positions: empty string for null/undefined rather than dropping the cell.
    const s = (v === null || v === undefined) ? '' : String(v).replace(/"/g, '""');
    parts.push(`"${s}"`);
  }
  return parts.join(',');
}

async function main() {
  // Resolve output directory relative to repository root (two levels up from tools/ssdi-ts)
  const repoRoot = join(process.cwd(), '..', '..');
  const outDirPath = isAbsolute(OUT_DIR) ? OUT_DIR : join(repoRoot, OUT_DIR);
  if (!existsSync(outDirPath)) mkdirSync(outDirPath, { recursive: true });

  // Original flat CSV headers
  const schemaHeaders = [
    'Schema ID Number', 'Schema ID', 'Schema Name',
    'Site', 'Histology', 'Behavior', 'Sex', 'SD1', 'SD2', 'Year DX'
  ];
  const ssdiListHeaders = [
    'Schema ID Number', 'NAACCR Item Num', 'NAACCR Item Name', 'NAACCR XML ID',
    'Is SEER Required', 'Is NPCR Required', 'Is COC Required', 'Is CCCR Required',
    'Is Required For Staging', 'Default Value', 'Description', 'Rationale',
    'Additional Info', 'Table Notes', 'Coding Guidelines'
  ];
  const ssdiCodeHeaders = [
    'Schema ID Number', 'NAACCR Item Num', 'Code', 'Description'
  ];

  const schemaFilePath = join(outDirPath, 'schema-file.csv');
  const ssdiListFilePath = join(outDirPath, 'ssdi-list-file.csv');
  const ssdiCodeFilePath = join(outDirPath, 'ssdi-code-file.csv');

  const schemaLines: string[] = [writeCsvLine(schemaHeaders)];
  const ssdiListLines: string[] = [writeCsvLine(ssdiListHeaders)];
  const ssdiCodeLines: string[] = [writeCsvLine(ssdiCodeHeaders)];

  // 3NF CSV headers. dd_version_id is NOT emitted here: the loader upserts one
  // data_dictionary_version row per run and injects its resolved id into every insert.
  const ddVersionHeaders = ['algorithm', 'version', 'naaccr_version', 'source_api'];
  const stagingSchemaHeaders = ['schema_id_number', 'schema_id', 'schema_name'];
  const selectionRuleHeaders = ['schema_id_number', 'site', 'histology', 'behavior', 'sex_at_birth', 'discriminator_1', 'discriminator_2', 'year_dx'];
  const naaccrItemHeaders = ['item_num', 'name', 'xml_id', 'unit', 'decimal_places'];
  const schemaItemHeaders = ['schema_id_number', 'item_num', 'item_role', 'used_for_staging', 'default_value', 'description', 'rationale', 'additional_info', 'table_notes', 'coding_guidelines'];
  const registryHeaders = ['code', 'name'];
  const schemaItemRequirementHeaders = ['schema_id_number', 'item_num', 'registry_code', 'is_required'];
  const schemaItemCodeHeaders = ['schema_id_number', 'item_num', 'code', 'description'];
  const stagingTableHeaders = ['table_key', 'name', 'title', 'subtitle', 'description', 'notes', 'coding_guidelines'];
  const stagingTableColumnHeaders = ['table_key', 'col_index', 'col_key', 'col_name', 'col_type', 'col_source'];
  const stagingTableRowHeaders = ['table_key', 'row_index', 'cells'];
  const schemaInvolvedTableHeaders = ['schema_id_number', 'table_key'];

  const ddVersionFilePath = join(outDirPath, 'data_dictionary_version.csv');
  const stagingSchemaFilePath = join(outDirPath, 'staging_schema.csv');
  const selectionRuleFilePath = join(outDirPath, 'schema_selection_rule.csv');
  const naaccrItemFilePath = join(outDirPath, 'naaccr_item.csv');
  const schemaItemFilePath = join(outDirPath, 'schema_item.csv');
  const registryFilePath = join(outDirPath, 'registry.csv');
  const schemaItemRequirementFilePath = join(outDirPath, 'schema_item_requirement.csv');
  const schemaItemCodeFilePath3nf = join(outDirPath, 'schema_item_code.csv');
  const stagingTableFilePath = join(outDirPath, 'staging_table.csv');
  const stagingTableColumnFilePath = join(outDirPath, 'staging_table_column.csv');
  const stagingTableRowFilePath = join(outDirPath, 'staging_table_row.csv');
  const schemaInvolvedTableFilePath = join(outDirPath, 'schema_involved_table.csv');

  const stagingSchemaLines: string[] = [writeCsvLine(stagingSchemaHeaders)];
  const selectionRuleLines: string[] = [writeCsvLine(selectionRuleHeaders)];
  const naaccrItemLines: string[] = [writeCsvLine(naaccrItemHeaders)];
  const schemaItemLines: string[] = [writeCsvLine(schemaItemHeaders)];
  const registryLines: string[] = [writeCsvLine(registryHeaders)];
  const schemaItemRequirementLines: string[] = [writeCsvLine(schemaItemRequirementHeaders)];
  const schemaItemCodeLines3nf: string[] = [writeCsvLine(schemaItemCodeHeaders)];
  const schemaInvolvedTableLines: string[] = [writeCsvLine(schemaInvolvedTableHeaders)];

  const seenSchemas = new Set<string>();
  const naaccrItemMap = new Map<number, { name: string; xml_id: string; unit?: string; decimal_places?: number }>();
  // Gap #3: table catalog, deduped by table id. Fetched once, emitted once.
  const stagingTableMap = new Map<string, StagingTable>();
  // Gap #3: schema -> involved table ids (selection table + input/output tables).
  const involvedTables = new Set<string>(); // encoded as `${schemaNum}\0${tableId}`
  // Guard against (schema, item) duplicates when an item is both an input and an output.
  const seenSchemaItems = new Set<string>();

  // Fetch-and-cache a staging table (also registers it in the catalog for later emission).
  async function getTable(id: string | undefined): Promise<StagingTable | undefined> {
    if (!id) return undefined;
    let t = stagingTableMap.get(id);
    if (!t) {
      t = await apiGet<StagingTable>(`/rest/staging/${ALGORITHM}/${VERSION}/table/${encodeURIComponent(id)}`);
      stagingTableMap.set(id, t);
    }
    return t;
  }

  function markInvolved(schemaNumStr: string, tableId?: string) {
    if (tableId) involvedTables.add(`${schemaNumStr}\0${tableId}`);
  }

  // 1) List schemas for algorithm/version
  const projections = await apiGet<SchemaProjection[]>(`/rest/staging/${ALGORITHM}/${VERSION}/schemas`);

  // 2) Build map of numeric schema ID -> schema id (sort by numeric id asc)
  const pairs: { schemaNumStr: string; schemaId: string }[] = [];
  for (const proj of projections) {
    const sch = await apiGet<StagingSchema>(`/rest/staging/${ALGORITHM}/${VERSION}/schema/${encodeURIComponent(proj.id)}`);
    const naaccrSchemaOut = (sch.outputs || []).find(o => o.key === 'naaccr_schema_id');
    const num = naaccrSchemaOut?.default || '';
    if (!num) continue; // skip schemas without a numeric id
    pairs.push({ schemaNumStr: num, schemaId: sch.id });
  }
  pairs.sort((a, b) => Number(a.schemaNumStr) - Number(b.schemaNumStr));

  // 3) Iterate schemas in sorted order
  for (const { schemaNumStr, schemaId } of pairs) {
    const schema = await apiGet<StagingSchema>(`/rest/staging/${ALGORITHM}/${VERSION}/schema/${encodeURIComponent(schemaId)}`);

    // 3NF: add one row per schema
    if (!seenSchemas.has(schemaNumStr)) {
      stagingSchemaLines.push(writeCsvLine([
        schemaNumStr,
        schema.id,
        schema.name ?? ''
      ]));
      seenSchemas.add(schemaNumStr);
    }

    // 3a) Schema selection table rows -> schema-file.csv
    const selectionTableId = schema.schema_selection_table;
    if (selectionTableId) {
      const table = await getTable(selectionTableId);
      markInvolved(schemaNumStr, selectionTableId);
      // determine indices
      let siteIdx = -1, histIdx = -1, behIdx = -1, sexIdx = -1, sd1Idx = -1, sd2Idx = -1, yearIdx = -1;
      table!.definition.forEach((def, i) => {
        switch (def.key) {
          case 'site': siteIdx = i; break;
          case 'hist': histIdx = i; break;
          case 'sex_at_birth': sexIdx = i; break;
          case 'behavior': behIdx = i; break;
          case 'discriminator_1': sd1Idx = i; break;
          case 'discriminator_2': sd2Idx = i; break;
          case 'year_dx': yearIdx = i; break;
        }
      });

      for (const row of table!.rows) {
        const line = [
          schemaNumStr,
          schemaId,
          schema.name ?? '',
          siteIdx >= 0 ? row[siteIdx] : '',
          histIdx >= 0 ? row[histIdx] : '',
          behIdx >= 0 ? row[behIdx] : '',
          sexIdx >= 0 ? row[sexIdx] : '',
          sd1Idx >= 0 ? row[sd1Idx] : '',
          sd2Idx >= 0 ? row[sd2Idx] : '',
          yearIdx >= 0 ? row[yearIdx] : ''
        ];
        schemaLines.push(writeCsvLine(line));

        // 3NF: selection rules
        const selectionLine = [
          schemaNumStr,
          siteIdx >= 0 ? row[siteIdx] : '',
          histIdx >= 0 ? row[histIdx] : '',
          behIdx >= 0 ? row[behIdx] : '',
          sexIdx >= 0 ? row[sexIdx] : '',
          sd1Idx >= 0 ? row[sd1Idx] : '',
          sd2Idx >= 0 ? row[sd2Idx] : '',
          yearIdx >= 0 ? row[yearIdx] : ''
        ];
        selectionRuleLines.push(writeCsvLine(selectionLine));
      }
    }

    // 3b) SSDI inputs -> ssdi-list-file.csv, ssdi-code-file.csv, and 3NF schema_item(input)
    const inputs = schema.inputs || [];
    const ssdiInputs = inputs
      .filter(inp => (inp.metadata || []).some(m => m.name === 'SSDI'))
      .sort((a, b) => (a.naaccr_item ?? 0) - (b.naaccr_item ?? 0));

    for (const inp of ssdiInputs) {
      // Fetch related table (may be undefined)
      const table = await getTable(inp.table);
      markInvolved(schemaNumStr, inp.table);

      const isReq = (key: string) => (inp.metadata || []).some(m => m.name === key);
      const ssdiListLine = [
        schemaNumStr,
        inp.naaccr_item?.toString() ?? '',
        inp.name ?? '',
        inp.naaccr_xml_id ?? '',
        isReq('SEER_REQUIRED') ? 'SEER REQ' : 'NOT SEER REQ',
        isReq('NPCR_REQUIRED') ? 'NPCR REQ' : 'NOT NPCR REQ',
        isReq('COC_REQUIRED') ? 'COC REQ' : 'NOT COC REQ',
        isReq('CCCR_REQUIRED') ? 'CCCR REQ' : 'NOT CCCR REQ',
        String(Boolean(inp.used_for_staging)),
        inp.default ?? '',
        table?.description ?? '',
        table?.rationale ?? '',
        table?.additional_info ?? '',
        table?.notes ?? '',
        table?.coding_guidelines ?? ''
      ];
      ssdiListLines.push(writeCsvLine(ssdiListLine));

      // 3NF: accumulate canonical NAACCR items (with unit/decimal_places from the input)
      if (typeof inp.naaccr_item === 'number') {
        const existing = naaccrItemMap.get(inp.naaccr_item);
        if (!existing) {
          naaccrItemMap.set(inp.naaccr_item, {
            name: inp.name ?? '',
            xml_id: inp.naaccr_xml_id ?? '',
            unit: inp.unit,
            decimal_places: inp.decimal_places
          });
        } else {
          if (existing.unit === undefined && inp.unit !== undefined) existing.unit = inp.unit;
          if (existing.decimal_places === undefined && inp.decimal_places !== undefined) existing.decimal_places = inp.decimal_places;
        }
      }

      // 3NF: schema_item (role=input)
      const siKey = `${schemaNumStr}\0${inp.naaccr_item ?? ''}`;
      if (!seenSchemaItems.has(siKey)) {
        seenSchemaItems.add(siKey);
        schemaItemLines.push(writeCsvLine([
          schemaNumStr,
          inp.naaccr_item?.toString() ?? '',
          'input',
          String(Boolean(inp.used_for_staging)),
          inp.default ?? '',
          table?.description ?? '',
          table?.rationale ?? '',
          table?.additional_info ?? '',
          table?.notes ?? '',
          table?.coding_guidelines ?? ''
        ]));

        // 3NF: schema_item_requirement (four registries)
        const registryReqs: Array<{ code: string; required: boolean }> = [
          { code: 'SEER', required: isReq('SEER_REQUIRED') },
          { code: 'NPCR', required: isReq('NPCR_REQUIRED') },
          { code: 'COC', required: isReq('COC_REQUIRED') },
          { code: 'CCCR', required: isReq('CCCR_REQUIRED') }
        ];
        for (const rr of registryReqs) {
          schemaItemRequirementLines.push(writeCsvLine([
            schemaNumStr,
            inp.naaccr_item?.toString() ?? '',
            rr.code,
            String(rr.required)
          ]));
        }
      }

      if (table) {
        // find description column index (case-insensitive)
        let descriptionIdx = -1;
        for (let i = 0; i < table.definition.length; i++) {
          const def = table.definition[i];
          if ((def.key || '').toLowerCase() === 'description') {
            descriptionIdx = i; break;
          }
        }
        for (const row of table.rows) {
          const code = row[0] ?? '';
          const desc = descriptionIdx >= 0 ? (row[descriptionIdx] ?? '') : '';
          const codeLine = [
            schemaNumStr,
            inp.naaccr_item?.toString() ?? '',
            code,
            desc
          ];
          ssdiCodeLines.push(writeCsvLine(codeLine));
          schemaItemCodeLines3nf.push(writeCsvLine(codeLine));
        }
      }
    }

    // 3c) Gap #4: schema outputs -> 3NF schema_item(output) + their codes. Output items
    //     are ordinary NAACCR items (derived stage group, T/N/M, summary stage, etc.).
    for (const out of schema.outputs || []) {
      if (typeof out.naaccr_item !== 'number') continue; // skip non-NAACCR outputs (e.g. ajcc_id)
      const outTable = await getTable(out.table);
      markInvolved(schemaNumStr, out.table);

      const existing = naaccrItemMap.get(out.naaccr_item);
      if (!existing) {
        naaccrItemMap.set(out.naaccr_item, { name: out.name ?? '', xml_id: out.naaccr_xml_id ?? '' });
      }

      const siKey = `${schemaNumStr}\0${out.naaccr_item}`;
      if (!seenSchemaItems.has(siKey)) {
        seenSchemaItems.add(siKey);
        schemaItemLines.push(writeCsvLine([
          schemaNumStr,
          out.naaccr_item.toString(),
          'output',
          'false',
          out.default ?? '',
          outTable?.description ?? '',
          outTable?.rationale ?? '',
          outTable?.additional_info ?? '',
          outTable?.notes ?? '',
          outTable?.coding_guidelines ?? ''
        ]));

        if (outTable) {
          let descriptionIdx = -1;
          for (let i = 0; i < outTable.definition.length; i++) {
            if ((outTable.definition[i].key || '').toLowerCase() === 'description') { descriptionIdx = i; break; }
          }
          for (const row of outTable.rows) {
            schemaItemCodeLines3nf.push(writeCsvLine([
              schemaNumStr,
              out.naaccr_item.toString(),
              row[0] ?? '',
              descriptionIdx >= 0 ? (row[descriptionIdx] ?? '') : ''
            ]));
          }
        }
      }
    }
  }

  if (OUTPUT_3NF) {
    // Fill NAACCR items from map
    const sortedItemNums = Array.from(naaccrItemMap.keys()).sort((a, b) => a - b);
    for (const num of sortedItemNums) {
      const rec = naaccrItemMap.get(num)!;
      naaccrItemLines.push(writeCsvLine([
        num.toString(),
        rec.name,
        rec.xml_id,
        rec.unit ?? '',
        rec.decimal_places ?? ''
      ]));
    }

    // Static registry rows
    registryLines.push(writeCsvLine(['SEER', 'SEER']));
    registryLines.push(writeCsvLine(['NPCR', 'NPCR']));
    registryLines.push(writeCsvLine(['COC', 'COC']));
    registryLines.push(writeCsvLine(['CCCR', 'CCCR']));

    // Gap #1: one data_dictionary_version row for this run.
    const ddVersionLines: string[] = [writeCsvLine(ddVersionHeaders)];
    ddVersionLines.push(writeCsvLine([ALGORITHM, VERSION, NAACCR_VERSION, `${BASE}/rest/staging/${ALGORITHM}/${VERSION}`]));

    // Gap #3: staging table catalog.
    const stagingTableLines: string[] = [writeCsvLine(stagingTableHeaders)];
    const stagingTableColumnLines: string[] = [writeCsvLine(stagingTableColumnHeaders)];
    const stagingTableRowLines: string[] = [writeCsvLine(stagingTableRowHeaders)];
    for (const [tableKey, t] of stagingTableMap) {
      stagingTableLines.push(writeCsvLine([
        tableKey, t.name ?? '', t.title ?? '', t.subtitle ?? '',
        t.description ?? '', t.notes ?? '', t.coding_guidelines ?? ''
      ]));
      t.definition.forEach((def, i) => {
        stagingTableColumnLines.push(writeCsvLine([
          tableKey, i.toString(), def.key ?? '', def.name ?? '', def.type ?? '', def.source ?? ''
        ]));
      });
      t.rows.forEach((row, i) => {
        stagingTableRowLines.push(writeCsvLine([tableKey, i.toString(), JSON.stringify(row)]));
      });
    }

    // Gap #3: schema -> involved table links.
    for (const encoded of involvedTables) {
      const [schemaNumStr, tableKey] = encoded.split('\0');
      schemaInvolvedTableLines.push(writeCsvLine([schemaNumStr, tableKey]));
    }

    writeFileSync(ddVersionFilePath, ddVersionLines.join('\n') + '\n');
    writeFileSync(stagingSchemaFilePath, stagingSchemaLines.join('\n') + '\n');
    writeFileSync(selectionRuleFilePath, selectionRuleLines.join('\n') + '\n');
    writeFileSync(naaccrItemFilePath, naaccrItemLines.join('\n') + '\n');
    writeFileSync(schemaItemFilePath, schemaItemLines.join('\n') + '\n');
    writeFileSync(registryFilePath, registryLines.join('\n') + '\n');
    writeFileSync(schemaItemRequirementFilePath, schemaItemRequirementLines.join('\n') + '\n');
    writeFileSync(schemaItemCodeFilePath3nf, schemaItemCodeLines3nf.join('\n') + '\n');
    writeFileSync(stagingTableFilePath, stagingTableLines.join('\n') + '\n');
    writeFileSync(stagingTableColumnFilePath, stagingTableColumnLines.join('\n') + '\n');
    writeFileSync(stagingTableRowFilePath, stagingTableRowLines.join('\n') + '\n');
    writeFileSync(schemaInvolvedTableFilePath, schemaInvolvedTableLines.join('\n') + '\n');
  } else {
    // Original three flat files
    writeFileSync(schemaFilePath, schemaLines.join('\n') + '\n');
    writeFileSync(ssdiListFilePath, ssdiListLines.join('\n') + '\n');
    writeFileSync(ssdiCodeFilePath, ssdiCodeLines.join('\n') + '\n');
  }

  // eslint-disable-next-line no-console
  console.log(`Wrote files to ${outDirPath}`);
}

main().catch(err => {
  // eslint-disable-next-line no-console
  console.error(err.message || err);
  process.exitCode = 1;
});
