#!/usr/bin/env bash

set -euxo pipefail

# Set current directory to that of the script, for consistent file IO
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

SCHEMA_NAME="public"
SQLITE_SCHEMA_NAME="main"

pushd database/ddl

mkdir -p postgresql
pushd postgresql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_ddl.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 1_OMOPCDM_postgresql_5.4_postgresql_ddl.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_primary_keys.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 2_OMOPCDM_postgresql_5.4_postgresql_primary_keys.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_indices.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 3_OMOPCDM_postgresql_5.4_postgresql_indices.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_constraints.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 4_OMOPCDM_postgresql_5.4_postgresql_constraints.sql
popd

mkdir -p sqlite
pushd sqlite
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/sqlite/OMOPCDM_sqlite_5.4_ddl.sql \
  | sed "s/@cdmDatabaseSchema/${SQLITE_SCHEMA_NAME}/g" > 1_OMOPCDM_sqlite_5.4_ddl.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/sqlite/OMOPCDM_sqlite_5.4_primary_keys.sql \
  | sed "s/@cdmDatabaseSchema/${SQLITE_SCHEMA_NAME}/g" | sed "s/ALTER TABLE/-- ALTER TABLE/g" > 2_OMOPCDM_sqlite_5.4_primary_keys.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/sqlite/OMOPCDM_sqlite_5.4_indices.sql \
  | sed "s/@cdmDatabaseSchema/${SQLITE_SCHEMA_NAME}/g" > 3_OMOPCDM_sqlite_5.4_indices.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/heads/main/inst/ddl/5.4/sqlite/OMOPCDM_sqlite_5.4_constraints.sql \
  | sed "s/@cdmDatabaseSchema/${SQLITE_SCHEMA_NAME}/g" | sed "s/ALTER TABLE/-- ALTER TABLE/g" > 4_OMOPCDM_sqlite_5.4_constraints.sql
popd
