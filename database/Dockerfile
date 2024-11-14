FROM postgres:16.3-bookworm

# These .sql files will be executed in alphanumeric order the first time the 
# container is run
COPY ddl/postgresql/*.sql /docker-entrypoint-initdb.d/
