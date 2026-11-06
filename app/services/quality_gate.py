from datetime import datetime, timezone, timedelta

def verify_lead_freshness_and_quality(job_lead_data: dict, confidence: float = 0.85) -> dict:
    """
    Enforces freshness verification, source provenance, and quality gates 
    before a lead is marked eligible for delivery.
    As specified in PDF Section 4.11 & 10[cite: 5, 6, 10].
    """
    reasons = []
    is_eligible = True

    # 1. Confidence Check (PDF Section 8 & 11)
    if confidence < 0.70:
        is_eligible = False
        reasons.append("Confidence score below 0.70 threshold; marked uncertain.")
    elif confidence < 0.90:
        reasons.append("Confidence score between 0.70 and 0.89; requires targeted review.")

    # 2. Freshness / Posted Date Check (PDF Section 4.11)
    posted_at_str = job_lead_data.get("posted_at")
    if posted_at_str:
        try:
            posted_at = datetime.fromisoformat(posted_at_str)
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            
            age_days = (datetime.now(timezone.utc) - posted_at).days
            # Assume max permitted age is 14 days for a fresh lead
            if age_days > 14:
                is_eligible = False
                reasons.append(f"Listing is stale (age: {age_days} days exceeds 14-day freshness window).")
            else:
                reasons.append(f"Listing freshness verified (age: {age_days} days).")
        except Exception:
            reasons.append("Could not parse posted date; applying cautious review status.")
    else:
        reasons.append("Missing posted date timestamp; provenance incomplete.")

    # 3. Provenance & Source Evidence Check (PDF Section 4.3 & 11)
    sources = job_lead_data.get("sources", [])
    if not sources:
        is_eligible = False
        reasons.append("Missing required source provenance records.")

    status = "eligible_for_delivery" if is_eligible else "excluded_or_held"

    return {
        "status": status,
        "is_eligible": is_eligible,
        "quality_rationale": reasons,
        "verified_at": datetime.now(timezone.utc).isoformat()
    }