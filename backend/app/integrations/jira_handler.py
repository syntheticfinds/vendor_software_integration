"""Parse Jira Cloud webhook payloads and match to registered software."""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Jira event → our event_type mapping
# ---------------------------------------------------------------------------

_JIRA_EVENT_MAP: dict[str, tuple[str, str]] = {
    # webhookEvent → (event_type, default_severity)
    "jira:issue_created": ("ticket_created", "medium"),
    "jira:issue_updated": ("ticket_updated", "low"),
    "jira:issue_deleted": ("ticket_updated", "low"),
    "comment_created": ("comment_added", "low"),
    "comment_updated": ("comment_added", "low"),
}

# Jira priority name → our severity
_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "highest": "critical",
    "blocker": "critical",
    "critical": "critical",
    "high": "high",
    "major": "high",
    "medium": "medium",
    "low": "low",
    "lowest": "low",
    "minor": "low",
    "trivial": "low",
}


def parse_jira_webhook(payload: dict) -> dict | None:
    """Parse a Jira Cloud webhook payload into a normalised signal dict.

    Returns None if the event type is not one we track.
    """
    webhook_event = payload.get("webhookEvent", "")
    issue = payload.get("issue") or {}
    fields = issue.get("fields") or {}

    mapped = _JIRA_EVENT_MAP.get(webhook_event)
    if mapped is None:
        return None

    event_type, default_severity = mapped

    # Detect resolution: status changed to Done/Resolved/Closed
    changelog = payload.get("changelog") or {}
    if webhook_event == "jira:issue_updated" and changelog:
        for item in changelog.get("items", []):
            if item.get("field") == "status":
                to_status = (item.get("toString") or "").lower()
                if to_status in ("done", "resolved", "closed", "complete"):
                    event_type = "ticket_resolved"
                    default_severity = "medium"
                    break

    # Map Jira priority to our severity
    priority_name = (fields.get("priority") or {}).get("name", "")
    severity = _PRIORITY_TO_SEVERITY.get(priority_name.lower(), default_severity)

    # Extract fields
    issue_key = issue.get("key", "")
    project_key = (fields.get("project") or {}).get("key", "")
    summary = fields.get("summary", "")
    description = fields.get("description") or ""
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    status_name = (fields.get("status") or {}).get("name", "")

    # Build title
    title = f"[{issue_key}] {summary}" if issue_key else summary

    # Build body
    body_parts: list[str] = []
    if description:
        body_parts.append(description[:2000])

    comment = payload.get("comment") or {}
    if comment:
        comment_body = comment.get("body", "")
        comment_author = (comment.get("author") or {}).get("displayName", "unknown")
        if comment_body:
            body_parts.append(f"Comment by {comment_author}: {comment_body[:1000]}")

    if changelog and event_type == "ticket_updated":
        changes = []
        for item in changelog.get("items", []):
            field_name = item.get("field", "")
            from_val = item.get("fromString", "")
            to_val = item.get("toString", "")
            changes.append(f"{field_name}: {from_val} -> {to_val}")
        if changes:
            body_parts.append("Changes: " + "; ".join(changes[:5]))

    body = "\n\n".join(body_parts) if body_parts else None

    # Reporter
    user = payload.get("user") or {}
    reporter = user.get("displayName") or user.get("emailAddress") or "unknown"

    return {
        "event_type": event_type,
        "severity": severity,
        "title": title,
        "body": body,
        "source_id": issue_key,
        "project_key": project_key,
        "reporter": reporter,
        "occurred_at": datetime.now(timezone.utc),
        "event_metadata": {
            "reporter": reporter,
            "issue_key": issue_key,
            "issue_type": issue_type,
            "status": status_name,
            "priority": priority_name,
            "project_key": project_key,
            "webhook_event": webhook_event,
        },
    }


async def match_jira_to_software(
    db: AsyncSession,
    company_id: uuid.UUID,
    project_key: str,
    text: str,
) -> SoftwareRegistration | None:
    """Match a Jira project key to a registered software.

    1. Direct match on SoftwareRegistration.jira_workspace (case-insensitive).
    2. Fallback: infer from text content via _infer_software.
    """
    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.company_id == company_id,
            SoftwareRegistration.status == "active",
        )
    )
    all_sw = result.scalars().all()

    # Direct match
    for sw in all_sw:
        if sw.jira_workspace and sw.jira_workspace.upper() == project_key.upper():
            return sw

    # Fallback: text-based inference
    from app.demo.router import _infer_software

    return await _infer_software(
        db, company_id, text,
        source_type="jira", source_id=project_key,
    )
