from datetime import datetime, timedelta, timezone


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


def calculate_company_hiring_intent(
    company_id: str,
    company_jobs: list[dict],
    measurement_window_days: int = 90,
) -> dict:
    """Estimate hiring activity from dated active jobs; unknown history stays unknown."""
    if measurement_window_days < 1:
        raise ValueError("measurement_window_days must be positive.")

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=measurement_window_days)
    recent_start = now - timedelta(days=min(30, measurement_window_days))
    dated_jobs = []
    for job in company_jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("status", "active")).casefold() not in {"active", "open", "published"}:
            continue
        posted_at = _parse_datetime(job.get("posted_at"))
        if posted_at and window_start <= posted_at <= now:
            dated_jobs.append((job, posted_at))

    if not dated_jobs:
        return {
            "company_id": company_id,
            "status": "unknown_signals",
            "intent_score": 0,
            "open_roles_count": 0,
            "measurement_window_days": measurement_window_days,
            "measurement_timestamp": now.isoformat(),
            "rationale": "No dated active-job history in the measurement window; hiring intent is unknown.",
        }

    open_roles_count = len(dated_jobs)
    recent_count = sum(posted_at >= recent_start for _, posted_at in dated_jobs)
    previous_count = open_roles_count - recent_count
    tech_stack = {
        technology.strip().casefold()
        for job, _ in dated_jobs
        for technology in (job.get("technologies") or [])
        if isinstance(technology, str) and technology.strip()
    }

    if open_roles_count >= 10:
        intent_score, signal_level = 15, "strong_active_hiring"
    elif open_roles_count >= 5:
        intent_score, signal_level = 12, "strong_active_hiring"
    elif open_roles_count >= 2:
        intent_score, signal_level = 8, "moderate_hiring_velocity"
    else:
        intent_score, signal_level = 5, "single_role_modest_signal"

    if recent_count >= 3 and recent_count > previous_count:
        intent_score = min(20, intent_score + 5)
        signal_level = "accelerating_hiring"

    return {
        "company_id": company_id,
        "status": "calculated",
        "intent_score": intent_score,
        "max_score": 20,
        "signal_level": signal_level,
        "open_roles_count": open_roles_count,
        "recent_roles_count": recent_count,
        "previous_period_roles_count": previous_count,
        "unique_technologies_count": len(tech_stack),
        "measurement_window_days": measurement_window_days,
        "measurement_timestamp": now.isoformat(),
        "rationale": (
            f"Based on {open_roles_count} dated active role(s) in {measurement_window_days} days; "
            "this is a hiring signal, not proof of purchase intent."
        ),
    }
