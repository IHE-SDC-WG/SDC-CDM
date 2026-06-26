# OMOP SDC MVP - Elective Case Pre-Adjudication (ECP) Data Import

[![.NET](https://img.shields.io/badge/.NET-8.0-blue.svg)](https://dotnet.microsoft.com/download/dotnet/8.0)
[![SQLite](https://img.shields.io/badge/SQLite-3.x-green.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A proof-of-concept implementation for importing Elective Case Pre-Adjudication (ECP) data from NAACCR V2 CPR messages into the OMOP Common Data Model (CDM) v5.4. This MVP addresses urgent needs from institutions like Hartford, Northwestern Medicine, University of Nebraska Medical Center, and Memorial Sloan Kettering.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Testing the MVP](#testing-the-mvp)
- [Database Schema](#database-schema)
- [Sample Queries](#sample-queries)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🎯 Overview

The OMOP SDC MVP provides a standardized approach to importing structured ECP data from NAACCR V2 pathology reports into OMOP CDM v5.4. The implementation:

- **Extends the OMOP `measurement` table** with 14 SDC-specific columns
- **Creates a custom `sdc_template_instance_ecp` table** for template metadata
- **Maintains full OMOP compliance** while adding ECP-specific functionality
- **Supports structured data import** from NAACCR V2 CPR messages
- **Provides query flexibility** for both standard OMOP and SDC-specific analytics

## ✨ Features

- ✅ **OMOP CDM v5.4 Compliance**: Maintains full compatibility with existing OMOP tools
- ✅ **NAACCR V2 Support**: Imports structured ECP data from pathology reports
- ✅ **Template Metadata Tracking**: Stores template name, version, and lineage information
- ✅ **Response Type Handling**: Supports numeric, text, and list selection responses
- ✅ **Data Integrity**: Preserves original data structure without "mangling"
- ✅ **Query Flexibility**: Enables both vanilla OMOP and SDC-specific queries
- ✅ **Scalable Architecture**: Designed for batch processing and production use

## 🔧 Prerequisites

Before running the MVP, ensure you have the following installed:

### Required Software

- **[.NET 8.0 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)** or later
- **[SQLite](https://www.sqlite.org/download.html)** (included with .NET)
- **Git** for cloning the repository

### Optional Tools

- **Visual Studio Code** with C# extension for development
- **Polyglot Notebooks extension** for interactive testing (recommended)
- **SQLite Browser** for database inspection
- **Python 3.8+** for Jupyter notebooks (if using the notebooks directory)

## 🚀 Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd SDC-CDM
   ```

2. **Navigate to the SdcCdmLib directory**

   ```bash
   cd SdcCdmLib
   ```

3. **Build the solution**
   ```bash
   dotnet build
   ```

## ⚡ Quick Start

### Option 1: Interactive Notebook (Recommended)

For the best experience, use the interactive Polyglot notebook:

```bash
# Open the notebook in VS Code
code notebooks/test_omop_sdc_mvp.dib
```

Then run all cells in the notebook for a complete interactive test experience.

### Option 2: Command Line Test

```bash
cd SdcCdmLib/SdcCdmInSqlite
dotnet run
```

This will:

- Create a test database (`test_ecp.db`)
- Import the sample NAACCR V2 message (`obx-Adrenal.hl7`)
- Display template instances and measurements
- Show data statistics and sample records

### 2. Expected Output

```
OMOP SDC MVP - ECP Data Import Test
=====================================
Building database schema...
Read HL7 message from: ../../../SDC-CDM/sample_data/naaccr_v2/obx-Adrenal.hl7
Message length: 4706 characters

Importing NAACCR V2 message...
Import completed successfully!

Template Instances:
ID      Template Name   Version GUID    Tumor Site      Procedure       Laterality
--      -------------   ------- ----    ----------      ---------       ----------
1       129.1000043^ADRENAL GLAND^CAPECC        3.007.011.1000043       8149483a...     N/A     N/A     N/A

Total ECP measurements imported: 23

Measurements by Response Type:
Type            Count
----            -----
list_selection          19
text            2
numeric         2

Sample Measurements:
Question ID     Question Text   Response        Type    Units   Order
-----------     -------------   --------        ----    -----   -----
2118.1000043    Tumor Site      2119.1000043^Adrenal gland^CAPECC       list_selection          1
820603.1000043  Procedure       2122.1000043^Adrenalectomy, total^CAPECC        list_selection          2
...

Test completed successfully!
Database file: /path/to/test_ecp.db
```

## 🧪 Testing the MVP

### Option 1: Interactive Notebook (Recommended)

For the best developer experience, use the interactive Polyglot notebook:

1. **Open the notebook** in VS Code with the Polyglot Notebooks extension
2. **Run all cells** to execute the complete test suite
3. **Review results** interactively with detailed output

```bash
# Open the notebook
code notebooks/test_omop_sdc_mvp.dib
```

The notebook provides:

- ✅ **Step-by-step execution** with detailed explanations
- ✅ **Interactive validation** of all components
- ✅ **Real-time query results** and data analysis
- ✅ **Comprehensive testing** without terminal commands
- ✅ **Visual feedback** on test success/failure

### Option 2: Command Line Test

```bash
# Navigate to the test application
cd SdcCdmLib/SdcCdmInSqlite

# Run the test
dotnet run
```

### 2. Database Inspection

```bash
# Using SQLite command line
sqlite3 test_ecp.db

# View the extended measurement table structure
.schema measurement

# Check the new ECP table
.schema sdc_template_instance_ecp

# View imported data
SELECT COUNT(*) FROM measurement WHERE sdc_template_instance_guid IS NOT NULL;
SELECT * FROM sdc_template_instance_ecp;
```

### 3. Test with Different NAACCR Messages

```bash
# Copy other HL7 files from the sample data
cp ../../../SDC-CDM/sample_data/naaccr_v2/CDCECC/264.1000043/3808961.hl7 ./test_message.hl7

# Modify Program.cs to use the new file
# Update the sampleDataPath variable in Program.cs
```

### 4. Validate OMOP Compliance

```sql
-- Check that standard OMOP fields are populated
SELECT
    measurement_id,
    person_id,
    measurement_concept_id,
    measurement_date,
    measurement_type_concept_id,
    value_as_number,
    value_source_value,
    unit_source_value
FROM measurement
WHERE sdc_template_instance_guid IS NOT NULL
LIMIT 5;

-- Verify person data
SELECT * FROM person;
```

## 🗄️ Database Schema

### Extended Measurement Table

The `measurement` table has been extended with 14 SDC-specific columns:

```sql
-- SDC-specific columns for ECP data
sdc_template_instance_guid TEXT NULL,
sdc_question_identifier TEXT NULL,
sdc_response_value TEXT NULL,
sdc_response_type TEXT NULL,
sdc_template_version TEXT NULL,
sdc_question_text TEXT NULL,
sdc_section_identifier TEXT NULL,
sdc_list_item_id TEXT NULL,
sdc_list_item_text TEXT NULL,
sdc_units TEXT NULL,
sdc_datatype TEXT NULL,
sdc_order INTEGER NULL,
sdc_repeat_level INTEGER NULL,
sdc_comments TEXT NULL
```

### New ECP Template Instance Table

```sql
CREATE TABLE sdc_template_instance_ecp (
    sdc_template_instance_ecp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_lineage TEXT NULL,
    template_base_uri TEXT NULL,
    template_instance_guid TEXT NOT NULL UNIQUE,
    template_instance_version_guid TEXT NULL,
    template_instance_version_uri TEXT NULL,
    instance_version_date DATE NULL,
    person_id INTEGER NULL,
    visit_occurrence_id INTEGER NULL,
    provider_id INTEGER NULL,
    report_text TEXT NULL,
    -- NAACCR V2 specific fields
    report_template_source TEXT NULL,
    report_template_id TEXT NULL,
    report_template_version_id TEXT NULL,
    tumor_site TEXT NULL,
    procedure_type TEXT NULL,
    specimen_laterality TEXT NULL,
    created_datetime REAL DEFAULT (julianday('now')),
    updated_datetime REAL DEFAULT (julianday('now'))
);
```

## 📊 Sample Queries

### 1. Count Measurements by Response Type

```sql
SELECT
    sdc_response_type,
    COUNT(*) as count
FROM measurement
WHERE sdc_template_instance_guid IS NOT NULL
GROUP BY sdc_response_type
ORDER BY count DESC;
```

### 2. View Sample Measurements with SDC Data

```sql
SELECT
    sdc_question_identifier,
    sdc_question_text,
    sdc_response_value,
    sdc_response_type,
    sdc_units,
    sdc_order
FROM measurement
WHERE sdc_template_instance_guid IS NOT NULL
ORDER BY sdc_order
LIMIT 10;
```

### 3. Get Template Metadata

```sql
SELECT
    template_name,
    template_version,
    tumor_site,
    procedure_type,
    specimen_laterality
FROM sdc_template_instance_ecp;
```

### 4. Find Patients with Specific Tumor Characteristics

```sql
SELECT
    p.person_id,
    p.person_source_value,
    m_tumor.sdc_response_value as tumor_size,
    m_tumor.sdc_units as tumor_size_units
FROM person p
JOIN measurement m_tumor ON p.person_id = m_tumor.person_id
WHERE m_tumor.sdc_question_identifier LIKE '%2129%'  -- Tumor Size
  AND m_tumor.sdc_template_instance_guid IS NOT NULL;
```

### 5. Get All Measurements for a Specific Template Instance

```sql
SELECT
    sdc_question_identifier,
    sdc_question_text,
    sdc_response_value,
    sdc_response_type,
    sdc_units,
    sdc_order
FROM measurement
WHERE sdc_template_instance_guid = 'your-guid-here'
ORDER BY sdc_order;
```

### 6. Complex Analytics Example

```sql
-- Find all adrenal gland procedures with tumor size > 5cm
SELECT
    p.person_source_value,
    ti.template_name,
    m_tumor.sdc_response_value as tumor_size,
    m_proc.sdc_response_value as procedure_type
FROM sdc_template_instance_ecp ti
JOIN measurement m_tumor ON ti.template_instance_guid = m_tumor.sdc_template_instance_guid
JOIN measurement m_proc ON ti.template_instance_guid = m_proc.sdc_template_instance_guid
JOIN person p ON ti.person_id = p.person_id
WHERE m_tumor.sdc_question_identifier LIKE '%2129%'  -- Tumor Size
  AND m_proc.sdc_question_identifier LIKE '%820603%'  -- Procedure
  AND CAST(m_tumor.sdc_response_value AS REAL) > 5.0;
```

## 📁 Project Structure

```
SDC-CDM/
├── SdcCdmLib/                          # Main .NET library
│   ├── SdcCdm/                         # Core SDC CDM implementation
│   │   ├── ImportNaaccrVolV.cs         # NAACCR V2 import logic
│   │   ├── ISdcCdm.cs                  # Interface definitions
│   │   └── FHIR/                       # FHIR importers
│   ├── SdcCdmInSqlite/                 # SQLite implementation
│   │   ├── SdcCdmInSqlite.cs           # SQLite database operations
│   │   ├── Program.cs                  # Test application
│   │   └── SdcCdmInSqlite.csproj       # Project file
│   └── SdcCdm.Tests/                   # Unit tests
├── database/                           # Database schema definitions
│   └── ddl/
│       ├── postgresql/                 # PostgreSQL DDL
│       └── sqlite/                     # SQLite DDL
├── sample_data/                        # Sample data files
│   └── naaccr_v2/                      # NAACCR V2 sample messages
├── notebooks/                          # Jupyter notebooks
│   ├── try_sdc_cdm_dotnet.dib          # Original SDC CDM notebook
│   └── test_omop_sdc_mvp.dib           # **NEW: OMOP SDC MVP testing notebook**
└── README.md                           # This file
```

## 🔍 Troubleshooting

### Common Issues

#### 1. Build Errors

```bash
# Clean and rebuild
dotnet clean
dotnet build
```

#### 2. Database File Not Found

```bash
# Check if the sample data path is correct
ls ../../../SDC-CDM/sample_data/naaccr_v2/obx-Adrenal.hl7
```

#### 3. Foreign Key Constraint Errors

- The application automatically inserts essential concepts
- If errors persist, check the database schema creation

#### 4. SQLite Command Line Issues

```bash
# Install SQLite if not available
# macOS: brew install sqlite3
# Ubuntu: sudo apt-get install sqlite3
# Windows: Download from https://www.sqlite.org/download.html
```

### Debug Mode

To run with detailed logging:

```bash
cd SdcCdmLib/SdcCdmInSqlite
dotnet run --verbosity detailed
```

### Database Inspection

```bash
# Open the database file
sqlite3 test_ecp.db

# List all tables
.tables

# Check table schemas
.schema measurement
.schema sdc_template_instance_ecp

# View sample data
SELECT * FROM sdc_template_instance_ecp;
SELECT COUNT(*) FROM measurement WHERE sdc_template_instance_guid IS NOT NULL;
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd SDC-CDM

# Build the solution
cd SdcCdmLib
dotnet build

# Run tests
dotnet test

# Run the test application
cd SdcCdmInSqlite
dotnet run
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OMOP CDM Community** for the standardized data model
- **NAACCR** for the pathology reporting standards
- **Institutional Partners** (Hartford, Northwestern Medicine, University of Nebraska Medical Center, Memorial Sloan Kettering) for their urgent needs and feedback

## 📞 Support

For questions, issues, or contributions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review the [Sample Queries](#sample-queries) for usage examples
3. Open an issue on GitHub
4. Contact the development team

---

**Note**: This is a Minimum Viable Product (MVP) designed for proof-of-concept and urgent institutional needs. Future versions will include additional features and optimizations.
