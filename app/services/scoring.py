from datetime import datetime, timezone


_COMPONENT_MAXIMUMS = {
    "relevance": 25,
    "hiring_intent": 20,
    "freshness": 15,
    "remote_fit": 10,
    "salary_value": 10,
    "company_activity": 10,
    "seniority": 5,
    "data_quality": 5,
}


def _strings(values) -> set[str]:
    if isinstance(values, str):
        return {values.strip().casefold()} if values.strip() else set()
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {
        value.strip().casefold()
        for value in values
        if isinstance(value, str) and value.strip()
    }


def _as_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_score(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, min(maximum, int(round(value))))


def calculate_lead_score(
    normalized_lead: dict,
    target_criteria: dict,
    company_signals: dict = None,
) -> tuple[int, dict]:
    """Calculate the versioned eight-component 100-point lead score."""
    criteria = target_criteria if isinstance(target_criteria, dict) else {}
    signals = company_signals if isinstance(company_signals, dict) else {}
    breakdown = {component: 0 for component in _COMPONENT_MAXIMUMS}

    job_technologies = _strings(normalized_lead.get("technologies"))
    requested_technologies = _strings(
        criteria.get("tech_stack", criteria.get("technologies"))
    )
    requested_services = _strings(criteria.get("services"))
    if requested_technologies:
        breakdown["relevance"] = int(
            25 * len(job_technologies & requested_technologies) / len(requested_technologies)
        )
    elif requested_services:
        category = normalized_lead.get("category")
        if isinstance(category, str) and category.strip().casefold() in requested_services:
            breakdown["relevance"] = 25
    else:
        breakdown["relevance"] = 12

    breakdown["hiring_intent"] = _bounded_score(
        signals.get("intent_score"), _COMPONENT_MAXIMUMS["hiring_intent"]
    )

    posted_at = _as_datetime(normalized_lead.get("posted_at"))
    if posted_at is not None:
        age_days = max(0, (datetime.now(timezone.utc) - posted_at).total_seconds() / 86400)
        max_age_days = criteria.get("max_age_days", 14)
        if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 1:
            max_age_days = 14
        if age_days <= max_age_days:
            breakdown["freshness"] = 15
        elif age_days <= max_age_days * 2:
            breakdown["freshness"] = 8
        elif age_days <= max_age_days * 4:
            breakdown["freshness"] = 4

    remote_policy = normalized_lead.get("remote_policy")
    remote_policy = remote_policy.casefold().replace("-", " ") if isinstance(remote_policy, str) else ""
    requested_countries = _strings(criteria.get("countries"))
    allowed_countries = _strings(normalized_lead.get("allowed_countries"))
    geography = criteria.get("region", criteria.get("geography"))
    if isinstance(geography, str) and geography.strip():
        requested_countries.add(geography.strip().casefold())
    country_fit = (
        not requested_countries
        or bool({"global", "worldwide"} & allowed_countries)
        or bool(requested_countries & allowed_countries)
    )
    remote_only = criteria.get("remote_only", False)
    if remote_policy and country_fit:
        is_remote = "remote" in remote_policy or "distributed" in remote_policy
        is_fully_remote = is_remote and not any(
            term in remote_policy for term in ("hybrid", "on site", "onsite")
        )
        if is_fully_remote:
            breakdown["remote_fit"] = 10
        elif is_remote:
            breakdown["remote_fit"] = 5 if not remote_only else 0
        elif not remote_only:
            breakdown["remote_fit"] = 5

    salary = normalized_lead.get("salary")
    if isinstance(salary, dict):
        salary_min = salary.get("min")
        salary_max = salary.get("max")
        if any(isinstance(value, (int, float)) and value > 0 for value in (salary_min, salary_max)):
            breakdown["salary_value"] = 5
            target_min = criteria.get("salary_min")
            target_max = criteria.get("salary_max")
            if (
                isinstance(target_min, (int, float))
                and isinstance(target_max, (int, float))
                and isinstance(salary_min, (int, float))
                and isinstance(salary_max, (int, float))
                and salary_max >= target_min
                and salary_min <= target_max
            ):
                breakdown["salary_value"] = 10
            elif target_min is None and target_max is None:
                breakdown["salary_value"] = 10

    active_roles = signals.get("open_roles_count", 0)
    if isinstance(active_roles, int) and not isinstance(active_roles, bool):
        breakdown["company_activity"] = min(10, max(0, active_roles * 2))

    seniority = normalized_lead.get("seniority")
    seniority = seniority.casefold() if isinstance(seniority, str) else ""
    requested_seniority = _strings(criteria.get("seniority"))
    if seniority and requested_seniority:
        breakdown["seniority"] = 5 if seniority in requested_seniority else 2
    elif seniority:
        breakdown["seniority"] = 3

    confidence = normalized_lead.get("confidence")
    source_count = normalized_lead.get("sources_count", 0)
    completeness = sum(
        bool(normalized_lead.get(field))
        for field in ("title", "company_name", "location", "description")
    )
    breakdown["data_quality"] = (
        (2 if isinstance(confidence, (int, float)) and confidence >= 0.9 else 1 if isinstance(confidence, (int, float)) and confidence >= 0.7 else 0)
        + (2 if isinstance(source_count, int) and source_count > 0 else 0)
        + (1 if completeness == 4 else 0)
    )

    for component, maximum in _COMPONENT_MAXIMUMS.items():
        breakdown[component] = _bounded_score(breakdown[component], maximum)
    total_score = sum(breakdown.values())
    if total_score > 100:
        raise ValueError("Lead score exceeds the 100-point maximum.")
    breakdown["total_score"] = total_score
    breakdown["score_version"] = "pdf-v1"
    return total_score, breakdown
