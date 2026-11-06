from sqlalchemy.orm import Session

from app.models.models import JobLeadModel


_MERGEABLE_FIELDS = (
    "location",
    "remote_policy",
    "allowed_countries",
    "technologies",
    "salary",
    "score_breakdown",
    "total_score",
    "description",
    "category",
    "seniority",
    "status",
    "confidence",
    "extraction",
    "posted_at",
    "verified_at",
    "target_criteria",
    "score_version",
)


def deduplicate_and_merge_lead(workspace_id: str, normalized_data: dict, db: Session) -> dict:
    canonical_url = normalized_data.get("canonical_url")
    company_name = normalized_data.get("company_name")
    title = normalized_data.get("title")

    existing_lead = None
    if canonical_url:
        existing_lead = db.query(JobLeadModel).filter(
            JobLeadModel.workspace_id == workspace_id,
            JobLeadModel.canonical_url == canonical_url,
        ).first()
    elif company_name and company_name.casefold() != "unknown company" and title:
        existing_lead = db.query(JobLeadModel).filter(
            JobLeadModel.workspace_id == workspace_id,
            JobLeadModel.company_name == company_name,
            JobLeadModel.title == title,
        ).first()

# ///

    if existing_lead:
        for field in _MERGEABLE_FIELDS:
            value = normalized_data.get(field)
            if value is not None:
                setattr(existing_lead, field, value)
        db.commit()
        db.refresh(existing_lead)
        return {
            "status": "merged",
            "job_id": existing_lead.job_id,
            "message": "Duplicate detected. Updated the existing canonical lead.",
        }

    lead_fields = {
        "workspace_id": workspace_id,
        "company_name": company_name or "Unknown Company",
        "title": title or "Unknown title",
        "location": normalized_data.get("location") or "Unknown",
    }
    for field in (
        "remote_policy",
        "allowed_countries",
        "technologies",
        "salary",
        "score_breakdown",
        "total_score",
        "sources_count",
        "company_id",
        "canonical_url",
        "description",
        "category",
        "seniority",
        "status",
        "confidence",
        "extraction",
        "posted_at",
        "verified_at",
        "target_criteria",
        "score_version",
    ):
        if field in normalized_data:
            lead_fields[field] = normalized_data[field]

    db_lead = JobLeadModel(**lead_fields)
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return {
        "status": "created",
        "job_id": db_lead.job_id,
        "message": "No duplicate found. Created a new canonical lead.",
    }
