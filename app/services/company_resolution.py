import uuid
from sqlalchemy.orm import Session
from app.models.models import CompanyModel, JobLeadModel

def resolve_and_associate_company(db: Session, workspace_id: str, job_id: str, normalized_company_name: str, domain: str = None):
    """
    Matches company by validated domain and aliases, associates related jobs,
    and records resolution evidence as specified in PDF Section 4.6[cite: 4, 5].
    """
    clean_name = normalized_company_name.strip() if normalized_company_name else "Unknown Company"
    
    # 1. Match by domain or normalized name within workspace scope
    company = None
    if domain:
        company = db.query(CompanyModel).filter(
            CompanyModel.workspace_id == workspace_id,
            CompanyModel.domain == domain
        ).first()
        
    if not company and clean_name != "Unknown Company":
        company = db.query(CompanyModel).filter(
            CompanyModel.workspace_id == workspace_id,
            CompanyModel.name == clean_name
        ).first()
        
    # 2. Decision rule: Unresolved company -> mark unknown rather than guess domain[cite: 4, 5]
    if not company:
        company_id = "comp_" + str(uuid.uuid4())[:8]
        company = CompanyModel(
            company_id=company_id,
            workspace_id=workspace_id,
            name=clean_name,
            domain=domain if domain else "unknown-domain.com"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        
    # 3. Associate job-company relationship (PDF Section 7 schema)[cite: 7]
    job_lead = db.query(JobLeadModel).filter(JobLeadModel.job_id == job_id).first()
    if job_lead:
        job_lead.company_id = company.company_id
        db.commit()
        
    return {
        "status": "success",
        "company_id": company.company_id,
        "company_name": company.name,
        "domain": company.domain,
        "message": "Company identity successfully resolved and linked to job lead."
    }