FROM postgres:16.3-bookworm

# These files execute in numeric order the first time the container starts.
COPY schemas/omop/ddl/postgresql/1_OMOPCDM_postgresql_5.4_ddl.sql /docker-entrypoint-initdb.d/10_omop_ddl.sql
COPY schemas/omop/ddl/postgresql/2_OMOPCDM_postgresql_5.4_primary_keys.sql /docker-entrypoint-initdb.d/20_omop_primary_keys.sql
COPY schemas/omop/ddl/postgresql/3_OMOPCDM_postgresql_5.4_constraints.sql /docker-entrypoint-initdb.d/30_omop_constraints.sql
COPY schemas/omop/ddl/postgresql/4_OMOPCDM_postgresql_5.4_indices.sql /docker-entrypoint-initdb.d/40_omop_indices.sql
COPY schemas/naaccr/ddl/postgresql/1_naaccr_postgresql_ddl.sql /docker-entrypoint-initdb.d/50_naaccr_ddl.sql
COPY schemas/sdc/ddl/postgresql/1_sdc_postgresql_ddl.sql /docker-entrypoint-initdb.d/60_sdc_ddl.sql
