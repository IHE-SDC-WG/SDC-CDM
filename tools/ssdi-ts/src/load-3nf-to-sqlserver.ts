// Loads 3NF CSVs into SQL Server tables in the cap schema
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

const TABLES = [
  { file: 'staging_schema.csv', table: 'cap.STAGING_SCHEMA', columns: ['schema_id_number', 'schema_id', 'schema_name'] },
  { file: 'naaccr_item.csv', table: 'cap.NAACCR_ITEM', columns: ['item_num', 'name', 'xml_id'] },
  { file: 'registry.csv', table: 'cap.REGISTRY', columns: ['code', 'name'] },
  { file: 'schema_selection_rule.csv', table: 'cap.SCHEMA_SELECTION_RULE', columns: ['schema_id_number', 'site', 'histology', 'behavior', 'sex_at_birth', 'discriminator_1', 'discriminator_2', 'year_dx'] },
  { file: 'schema_item.csv', table: 'cap.SCHEMA_ITEM', columns: ['schema_id_number', 'item_num', 'used_for_staging', 'default_value', 'description', 'rationale', 'additional_info', 'table_notes', 'coding_guidelines'] },
  { file: 'schema_item_requirement.csv', table: 'cap.SCHEMA_ITEM_REQUIREMENT', columns: ['schema_id_number', 'item_num', 'registry_code', 'is_required'] },
  { file: 'schema_item_code.csv', table: 'cap.SCHEMA_ITEM_CODE', columns: ['schema_id_number', 'item_num', 'code', 'description'] },
];

async function loadCsvToTable(filePath: string, table: string, columns: string[], pool: sql.ConnectionPool) {
  return new Promise<void>((resolve, reject) => {
    const rows: any[] = [];
    fs.createReadStream(filePath)
      .pipe(parse({ headers: true, trim: true }))
      .on('error', reject)
      .on('data', row => rows.push(row))
      .on('end', async () => {
        if (rows.length === 0) return resolve();
        // For registry, handle id auto-increment
        if (table === 'cap.REGISTRY') {
          for (const row of rows) {
            await pool.request()
              .input('code', sql.NVarChar(50), row.code)
              .input('name', sql.NVarChar(255), row.name)
              .query(`INSERT INTO cap.REGISTRY (code, name) VALUES (@code, @name)`);
          }
          return resolve();
        }
        // For schema_item_requirement, lookup registry_id from code
        if (table === 'cap.SCHEMA_ITEM_REQUIREMENT') {
          for (const row of rows) {
            const regRes = await pool.request()
              .input('code', sql.NVarChar(50), row.registry_code)
              .query('SELECT id FROM cap.REGISTRY WHERE code = @code');
            if (!regRes.recordset[0]) throw new Error(`Registry code not found: ${row.registry_code}`);
            const registry_id = regRes.recordset[0].id;
            await pool.request()
              .input('schema_id_number', sql.NVarChar(255), row.schema_id_number)
              .input('item_num', sql.Int, row.item_num)
              .input('registry_id', sql.SmallInt, registry_id)
              .input('is_required', sql.Bit, row.is_required === 'true' || row.is_required === '1')
              .query(`INSERT INTO cap.SCHEMA_ITEM_REQUIREMENT (schema_id_number, item_num, registry_id, is_required) VALUES (@schema_id_number, @item_num, @registry_id, @is_required)`);
          }
          return resolve();
        }
        // For all other tables
        for (const row of rows) {
          const colNames = columns.join(', ');
          const paramNames = columns.map(c => '@' + c).join(', ');
          const req = pool.request();
          for (const col of columns) {
            let val = row[col];
            // Type binding by column name
            if (col === 'item_num') {
              val = val ? parseInt(val, 10) : null;
              req.input(col, sql.Int, val);
            } else if (col === 'used_for_staging') {
              val = val === 'true' || val === '1';
              req.input(col, sql.Bit, val);
            } else if (col === 'registry_id') {
              val = val ? parseInt(val, 10) : null;
              req.input(col, sql.SmallInt, val);
            } else {
              req.input(col, sql.NVarChar(sql.MAX), val);
            }
          }
          await req.query(`INSERT INTO ${table} (${colNames}) VALUES (${paramNames})`);
        }
        resolve();
      });
  });
}

(async () => {
  const pool = await sql.connect(config);
  try {
    for (const { file, table, columns } of TABLES) {
      const filePath = path.join(CSV_DIR, file);
      if (!fs.existsSync(filePath)) {
        console.warn(`File not found: ${filePath}`);
        continue;
      }
      console.log(`Loading ${file} into ${table}...`);
      await loadCsvToTable(filePath, table, columns, pool);
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
