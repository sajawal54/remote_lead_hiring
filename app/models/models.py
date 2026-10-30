from sqlalchemy import Column , String , Integer , DateTime , JSON , ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class WorkSpaceModel(Base):
  __tablename__ = "workspaces"
  
  workspace_id = Column(String , primary_key=True , index=True)
  name = Column(String , nullable=False)
  created_at = Column(DateTime(timezone=True) , server_default=func.now())
  
class WorkFlowExecutionModel(Base):
  __tablename__ = "workflow_executions"
  
  workflow_id = Column(String , primary_key=True , index=True)
  workspace_id = Column(String , ForeignKey("workspaces.workspace_id") , nullable=False)
  status = Column(String , default="queued")
  stage = Column(String , default="source_selection")
  criteria = Column(JSON , nullable=False)
  created_at = Column(DateTime(timezone=True) , server_default=func.now())
  
class JobLeadModel(Base):
  __tablename__ = "job_leads"
  
  job_id = Column(String , primary_key=True , index=True)
  workspace_id = Column(String , ForeignKey("workspaces.workspace_id") , nullable=False)
  company_name = Column(String , nullable=False)
  title = Column(String , nullable=False)
  location = Column(String , nullable=False)
  remote_policy = Column(String , nullable=True)
  allowed_countries = Column(JSON , nullable=True)
  technologies = Column(JSON , nullable=True)
  salary = Column(JSON , nullable=True)
  score_breakdown = Column(JSON , nullable=False)
  total_score = Column(Integer , nullable=False)
  last_verified_at = Column(DateTime(timezone=True) , server_default=func.now())
  sources_count = Column(Integer , default=1)
  
class RawSourceRecordModel(Base):
  __tablename__ = "raw_source_records"
  
  record_id = Column(String , primary_key=True , index=True)
  workspace_id = Column(String , ForeignKey("workspaces.workspace_id") , nullable=False)
  source_name = Column(String , nullable=False)
  raw_payload = Column(JSON , nullable= False)
  fetched_at = Column(DateTime(timezone=True) , server_default=func.now())
  