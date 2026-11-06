import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.models import JobLeadModel

router = APIRouter(prefix="/exports", tags=["Exports"])

@router.post("")
def create_export(
    payload: Optional[dict] = None,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Generates scoped CSV export artifact of qualified leads from the database.
    PDF Section 15: POST /exports
    """
    # Fetch qualified leads for this workspace from database
    workspace_id = current_user["workspace_id"]
    leads = [
        lead
        for lead in db.query(JobLeadModel).filter(
            JobLeadModel.workspace_id == workspace_id
        ).all()
        if lead.passed_threshold
    ]

    if not leads:
        raise HTTPException(status_code=404, detail="No qualified leads found to export for this workspace.")

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV Header
    writer.writerow(["Lead ID", "Job Title", "Location", "Remote Policy", "Score", "Verified At"])

    # Write Data Rows
    for lead in leads:
        writer.writerow([
            lead.id,
            lead.title,
            lead.location,
            lead.remote_policy,
            lead.score,
            lead.verified_at
        ])

    output.seek(0)

    # Return as direct downloadable CSV stream response
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=qualified_leads_{workspace_id}.csv"}
    )

@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    current_user: dict = Depends(verify_access_token),
):
    """
    Permission and expiry checked download gateway.
    PDF Section 15: GET /exports/{id}/download
    """
    raise HTTPException(
        status_code=501,
        detail="Export artifacts are not stored yet. Download the CSV returned by POST /exports instead.",
    )