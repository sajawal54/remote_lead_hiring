from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class WorkflowExecutionModel(Base):
    __tablename__ = "workflow_executions"

    id = Column(String, primary_key=True, index=True)
    workspace_id = Column(String, index=True, nullable=False)
    request_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="pending", nullable=False) # pending, queued, running, succeeded, failed, cancelled
    stage = Column(String, default="init", nullable=False)
    policy_version = Column(String, default="v1.0", nullable=False)
    last_error_code = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

class WorkflowStepModel(Base):
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String, ForeignKey("workflow_executions.id"), nullable=False, index=True)
    stage_name = Column(String, nullable=False)
    attempt = Column(Integer, default=1, nullable=False)
    status = Column(String, default="pending", nullable=False) # pending, running, succeeded, retry_wait, failed
    input_ref = Column(Text, nullable=True)
    output_ref = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)