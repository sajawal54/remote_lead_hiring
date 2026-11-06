from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.models import JobLeadModel

router = APIRouter(prefix="/leads", tags=["Job Leads"])

@router.get("")
def get_workspace_leads(
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Retrieves all processed and scored job leads for the authenticated workspace.
    PDF Section 8 & 9 (Lead Delivery & Intelligence).
    """
    leads = db.query(JobLeadModel).filter(
        JobLeadModel.workspace_id == current_user["workspace_id"]
    ).all()

    return {
        "status": "success",
        "workspace_id": current_user["workspace_id"],
        "total_leads": len(leads),
        "leads": [
            {
                "id": lead.id,
                "title": lead.title,
                "location": lead.location,
                "remote_policy": lead.remote_policy,
                "score": lead.score,
                "passed_threshold": lead.passed_threshold,
                "posted_at": lead.posted_at
            }
            for lead in leads
        ]
    }

@router.get("/{lead_id}")
def get_lead_detail(
    lead_id: str,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Retrieves full details and score breakdown for a specific job lead.
    """
    lead = db.query(JobLeadModel).filter(
        JobLeadModel.job_id == lead_id,
        JobLeadModel.workspace_id == current_user["workspace_id"]
    ).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Job lead not found.")

    return {
        "status": "success",
        "lead": {
            "id": lead.id,
            "title": lead.title,
            "description": lead.description,
            "location": lead.location,
            "remote_policy": lead.remote_policy,
            "score": lead.score,
            "passed_threshold": lead.passed_threshold,
            "verified_at": lead.verified_at
        }
    }