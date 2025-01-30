-- Based on the mapping at "../SDC CDM Requirements.xlsx"

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE main.templatesdcclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    sdcformdesignid varchar(255) NULL,
    baseuri varchar(255) NULL,
    lineage varchar(255) NULL,
    version varchar(255) NULL,
    fulluri varchar(255) NULL,
    formtitle varchar(255) NULL,
    sdc_xml text NULL,
    doctype varchar(255) NULL
);

CREATE TABLE main.templateinstanceclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templateinstanceversionguid varchar(255) NULL,
    templateinstanceversionuri varchar(255) NULL,
    templatesdcfk integer NOT NULL REFERENCES templatesdcclass(pk),
    instanceversiondate varchar(255) NULL,
    diagreportprops varchar(255) NULL,
    surgpathid varchar(255) NULL,
    personfk integer NULL,
    encounterfk integer NULL,
    practitionerfk integer NULL,
    reporttext varchar(255) NULL
);

CREATE TABLE main.sdcobsclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templateinstanceclassfk integer NOT NULL REFERENCES templateinstanceclass(pk),
    parentfk integer NULL REFERENCES sdcobsclass(pk),
    parentinstanceguid varchar(255) NULL,
    section_id varchar(255) NULL,
    section_guid varchar(255) NULL,
    q_text varchar(255) NULL,
    q_instanceguid varchar(255) NULL,
    q_id varchar(255) NULL,
    li_text varchar(255) NULL,
    li_id varchar(255) NULL,
    li_instanceguid varchar(255) NULL,
    li_parentguid varchar(255) NULL,
    response varchar(255) NULL,
    units varchar(255) NULL,
    units_system varchar(255) NULL,
    datatype varchar(255) NULL,
    response_int integer NULL,
    response_float real NULL,
    response_datetime date NULL,
    reponse_string_nvarchar varchar(255) NULL,
    obsdatetime varchar(255) NULL,
    sdcorder varchar(255) NULL,
    sdcrepeatlevel varchar(255) NULL,
    sdccomments varchar(255) NULL,
    personfk integer NULL,
    encounterfk integer NULL,
    practitionerfk integer NULL
);
CREATE TABLE main.templatetermmapclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templatemapid varchar(255) NULL,
    template varchar(255) NULL,
    templatesdcfk integer NOT NULL REFERENCES templatesdcclass(pk),
    mapxml varchar(255) NULL,
    codesystemname varchar(255) NULL,
    codesystemreleasedate varchar(255) NULL,
    codesystemversion varchar(255) NULL,
    codesystemoid varchar(255) NULL,
    codesystemuri varchar(255) NULL
);
CREATE TABLE main.templatemapcontentclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templatetermmap_fk integer NOT NULL REFERENCES templatetermmapclass(pk),
    targetid varchar(255) NULL,
    code varchar(255) NULL,
    codetext varchar(255) NULL,
    codematch varchar(255) NULL
);
CREATE TABLE main.specimenclass (
    specimenpk integer PRIMARY KEY AUTOINCREMENT,
    parentspecimenfk integer NULL REFERENCES specimenclass(specimenpk),
    patientid varchar(255) NULL,
    encounterid varchar(255) NULL,
    specimentypetext varchar(255) NULL,
    specimentypecode varchar(255) NULL,
    sourcesitetext varchar(255) NULL,
    sourcesitecode varchar(255) NULL,
    collectionmethodtext varchar(255) NULL,
    collectionmethodcode varchar(255) NULL,
    specimencount varchar(255) NULL,
    collectiondate varchar(255) NULL
);

CREATE TABLE main.observationspecimensclass (
    observationspecimensclasspk integer PRIMARY KEY AUTOINCREMENT,
    sdcobsclassfk integer NOT NULL REFERENCES sdcobsclass(pk),
    specimenfk integer NOT NULL REFERENCES specimenclass(specimenpk)
);

COMMIT;
