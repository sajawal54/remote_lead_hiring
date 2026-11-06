import csv
import hashlib
import io
import httpx
import uuid
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.models import RawSourceRecordModel
from app.services.ingestion import verify_source_eligibility

def ingest_csv_upload(db: Session, workspace_id: str, file_content: bytes, source_name: str = "csv_upload") -> dict:
    """
    Parses uploaded CSV file bytes, creates raw records, and stores them in RawSourceRecordModel.
    PDF Section 4.3 (Ingestion and Raw Evidence Capture).
    """
    eligibility = verify_source_eligibility("csv_upload")
    if not eligibility["eligible"]:
        return {"status": "blocked", "message": eligibility["reason"]}

    try:
        # Decode bytes to string stream
        decoded_file = file_content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded_file))
        if not reader.fieldnames or not any(field.strip() for field in reader.fieldnames if field):
            return {"status": "error", "message": "CSV file must include a header row."}
        
        imported_count = 0
        record_ids = []

        for row in reader:
            record_id = "raw_" + str(uuid.uuid4())[:10]
            
            raw_record = RawSourceRecordModel(
                record_id=record_id,
                workspace_id=workspace_id,
                source_name="csv_upload",
                source_url=source_name or "local_file_upload",
                raw_payload=row,
                fetched_at=datetime.now(timezone.utc)
            )
            db.add(raw_record)
            record_ids.append(record_id)
            imported_count += 1

        db.commit()
        return {
            "status": "success",
            "imported_records": imported_count,
            "record_ids": record_ids,
            "message": f"Successfully ingested {imported_count} raw records from CSV upload."
        }
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Failed to parse CSV upload: {str(e)}"
        }

def ingest_api_feed(db: Session, workspace_id: str, source_name: str, api_payloads: list[dict]) -> dict:
    """
    Ingests external API payloads into raw source records.
    PDF Section 4.3 (API Feed Ingestion).
    """
    if not isinstance(api_payloads, list) or not all(isinstance(item, dict) for item in api_payloads):
        return {"status": "error", "message": "jobs must be a list of JSON objects."}

    eligibility = verify_source_eligibility(source_name)
    if not eligibility["eligible"]:
        return {"status": "blocked", "message": eligibility["reason"]}

    try:
        imported_count = 0
        record_ids = []

        for payload in api_payloads:
            record_id = "raw_" + str(uuid.uuid4())[:10]
            
            raw_record = RawSourceRecordModel(
                record_id=record_id,
                workspace_id=workspace_id,
                source_name=source_name,
                source_url=payload.get("source_url", "api_feed"),
                raw_payload=payload,
                fetched_at=datetime.now(timezone.utc)
            )
            db.add(raw_record)
            record_ids.append(record_id)
            imported_count += 1

        db.commit()
        return {
            "status": "success",
            "imported_records": imported_count,
            "record_ids": record_ids,
            "message": f"Successfully ingested {imported_count} raw records from API feed {source_name}."
        }
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Failed to ingest API feed: {str(e)}"
        }
        
def fetch_and_store_remote_jobs(db: Session, workspace_id: str) -> dict:
    """
    Fetches live remote job listings from RemoteOK public API and ingests them as raw records.
    PDF Section 4.3 (External Job Board API Connector).
    """
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    eligibility = verify_source_eligibility("remoteok_live_api")
    if not eligibility["eligible"]:
        return {"status": "blocked", "message": eligibility["reason"]}
    
    try:
        # Fetch data from RemoteOK API
        response = None
        for attempt in range(1, 4):
            try:
                response = httpx.get(url, headers=headers, timeout=10.0)
            except httpx.TimeoutException:
                if attempt == 3:
                    raise
                time.sleep(0.5 * attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 3:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(5.0, max(0.0, float(retry_after))) if retry_after else 0.5 * attempt
                except ValueError:
                    delay = 0.5 * attempt
                time.sleep(delay)
                continue
            response.raise_for_status()
            break
        if response is None:
            raise httpx.TimeoutException("RemoteOK did not respond after three attempts.")

        data = response.json()
        if not isinstance(data, list):
            raise ValueError("RemoteOK returned an unexpected response format.")
        
        # RemoteOK API returns the first element as metadata, jobs start from index 1
        job_listings = data[1:] if len(data) > 1 else []
        
        imported_count = 0
        record_ids = []

        for job in job_listings:
            # Skip non-job entries if any
            if not isinstance(job, dict) or job.get("id") is None:
                continue
                
            stable_id = hashlib.sha256(
                f"{workspace_id}:{job.get('id')}".encode("utf-8")
            ).hexdigest()[:20]
            record_id = "raw_rok_" + stable_id
            
            # Check if this raw record already exists to avoid duplicates
            existing = db.query(RawSourceRecordModel).filter(RawSourceRecordModel.record_id == record_id).first()
            if existing:
                continue

            raw_record = RawSourceRecordModel(
                record_id=record_id,
                workspace_id=workspace_id,
                source_name="remoteok_live_api",
                source_url=job.get("url", "https://remoteok.com"),
                raw_payload=job,
                fetched_at=datetime.now(timezone.utc)
            )
            db.add(raw_record)
            record_ids.append(record_id)
            imported_count += 1

        db.commit()
        return {
            "status": "success",
            "imported_records": imported_count,
            "record_ids": record_ids,
            "message": f"Successfully fetched and ingested {imported_count} live jobs from RemoteOK API."
        }
        
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Error connecting to external job board API: {str(e)}"
        }