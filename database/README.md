Supported database DDLs are fetched from [our OHDSI/CommonDataModel fork](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC) and edited to work with the default settings of each database.

The Python script `fetch-latest-ddls.py` will fetch supported DDLs and process them accordingly.

The following .csv files in our CommonDataModel fork are considered the source of truth for DDL generation:
- [OMOP_CDMv5.4-SDC_Table_Level.csv](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC/blob/add-SDC-schema/inst/csv/OMOP_CDMv5.4-SDC_Table_Level.csv)
- [OMOP_CDMv5.4-SDC_Field_Level.csv](https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC/blob/add-SDC-schema/inst/csv/OMOP_CDMv5.4-SDC_Field_Level.csv)

Any change to the schema should be made to the linked CSV files first. Note that all SDC additions are at the end of each CSV file.