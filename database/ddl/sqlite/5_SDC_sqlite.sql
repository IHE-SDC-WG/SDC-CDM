-- Based on the mapping at "../SDC CDM Requirements.xlsx"

CREATE TABLE main.sdcobsclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templateinstanceclassfk integer NOT NULL,
    -- parentfk integer NULL,
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
    response_int varchar(255) NULL,
    response_float varchar(255) NULL,
    response_datetime varchar(255) NULL,
    reponse_string_nvarchar varchar(255) NULL,
    obsdatetime varchar(255) NULL,
    sdcorder varchar(255) NULL,
    sdcrepeatlevel varchar(255) NULL,
    sdccomments varchar(255) NULL,
    personfk integer NULL,
    encounterfk integer NULL,
    practitionerfk integer NULL
);
CREATE TABLE main.templateinstanceclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templateinstanceversionguid varchar(255) NULL,
    templateinstanceversionuri varchar(255) NULL,
    templatesdcfk integer NOT NULL,
    instanceversiondate varchar(255) NULL,
    diagreportprops varchar(255) NULL,
    surgpathid varchar(255) NULL,
    personfk integer NULL,
    encounterfk integer NULL,
    practitionerfk integer NULL,
    reporttext varchar(255) NULL
);
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
CREATE TABLE main.templatetermmapclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templatemapid varchar(255) NULL,
    template varchar(255) NULL,
    templatesdcfk integer NOT NULL,
    mapxml varchar(255) NULL,
    codesystemname varchar(255) NULL,
    codesystemreleasedate varchar(255) NULL,
    codesystemversion varchar(255) NULL,
    codesystemoid varchar(255) NULL,
    codesystemuri varchar(255) NULL
);
CREATE TABLE main.templatemapcontentclass (
    pk integer PRIMARY KEY AUTOINCREMENT,
    templatetermmap_fk integer NOT NULL,
    targetid varchar(255) NULL,
    code varchar(255) NULL,
    codetext varchar(255) NULL
);
CREATE TABLE main.observationspecimensclass (
    observationspecimensclasspk integer PRIMARY KEY AUTOINCREMENT,
    sdcobsclassfk integer NOT NULL,
    specimenfk integer NOT NULL
);
CREATE TABLE main.specimenclass (
    specimenpk integer PRIMARY KEY AUTOINCREMENT,
    parentspecimenfk integer NOT NULL,
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

-- ALTER TABLE main.sdcobsclass ADD CONSTRAINT fk_templateinstanceclass FOREIGN KEY (templateinstanceclassfk) REFERENCES main.templateinstanceclass (pk);

-- -- ALTER TABLE main.sdcobsclass  ADD CONSTRAINT fk_parentfk FOREIGN KEY (parentfk) REFERENCES main.sdcobsclass (pk);

-- ALTER TABLE main.templateinstanceclass  ADD CONSTRAINT fk_templatesdcfk FOREIGN KEY (templatesdcfk) REFERENCES main.templatesdcclass (pk);

-- ALTER TABLE main.templatetermmapclass  ADD CONSTRAINT fk_templatesdcfk FOREIGN KEY (templatesdcfk) REFERENCES main.templatesdcclass (pk);

-- ALTER TABLE main.templatemapcontentclass  ADD CONSTRAINT fk_templatetermmap_fk FOREIGN KEY (templatetermmap_fk) REFERENCES main.templatetermmapclass (pk);

-- ALTER TABLE main.observationspecimensclass  ADD CONSTRAINT fk_sdcobsclass FOREIGN KEY (sdcobsclassfk) REFERENCES main.sdcobsclass(pk);

-- ALTER TABLE main.observationspecimensclass  ADD CONSTRAINT fk_specimen FOREIGN KEY (specimenfk) REFERENCES main.specimenclass(specimenpk);

-- ALTER TABLE main.specimenclass  ADD CONSTRAINT fk_parentspecimen FOREIGN KEY (parentspecimenfk) REFERENCES main.specimenclass(specimenpk);

-- -- ALTER TABLE main.sdcobsclass  ADD CONSTRAINT fk_person FOREIGN KEY (personfk) REFERENCES main.person (person_id);

-- -- ALTER TABLE main.sdcobsclass  ADD CONSTRAINT fk_encounter FOREIGN KEY (encounterfk) REFERENCES main.visit_occurrence (visit_occurrence_id);

-- -- ALTER TABLE main.sdcobsclass  ADD CONSTRAINT fk_practitioner FOREIGN KEY (practitionerfk) REFERENCES main.provider (provider_id);
