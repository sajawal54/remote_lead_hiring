def calculate_lead_score(normalized_lead: dict, target_criteria: dict) -> tuple[int, dict]:
    """
    100-point deterministic scoring engine.
    Job lead ko target criteria ke against evaluate karta hai aur score breakdown return karta hai.
    """
    breakdown = {
        "tech_stack_match": 0,    # Max 30 points
        "remote_policy_fit": 0,   # Max 20 points
        "salary_presence": 0,     # Max 20 points
        "location_fit": 0,        # Max 15 points
        "data_completeness": 0    # Max 15 points
    }

    # 1. Tech Stack Match (Max 30 pts)
    job_techs = set(normalized_lead.get("technologies", []))
    target_techs = set([t.lower() for t in target_criteria.get("tech_stack", [])])
    
    if target_techs:
        matched_techs = job_techs.intersection(target_techs)
        match_ratio = len(matched_techs) / len(target_techs)
        breakdown["tech_stack_match"] = int(30 * match_ratio)
    else:
        breakdown["tech_stack_match"] = 15  # if no target crieteria then give default score

    # 2. Remote Policy Fit (Max 20 pts)
    remote_policy = normalized_lead.get("remote_policy", "").lower()
    if "100%" in remote_policy or "fully remote" in remote_policy or remote_policy == "remote":
        breakdown["remote_policy_fit"] = 20
    elif "hybrid" in remote_policy:
        breakdown["remote_policy_fit"] = 10
    else:
        breakdown["remote_policy_fit"] = 5

    # 3. Salary Presence (Max 20 pts)
    salary = normalized_lead.get("salary", {})
    if salary and salary.get("max", 0) > 0:
        breakdown["salary_presence"] = 20
    else:
        breakdown["salary_presence"] = 5

    # 4. Location / Allowed Countries Fit (Max 15 pts)
    allowed_countries = [c.lower() for c in normalized_lead.get("allowed_countries", [])]
    target_region = target_criteria.get("region", "").lower()
    
    if "global" in allowed_countries or "worldwide" in allowed_countries or target_region in allowed_countries:
        breakdown["location_fit"] = 15
    else:
        breakdown["location_fit"] = 8

    # 5. Data Completeness (Max 15 pts)
    completeness_score = 15
    if not normalized_lead.get("company_name") or normalized_lead.get("company_name") == "Unknown Company":
        completeness_score -= 5
    if not normalized_lead.get("title"):
        completeness_score -= 5
    breakdown["data_completeness"] = max(0, completeness_score)

    # Total Score Calculation (Out of 100)
    total_score = sum(breakdown.values())

    return total_score, breakdown