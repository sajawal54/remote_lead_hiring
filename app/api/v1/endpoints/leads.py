from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import JobLeadModel

router = APIRouter()

@router.get("/leads")
def get_leads(
    min_score: int = Query(80, description="Minimum lead score filter"),
    tech: Optional[str] = Query(None, description="Filter by technology"),
    db: Session = Depends(get_db)
):
    """
    GET /leads: Database se filtered aur authorized leads return karta hai.
    """
    query = db.query(JobLeadModel).filter(JobLeadModel.total_score >= min_score)
    leads = query.all()
    
    if not leads:
        return []
        
    return leads

@router.get("/leads/{job_id}")
def get_lead_detail(job_id: str, db: Session = Depends(get_db)):
    """
    GET /leads/{id}: Database se single lead ki complete details deta hai.
    """
    lead = db.query(JobLeadModel).filter(JobLeadModel.job_id == job_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead