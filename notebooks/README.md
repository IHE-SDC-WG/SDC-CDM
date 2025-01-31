## serve_db.py

This script is used to serve the SQLite database in a web browser.

### Requirements

- Python 3.12
- `sql-wasm-debug.wasm` and `sql-wasm-debug.js` from https://github.com/sql-js/sql.js under `./public`
  - Use script `./fetch-sqlite-wasm.sh` to fulfill this requirement
- A SQLite database file at `./public/sdc_cdm.db`
  - Use either notebook to fulfill this requirement

### Usage

```bash
python serve_db.py
```

The webpage will be served at http://localhost:8000

Enter a SQL query in the text area and click "Run" to execute the query.