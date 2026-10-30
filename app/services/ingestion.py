from sqlalchemy.orm import Session
from app.models.models import RawSourceRecordModel
import uuid


def normalize_and_save_lead(workspace_id: str ,source_name: str , raw_payload: dict , db: Session):
  record_id = "raw_" + str(uuid.uuid4())[:8]
  raw_record = RawSourceRecordModel(
    record_id=record_id,
    workspace_id = workspace_id,
    source_name = source_name,
    raw_payload=raw_payload
  )
  db.add(raw_record)
  db.commit()

  
  technologies = [tech.strip().lower() for tech in raw_payload.get("technologies" , [])]
  remote_policy = raw_payload.get("remote_policy" , "remote").lower()
  
  normalize_data = {
    "job_id": "job_" + str(uuid.uuid4())[:8],
    "workspace_id": workspace_id,
    "company_name": raw_payload.get("company_name" , "Unknown_company").strip(),
    "title": raw_payload.get("title" , "Untitled Role").strip(),
    "location": raw_payload.get("location" , "Remote").strip(),
    "remote_policy" : remote_policy,
    "allowed_countries": raw_payload.get("allowed_countries" , ["Global"]),
    "technologies" : technologies,
    "salary": raw_payload.get("salary" , {"min":0 , "max":0 , "currency":"USD" , "period":"yearly"}),
    "score_breakdown": {},
    "total_score":0
  }
  
  return normalize_data