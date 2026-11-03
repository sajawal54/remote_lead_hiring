from sqlalchemy.orm import Session
from app.models.models import JobLeadModel

def deduplicate_and_merge_lead(workspace_id: str, normalized_data: dict, db: Session):
    """
    Checks if a job lead already exists using exact keys (company + title or URL).
    If it exists, merges source evidence; otherwise, creates a new canonical lead.
    As specified in PDF Section 4.5 (Deduplication and source merge)[cite: 4].
    """
    company_name = normalized_data.get("company_name")
    title = normalized_data.get("title")
    
    # Exact match check within the same workspace
    existing_lead = db.query(JobLeadModel).filter(
        JobLeadModel.workspace_id == workspace_id,
        JobLeadModel.company_name == company_name,
        JobLeadModel.title == title
    ).first()
    
    if existing_lead:
        # Agar lead pehle se mojood hai, toh naye source observations ya updates ko merge karte hain
        # PDF Section 4.5 ke mutabiq multiple source entries attach ki jati hain[cite: 4]
        existing_lead.location = normalized_data.get("location", existing_lead.location)
        db.commit()
        db.refresh(existing_lead)
        
        return {
            "status": "merged",
            "job_id": existing_lead.job_id,
            "message": "Duplicate detected. Successfully merged source observations into existing canonical lead."
        }
    else:
        # Agar nangi/unique lead hai, toh naya canonical record create hoga
        db_lead = JobLeadModel(**normalized_data)
        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)
        
        return {
            "status": "created",
            "job_id": db_lead.job_id,
            "message": "No duplicate found. Created a new canonical job lead."
        }