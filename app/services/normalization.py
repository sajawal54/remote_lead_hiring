import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


def _clean_text(value, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    return " ".join(value.split())


def _parse_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.]", "", value.replace(",", ""))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def parse_posted_at(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_url(value):
    raw_url = _clean_text(value)
    if not raw_url:
        return None
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        hostname = parsed.hostname.casefold()
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
        query = urlencode(
            [
                (key, val)
                for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                if key.casefold() not in _TRACKING_QUERY_KEYS
                and not key.casefold().startswith("utm_")
            ]
        )
        return urlunsplit((parsed.scheme.casefold(), hostname, parsed.path.rstrip("/"), query, ""))
    except ValueError:
        return None


def normalize_job_payload(payload: dict, source_name: str) -> dict:
    """Map common CSV, API-feed, and RemoteOK fields into one canonical job shape."""
    if not isinstance(payload, dict):
        raise ValueError("Job payload must be a JSON object.")

    title = _clean_text(payload.get("title") or payload.get("position"), "Unknown title")
    company = _clean_text(
        payload.get("company_name") or payload.get("company"),
        "Unknown Company",
    )
    location = _clean_text(payload.get("location"), "Unknown")
    description = _clean_text(payload.get("description"))
    source_url = _clean_text(
        payload.get("source_url") or payload.get("url") or payload.get("canonical_url")
    ) or None

    salary = payload.get("salary")
    if not isinstance(salary, dict):
        salary = {}
    salary_min = _parse_number(
        salary.get("min", payload.get("salary_min", payload.get("min_salary")))
    )
    salary_max = _parse_number(
        salary.get("max", payload.get("salary_max", payload.get("max_salary")))
    )
    normalized_salary = None
    if salary_min is not None or salary_max is not None:
        normalized_salary = {
            "min": salary_min,
            "max": salary_max,
            "currency": _clean_text(
                salary.get("currency") or payload.get("salary_currency"), "USD"
            ).upper(),
            "period": _clean_text(
                salary.get("period") or payload.get("salary_period"), "unknown"
            ).casefold(),
        }

    raw_status = _clean_text(payload.get("status")).casefold()
    if raw_status in {"closed", "expired", "filled", "removed", "inactive"}:
        status = "closed"
    elif raw_status in {"active", "open", "published"}:
        status = "active"
    elif source_name == "remoteok_live_api":
        status = "active"
    else:
        status = "unverified"

    raw_tags = payload.get("tags", payload.get("technologies", []))
    technologies = [
        _clean_text(tag)
        for tag in raw_tags
        if isinstance(tag, str) and _clean_text(tag)
    ] if isinstance(raw_tags, list) else []
    raw_countries = payload.get("allowed_countries", [])
    allowed_countries = [
        _clean_text(country)
        for country in raw_countries
        if isinstance(country, str) and _clean_text(country)
    ] if isinstance(raw_countries, list) else []

    return {
        "title": title,
        "company_name": company,
        "company_domain": _clean_text(payload.get("company_domain") or payload.get("domain")) or None,
        "location": location,
        "description": description,
        "source_url": source_url,
        "canonical_url": normalize_url(
            payload.get("canonical_url") or payload.get("url") or payload.get("source_url")
        ),
        "posted_at": parse_posted_at(
            payload.get("posted_at") or payload.get("date") or payload.get("date_posted")
        ),
        "remote_policy": _clean_text(payload.get("remote_policy") or payload.get("remote_type")) or None,
        "allowed_countries": allowed_countries,
        "technologies": technologies,
        "salary": normalized_salary,
        "status": status,
    }
