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
    job_technologies = normalized_lead.get("technologies", [])
    job_techs = {
        tech.strip().casefold()
        for tech in job_technologies
        if isinstance(tech, str) and tech.strip()
    } if isinstance(job_technologies, list) else set()
    requested_techs = target_criteria.get("tech_stack", target_criteria.get("technologies", []))
    target_techs = {
        tech.strip().casefold()
        for tech in requested_techs
        if isinstance(tech, str) and tech.strip()
    } if isinstance(requested_techs, list) else set()
    
    if target_techs:
        matched_techs = job_techs.intersection(target_techs)
        match_ratio = len(matched_techs) / len(target_techs)
        breakdown["tech_stack_match"] = int(30 * match_ratio)
    else:
        breakdown["tech_stack_match"] = 15  # if no target crieteria then give default score

    # 2. Remote Policy Fit (Max 20 pts)
    remote_value = normalized_lead.get("remote_policy")
    remote_policy = remote_value.casefold() if isinstance(remote_value, str) else ""
    if "100%" in remote_policy or "fully remote" in remote_policy or remote_policy == "remote":
        breakdown["remote_policy_fit"] = 20
    elif "hybrid" in remote_policy:
        breakdown["remote_policy_fit"] = 10
    else:
        breakdown["remote_policy_fit"] = 5

    # 3. Salary Presence (Max 20 pts)
    salary = normalized_lead.get("salary")
    if not isinstance(salary, dict):
        salary = {}
    salary_max = salary.get("max", 0)
    if isinstance(salary_max, (int, float)) and salary_max > 0:
        breakdown["salary_presence"] = 20
    else:
        breakdown["salary_presence"] = 5

    # 4. Location / Allowed Countries Fit (Max 15 pts)
    country_values = normalized_lead.get("allowed_countries", [])
    allowed_countries = [
        country.casefold()
        for country in country_values
        if isinstance(country, str)
    ] if isinstance(country_values, list) else []
    region_value = target_criteria.get("region", target_criteria.get("geography", ""))
    target_region = region_value.casefold() if isinstance(region_value, str) else ""
    
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