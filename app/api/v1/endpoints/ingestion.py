from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import JobLeadModel
from app.services.ingestion import normalize_and_save_lead

router = APIRouter()

class IngestRequest(BaseModel):
  source_name: str
  workspace_id: str
  raw_payload: Dict[str , Any]
  
@router.post("/ingest" , status_code=201)
def ingest_job_data(payload: IngestRequest , db:Session = Depends(get_db)):
  
  try:
    normalized_data = normalize_and_save_lead(
      workspace_id=payload.workspace_id,
      source_name = payload.source_name,
      raw_payload = payload.raw_payload,
      db = db
    )
    
    db_lead = JobLeadModel(**normalized_data)
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    
    return {
      "status": "success",
      "message": "Raw data successfully ingested , normalized , and saved as a Job Lead",
      "job_id": db_lead.job_id,
      "normalized_preview": normalized_data
    }
  except Exception as e:
    db.rollback()
    raise HTTPException (status_code=400 , detail=f"Ingestion failed:{str(e)}")