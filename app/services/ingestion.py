import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.models import RawSourceRecordModel

# Pre-approved source registry according to policy (Section 4.2)
APPROVED_SOURCES = {
    "job_board_api": {"permitted": True, "rate_limit": 100},
    "career_page_feed": {"permitted": True, "rate_limit": 50},
    "remoteok_live_api": {"permitted": True, "rate_limit": 100},
    "csv_upload": {"permitted": True, "rate_limit": 0},
    "unlicensed_scraper": {"permitted": False, "rate_limit": 0}
}

def verify_source_eligibility(source_name: str) -> dict:
    """
    Checks if a source is permitted and licensed under workspace policy.
    PDF Section 4.2 (Source eligibility and planning)
    """
    source_info = APPROVED_SOURCES.get(source_name.lower(), {"permitted": False})
    if not source_info.get("permitted"):
        return {
            "eligible": False,
            "reason": f"Source '{source_name}' is not permitted or lacks license approval."
        }
    return {
        "eligible": True,
        "reason": f"Source '{source_name}' verified and eligible for ingestion."
    }


def ingest_raw_source_record(db: Session, workspace_id: str, source_name: str, raw_payload: dict, source_url: str = None) -> dict:
    """
    Fetches and stores raw source evidence, source URL, and timestamp.
    PDF Section 4.3 (Ingestion and raw evidence)
    """
    # 1. Eligibility Check
    eligibility = verify_source_eligibility(source_name)
    if not eligibility["eligible"]:
        return {
            "status": "blocked",
            "message": eligibility["reason"]
        }

    # 2. Capture Raw Record with Provenance
    record_id = "raw_" + str(uuid.uuid4())[:8]
    raw_record = RawSourceRecordModel(
        record_id=record_id,
        workspace_id=workspace_id,
        source_name=source_name,
        raw_payload=raw_payload,
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc)
    )

    db.add(raw_record)
    db.commit()
    db.refresh(raw_record)

    return {
        "status": "ingested",
        "record_id": raw_record.record_id,
        "source_name": source_name,
        "message": "Raw source evidence successfully ingested and persisted."
    }