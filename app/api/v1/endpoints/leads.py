from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.models import (
    AuditEventModel,
    JobLeadModel,
    JobSourceModel,
    RawSourceRecordModel,
    UserModel,
)

router = APIRouter(prefix="/leads", tags=["Job Leads"])


class LeadReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = Field(default=None, max_length=2000)


@router.get("")
def get_workspace_leads(
    min_score: int = Query(default=0, ge=0, le=100),
    region: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db),
):
    """Return paginated workspace leads with scores and source provenance."""
    query = db.query(JobLeadModel).filter(
        JobLeadModel.workspace_id == current_user["workspace_id"],
        JobLeadModel.total_score >= min_score,
    )
    if status:
        query = query.filter(JobLeadModel.status == status.strip().casefold())
    if region:
        query = query.filter(JobLeadModel.location.ilike(f"%{region.strip()}%"))

    total = query.count()
    leads = (
        query.order_by(JobLeadModel.total_score.desc(), JobLeadModel.posted_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    lead_ids = [lead.job_id for lead in leads]
    source_links = (
        db.query(JobSourceModel)
        .filter(
            JobSourceModel.workspace_id == current_user["workspace_id"],
            JobSourceModel.job_id.in_(lead_ids),
        )
        .all()
        if lead_ids
        else []
    )
    provenance = {}
    for source in source_links:
        provenance.setdefault(source.job_id, []).append(
            {
                "source_name": source.source_name,
                "source_url": source.source_url,
                "first_seen_at": source.first_seen_at,
                "last_seen_at": source.last_seen_at,
            }
        )

    return {
        "status": "success",
        "workspace_id": current_user["workspace_id"],
        "total_leads": total,
        "limit": limit,
        "offset": offset,
        "leads": [
            {
                "id": lead.job_id,
                "title": lead.title,
                "company_name": lead.company_name,
                "location": lead.location,
                "remote_policy": lead.remote_policy,
                "score": lead.total_score,
                "score_breakdown": lead.score_breakdown or {},
                "passed_threshold": lead.passed_threshold,
                "status": lead.status,
                "posted_at": lead.posted_at,
                "sources": provenance.get(lead.job_id, []),
            }
            for lead in leads
        ],
    }


@router.get("/{lead_id}")
def get_lead_detail(
    lead_id: str,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db),
):
    """Return details, score components, extraction evidence, and source provenance."""
    lead = (
        db.query(JobLeadModel)
        .filter(
            JobLeadModel.job_id == lead_id,
            JobLeadModel.workspace_id == current_user["workspace_id"],
        )
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Job lead not found.")

    sources = (
        db.query(JobSourceModel, RawSourceRecordModel)
        .join(
            RawSourceRecordModel,
            RawSourceRecordModel.record_id == JobSourceModel.record_id,
        )
        .filter(
            JobSourceModel.workspace_id == current_user["workspace_id"],
            JobSourceModel.job_id == lead.job_id,
        )
        .all()
    )
    extraction = lead.extraction or {}
    return {
        "status": "success",
        "lead": {
            "id": lead.job_id,
            "company_name": lead.company_name,
            "title": lead.title,
            "description": lead.description,
            "location": lead.location,
            "remote_policy": lead.remote_policy,
            "allowed_countries": lead.allowed_countries or [],
            "technologies": lead.technologies or [],
            "salary": lead.salary,
            "score": lead.total_score,
            "score_breakdown": lead.score_breakdown or {},
            "passed_threshold": lead.passed_threshold,
            "status": lead.status,
            "review_notes": lead.review_notes,
            "posted_at": lead.posted_at,
            "verified_at": lead.verified_at,
            "last_verified_at": lead.last_verified_at,
            "canonical_url": lead.canonical_url,
            "sources_count": lead.sources_count or len(sources),
            "sources": [
                {
                    "source_name": source.source_name,
                    "source_url": source.source_url,
                    "first_seen_at": source.first_seen_at,
                    "last_seen_at": source.last_seen_at,
                    "fetched_at": record.fetched_at,
                }
                for source, record in sources
            ],
            "extraction": extraction,
            "quality_gate": extraction.get("quality_gate"),
            "company_signals": extraction.get("company_signals"),
        },
    }


@router.patch("/{lead_id}/review")
def review_lead(
    lead_id: str,
    payload: LeadReviewRequest,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db),
):
    """Approve or reject a lead currently awaiting human review."""
    workspace_id = current_user["workspace_id"]
    lead = (
        db.query(JobLeadModel)
        .filter(
            JobLeadModel.job_id == lead_id,
            JobLeadModel.workspace_id == workspace_id,
        )
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Job lead not found.")
    if lead.status != "review_required":
        raise HTTPException(
            status_code=409,
            detail="Only leads requiring review can be approved or rejected.",
        )

    user = db.query(UserModel).filter(
        UserModel.workspace_id == workspace_id,
        UserModel.email == current_user["email"],
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user was not found.")

    extraction = dict(lead.extraction or {})
    quality_gate = dict(extraction.get("quality_gate") or {})
    if payload.action == "approve" and quality_gate.get("status") == "excluded":
        raise HTTPException(
            status_code=409,
            detail="A lead excluded by quality checks cannot be approved.",
        )

    notes = payload.notes.strip() if payload.notes else ""
    if payload.action == "approve":
        lead.status = "active"
        lead.review_notes = notes or "Approved by reviewer."
        quality_gate.update(
            {
                "status": "approved_by_reviewer",
                "is_eligible": True,
            }
        )
        action = "lead.review.approved"
    else:
        lead.status = "excluded"
        lead.review_notes = notes or "Rejected by reviewer."
        quality_gate.update(
            {
                "status": "excluded",
                "is_eligible": False,
            }
        )
        action = "lead.review.rejected"

    extraction["quality_gate"] = quality_gate
    lead.extraction = extraction
    lead.reviewed_by_user_id = user.id
    db.add(
        AuditEventModel(
            workspace_id=workspace_id,
            user_id=user.id,
            action=action,
            resource_type="job_lead",
            resource_id=lead.job_id,
            details={"notes": notes or None},
        )
    )
    db.commit()
    db.refresh(lead)
    return {
        "status": "success",
        "lead_id": lead.job_id,
        "review_status": lead.status,
        "reviewed_by_user_id": lead.reviewed_by_user_id,
        "review_notes": lead.review_notes,
    }
