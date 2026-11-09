import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import (
    AuditEventModel,
    JobLeadModel,
    JobSourceModel,
    LeadEmbeddingModel,
    RawSourceRecordModel,
    WorkflowExecutionModel,
    WorkflowStepModel,
)
from app.services.ai_extraction import extract_job_details_with_gemini
from app.services.company_resolution import resolve_and_associate_company
from app.services.deduplication import deduplicate_and_merge_lead
from app.services.embedding_service import generate_lead_embedding
from app.services.ingestion import verify_source_eligibility
from app.services.ingestion_connector import fetch_and_store_remote_jobs
from app.services.intents_analytics import calculate_company_hiring_intent
from app.services.normalization import normalize_job_payload
from app.services.quality_gate import verify_lead_freshness_and_quality
from app.services.scoring import calculate_lead_score

logger = logging.getLogger(__name__)


def _record_step(
    db: Session,
    workspace_id: str,
    workflow_id: str,
    stage: str,
    status: str,
    reason: str = None,
    attempt: int = 1,
) -> None:
    db.add(
        WorkflowStepModel(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            stage=stage,
            status=status,
            attempt=attempt,
            decision_reason=reason,
        )
    )
    db.commit()


def process_workflow_job(workflow_id: str, workspace_id: str) -> None:
    """Run a queued workflow with a worker-owned database session."""
    db = SessionLocal()
    try:
        process_raw_records_pipeline(db, workflow_id, workspace_id)
    finally:
        db.close()


def process_raw_records_pipeline(db: Session, workflow_id: str, workspace_id: str):
    """Process workspace raw records through extraction, scoring, and quality decisions."""
    counts = {"processed": 0, "eligible": 0, "review_required": 0, "failed": 0}
    try:
        execution = db.query(WorkflowExecutionModel).filter(
            WorkflowExecutionModel.id == workflow_id,
            WorkflowExecutionModel.workspace_id == workspace_id,
        ).first()
        if not execution:
            logger.warning("Workflow %s was not found for its workspace.", workflow_id)
            return

        criteria = execution.criteria or {}
        selected_sources = criteria.get("source_names") or []
        if not isinstance(selected_sources, list):
            raise ValueError("source_names must be a list.")
        selected_sources = list(dict.fromkeys(
            source.strip().casefold()
            for source in selected_sources
            if isinstance(source, str) and source.strip()
        ))

        execution.status = "running"
        execution.stage = "source_eligibility"
        execution.started_at = datetime.now(timezone.utc)
        execution.last_error_code = None
        db.commit()

        for source_name in selected_sources:
            eligibility = verify_source_eligibility(source_name)
            _record_step(
                db, workspace_id, workflow_id, "source_eligibility",
                "succeeded" if eligibility["eligible"] else "blocked",
                eligibility["reason"],
            )
            if not eligibility["eligible"]:
                raise ValueError(f"Source '{source_name}' is not eligible.")

        if not selected_sources:
            _record_step(
                db, workspace_id, workflow_id, "source_eligibility",
                "succeeded", "Processing previously ingested workspace records.",
            )

        source_errors = []
        if "remoteok_live_api" in selected_sources:
            execution.stage = "ingestion"
            db.commit()
            ingestion_result = fetch_and_store_remote_jobs(db, workspace_id)
            ingestion_ok = ingestion_result.get("status") == "success"
            _record_step(
                db,
                workspace_id,
                workflow_id,
                "ingestion",
                "succeeded" if ingestion_ok else "failed",
                ingestion_result.get("message"),
            )
            if not ingestion_ok:
                source_errors.append(ingestion_result.get("message", "RemoteOK ingestion failed."))

        execution.stage = "ingestion_and_normalization"
        db.commit()
        raw_query = db.query(RawSourceRecordModel).filter(
            RawSourceRecordModel.workspace_id == workspace_id
        )
        if selected_sources:
            raw_query = raw_query.filter(RawSourceRecordModel.source_name.in_(selected_sources))
        raw_records = raw_query.order_by(RawSourceRecordModel.fetched_at.asc()).all()

        linked_records = {
            record_id
            for (record_id,) in db.query(JobSourceModel.record_id).filter(
                JobSourceModel.workspace_id == workspace_id
            ).all()
        }

        for raw_record in raw_records:
            if raw_record.record_id in linked_records:
                continue

            try:
                normalized = normalize_job_payload(raw_record.raw_payload, raw_record.source_name)
            except (TypeError, ValueError) as exc:
                counts["failed"] += 1
                _record_step(
                    db, workspace_id, workflow_id, "normalization",
                    "quarantined", str(exc),
                )
                continue

            _record_step(
                db, workspace_id, workflow_id, "normalization",
                "succeeded", f"Normalized raw record {raw_record.record_id}.",
            )

            extraction = {"status": "unavailable", "extraction": {}}
            if normalized["description"]:
                execution.stage = "ai_extraction"
                db.commit()
                extraction = None
                extraction_failure_reason = None
                for attempt in range(1, 3):
                    result = extract_job_details_with_gemini(normalized["description"])
                    if (
                        result.get("status") == "success"
                        and isinstance(result.get("extraction"), dict)
                    ):
                        extraction = result
                        _record_step(
                            db, workspace_id, workflow_id, "ai_extraction",
                            "succeeded", f"Extracted raw record {raw_record.record_id}.", attempt,
                        )
                        break
                    if attempt == 2:
                        reason = result.get("message") or result.get("error") or "Extraction failed."
                        extraction = result
                        extraction_failure_reason = reason
                        _record_step(
                            db, workspace_id, workflow_id, "ai_extraction",
                            "review_required", reason, attempt,
                        )
                    else:
                        _record_step(
                            db, workspace_id, workflow_id, "ai_extraction",
                            "retrying", "Retrying a failed extraction.", attempt,
                        )
                        time.sleep(0.25)
            else:
                extraction_failure_reason = "Description is missing; AI extraction was skipped."
                _record_step(
                    db, workspace_id, workflow_id, "ai_extraction",
                    "review_required", extraction_failure_reason,
                )

            if extraction is None:
                raise RuntimeError(
                    f"AI extraction produced no result for raw record {raw_record.record_id}."
                )

            extracted_data = extraction.get("extraction") or {}
            technologies = list(dict.fromkeys(
                normalized["technologies"] + [
                    value for value in extracted_data.get("skills", [])
                    if isinstance(value, str) and value.strip()
                ]
            ))
            normalized["technologies"] = technologies
            if extracted_data.get("remote_type"):
                normalized["remote_policy"] = extracted_data["remote_type"]
            if extracted_data.get("allowed_countries"):
                normalized["allowed_countries"] = extracted_data["allowed_countries"]
            normalized["category"] = extracted_data.get("category")
            normalized["seniority"] = extracted_data.get("seniority")
            normalized["confidence"] = extracted_data.get("confidence")
            normalized["sources_count"] = 1

            embedding_text = " ".join(
                part for part in (
                    normalized["title"],
                    normalized["company_name"],
                    normalized["location"],
                    normalized["description"],
                ) if part
            )
            embedding_result = generate_lead_embedding(embedding_text)
            embedding_vector = embedding_result.get("vector")
            normalized["_embedding_vector"] = embedding_vector
            _record_step(
                db, workspace_id, workflow_id, "embeddings",
                embedding_result.get("status", "degraded"),
                embedding_result.get("message"),
            )

            execution.stage = "deduplication_and_resolution"
            db.commit()
            lead_data = {
                **normalized,
                "workspace_id": workspace_id,
                "score_breakdown": {},
                "total_score": 0,
                "target_criteria": criteria,
                "score_version": "pdf-v1",
                "extraction": {
                    **extraction,
                    "data": extracted_data,
                    "embedding": embedding_result.get("embedding_metadata"),
                },
                "last_verified_at": datetime.now(timezone.utc),
                "verified_at": datetime.now(timezone.utc),
                "sources_count": 0,
            }
            lead_result = deduplicate_and_merge_lead(workspace_id, lead_data, db)
            lead_id = lead_result["job_id"]
            _record_step(
                db, workspace_id, workflow_id, "deduplication",
                "review_required" if lead_result["status"] == "review_required" else lead_result["status"],
                lead_result.get("message"),
            )

            company_result = resolve_and_associate_company(
                db,
                workspace_id=workspace_id,
                job_id=lead_id,
                normalized_company_name=normalized["company_name"],
                domain=normalized["company_domain"],
            )
            _record_step(
                db, workspace_id, workflow_id, "company_resolution",
                company_result["status"], company_result.get("message"),
            )

            db.add(
                JobSourceModel(
                    workspace_id=workspace_id,
                    job_id=lead_id,
                    record_id=raw_record.record_id,
                    source_name=raw_record.source_name,
                    source_url=raw_record.source_url or normalized["source_url"],
                    first_seen_at=raw_record.fetched_at,
                )
            )
            lead = db.query(JobLeadModel).filter(
                JobLeadModel.job_id == lead_id,
                JobLeadModel.workspace_id == workspace_id,
            ).first()
            if not lead:
                raise RuntimeError(f"Lead {lead_id} disappeared during processing.")
            lead.sources_count = (lead.sources_count or 0) + 1
            db.commit()

            if embedding_vector:
                stored_embedding = db.query(LeadEmbeddingModel).filter(
                    LeadEmbeddingModel.job_id == lead_id
                ).first()
                if stored_embedding:
                    stored_embedding.vector = embedding_vector
                    stored_embedding.model = embedding_result["embedding_metadata"]["model_id"]
                    stored_embedding.content_hash = embedding_result["embedding_metadata"]["content_hash"]
                    stored_embedding.updated_at = datetime.now(timezone.utc)
                else:
                    db.add(
                        LeadEmbeddingModel(
                            job_id=lead_id,
                            workspace_id=workspace_id,
                            model=embedding_result["embedding_metadata"]["model_id"],
                            vector=embedding_vector,
                            content_hash=embedding_result["embedding_metadata"]["content_hash"],
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                db.commit()

            company_jobs = []
            if lead.company_id:
                related_jobs = db.query(JobLeadModel).filter(
                    JobLeadModel.workspace_id == workspace_id,
                    JobLeadModel.company_id == lead.company_id,
                ).all()
                company_jobs = [
                    {
                        "status": item.status,
                        "posted_at": item.posted_at,
                        "technologies": item.technologies or [],
                    }
                    for item in related_jobs
                ]
            company_signals = calculate_company_hiring_intent(
                lead.company_id or "unknown",
                company_jobs,
            )
            score_inputs = {
                **normalized,
                "sources_count": lead.sources_count,
            }
            total_score, score_breakdown = calculate_lead_score(
                score_inputs,
                criteria,
                company_signals,
            )

            source_links = db.query(JobSourceModel).filter(
                JobSourceModel.workspace_id == workspace_id,
                JobSourceModel.job_id == lead_id,
            ).all()
            quality_result = verify_lead_freshness_and_quality(
                {
                    **normalized,
                    "status": lead.status,
                    "sources_count": len(source_links),
                    "target_criteria": criteria,
                },
                confidence=normalized.get("confidence"),
                max_age_days=criteria.get("max_age_days", 14),
            )
            if extraction_failure_reason and quality_result["status"] != "excluded":
                quality_result["status"] = "review_required"
                quality_result["is_eligible"] = False
                quality_result["quality_rationale"].append(extraction_failure_reason)
            if lead_result["status"] == "review_required":
                quality_result["is_eligible"] = False
                quality_result["status"] = "review_required"
                quality_result["quality_rationale"].append(
                    lead_result.get("message", "Semantic duplicate requires review.")
                )

            lead.total_score = total_score
            lead.score_breakdown = score_breakdown
            lead.target_criteria = criteria
            lead.score_version = "pdf-v1"
            lead.last_verified_at = datetime.now(timezone.utc)
            lead.extraction = {
                **(lead.extraction or {}),
                "company_signals": company_signals,
                "quality_gate": quality_result,
            }
            if quality_result["is_eligible"]:
                lead.status = "active"
                lead.review_notes = None
                counts["eligible"] += 1
            elif quality_result["status"] == "excluded":
                if lead.status not in {"closed", "stale"}:
                    lead.status = "stale"
                lead.review_notes = "; ".join(quality_result["quality_rationale"])
                counts["review_required"] += 1
            else:
                lead.status = "review_required"
                lead.review_notes = "; ".join(quality_result["quality_rationale"])
                counts["review_required"] += 1

            _record_step(
                db, workspace_id, workflow_id, "hiring_intent_and_scoring",
                "succeeded",
                f"Score {total_score}/100; intent {company_signals['status']}.",
            )
            _record_step(
                db, workspace_id, workflow_id, "quality_gate_verification",
                "succeeded" if quality_result["is_eligible"] else quality_result["status"],
                "; ".join(quality_result["quality_rationale"]),
            )
            db.commit()
            counts["processed"] += 1

        execution = db.query(WorkflowExecutionModel).filter(
            WorkflowExecutionModel.id == workflow_id,
            WorkflowExecutionModel.workspace_id == workspace_id,
        ).first()
        if source_errors:
            counts["failed"] += len(source_errors)
            for error in source_errors:
                _record_step(
                    db, workspace_id, workflow_id, "ingestion",
                    "failed", error,
                )

        if counts["failed"] and counts["processed"]:
            execution.status = "partial"
        elif counts["failed"]:
            execution.status = "failed"
        elif counts["review_required"]:
            execution.status = "review_required"
        else:
            execution.status = "succeeded"
        execution.stage = "completed"
        execution.finished_at = datetime.now(timezone.utc)
        db.add(
            AuditEventModel(
                workspace_id=workspace_id,
                action="workflow.completed",
                resource_type="workflow",
                resource_id=workflow_id,
                details={**counts, "status": execution.status},
            )
        )
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
            db.add(
                AuditEventModel(
                    workspace_id=workspace_id,
                    action="workflow.failed",
                    resource_type="workflow",
                    resource_id=workflow_id,
                    details={"status": "failed", "counts": counts},
                )
            )
            db.commit()
