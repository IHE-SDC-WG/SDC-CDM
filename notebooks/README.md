## try_sdc_cdm_python.ipynb

This Python Jupyter Notebook demonstrates how to use the SDC-CDM with Python to create databases, import SDC data, and work with the schema.

### Requirements

- Python 3.12 (as specified in `.python-version`)
- Jupyter Notebook or VS Code with Python extension
- Required Python packages:
  - `lxml==5.3.0` (automatically installed by the notebook)
  - Local modules in `python_cdm_utils/` (included in repository)
- Sample data files in the repository (automatically available with git clone)

### Usage

#### Using VS Code

1. Open VS Code in the notebooks directory
2. Install the Python extension if not already installed
3. Open `try_sdc_cdm_python.ipynb`
4. Select Python 3.12 as the kernel when prompted
5. Run each cell sequentially using Shift+Enter or the Run button

#### Using Jupyter Notebook

```bash
# Install Jupyter if not already installed
pip install jupyter

# Start Jupyter Notebook server
jupyter notebook

# Open try_sdc_cdm_python.ipynb in the browser interface
```
## serve_db.py

This script is used to serve the SQLite database in a web browser.

### Requirements

- Python 3.12
- `sql-wasm-debug.wasm` and `sql-wasm-debug.js` from https://github.com/sql-js/sql.js under `./public`
  - Use script `./fetch-sqlite-wasm.sh` to fulfill this requirement
- The SQLite database files under `./public/`
  - Use the repository build command to create the current five-schema set
  - The retained notebook covers only the older clinical-schema subset and is scheduled for
    replacement in Phase 6
  - The logical model (see `../database/SCHEMA_ARCHITECTURE.md`) produces a
    control database `sdc_cdm.db` plus five attached schema files: `etl`,
    `intake`, `omop`, `naaccr`, and `sdc`

### Usage

```bash
python serve_db.py
```

The webpage will be served at http://localhost:8000

On startup the script prints a [Datasette Lite](https://lite.datasette.io/) URL
that opens all five attached schema files at once for a friendlier GUI. You can
also enter a SQL query in the text area and click "Run".
