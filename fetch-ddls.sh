#!/usr/bin/env bash

set -euxo pipefail

# Set current directory to that of the script, for consistent file IO
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

SCHEMA_NAME="public"

cd database/ddl
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_ddl.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 1_OMOPCDM_postgresql_5.4_ddl.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_primary_keys.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 2_OMOPCDM_postgresql_5.4_primary_keys.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_indices.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 3_OMOPCDM_postgresql_5.4_indices.sql
curl -L \
  https://github.com/OHDSI/CommonDataModel/raw/refs/tags/v5.4.2/inst/ddl/5.4/postgresql/OMOPCDM_postgresql_5.4_constraints.sql \
  | sed "s/@cdmDatabaseSchema/${SCHEMA_NAME}/g" > 4_OMOPCDM_postgresql_5.4_constraints.sql