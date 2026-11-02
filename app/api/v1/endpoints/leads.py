from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
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
    Scores descending order (high score first) mein sorted hongi.
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

@router.get("/{job_id}")
def get_job_lead_detail(job_id: str, db: Session = Depends(get_db)):
    """
    Ek specific job lead ki poori details fetch karta hai uske Job ID ke zariye.
    """
    lead = db.query(JobLeadModel).filter(JobLeadModel.job_id == job_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Yeh job lead database mein nahi mili.")
    
    return {
        "status": "success",
        "lead": lead
    }