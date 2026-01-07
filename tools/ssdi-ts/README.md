# SEER SSDI CSV Export (TypeScript)

This script (Node 18+ required) replicates the functionality of the Java `CreateSSDIFile` and generates:
- out-egs/schema-file.csv
- out-egs/ssdi-list-file.csv
- out-egs/ssdi-code-file.csv

It calls the SEER Staging REST API. Provide your API key via `SEER_API_KEY`.

## Quick start

```bash
# From repo root
cd tools/ssdi-ts
npm install

# Option 1: Run with tsx (dev)
SEER_API_KEY=your_key_here npm run dev

# Option 2: Build + run
npm run build
SEER_API_KEY=your_key_here npm start
```

## Options
- `SEER_API_KEY`: SEER API key (header `X-SEERAPI-Key`).
- `SSDI_ALGORITHM`: defaults to `eod_public`.
- `SSDI_VERSION`: defaults to `3.3`.
- `SSDI_OUT_DIR`: defaults to `out-egs`.

Outputs are written under the given `SSDI_OUT_DIR` relative to the repository root.
