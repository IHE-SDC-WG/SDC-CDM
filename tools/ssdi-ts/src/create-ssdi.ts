/*
  TypeScript port of CreateSSDIFile.java
  - Generates three CSVs: schema-file.csv, ssdi-list-file.csv, ssdi-code-file.csv
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
const OUT_DIR = process.env.SSDI_OUT_DIR || 'out-egs';

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
    if (v === null || v === undefined) continue;
    const s = String(v).replace(/"/g, '""');
    parts.push(`"${s}"`);
  }
  return parts.join(',');
}

async function main() {
  // Resolve output directory relative to repository root (two levels up from tools/ssdi-ts)
  const repoRoot = join(process.cwd(), '..', '..');
  const outDirPath = isAbsolute(OUT_DIR) ? OUT_DIR : join(repoRoot, OUT_DIR);
  if (!existsSync(outDirPath)) mkdirSync(outDirPath, { recursive: true });

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

    // 3a) Schema selection table rows -> schema-file.csv
    const selectionTableId = schema.schema_selection_table;
    if (selectionTableId) {
      const table = await apiGet<StagingTable>(`/rest/staging/${ALGORITHM}/${VERSION}/table/${encodeURIComponent(selectionTableId)}`);
      // determine indices
      let siteIdx = -1, histIdx = -1, behIdx = -1, sexIdx = -1, sd1Idx = -1, sd2Idx = -1, yearIdx = -1;
      table.definition.forEach((def, i) => {
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

      for (const row of table.rows) {
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
      }
    }

    // 3b) SSDI inputs -> ssdi-list-file.csv and ssdi-code-file.csv
    const inputs = schema.inputs || [];
    const ssdiInputs = inputs
      .filter(inp => (inp.metadata || []).some(m => m.name === 'SSDI'))
      .sort((a, b) => (a.naaccr_item ?? 0) - (b.naaccr_item ?? 0));

    for (const inp of ssdiInputs) {
      // Fetch related table (may be undefined)
      const table = inp.table ? await apiGet<StagingTable>(`/rest/staging/${ALGORITHM}/${VERSION}/table/${encodeURIComponent(inp.table)}`) : undefined;

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
        }
      }
    }
  }

  writeFileSync(schemaFilePath, schemaLines.join('\n') + '\n');
  writeFileSync(ssdiListFilePath, ssdiListLines.join('\n') + '\n');
  writeFileSync(ssdiCodeFilePath, ssdiCodeLines.join('\n') + '\n');

  // eslint-disable-next-line no-console
  console.log(`Wrote files to ${outDirPath}`);
}

main().catch(err => {
  // eslint-disable-next-line no-console
  console.error(err.message || err);
  process.exitCode = 1;
});
