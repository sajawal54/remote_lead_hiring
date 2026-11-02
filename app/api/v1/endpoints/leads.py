from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import JobLeadModel

router = APIRouter()

@router.get("/")
def get_leads(
    min_score: Optional[int] = Query(None, description="Minimum score filter (e.g. 70)"),
    db: Session = Depends(get_db)
):
    """
    Database se leads fetch karta hai. Agar min_score doge toh sirf usse upar wali jobs aayengi.
    """
    query = db.query(JobLeadModel)
    
    if min_score is not None:
        query = query.filter(JobLeadModel.total_score >= min_score)
        
    leads = query.order_by(JobLeadModel.total_score.desc()).all()
    
    return {
        "status": "success",
        "count": len(leads),
        "leads": leads
    }
@router.get("/leads/{job_id}")
def get_lead_detail(job_id: str, db: Session = Depends(get_db)):
    
    lead = db.query(JobLeadModel).filter(JobLeadModel.job_id == job_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead