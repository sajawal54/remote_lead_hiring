import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "local-test-secret-not-for-production")

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.api import api_router
from app.core.database import Base, get_db
from app.models.models import (
    AuditEventModel,
    JobLeadModel,
    RawSourceRecordModel,
    WorkflowExecutionModel,
)
from app.services import background_worker
from app.services.orchestrator import initialize_workflow_execution
import app.api.v1.endpoints.exports as exports_endpoint
from app.services.quality_gate import verify_lead_freshness_and_quality


class ProjectApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
        )
        self.export_directory = tempfile.TemporaryDirectory()
        self.original_export_directory = exports_endpoint._EXPORT_DIR
        exports_endpoint._EXPORT_DIR = Path(self.export_directory.name).resolve()

    async def asyncTearDown(self):
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        exports_endpoint._EXPORT_DIR = self.original_export_directory
        self.export_directory.cleanup()
        self.engine.dispose()

    async def signup(self, email, workspace_name):
        response = await self.client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "test-password-123",
                "workspace_name": workspace_name,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        return result["workspace_id"], result["access_token"]

    def test_quality_gate_excludes_job_that_misses_requested_criteria(self):
        result = verify_lead_freshness_and_quality(
            {
                "title": "Office Engineer",
                "status": "active",
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "confidence": 0.99,
                "sources_count": 1,
                "remote_policy": "on-site",
                "allowed_countries": ["United States"],
                "target_criteria": {
                    "remote_only": True,
                    "countries": ["Pakistan"],
                },
            },
            confidence=0.99,
            max_age_days=14,
        )

        self.assertEqual(result["status"], "excluded")
        self.assertFalse(result["is_eligible"])

    async def test_failed_ai_extraction_creates_reviewable_lead(self):
        workspace_id, _ = await self.signup("review@example.com", "Review Team")
        db = self.session_factory()
        try:
            db.add(
                RawSourceRecordModel(
                    record_id="raw_extraction_failure",
                    workspace_id=workspace_id,
                    source_name="csv_upload",
                    source_url="test.csv",
                    fetched_at=datetime.now(timezone.utc),
                    raw_payload={
                        "title": "Python Engineer",
                        "company": "Example Inc",
                        "location": "Remote",
                        "description": "Build Python services.",
                        "url": "https://example.com/jobs/failure",
                        "posted_at": datetime.now(timezone.utc).isoformat(),
                        "status": "active",
                    },
                )
            )
            db.commit()
            workflow = initialize_workflow_execution(
                db,
                workspace_id,
                {"source_names": ["csv_upload"], "max_age_days": 14},
            )

            with (
                patch.object(
                    background_worker,
                    "extract_job_details_with_gemini",
                    return_value={
                        "status": "failed",
                        "message": "Test extraction failure.",
                    },
                ),
                patch.object(background_worker.time, "sleep"),
                patch.object(
                    background_worker,
                    "generate_lead_embedding",
                    return_value={
                        "status": "degraded",
                        "embedding_metadata": {"status": "unavailable"},
                        "message": "Embeddings disabled for test.",
                    },
                ),
            ):
                background_worker.process_raw_records_pipeline(
                    db,
                    workflow["workflow_id"],
                    workspace_id,
                )

            execution = db.query(WorkflowExecutionModel).filter_by(
                id=workflow["workflow_id"],
                workspace_id=workspace_id,
            ).one()
            lead = db.query(JobLeadModel).filter_by(
                workspace_id=workspace_id,
                title="Python Engineer",
            ).one()
            self.assertEqual(execution.status, "review_required")
            self.assertEqual(lead.status, "review_required")
            self.assertIn("Test extraction failure.", lead.review_notes)
            self.assertEqual(
                lead.extraction["quality_gate"]["status"],
                "review_required",
            )
        finally:
            db.close()

    async def test_review_endpoint_approves_and_rejects_pending_leads(self):
        workspace_id, token = await self.signup("reviewer@example.com", "Reviewers")
        db = self.session_factory()
        try:
            db.add_all(
                [
                    JobLeadModel(
                        job_id="job_approve",
                        workspace_id=workspace_id,
                        company_name="Approve Co",
                        title="Approve Engineer",
                        location="Remote",
                        status="review_required",
                        extraction={
                            "quality_gate": {
                                "status": "review_required",
                                "is_eligible": False,
                            }
                        },
                    ),
                    JobLeadModel(
                        job_id="job_reject",
                        workspace_id=workspace_id,
                        company_name="Reject Co",
                        title="Reject Engineer",
                        location="Remote",
                        status="review_required",
                        extraction={
                            "quality_gate": {
                                "status": "review_required",
                                "is_eligible": False,
                            }
                        },
                    ),
                    JobLeadModel(
                        job_id="job_excluded",
                        workspace_id=workspace_id,
                        company_name="Excluded Co",
                        title="Excluded Engineer",
                        location="On-site",
                        status="review_required",
                        extraction={
                            "quality_gate": {
                                "status": "excluded",
                                "is_eligible": False,
                            }
                        },
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        headers = {"Authorization": f"Bearer {token}"}
        approved = await self.client.patch(
            "/api/v1/leads/job_approve/review",
            headers=headers,
            json={"action": "approve", "notes": "Checked listing details."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["review_status"], "active")

        rejected = await self.client.patch(
            "/api/v1/leads/job_reject/review",
            headers=headers,
            json={"action": "reject"},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["review_status"], "excluded")

        excluded_approval = await self.client.patch(
            "/api/v1/leads/job_excluded/review",
            headers=headers,
            json={"action": "approve"},
        )
        self.assertEqual(excluded_approval.status_code, 409)

        db = self.session_factory()
        try:
            events = db.query(AuditEventModel).filter(
                AuditEventModel.workspace_id == workspace_id,
                AuditEventModel.resource_type == "job_lead",
            ).all()
            self.assertEqual(
                {event.action for event in events},
                {"lead.review.approved", "lead.review.rejected"},
            )
        finally:
            db.close()

    async def test_signup_signin_and_authentication(self):
        workspace_id, token = await self.signup("member@example.com", "Example")

        signin = await self.client.post(
            "/api/v1/auth/signin",
            json={"email": "member@example.com", "password": "test-password-123"},
        )
        self.assertEqual(signin.status_code, 200, signin.text)
        self.assertEqual(signin.json()["workspace_id"], workspace_id)

        unauthenticated = await self.client.get("/api/v1/leads")
        self.assertEqual(unauthenticated.status_code, 401)

        leads = await self.client.get(
            "/api/v1/leads",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(leads.status_code, 200, leads.text)
        self.assertEqual(leads.json()["total_leads"], 0)

        invalid_signin = await self.client.post(
            "/api/v1/auth/signin",
            json={"email": "member@example.com", "password": "wrong-password"},
        )
        self.assertEqual(invalid_signin.status_code, 401)

    async def test_csv_workflow_leads_and_export(self):
        workspace_id, token = await self.signup("owner@example.com", "Hiring Team")
        headers = {"Authorization": f"Bearer {token}"}
        posted_at = datetime.now(timezone.utc).isoformat()
        csv_content = (
            "title,company,location,description,url,posted_at,status,remote_policy,"
            "allowed_countries,technologies,salary_min,salary_max\n"
            f"Senior Python Engineer,Example Inc,Remote - Pakistan,"
            f"Build Python APIs,https://example.com/jobs/1,{posted_at},active,"
            "fully remote,Pakistan,Python,100000,150000\n"
        )

        upload = await self.client.post(
            "/api/v1/ingest/csv",
            headers=headers,
            files={"file": ("jobs.csv", csv_content, "text/csv")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["imported_records"], 1)

        def run_worker_in_test_database(workflow_id, workspace_id):
            db = self.session_factory()
            try:
                background_worker.process_raw_records_pipeline(
                    db,
                    workflow_id,
                    workspace_id,
                )
            finally:
                db.close()

        extraction_result = {
            "status": "success",
            "extraction": {
                "skills": ["Python"],
                "category": "Software Development",
                "seniority": "Senior",
                "remote_type": "fully remote",
                "allowed_countries": ["Pakistan"],
                "confidence": 0.99,
            },
            "model_version": "test",
            "prompt_version": "test",
        }
        embedding_result = {
            "status": "success",
            "vector": [1.0, 0.0],
            "embedding_metadata": {
                "model_id": "test-embedding",
                "content_hash": "test-hash",
            },
            "message": "Test embedding generated.",
        }
        with (
            patch(
                "app.api.v1.endpoints.workflows.process_workflow_job",
                side_effect=run_worker_in_test_database,
            ),
            patch.object(
                background_worker,
                "extract_job_details_with_gemini",
                return_value=extraction_result,
            ),
            patch.object(
                background_worker,
                "generate_lead_embedding",
                return_value=embedding_result,
            ),
        ):
            workflow_response = await self.client.post(
                "/api/v1/workflows",
                headers=headers,
                json={
                    "tech_stack": ["Python"],
                    "region": "Pakistan",
                    "countries": ["Pakistan"],
                    "remote_only": True,
                    "min_score": 30,
                    "max_age_days": 14,
                    "source_names": ["csv_upload"],
                },
            )

        self.assertEqual(workflow_response.status_code, 200, workflow_response.text)
        workflow_id = workflow_response.json()["workflow_id"]

        status_response = await self.client.get(
            f"/api/v1/workflows/{workflow_id}",
            headers=headers,
        )
        self.assertEqual(status_response.status_code, 200, status_response.text)
        self.assertEqual(status_response.json()["status"], "succeeded")
        self.assertTrue(status_response.json()["steps"])

        lead_list = await self.client.get(
            "/api/v1/leads?min_score=30&region=Pakistan",
            headers=headers,
        )
        self.assertEqual(lead_list.status_code, 200, lead_list.text)
        self.assertEqual(lead_list.json()["total_leads"], 1)
        lead = lead_list.json()["leads"][0]
        self.assertEqual(lead["company_name"], "Example Inc")
        self.assertGreaterEqual(lead["score"], 30)
        self.assertEqual(lead["sources"][0]["source_name"], "csv_upload")

        detail = await self.client.get(
            f"/api/v1/leads/{lead['id']}",
            headers=headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(
            detail.json()["lead"]["quality_gate"]["status"],
            "eligible_for_delivery",
        )

        export_response = await self.client.post(
            "/api/v1/exports",
            headers=headers,
        )
        self.assertEqual(export_response.status_code, 200, export_response.text)
        self.assertIn("Senior Python Engineer", export_response.text)
        export_id = export_response.headers["X-Export-Id"]

        download = await self.client.get(
            f"/api/v1/exports/{export_id}/download",
            headers=headers,
        )
        self.assertEqual(download.status_code, 200, download.text)
        self.assertIn("Example Inc", download.text)

        other_workspace_id, other_token = await self.signup(
            "other@example.com",
            "Other Team",
        )
        self.assertNotEqual(workspace_id, other_workspace_id)
        other_headers = {"Authorization": f"Bearer {other_token}"}
        other_leads = await self.client.get("/api/v1/leads", headers=other_headers)
        self.assertEqual(other_leads.status_code, 200, other_leads.text)
        self.assertEqual(other_leads.json()["total_leads"], 0)

        hidden_lead = await self.client.get(
            f"/api/v1/leads/{lead['id']}",
            headers=other_headers,
        )
        self.assertEqual(hidden_lead.status_code, 404)

        foreign_export = await self.client.get(
            f"/api/v1/exports/{export_id}/download",
            headers=other_headers,
        )
        self.assertEqual(foreign_export.status_code, 404)

        db = self.session_factory()
        try:
            execution = db.query(WorkflowExecutionModel).filter_by(
                id=workflow_id,
                workspace_id=workspace_id,
            ).one()
            self.assertEqual(execution.status, "succeeded")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
