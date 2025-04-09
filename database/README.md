## SDC-CDM Schema Files

The SDC tables in described in a human-readable format in `SDC CDM Requirements.xlsx`

The OMOP tables are described at https://ohdsi.github.io/CommonDataModel/cdm54.html

Data Definition Language (DDL) files are provided under `ddl/` for the following backends:

- PostgreSQL
- SQLite

### Guide to updating the DDLs

DDL templates are generated in our [OHDSI/CommonDataModel fork](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC). The following .csv files should be considered the source of truth for the SDC-CDM schema:
- [OMOP_CDMv5.4-SDC_Table_Level.csv](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC/blob/add-SDC-schema/inst/csv/OMOP_CDMv5.4-SDC_Table_Level.csv)
- [OMOP_CDMv5.4-SDC_Field_Level.csv](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC/blob/add-SDC-schema/inst/csv/OMOP_CDMv5.4-SDC_Field_Level.csv)

The script `update-ddl-files.py [commit_hash]` fetches DDL templates from the fork, processes them, then writes ready-to-use files to the `ddl/` directory. The details of this process depends on the database type. See the script for details.

Any change to the schema should be made to the linked CSV files first. Note that all SDC additions are at the end of each CSV file.
