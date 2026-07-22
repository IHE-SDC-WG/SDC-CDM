// Loads 3NF CSVs into SQL Server tables in the naaccr schema
// Usage: set env MSSQL_SERVER, MSSQL_DATABASE, MSSQL_USER, MSSQL_PASSWORD, optionally MSSQL_PORT, CSV_DIR
// Example: pnpm ts-node tools/ssdi-ts/src/load-3nf-to-sqlserver.ts

import { parse } from 'fast-csv';
import * as fs from 'fs';
import sql from 'mssql';
import * as path from 'path';

const config: sql.config = {
  server: process.env.MSSQL_SERVER || 'pdbcpdsrds02.cap.org',
  database: process.env.MSSQL_DATABASE || 'NAACCRDDPRD',
  user: process.env.MSSQL_USER || 'XXUJOSH',
  password: process.env.MSSQL_PASSWORD || '',
  port: process.env.MSSQL_PORT ? parseInt(process.env.MSSQL_PORT, 10) : 1983,
  options: {
    encrypt: true, // for Azure
    trustServerCertificate: true, // for local dev/self-signed
  },
};

const CSV_DIR = process.env.CSV_DIR || path.join(process.cwd(), 'out-egs');

// Ordered for FK safety: parents before children. `versioned` tables receive the
// resolved dd_version_id (Gap #1) injected into every insert.
const TABLES: { file: string; table: string; columns: string[]; versioned?: boolean }[] = [
  { file: 'staging_schema.csv', table: 'naaccr.STAGING_SCHEMA', columns: ['schema_id_number', 'schema_id', 'schema_name'], versioned: true },
  { file: 'naaccr_item.csv', table: 'naaccr.NAACCR_ITEM', columns: ['item_num', 'name', 'xml_id', 'unit', 'decimal_places'], versioned: true },
  { file: 'registry.csv', table: 'naaccr.REGISTRY', columns: ['code', 'name'] },
  { file: 'staging_table.csv', table: 'naaccr.STAGING_TABLE', columns: ['table_key', 'name', 'title', 'subtitle', 'description', 'notes', 'coding_guidelines'], versioned: true },
  { file: 'staging_table_column.csv', table: 'naaccr.STAGING_TABLE_COLUMN', columns: ['table_key', 'col_index', 'col_key', 'col_name', 'col_type', 'col_source'], versioned: true },
  { file: 'staging_table_row.csv', table: 'naaccr.STAGING_TABLE_ROW', columns: ['table_key', 'row_index', 'cells'], versioned: true },
  { file: 'schema_selection_rule.csv', table: 'naaccr.SCHEMA_SELECTION_RULE', columns: ['schema_id_number', 'site', 'histology', 'behavior', 'sex_at_birth', 'discriminator_1', 'discriminator_2', 'year_dx'], versioned: true },
  { file: 'schema_item.csv', table: 'naaccr.SCHEMA_ITEM', columns: ['schema_id_number', 'item_num', 'item_role', 'used_for_staging', 'default_value', 'description', 'rationale', 'additional_info', 'table_notes', 'coding_guidelines'], versioned: true },
  { file: 'schema_item_requirement.csv', table: 'naaccr.SCHEMA_ITEM_REQUIREMENT', columns: ['schema_id_number', 'item_num', 'registry_code', 'is_required'], versioned: true },
  { file: 'schema_item_code.csv', table: 'naaccr.SCHEMA_ITEM_CODE', columns: ['schema_id_number', 'item_num', 'code', 'description'], versioned: true },
  { file: 'schema_involved_table.csv', table: 'naaccr.SCHEMA_INVOLVED_TABLE', columns: ['schema_id_number', 'table_key'], versioned: true },
];

function bindByName(req: sql.Request, col: string, raw: any) {
  let val = raw;
  if (col === 'item_num' || col === 'decimal_places' || col === 'col_index' || col === 'row_index' || col === 'dd_version_id') {
    val = (val === undefined || val === null || val === '') ? null : parseInt(val, 10);
    req.input(col, sql.Int, val);
  } else if (col === 'used_for_staging') {
    req.input(col, sql.Bit, val === 'true' || val === '1');
  } else if (col === 'registry_id') {
    val = (val === undefined || val === null || val === '') ? null : parseInt(val, 10);
    req.input(col, sql.SmallInt, val);
  } else {
    req.input(col, sql.NVarChar(sql.MAX), val ?? null);
  }
}

// Gap #1: upsert the single data_dictionary_version row for this batch and return its id.
async function upsertVersion(pool: sql.ConnectionPool): Promise<number> {
  const filePath = path.join(CSV_DIR, 'data_dictionary_version.csv');
  if (!fs.existsSync(filePath)) {
    throw new Error(`Required file not found: ${filePath} (run create-ssdi with SSDI_OUTPUT_3NF=1)`);
  }
  const rows: any[] = await new Promise((resolve, reject) => {
    const acc: any[] = [];
    fs.createReadStream(filePath)
      .pipe(parse({ headers: true, trim: true }))
      .on('error', reject)
      .on('data', (r: any) => acc.push(r))
      .on('end', () => resolve(acc));
  });
  if (rows.length === 0) throw new Error('data_dictionary_version.csv has no rows');
  const { algorithm, version, naaccr_version, source_api } = rows[0];

  const existing = await pool.request()
    .input('algorithm', sql.NVarChar(255), algorithm)
    .input('version', sql.NVarChar(255), version)
    .query('SELECT dd_version_id FROM naaccr.DATA_DICTIONARY_VERSION WHERE algorithm = @algorithm AND version = @version');
  if (existing.recordset[0]) return existing.recordset[0].dd_version_id;

  const inserted = await pool.request()
    .input('algorithm', sql.NVarChar(255), algorithm)
    .input('version', sql.NVarChar(255), version)
    .input('naaccr_version', sql.NVarChar(255), naaccr_version || null)
    .input('source_api', sql.NVarChar(512), source_api || null)
    .query(`INSERT INTO naaccr.DATA_DICTIONARY_VERSION (algorithm, version, naaccr_version, source_api)
            OUTPUT INSERTED.dd_version_id
            VALUES (@algorithm, @version, @naaccr_version, @source_api)`);
  return inserted.recordset[0].dd_version_id;
}

async function loadCsvToTable(
  filePath: string,
  table: string,
  columns: string[],
  versioned: boolean,
  ddVersionId: number,
  pool: sql.ConnectionPool
) {
  return new Promise<void>((resolve, reject) => {
    const rows: any[] = [];
    fs.createReadStream(filePath)
      .pipe(parse({ headers: true, trim: true }))
      .on('error', reject)
      .on('data', (row: any) => rows.push(row))
      .on('end', async () => {
        try {
          if (rows.length === 0) return resolve();

          // For registry, handle id auto-increment (no version scope)
          if (table === 'naaccr.REGISTRY') {
            for (const row of rows) {
              await pool.request()
                .input('code', sql.NVarChar(50), row.code)
                .input('name', sql.NVarChar(255), row.name)
                .query(`INSERT INTO naaccr.REGISTRY (code, name) VALUES (@code, @name)`);
            }
            return resolve();
          }

          // For schema_item_requirement, lookup registry_id from code
          if (table === 'naaccr.SCHEMA_ITEM_REQUIREMENT') {
            for (const row of rows) {
              const regRes = await pool.request()
                .input('code', sql.NVarChar(50), row.registry_code)
                .query('SELECT id FROM naaccr.REGISTRY WHERE code = @code');
              if (!regRes.recordset[0]) throw new Error(`Registry code not found: ${row.registry_code}`);
              const registry_id = regRes.recordset[0].id;
              await pool.request()
                .input('dd_version_id', sql.Int, ddVersionId)
                .input('schema_id_number', sql.NVarChar(255), row.schema_id_number)
                .input('item_num', sql.Int, parseInt(row.item_num, 10))
                .input('registry_id', sql.SmallInt, registry_id)
                .input('is_required', sql.Bit, row.is_required === 'true' || row.is_required === '1')
                .query(`INSERT INTO naaccr.SCHEMA_ITEM_REQUIREMENT (dd_version_id, schema_id_number, item_num, registry_id, is_required)
                        VALUES (@dd_version_id, @schema_id_number, @item_num, @registry_id, @is_required)`);
            }
            return resolve();
          }

          // Generic path
          const insertCols = versioned ? ['dd_version_id', ...columns] : columns;
          const colNames = insertCols.join(', ');
          const paramNames = insertCols.map(c => '@' + c).join(', ');
          for (const row of rows) {
            const req = pool.request();
            if (versioned) req.input('dd_version_id', sql.Int, ddVersionId);
            for (const col of columns) bindByName(req, col, row[col]);
            await req.query(`INSERT INTO ${table} (${colNames}) VALUES (${paramNames})`);
          }
          resolve();
        } catch (e) {
          reject(e);
        }
      });
  });
}

(async () => {
  const pool = await sql.connect(config);
  try {
    const ddVersionId = await upsertVersion(pool);
    console.log(`Using dd_version_id=${ddVersionId}`);
    for (const { file, table, columns, versioned } of TABLES) {
      const filePath = path.join(CSV_DIR, file);
      if (!fs.existsSync(filePath)) {
        console.warn(`File not found: ${filePath}`);
        continue;
      }
      console.log(`Loading ${file} into ${table}...`);
      await loadCsvToTable(filePath, table, columns, Boolean(versioned), ddVersionId, pool);
      console.log(`Loaded ${file}`);
    }
    console.log('All CSVs loaded.');
  } catch (err) {
    console.error('Error loading CSVs:', err);
    process.exit(1);
  } finally {
    await pool.close();
  }
})();
