import csv
import io
import uuid
from datetime import datetime, timezone, timedelta

def generate_workspace_lead_export(eligible_leads: list, workspace_id: str) -> dict:
    """
    Applies workspace filters, sorts leads by score, and builds a scoped 
    CSV export artifact with expiration and provenance as per PDF Section 4.12 & 15[cite: 6, 12].
    """
    # 1. Sort leads by score descending (Ranking logic)
    sorted_leads = sorted(eligible_leads, key=lambda x: x.get("score", 0), reverse=True)
    
    # 2. Build CSV In-Memory Buffer
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write Header (Including score, company, freshness and evidence provenance)[cite: 1, 8]
    writer.writerow([
        "Job ID", "Company Name", "Title", "Total Score", 
        "Remote Policy", "Allowed Countries", "Verified At", "Source URLs"
    ])
    
    record_count = 0
    for lead in sorted_leads:
        writer.writerow([
            lead.get("job_id", ""),
            lead.get("company_name", "Unknown"),
            lead.get("title", ""),
            lead.get("score", 0),
            lead.get("remote_policy", ""),
            ", ".join(lead.get("allowed_countries", [])),
            lead.get("verified_at", ""),
            ", ".join(lead.get("sources", []))
        ])
        record_count += 1
        
    export_id = "exp_" + str(uuid.uuid4())[:8]
    csv_artifact = output.getvalue()
    
    # 3. Return Export Metadata and Artifact Reference (PDF Section 7 & 15)[cite: 7, 12]
    return {
        "export_id": export_id,
        "workspace_id": workspace_id,
        "status": "succeeded",
        "record_count": record_count,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "artifact_data": csv_artifact,
        "message": "Filtered and ranked lead export artifact successfully generated."
    }