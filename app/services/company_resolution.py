import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import CompanyModel, JobLeadModel


def resolve_and_associate_company(
    db: Session,
    workspace_id: str,
    job_id: str,
    normalized_company_name: str,
    domain: str = None,
) -> dict:
    clean_name = normalized_company_name.strip() if normalized_company_name else ""
    clean_domain = domain.strip().lower() if domain else None
    company = None

    if clean_domain:
        company = db.query(CompanyModel).filter(
            CompanyModel.workspace_id == workspace_id,
            func.lower(CompanyModel.domain) == clean_domain,
        ).first()

    if not company and clean_name and clean_name.casefold() != "unknown company":
        company = db.query(CompanyModel).filter(
            CompanyModel.workspace_id == workspace_id,
            func.lower(CompanyModel.normalized_name) == clean_name.lower(),
        ).first()

    if not company and clean_name and clean_name.casefold() != "unknown company":
        company = CompanyModel(
            id="comp_" + str(uuid.uuid4())[:8],
            workspace_id=workspace_id,
            normalized_name=clean_name,
            domain=clean_domain,
            resolution_status="resolved" if clean_domain else "unresolved",
        )
        db.add(company)
        db.flush()

    job_lead = db.query(JobLeadModel).filter(
        JobLeadModel.job_id == job_id,
        JobLeadModel.workspace_id == workspace_id,
    ).first()
    if job_lead and company:
        job_lead.company_id = company.id

    db.commit()

    if not company:
        return {
            "status": "unresolved",
            "company_id": None,
            "company_name": "Unknown Company",
            "domain": None,
            "message": "Company identity could not be resolved from the supplied data.",
        }

    return {
        "status": "success",
        "company_id": company.id,
        "company_name": company.normalized_name,
        "domain": company.domain,
        "message": "Company identity successfully resolved and linked to the job lead.",
    }
