import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.models import AuditEventModel, ExportModel, JobLeadModel, JobSourceModel, UserModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/exports", tags=["Exports"])
_EXPORT_DIR = Path("generated_exports").resolve()
_EXPORT_LIFETIME = timedelta(hours=24)


def _csv_content(db: Session, workspace_id: str) -> tuple[str, int]:
    leads = (
        db.query(JobLeadModel)
        .filter(
            JobLeadModel.workspace_id == workspace_id,
            JobLeadModel.status == "active",
        )
        .order_by(JobLeadModel.total_score.desc())
        .all()
    )
    leads = [lead for lead in leads if lead.passed_threshold]
    if not leads:
        raise HTTPException(
            status_code=404,
            detail="No qualified leads found to export for this workspace.",
        )

    source_links = (
        db.query(JobSourceModel)
        .filter(
            JobSourceModel.workspace_id == workspace_id,
            JobSourceModel.job_id.in_([lead.job_id for lead in leads]),
        )
        .all()
    )
    source_names = {}
    for source in source_links:
        source_names.setdefault(source.job_id, set()).add(source.source_name)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Lead ID",
            "Job Title",
            "Company",
            "Location",
            "Remote Policy",
            "Score",
            "Score Breakdown",
            "Source Names",
            "Job URL",
            "Verified At",
        ]
    )
    for lead in leads:
        writer.writerow(
            [
                lead.job_id,
                lead.title,
                lead.company_name,
                lead.location,
                lead.remote_policy or "",
                lead.total_score,
                lead.score_breakdown or {},
                ", ".join(sorted(source_names.get(lead.job_id, set()))),
                lead.canonical_url or "",
                lead.last_verified_at or lead.verified_at or "",
            ]
        )
    return output.getvalue(), len(leads)


@router.post("")
def create_export(
    payload: dict | None = None,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db),
):
    """Create a workspace-scoped CSV artifact and return its contents directly."""
    workspace_id = current_user["workspace_id"]
    csv_text, lead_count = _csv_content(db, workspace_id)
    user = db.query(UserModel).filter(
        UserModel.workspace_id == workspace_id,
        UserModel.email == current_user["email"],
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user was not found.")

    export_id = "exp_" + uuid.uuid4().hex
    file_name = f"qualified_leads_{export_id}.csv"
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    file_path = (_EXPORT_DIR / file_name).resolve()
    if file_path.parent != _EXPORT_DIR:
        raise HTTPException(status_code=500, detail="Export path could not be validated.")

    try:
        file_path.write_text(csv_text, encoding="utf-8", newline="")
        expires_at = datetime.now(timezone.utc) + _EXPORT_LIFETIME
        db.add(
            ExportModel(
                export_id=export_id,
                workspace_id=workspace_id,
                user_id=user.id,
                file_name=file_name,
                file_path=str(file_path),
                format="csv",
                expires_at=expires_at,
            )
        )
        db.add(
            AuditEventModel(
                workspace_id=workspace_id,
                user_id=user.id,
                action="export_created",
                resource_type="export",
                resource_id=export_id,
                details={"format": "csv", "lead_count": lead_count},
            )
        )
        db.commit()
    except OSError as exc:
        db.rollback()
        logger.exception("Could not write export artifact %s.", export_id)
        raise HTTPException(status_code=500, detail="Export file could not be created.") from exc
    except Exception:
        db.rollback()
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove incomplete export artifact %s.", export_id)
        raise

    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "X-Export-Id": export_id,
        },
    )


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db),
):
    """Download a non-expired CSV artifact owned by the authenticated workspace."""
    artifact = db.query(ExportModel).filter(
        ExportModel.export_id == export_id,
        ExportModel.workspace_id == current_user["workspace_id"],
    ).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Export artifact not found.")

    expires_at = artifact.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Export artifact has expired.")

    path = Path(artifact.file_path).resolve()
    if path.parent != _EXPORT_DIR or path.name != artifact.file_name:
        logger.error("Export %s has an invalid stored path.", export_id)
        raise HTTPException(status_code=500, detail="Export artifact path is invalid.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export file is no longer available.")
    return FileResponse(
        path,
        media_type="text/csv",
        filename=artifact.file_name,
    )
