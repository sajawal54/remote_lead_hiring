from datetime import datetime, timedelta, timezone


_CLOSED_STATUSES = {"closed", "expired", "filled", "removed", "inactive"}
_ACTIVE_STATUSES = {"active", "open", "published"}


def _parse_datetime(value):
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


def verify_lead_freshness_and_quality(
    job_lead_data: dict,
    confidence: float = None,
    max_age_days: int = 14,
) -> dict:
    """Return a delivery decision based on source evidence, status, freshness, and confidence."""
    reasons = []
    now = datetime.now(timezone.utc)
    quality_status = "eligible_for_delivery"

    def hold(reason: str):
        nonlocal quality_status
        if quality_status == "eligible_for_delivery":
            quality_status = "review_required"
        reasons.append(reason)

    def exclude(reason: str):
        nonlocal quality_status
        quality_status = "excluded"
        reasons.append(reason)

    if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 1:
        raise ValueError("max_age_days must be a positive integer.")

    status = str(job_lead_data.get("status") or "unverified").strip().casefold()
    if status in _CLOSED_STATUSES:
        exclude(f"Listing status is '{status}'.")
    elif status not in _ACTIVE_STATUSES:
        hold("Listing status is not confirmed active.")

    if confidence is None:
        confidence = job_lead_data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        hold("Extraction confidence is unavailable.")
    elif not 0 <= confidence <= 1:
        hold("Extraction confidence is outside the valid 0.0-1.0 range.")
    elif confidence < 0.70:
        hold("Extraction confidence is below 0.70; human review is required.")
    elif confidence < 0.90:
        hold("Extraction confidence is below 0.90; targeted review is required.")

    posted_at = _parse_datetime(job_lead_data.get("posted_at"))
    if posted_at is None:
        hold("Posting date is missing or invalid; freshness cannot be verified.")
    else:
        age = now - posted_at
        if age < timedelta(days=-1):
            hold("Posting date is in the future.")
        elif age > timedelta(days=max_age_days):
            exclude(f"Listing is older than the {max_age_days}-day freshness window.")
        else:
            reasons.append(f"Posting date is within the {max_age_days}-day freshness window.")

    sources = job_lead_data.get("sources")
    source_count = job_lead_data.get("sources_count", 0)
    if not sources and (not isinstance(source_count, int) or source_count < 1):
        hold("Source provenance is missing.")

    if not job_lead_data.get("title"):
        hold("Job title is missing.")

    criteria = job_lead_data.get("target_criteria") or {}
    if criteria.get("remote_only"):
        remote_policy = job_lead_data.get("remote_policy")
        remote_policy = remote_policy.casefold() if isinstance(remote_policy, str) else ""
        if not remote_policy:
            hold("Remote eligibility is unknown.")
        elif not any(term in remote_policy for term in ("remote", "distributed")):
            exclude("The job does not meet the remote-only requirement.")

    requested_countries = criteria.get("countries") or []
    if isinstance(requested_countries, str):
        requested_countries = [requested_countries]
    if isinstance(criteria.get("region"), str) and criteria["region"].strip():
        requested_countries = list(requested_countries) + [criteria["region"]]
    allowed_countries = job_lead_data.get("allowed_countries") or []
    if requested_countries:
        normalized_requested = {
            value.strip().casefold()
            for value in requested_countries
            if isinstance(value, str) and value.strip()
        }
        normalized_allowed = {
            value.strip().casefold()
            for value in allowed_countries
            if isinstance(value, str) and value.strip()
        }
        if not normalized_allowed:
            hold("Allowed work countries are unknown.")
        elif not (
            normalized_requested & normalized_allowed
            or {"global", "worldwide"} & normalized_allowed
        ):
            exclude("The permitted work countries do not match the requested geography.")

    return {
        "status": quality_status,
        "is_eligible": quality_status == "eligible_for_delivery",
        "quality_rationale": reasons,
        "verified_at": now.isoformat(),
    }
