from fastapi import APIRouter
from pydantic import BaseModel
from typing import List , Optional

router = APIRouter()

class ExportRequest(BaseModel):
  min_score: int = 80
  lead_ids : Optional[List[str]] = None
  format : str = "csv"
  
@router.post("/exports" , status_code=202)
def create_export(request: ExportRequest):
  return {
    "export_id": "exp_12345",
    "status": "processing",
    "record_count" : 1,
  }
  
@router.get("/exports/{export_id}/download")
def download_export(export_id : str):
  return {
    "export_id" : export_id,
    "download_url" : f"https://api.example.com/downloads/{export_id}.csv",
    "expires_in_seconds" : 3600
  }