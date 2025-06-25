## try_sdc_cdm_dotnet.dib

This .NET Polyglot Notebook demonstrates how to use the SDC-CDM with .NET libraries to create databases, import data, and export FHIR bundles.

### Requirements

- .NET SDK 8.0 (version specified in `global.json` at repository root)
- VS Code with the [Polyglot Notebooks extension](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.polyglot-notebooks) installed
- Sample data files in the repository (automatically available with git clone)

### Usage

#### Using VS Code

1. Open VS Code in the notebooks directory
2. Install the Polyglot Notebooks extension if not already installed
3. Open `try_sdc_cdm_dotnet.dib`
4. Run each cell sequentially using Ctrl+Enter or the Run button

#### From Command Line

```bash
# Build the required libraries first
dotnet build ../SdcCdmLib

# Note: Command line execution of .dib files requires the dotnet interactive tool
dotnet tool install -g Microsoft.dotnet-interactive
dotnet interactive jupyter install
# Then open with jupyter or VS Code
```

The notebook will guide you through:
- Building the SDC CDM libraries
- Creating a SQLite database loaded with the CDM schema
- Importing SDC templates and forms
- Importing NAACCR V2 messages
- Exporting CDM data into FHIR CPDS bundles

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
- A SQLite database file at `./public/sdc_cdm.db`
  - Use either notebook to fulfill this requirement

### Usage

```bash
python serve_db.py
```

The webpage will be served at http://localhost:8000

Enter a SQL query in the text area and click "Run" to execute the query.
