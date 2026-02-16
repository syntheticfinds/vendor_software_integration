"""Fetch issues from Jira Cloud REST API using httpx."""

import base64
from datetime import datetime, timezone

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

MAX_ISSUES_PER_CYCLE = 50
DESCRIPTION_SNIPPET_MAX_CHARS = 500


def _build_auth_header() -> str:
    """Build Basic Auth header from global Jira credentials."""
    credentials = f"{settings.JIRA_USER_EMAIL}:{settings.JIRA_API_TOKEN}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def fetch_jira_issues(
    jql: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Fetch issues from Jira Cloud using JQL search.

    If *jql* is provided, uses that directly (with optional since filter).
    Otherwise builds a default JQL for recently-updated issues.

    Returns list of normalised issue dicts with keys:
        issue_key, project_key, summary, description_snippet,
        issue_type, status, priority, reporter,
        created_at, updated_at, web_url
    """
    base_url = f"{settings.JIRA_SITE_URL.rstrip('/')}/rest/api/3"
    headers = {
        "Authorization": _build_auth_header(),
        "Accept": "application/json",
    }

    # Build JQL
    if jql:
        effective_jql = jql
        if since:
            since_str = since.strftime("%Y-%m-%d %H:%M")
            effective_jql = f"({jql}) AND updated >= '{since_str}'"
    else:
        if since:
            since_str = since.strftime("%Y-%m-%d %H:%M")
            effective_jql = f"updated >= '{since_str}'"
        else:
            effective_jql = "updated >= -7d ORDER BY updated DESC"

    issues: list[dict] = []
    next_page_token: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while len(issues) < MAX_ISSUES_PER_CYCLE:
            body: dict = {
                "jql": effective_jql,
                "maxResults": 50,
                "fields": [
                    "summary", "description", "issuetype", "status",
                    "priority", "reporter", "project", "created", "updated",
                ],
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            resp = await client.post(
                f"{base_url}/search/jql",
                headers={**headers, "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            for raw_issue in data.get("issues", []):
                issues.append(_normalize_issue(raw_issue))
                if len(issues) >= MAX_ISSUES_PER_CYCLE:
                    break

            next_page_token = data.get("nextPageToken")
            if not next_page_token or data.get("isLast", True):
                break

    return issues


def _normalize_issue(raw: dict) -> dict:
    """Normalize a Jira issue resource to a standard dict."""
    fields = raw.get("fields", {})

    created_at = _parse_jira_datetime(fields.get("created"))
    updated_at = _parse_jira_datetime(fields.get("updated"))

    # Handle Atlassian Document Format (ADF) descriptions
    description = fields.get("description")
    description_snippet = None
    if description:
        if isinstance(description, dict):
            description_snippet = _extract_adf_text(description)[:DESCRIPTION_SNIPPET_MAX_CHARS]
        elif isinstance(description, str):
            description_snippet = description[:DESCRIPTION_SNIPPET_MAX_CHARS]

    site_url = settings.JIRA_SITE_URL.rstrip("/")
    issue_key = raw.get("key", "")
    web_url = f"{site_url}/browse/{issue_key}" if issue_key else None

    return {
        "issue_key": issue_key,
        "project_key": (fields.get("project") or {}).get("key", ""),
        "summary": fields.get("summary", ""),
        "description_snippet": description_snippet,
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "reporter": (fields.get("reporter") or {}).get("displayName", ""),
        "created_at": created_at,
        "updated_at": updated_at,
        "web_url": web_url,
    }


def _parse_jira_datetime(dt_str: str | None) -> datetime | None:
    """Parse a Jira datetime string (ISO 8601) to a timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _extract_adf_text(adf: dict) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    texts: list[str] = []
    if adf.get("type") == "text":
        texts.append(adf.get("text", ""))
    for child in adf.get("content", []):
        texts.append(_extract_adf_text(child))
    return " ".join(texts).strip()
