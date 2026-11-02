from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import JobLeadModel
from app.services.ingestion import normalize_and_save_lead
from app.services.scoring import calculate_lead_score

router = APIRouter()

class IngestRequest(BaseModel):
    source_name: str
    workspace_id: str
    target_criteria: Optional[Dict[str, Any]] = {}  # Target criteria scoring ke liye
    raw_payload: Dict[str, Any]

@router.post("/ingest", status_code=201)
def ingest_job_data(payload: IngestRequest, db: Session = Depends(get_db)):
    try:
        # 1. Normalize data
        normalized_data = normalize_and_save_lead(
            workspace_id=payload.workspace_id,
            source_name=payload.source_name,
            raw_payload=payload.raw_payload,
            db=db
        )

        # 2. Calculate 100-point score using the Scoring Engine
        target_criteria = payload.target_criteria or {
            "tech_stack": normalized_data.get("technologies", []),
            "region": "global"
        }
        total_score, score_breakdown = calculate_lead_score(normalized_data, target_criteria)

        # 3. Add score and breakdown to normalized data
        normalized_data["total_score"] = total_score
        normalized_data["score_breakdown"] = score_breakdown

        # 4. Save into JobLeadModel
        db_lead = JobLeadModel(**normalized_data)
        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)

        return {
            "status": "success",
            "message": "Job ingested, normalized, and scored successfully!",
            "job_id": db_lead.job_id,
            "total_score": total_score,
            "score_breakdown": score_breakdown
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Ingestion & Scoring failed: {str(e)}")