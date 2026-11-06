import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import JobLeadModel, JobSourceModel, RawSourceRecordModel, WorkflowExecutionModel
from app.services.ai_extraction import extract_job_details_with_gemini
from app.services.company_resolution import resolve_and_associate_company
from app.services.deduplication import deduplicate_and_merge_lead
from app.services.scoring import calculate_lead_score

logger = logging.getLogger(__name__)


def _parse_posted_at(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def process_raw_records_pipeline(db: Session, workflow_id: str, workspace_id: str):
    """
    Extracts and scores raw records for one workspace and records their source links.
    """
    execution = None
    try:
        execution = db.query(WorkflowExecutionModel).filter(
            WorkflowExecutionModel.id == workflow_id,
            WorkflowExecutionModel.workspace_id == workspace_id,
        ).first()

        if not execution:
            logger.warning("Workflow %s was not found for its workspace.", workflow_id)
            return

        execution.status = "running"
        execution.stage = "ai_extraction_and_scoring"
        execution.started_at = datetime.now(timezone.utc)
        db.commit()

        criteria = execution.criteria or {}
        raw_records = db.query(RawSourceRecordModel).filter(
            RawSourceRecordModel.workspace_id == workspace_id
        ).all()

        for raw_record in raw_records:
            linked_source = db.query(JobSourceModel).filter(
                JobSourceModel.workspace_id == workspace_id,
                JobSourceModel.record_id == raw_record.record_id,
            ).first()
            if linked_source:
                continue

            payload = raw_record.raw_payload
            if not isinstance(payload, dict):
                raise ValueError(f"Raw record {raw_record.record_id} is not a JSON object.")

            raw_description = payload.get("description") or payload.get("position") or ""
            if not isinstance(raw_description, str):
                raise ValueError(f"Raw record {raw_record.record_id} has an invalid description.")
            extraction_result = extract_job_details_with_gemini(raw_description)
            if extraction_result.get("status") != "success":
                raise RuntimeError(f"AI extraction failed for raw record {raw_record.record_id}.")

            extracted_data = extraction_result.get("extraction")
            if not isinstance(extracted_data, dict):
                raise ValueError(f"AI extraction returned invalid data for raw record {raw_record.record_id}.")

            job_title = payload.get("position") or payload.get("title") or "Remote Opportunity"
            if not isinstance(job_title, str):
                job_title = "Remote Opportunity"
            company_name = payload.get("company") or payload.get("company_name") or "Unknown Company"
            if not isinstance(company_name, str):
                company_name = "Unknown Company"
            location = payload.get("location") or "Unknown"
            if not isinstance(location, str):
                location = "Unknown"
            canonical_url = payload.get("url") or payload.get("canonical_url")
            if not isinstance(canonical_url, str):
                canonical_url = None
            posted_at = _parse_posted_at(payload.get("date") or payload.get("posted_at"))

            normalized_lead = {
                "company_name": company_name,
                "title": job_title,
                "location": location,
                "remote_policy": extracted_data.get("remote_type"),
                "allowed_countries": extracted_data.get("allowed_countries", []),
                "technologies": extracted_data.get("skills", []),
                "salary": payload.get("salary"),
            }
            total_score, score_breakdown = calculate_lead_score(normalized_lead, criteria)
            target_criteria = dict(criteria)
            min_score = target_criteria.get("min_score", 0)
            if not isinstance(min_score, (int, float)):
                raise ValueError("min_score must be a number.")
            target_criteria["min_score"] = min_score

            lead_data = {
                **normalized_lead,
                "workspace_id": workspace_id,
                "canonical_url": canonical_url,
                "description": raw_description[:500],
                "category": extracted_data.get("category"),
                "seniority": extracted_data.get("seniority"),
                "score_breakdown": score_breakdown,
                "total_score": total_score,
                "sources_count": 0,
                "confidence": extracted_data.get("confidence"),
                "extraction": {
                    **extraction_result,
                    "data": extracted_data,
                },
                "posted_at": posted_at,
                "last_verified_at": datetime.now(timezone.utc),
                "verified_at": datetime.now(timezone.utc),
                "target_criteria": target_criteria,
                "score_version": "prototype-v1",
            }

            lead_result = deduplicate_and_merge_lead(workspace_id, lead_data, db)
            lead_id = lead_result["job_id"]

            domain = payload.get("company_domain") or payload.get("domain")
            if not isinstance(domain, str):
                domain = None
            resolve_and_associate_company(
                db,
                workspace_id=workspace_id,
                job_id=lead_id,
                normalized_company_name=company_name,
                domain=domain,
            )

            source = JobSourceModel(
                workspace_id=workspace_id,
                job_id=lead_id,
                record_id=raw_record.record_id,
                source_name=raw_record.source_name,
                source_url=raw_record.source_url,
                first_seen_at=raw_record.fetched_at,
            )
            db.add(source)
            lead = db.query(JobLeadModel).filter(
                JobLeadModel.job_id == lead_id,
                JobLeadModel.workspace_id == workspace_id,
            ).first()
            if lead:
                lead.sources_count = (lead.sources_count or 0) + 1
            db.commit()

        execution.status = "succeeded"
        execution.stage = "completed"
        execution.finished_at = datetime.now(timezone.utc)
        db.commit()

    except Exception:
        db.rollback()
        logger.exception("Workflow %s failed while processing workspace %s.", workflow_id, workspace_id)
        execution = db.query(WorkflowExecutionModel).filter(
            WorkflowExecutionModel.id == workflow_id,
            WorkflowExecutionModel.workspace_id == workspace_id,
        ).first()
        if execution:
            execution.status = "failed"
            execution.stage = "failed"
            execution.last_error_code = "pipeline_processing_failed"
            execution.finished_at = datetime.now(timezone.utc)
            db.commit()
