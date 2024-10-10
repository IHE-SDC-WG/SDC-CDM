from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import relationship

Base = declarative_base()


class TemplateSdcClass(Base):
    __tablename__ = "templatesdcclass"
    __table_args__ = {"schema": "public"}

    pk = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    sdcformdesignid = Column(String, nullable=True)
    baseuri = Column(String, nullable=True)
    lineage = Column(String, nullable=True)
    version = Column(String, nullable=True)
    fulluri = Column(String, nullable=True)
    formtitle = Column(String, nullable=True)
    sdc_xml = Column(Text, nullable=True)
    doctype = Column(String, nullable=True)

    def __repr__(self):
        return f"<TemplateSdcClass(sdcformdesignid={self.sdcformdesignid}, formtitle='{self.formtitle}')>"


class TemplateInstanceClass(Base):
    __tablename__ = "templateinstanceclass"
    __table_args__ = {"schema": "public"}

    pk = Column(Integer, primary_key=True, autoincrement=True)
    templateinstanceversionguid = Column(String, nullable=True)
    templateinstanceversionuri = Column(String, nullable=True)
    templatesdcfk = Column(
        Integer, ForeignKey("public.templatesdcclass.pk"), nullable=False
    )
    instanceversiondate = Column(String, nullable=True)
    diagreportprops = Column(String, nullable=True)
    surgpathid = Column(String, nullable=True)
    personfk = Column(Integer, nullable=True)
    encounterfk = Column(Integer, nullable=True)
    practitionerfk = Column(Integer, nullable=True)
    reporttext = Column(String, nullable=True)

    def __repr__(self):
        return f"<TemplateInstanceClass(templateinstanceversionguid='{self.templateinstanceversionguid}')>"


class SdcObsClass(Base):
    __tablename__ = "sdcobsclass"
    __table_args__ = {"schema": "public"}

    pk = Column(Integer, primary_key=True, autoincrement=True)
    templateinstanceclassfk = Column(
        Integer, ForeignKey("public.templateinstanceclass.pk"), nullable=False
    )
    # parentfk = Column(Integer, nullable=True)
    parentinstanceguid = Column(String, nullable=True)
    section_id = Column(Integer, nullable=True)
    section_guid = Column(String, nullable=True)
    q_text = Column(String, nullable=True)
    q_instanceguid = Column(String, nullable=True)
    q_id = Column(String, nullable=True)
    li_text = Column(String, nullable=True)
    li_id = Column(String, nullable=True)
    li_instanceguid = Column(String, nullable=True)
    li_parentguid = Column(String, nullable=True)
    response = Column(String, nullable=True)
    units = Column(String, nullable=True)
    units_system = Column(String, nullable=True)
    datatype = Column(String, nullable=True)
    response_int = Column(String, nullable=True)
    response_float = Column(String, nullable=True)
    response_datetime = Column(String, nullable=True)
    reponse_string_nvarchar = Column(String, nullable=True)
    obsdatetime = Column(String, nullable=True)
    sdcorder = Column(String, nullable=True)
    sdcrepeatlevel = Column(String, nullable=True)
    sdccomments = Column(String, nullable=True)
    personfk = Column(Integer, nullable=True)
    encounterfk = Column(Integer, nullable=True)
    practitionerfk = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<SdcObsClass(pk={self.pk}, q_text='{self.q_text}', li_text='{self.li_text}')>"
