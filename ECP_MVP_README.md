# OMOP SDC MVP - Elective Case Pre-Adjudication (ECP) Implementation

## Overview

This implementation provides a proof of concept for importing Elective Case Pre-Adjudication (ECP) data from NAACCR V2 CPR messages into the OMOP CDM v5.4 framework. The solution focuses on structured ECP data while maintaining OMOP compliance and supporting the urgent needs of institutions like Hartford, Northwestern Medicine, University of Nebraska Medical Center, and Memorial Sloan Kettering.

## Key Features

### 1. Database Schema Extensions

**Enhanced OMOP Measurement Table**

- Extended the standard OMOP `measurement` table with SDC-specific columns
- Added fields for template instance GUID, question identifiers, response values, and metadata
- Maintains full OMOP CDM v5.4 compliance while supporting ECP data

**New SDC Template Instance Table**

- `sdc_template_instance_ecp` table for storing template metadata
- Captures NAACCR V2 specific fields from the first 3 OBX segments
- Supports template versioning and lineage tracking

### 2. Data Import Implementation

**Enhanced C# Library**

- `NAACCRVolVImporter.ImportNaaccrVolV()` method for processing NAACCR V2 CPR messages
- Extracts structured ECP data while excluding narrative content
- Maps data to both standard OMOP fields and SDC-specific columns
- Handles de-identified data appropriately

**Key Processing Features**

- Parses patient demographics from PID segments
- Extracts template metadata from first 3 OBX segments
- Processes structured ECP data from remaining OBX segments
- Supports multiple response types (numeric, list selection, text)
- Generates unique template instance GUIDs for tracking

### 3. Sample Data and Testing

**Sample NAACCR V2 Messages**

- `sample_data/naaccr_v2/obx-Adrenal.hl7` - Adrenal gland pathology report
- Contains structured ECP data for testing and demonstration

**Test Implementation**

- `TestEcpImport.cs` - Demonstrates the complete import process
- Shows how to query both vanilla OMOP fields and SDC-specific columns
- Provides examples of data validation and reporting

## Database Schema

### Extended Measurement Table

```sql
CREATE TABLE measurement (
    -- Standard OMOP fields
    measurement_id integer NOT NULL,
    person_id integer NOT NULL,
    measurement_concept_id integer NOT NULL,
    measurement_date date NOT NULL,
    -- ... other standard fields ...

    -- SDC-specific columns for ECP data
    sdc_template_instance_guid varchar(255) NULL,
    sdc_question_identifier varchar(255) NULL,
    sdc_response_value TEXT NULL,
    sdc_response_type varchar(50) NULL,
    sdc_template_version varchar(255) NULL,
    sdc_question_text varchar(500) NULL,
    sdc_section_identifier varchar(255) NULL,
    sdc_list_item_id varchar(255) NULL,
    sdc_list_item_text varchar(500) NULL,
    sdc_units varchar(100) NULL,
    sdc_datatype varchar(50) NULL,
    sdc_order integer NULL,
    sdc_repeat_level integer NULL,
    sdc_comments TEXT NULL
);
```

### New SDC Template Instance Table

```sql
CREATE TABLE sdc_template_instance_ecp (
    sdc_template_instance_ecp_id integer NOT NULL,
    template_name varchar(255) NOT NULL,
    template_version varchar(255) NOT NULL,
    template_lineage varchar(255) NULL,
    template_base_uri varchar(500) NULL,
    template_instance_guid varchar(255) NOT NULL UNIQUE,
    template_instance_version_guid varchar(255) NULL,
    template_instance_version_uri varchar(500) NULL,
    instance_version_date date NULL,
    person_id integer NULL,
    visit_occurrence_id integer NULL,
    provider_id integer NULL,
    report_text TEXT NULL,
    -- NAACCR V2 specific fields
    report_template_source varchar(255) NULL,
    report_template_id varchar(255) NULL,
    report_template_version_id varchar(255) NULL,
    tumor_site varchar(255) NULL,
    procedure_type varchar(255) NULL,
    specimen_laterality varchar(255) NULL,
    created_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Usage Examples

### 1. Import NAACCR V2 Message

```csharp
using var sdcCdm = new SdcCdmInSqlite("ecp_data.db");
var hl7Message = File.ReadAllText("sample_data/naaccr_v2/obx-Adrenal.hl7");
NAACCRVolVImporter.ImportNaaccrVolV(sdcCdm, hl7Message);
```

### 2. Query ECP Data

```sql
-- Find all measurements for a specific template instance
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

-- Get template metadata
SELECT
    template_name,
    template_version,
    tumor_site,
    procedure_type,
    specimen_laterality
FROM sdc_template_instance_ecp
WHERE template_instance_guid = 'your-guid-here';
```

### 3. Complex Queries

```sql
-- Find patients with specific tumor characteristics
SELECT
    p.person_id,
    m_tumor.sdc_response_value as tumor_size,
    m_grade.sdc_response_value as tumor_grade,
    m_margin.sdc_response_value as margin_status
FROM person p
JOIN measurement m_tumor ON p.person_id = m_tumor.person_id
LEFT JOIN measurement m_grade ON p.person_id = m_grade.person_id
LEFT JOIN measurement m_margin ON p.person_id = m_margin.person_id
WHERE m_tumor.sdc_question_identifier LIKE '%2129%'  -- Tumor Size
  AND m_grade.sdc_question_identifier LIKE '%820395%'  -- Tumor Grade
  AND m_margin.sdc_question_identifier LIKE '%2153%'   -- Margin Status
  AND m_tumor.sdc_template_instance_guid = m_grade.sdc_template_instance_guid
  AND m_tumor.sdc_template_instance_guid = m_margin.sdc_template_instance_guid;
```

## Key Benefits

### 1. OMOP Compliance

- Maintains full OMOP CDM v5.4 compliance
- Extends existing tables rather than creating custom ones
- Preserves all standard OMOP functionality

### 2. Data Integrity

- Avoids "mangling" of NAACCR data that previous models may have caused
- Preserves structured ECP data for registry work
- Maintains audit trail and versioning

### 3. Query Flexibility

- Supports both vanilla OMOP queries and SDC-specific queries
- Enables complex analytics across multiple template instances
- Provides rich metadata for template tracking

### 4. Scalability

- Designed for batch processing of multiple messages
- Supports template versioning and updates
- Handles de-identified data appropriately

## Implementation Status

### ✅ Completed

- Database schema extensions (PostgreSQL and SQLite)
- Enhanced C# library with ECP data handling
- NAACCR V2 message parsing and import
- Sample data and test implementation
- Query examples and documentation

### 🔄 Next Steps

- Integration with existing OMOP tools (ATLAS, Achilles)
- Performance optimization for large datasets
- Additional NAACCR V2 message types
- FHIR integration for future phases

## File Structure

```
SDC-CDM/
├── database/ddl/
│   ├── postgresql/1_OMOPCDM_postgresql_5.4-SDC_ddl.sql (extended)
│   └── sqlite/1_OMOPCDM_sqlite_5.4-SDC_ddl.sql (extended)
├── SdcCdmLib/
│   ├── SdcCdm/ImportNaaccrVolV.cs (enhanced)
│   ├── SdcCdm/ISdcCdm.cs (extended interface)
│   └── SdcCdmInSqlite/SdcCdmInSqlite.cs (new methods)
├── sample_data/
│   ├── naaccr_v2/obx-Adrenal.hl7 (sample data)
│   └── ecp_query_examples.sql (query examples)
└── SdcCdmLib/SdcCdmInSqlite/TestEcpImport.cs (test program)
```

## Running the Test

```bash
cd SdcCdmLib/SdcCdmInSqlite
dotnet run --project TestEcpImport.cs
```

This will:

1. Create a test database
2. Import the sample NAACCR V2 message
3. Display template instances and measurements
4. Show data statistics and sample records

## Support

For questions or issues with this implementation, please refer to:

- OMOP CDM v5.4 specification: https://ohdsi.github.io/CommonDataModel/cdm54.html
- NAACCR V2 message format documentation
- Sample data files for testing and validation
