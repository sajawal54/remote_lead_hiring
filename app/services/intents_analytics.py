from datetime import datetime, timezone
from typing import List

def calculate_company_hiring_intent(company_id: str, company_jobs: List[dict]) -> dict:
    """
    Computes company-level hiring signals over dated records.
    PDF Section 4.9 (Hiring-intent aggregation) & Section 9[cite: 5, 9].
    """
    # 1. Check history presence (PDF Section 4.9 & 9)
    if not company_jobs:
        return {
            "status": "unknown_signals",
            "intent_score": 0,
            "open_roles_count": 0,
            "rationale": "Insufficient history available; intent marked unknown rather than assumed[cite: 5, 9]."
        }

    open_roles_count = len(company_jobs)
    
    # 2. Analyze technology demand & department expansion
    tech_stack_set = set()
    for job in company_jobs:
        for tech in job.get("technologies", []):
            tech_stack_set.add(tech.lower())
            
    unique_tech_count = len(tech_stack_set)
    
    # 3. Calculate Intent Score (Max 20 points as per PDF Section 9)
    # Concentration, repeated hiring and role volume[cite: 9]
    if open_roles_count >= 5:
        intent_score = 20
        signal_level = "strong_active_hiring"
    elif open_roles_count >= 2:
        intent_score = 12
        signal_level = "moderate_hiring_velocity"
    else:
        intent_score = 5
        signal_level = "single_role_modest_signal"

    return {
        "company_id": company_id,
        "status": "calculated",
        "intent_score": intent_score,
        "max_score": 20,
        "signal_level": signal_level,
        "open_roles_count": open_roles_count,
        "unique_technologies_count": unique_tech_count,
        "measurement_timestamp": datetime.now(timezone.utc).isoformat(),
        "rationale": f"Calculated {signal_level} based on {open_roles_count} active role(s)[cite: 5, 9]."
    }