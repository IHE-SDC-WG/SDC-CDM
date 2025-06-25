# SdcCdmLib

This directory contains the SDC CDM .NET library, which provides reference implementations for importing and exporting SDC (Structured Data Capture) data. The library consists of three main projects:

- **SdcCdm** - Core library containing the abstract API (`ISdcCdm`) and various importers/exporters
  - **`ISdcCdm`** - Abstract interface defining the CDM API
  - **Import capabilities** for:
    - SDC XML Forms
    - NAACCR V2 Messages (HL7v2)
    - CSV data (concepts, templates)
  - **Export capabilities** for:
    - FHIR CPDS Bundles
    - Template data
- **SdcCdmInSqlite** - SQLite-based implementation of the SDC CDM API
  - Implements all abstract methods from `ISdcCdm`
  - Automatically builds database schema from embedded SQL scripts
  - Supports both in-memory and file-based databases
- **SdcCdm.Tests** - Unit tests for the library functionality

## Prerequisites

- .NET 8.0 SDK or later
- Basic familiarity with .NET development and command-line tools

> **Note**: If you encounter SDK version conflicts, you may need to update the `global.json` file in the repository root to match your installed .NET SDK version.

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/IHE-SDC-WG/SDC-CDM.git
cd SDC-CDM/SdcCdmLib
```

### 2. Build the Solution

```bash
dotnet build
```

This will restore NuGet packages and compile all three projects in the solution.

### 3. Run Unit Tests

```bash
dotnet test
```

## Development

### Dependencies

- **Microsoft.Data.Sqlite** - SQLite database access
- **Hl7.Fhir.R4** - FHIR R4 support for CPDS exports
- **CsvHelper** - CSV file processing
- **Microsoft.Extensions.Logging** - Logging infrastructure
- **xUnit** - Testing framework

## Usage Examples

For detailed usage examples and demonstrations of the library's capabilities, refer to the Polyglot Notebook located in the `notebooks/` directory of the main repository.

## Database Schema

The SQLite implementation automatically creates the required database schema using embedded SQL scripts located in the `database/ddl/sqlite/` directory of the main repository.
