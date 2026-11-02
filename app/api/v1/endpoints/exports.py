import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import JobLeadModel

router = APIRouter()

@router.get("/csv")
def export_leads_to_csv(db: Session = Depends(get_db)):
    """
    Database se saari leads fetch karta hai (score ke hisaab se sorted) 
    aur ek download-able CSV file generate karta hai.
    """
    try:
        # High score wali leads pehle aayengi
        leads = db.query(JobLeadModel).order_by(JobLeadModel.total_score.desc()).all()
        
        if not leads:
            raise HTTPException(status_code=404, detail="Export ke liye koi job leads mojood nahi hain.")

        # In-memory text buffer banate hain CSV data ke liye
        output = io.StringIO()
        writer = csv.writer(output)

        # CSV Header row
        writer.writerow(["Job ID", "Company", "Title", "Remote Policy", "Total Score", "Technologies"])

        # Data rows write karna
        for lead in leads:
            techs = ", ".join(lead.technologies) if lead.technologies else ""
            writer.writerow([
                lead.job_id,
                lead.company_name,
                lead.title,
                lead.remote_policy,
                lead.total_score,
                techs
            ])

        output.seek(0)
        
        # StreamingResponse ke zariye file download karana
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=remote_job_leads_export.csv"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")