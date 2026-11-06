import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, synonym

from app.core.database import Base


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id = Column("workspace_id", String, primary_key=True, index=True, default=lambda: "ws_" + str(uuid.uuid4())[:8])
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    users = relationship("UserModel", back_populates="workspace")
    workflows = relationship("WorkflowExecutionModel", back_populates="workspace")
    raw_records = relationship("RawSourceRecordModel", back_populates="workspace")
    companies = relationship("CompanyModel", back_populates="workspace")


class UserModel(Base):
    __tablename__ = "users"

    id = Column("user_id", String, primary_key=True, default=lambda: "usr_" + str(uuid.uuid4())[:8])
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column("password_hash", String, nullable=False)
    role = Column(String, nullable=False, default="workspace_user")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    workspace = relationship("WorkspaceModel", back_populates="users")


class RawSourceRecordModel(Base):
    __tablename__ = "raw_source_records"

    record_id = Column(String, primary_key=True, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    source_name = Column(String, nullable=False)
    raw_payload = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_url = Column(String, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="raw_records")


class CompanyModel(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_company_workspace_name"),
    )

    id = Column("company_id", String, primary_key=True, default=lambda: "comp_" + str(uuid.uuid4())[:8])
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    normalized_name = Column("name", String, nullable=False)
    domain = Column(String, nullable=True)
    aliases = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolution_status = Column(String, nullable=False, default="unresolved")

    workspace = relationship("WorkspaceModel", back_populates="companies")
    leads = relationship(
        "JobLeadModel",
        back_populates="company",
        foreign_keys="JobLeadModel.company_id",
        primaryjoin="CompanyModel.id == JobLeadModel.company_id",
    )


class JobLeadModel(Base):
    __tablename__ = "job_leads"

    job_id = Column(String, primary_key=True, default=lambda: "job_" + str(uuid.uuid4())[:8])
    id = synonym("job_id")
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    company_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    location = Column(String, nullable=False)
    remote_policy = Column(String, nullable=True)
    allowed_countries = Column(JSON, nullable=True)
    technologies = Column(JSON, nullable=True)
    salary = Column(JSON, nullable=True)
    score_breakdown = Column(JSON, nullable=False, default=dict)
    total_score = Column(Integer, nullable=False, default=0)
    score = synonym("total_score")
    last_verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sources_count = Column(Integer, default=1)
    company_id = Column(String, nullable=True)
    canonical_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    seniority = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    confidence = Column(Float, nullable=True)
    extraction = Column(JSON, nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_by_user_id = Column(String, nullable=True)
    review_notes = Column(Text, nullable=True)
    target_criteria = Column(JSON, nullable=False, default=dict)
    score_version = Column(String, nullable=False, default="pdf-v1")

    company = relationship(
        "CompanyModel",
        back_populates="leads",
        foreign_keys=[company_id],
        primaryjoin="JobLeadModel.company_id == CompanyModel.id",
    )

    @property
    def passed_threshold(self) -> bool:
        threshold = (self.target_criteria or {}).get("min_score", 0)
        return self.total_score >= threshold


class WorkflowExecutionModel(Base):
    __tablename__ = "workflow_executions"

    id = Column("workflow_id", String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    status = Column(String, default="pending")
    stage = Column(String, default="source_eligibility")
    criteria = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column("last_error", Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="workflows")


class JobSourceModel(Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("job_id", "record_id", name="uq_job_source_job_record"),
    )

    job_source_id = Column(String, primary_key=True, default=lambda: "src_" + str(uuid.uuid4())[:8])
    workspace_id = Column(String, ForeignKey("workspaces.workspace_id"), nullable=False)
    job_id = Column(String, ForeignKey("job_leads.job_id"), nullable=False)
    record_id = Column(String, ForeignKey("raw_source_records.record_id"), nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
