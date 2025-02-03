# SDC-CDM

A *Structured Data Capture Common Data Model* (**SDC-CDM**) for the SDC Implementation Guide (SDC IG).

## Purpose

The SDC-CDM is designed to streamline the management of SDC processes by providing a unified data model for SDC data.

### Example Use Cases

- **Data Integration:** Add support for SDC data into a new or existing database by adopting a single, consistent schema.
- **Unified Reporting and Analytics:** Be able to use the same SQL queries to generate reports and perform data analytics between any database that has adopted the schema.
- **Data Import/Export:** Import and export various SDC data types for interoperability with other systems.
- **Development and Testing:** Use the provided .NET library and Jupyter-style notebooks to develop, test, and validate the CDM schema.

### This Repository

The SDC-CDM GitHub repository hosts the following projects to help users and developers work with the SDC-CDM

- `database/` - A standardized schema to store SDC data.
- `notebooks/` - Jupyter-style notebooks to onboard users and familiarize themselves with the CDM.
- `SdcCdmLib/` - A .NET library serving as a reference implementation for some common operations on SDC data, including:
  - Importing SDC Forms and NAACCR V2 Messages into the CDM
  - Exporting data from the CDM into FHIR CPDS Bundles
- `sample_data/` - Sample data for testing and demonstration purposes.

## Getting Started

### Notebook

The notebooks contain a number of examples of how to use the CDM schema.

#### .NET Polyglot Notebook

1. **Open the Notebook:**
   Open [`notebooks/try_sdc_cdm_dotnet.dib`](notebooks/try_sdc_cdm_dotnet.dib) using VS Code with the [Polyglot Notebooks extension](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.polyglot-notebooks) installed.

2. **Notebook Walkthrough:**
   The notebook will guide you through:
   - Creating a SQLite database loaded with the CDM schema.
   - Importing SDC templates, SDC forms, and NAACCR V2 messages.
   - Exporting CDM data into FHIR CPDS bundles.

#### Python Jupyter Notebook

1. **Open the Notebook:**
   Open [`notebooks/try_sdc_cdm_python.ipynb`](notebooks/try_sdc_cdm_python.ipynb) using a Jupyter notebook viewer.

2. **Notebook Walkthrough:**
   The notebook will guide you through:
   - Creating a SQLite database loaded with the CDM schema.
   - Importing SDC templates, SDC forms, and NAACCR V2 messages.

### Library

We maintain a .NET library at `SdcCdmLib/` that provides reference implementations for various import and export operations related to SDC data. For example usage, refer to the Polyglot Notebook located in the `notebooks/` directory.

### Standalone Database

A docker compose file is provided to set up a PostgreSQL database along with the CDM schema.

1. **Copy Environment Variables:**
   ```
   cp .env.example .env
   ```
   The default values will work for initial setup.

2. **Start Docker Compose:**
   ```
   docker compose up
   ```
   This command initializes a PostgreSQL database and loads the OMOP CDM schema on the first run.

3. **Resetting the Database:**
   To reset the database, execute:
   ```
   docker compose down -v
   ```
   This command removes the database volume (with the `-v` flag). Afterward, you can restart the database with:
   ```
   docker compose up
   ```
