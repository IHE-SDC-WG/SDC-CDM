#!/bin/sh

SCHEMA="public"

cd database/ddl
curl -s \
  https://raw.githubusercontent.com/OHDSI/CommonDataModel/main/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_ddl.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA}/g" > 1OMOPCDM_postgresql_5.4_ddl.sql
curl -s \
  https://raw.githubusercontent.com/OHDSI/CommonDataModel/main/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_primary_keys.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA}/g" > 2OMOPCDM_postgresql_5.4_primary_keys.sql
curl -s \
  https://raw.githubusercontent.com/OHDSI/CommonDataModel/main/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_indices.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA}/g" > 3OMOPCDM_postgresql_5.4_indices.sql
curl -s \
  https://raw.githubusercontent.com/OHDSI/CommonDataModel/main/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_constraints.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA}/g" > 4OMOPCDM_postgresql_5.4_constraints.sql