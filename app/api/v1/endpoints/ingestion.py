from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_access_token
from app.services.ingestion import verify_source_eligibility
from app.services.ingestion_connector import ingest_csv_upload, ingest_api_feed
from app.services.ingestion_connector import fetch_and_store_remote_jobs

router = APIRouter(prefix="/ingest", tags=["Data Ingestion Connectors"])

@router.post("/csv")
async def upload_csv_jobs(
    file: UploadFile = File(...),
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Uploads and parses a CSV file containing job listings, storing them as raw records.
    PDF Section 4.3 (CSV Ingestion Pipeline).
    """
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content = await file.read()
    result = ingest_csv_upload(
        db,
        workspace_id=current_user["workspace_id"],
        file_content=content,
        source_name=file.filename,
    )
    if result["status"] == "blocked":
        raise HTTPException(status_code=403, detail=result["message"])
    return result

@router.post("/api-feed")
def ingest_external_feed(
    payload: dict,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Ingests batch job payloads from external API feeds.
    PDF Section 4.3 (External API Connector).
    """
    source_name = payload.get("source_name", "generic_api_feed")
    jobs = payload.get("jobs", [])

    if not jobs:
        raise HTTPException(status_code=400, detail="No job records provided in payload.")
    eligibility = verify_source_eligibility(source_name)
    if not eligibility["eligible"]:
        raise HTTPException(status_code=403, detail=eligibility["reason"])

    result = ingest_api_feed(
        db,
        workspace_id=current_user["workspace_id"],
        source_name=source_name,
        api_payloads=jobs,
    )
    return result

@router.post("/fetch-live-jobs")
def trigger_live_job_fetch(
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Triggers live fetching of remote job listings from external public boards (RemoteOK).
    PDF Section 4.3 (Automated Ingestion Pipeline Trigger).
    """
    eligibility = verify_source_eligibility("remoteok_live_api")
    if not eligibility["eligible"]:
        raise HTTPException(status_code=403, detail=eligibility["reason"])
    result = fetch_and_store_remote_jobs(db, workspace_id=current_user["workspace_id"])
    return result