# SDC-CDM
A Common Data Model (CDM) for the Structured Data Capture (SDC) IG

## Setup

Copy `.env.example` to `.env`. The default values will work

`docker compose up` starts a Postgres database with the OMOP CDM loaded in

To reset the database, run `docker compose down -v` to remove the db volume before running `docker compose up` again

## Importing SDC to the Database

`python db-utils/import_sdc_form.py [file]` imports an XML SDC form

`python db-utils/import_vol_v_message.py [file]` imports a NAACCR Vol V message