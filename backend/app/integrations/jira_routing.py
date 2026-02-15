"""Intelligent routing of Jira webhook events to the correct software.

Implements 2-tier routing:
  Tier 1: Deterministic matching via name/project-key scoring
  Tier 2: CrewAI LLM-based classification
  No match: event is dropped (better to drop than surface spam)
"""

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.models import JiraWebhook
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

ROUTING_CONFIDENCE_THRESHOLD = 0.6


async def route_jira_event(
    db: AsyncSession,
    webhooks: list[JiraWebhook],
    parsed: dict,
) -> list[JiraWebhook]:
    """Route a parsed Jira event to the appropriate webhook(s).

    Always runs (even for single webhooks) because users may configure
    broad Jira filters that send unrelated events.

    Returns a filtered list of JiraWebhook objects to create signals for.
    Returns an empty list when the event doesn't match any software (drop it).
    """
    company_id = webhooks[0].company_id

    # Build lookup: software_id -> webhook
    webhook_by_sw: dict[uuid.UUID, JiraWebhook] = {
        wh.software_id: wh for wh in webhooks
    }
    software_ids = list(webhook_by_sw.keys())

    # Load candidate software registrations
    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id.in_(software_ids),
            SoftwareRegistration.status == "active",
        )
    )
    candidates = list(result.scalars().all())

    if not candidates:
        logger.warning("jira_routing_no_candidates", company_id=str(company_id))
        return []

    # --- Tier 1: Deterministic matching ---
    matched_sw = _deterministic_match(parsed, candidates)
    if matched_sw is not None:
        wh = webhook_by_sw.get(matched_sw.id)
        if wh:
            logger.info(
                "jira_routing_tier1_match",
                software_id=str(matched_sw.id),
                software_name=matched_sw.software_name,
            )
            return [wh]

    # --- Tier 2: CrewAI classification ---
    try:
        matched_webhooks = await _crew_route(parsed, candidates, webhook_by_sw)
        if matched_webhooks:
            return matched_webhooks
    except Exception as e:
        logger.error("jira_routing_tier2_error", error=str(e))

    # --- No match: drop the event ---
    logger.info(
        "jira_routing_no_match",
        company_id=str(company_id),
        issue_key=parsed.get("source_id"),
        project_key=parsed.get("project_key"),
    )
    return []


def _deterministic_match(
    parsed: dict,
    candidates: list[SoftwareRegistration],
) -> SoftwareRegistration | None:
    """Tier 1: Score-based deterministic matching.

    Adapted from _infer_software() in app/demo/router.py but operating
    on a pre-filtered candidate list.
    """
    project_key = parsed.get("project_key", "")
    text = " ".join(filter(None, [parsed.get("title", ""), parsed.get("body", "")]))
    text_lower = text.lower()
    issue_key = parsed.get("source_id", "")

    best: SoftwareRegistration | None = None
    best_score = 0

    for sw in candidates:
        score = 0

        # Name match in event text
        if (
            sw.software_name.lower() in text_lower
            or sw.vendor_name.lower() in text_lower
        ):
            score = len(sw.software_name)

        # Jira workspace / project key matching
        # Skip the "enabled" flag — only real project keys
        if sw.jira_workspace and sw.jira_workspace.lower() != "enabled":
            if project_key and sw.jira_workspace.upper() == project_key.upper():
                score += 1000
            elif issue_key and issue_key.upper().startswith(
                sw.jira_workspace.upper() + "-"
            ):
                score += 1000

        # Support email domain in event text
        if sw.support_email:
            try:
                domain = sw.support_email.split("@")[1].lower()
                if domain in text_lower:
                    score += 500
            except (IndexError, AttributeError):
                pass

        if score > best_score:
            best = sw
            best_score = score

    if best and best_score > 0:
        return best

    return None


async def _crew_route(
    parsed: dict,
    candidates: list[SoftwareRegistration],
    webhook_by_sw: dict[uuid.UUID, JiraWebhook],
) -> list[JiraWebhook] | None:
    """Tier 2: LLM-based routing via CrewAI.

    Runs the synchronous crew in a thread executor with a hard timeout.
    Returns matched webhooks, or None to signal no-match.
    """
    from app.agents.jira_router.crew import JiraRoutingCrew

    # Build event summary
    event_summary = (
        f"Issue Key: {parsed.get('source_id', 'N/A')}\n"
        f"Project Key: {parsed.get('project_key', 'N/A')}\n"
        f"Event Type: {parsed.get('event_type', 'N/A')}\n"
        f"Title: {parsed.get('title', 'N/A')}\n"
        f"Body: {(parsed.get('body') or 'N/A')[:1500]}\n"
        f"Reporter: {parsed.get('reporter', 'N/A')}\n"
        f"Severity: {parsed.get('severity', 'N/A')}\n"
    )
    metadata = parsed.get("event_metadata", {})
    if metadata:
        event_summary += f"Issue Type: {metadata.get('issue_type', 'N/A')}\n"
        event_summary += f"Status: {metadata.get('status', 'N/A')}\n"
        event_summary += f"Priority: {metadata.get('priority', 'N/A')}\n"

    # Build candidate list for the LLM
    candidates_data = [
        {
            "software_id": str(sw.id),
            "software_name": sw.software_name,
            "vendor_name": sw.vendor_name,
            "intended_use": sw.intended_use or "Not specified",
            "jira_workspace": (
                sw.jira_workspace
                if sw.jira_workspace and sw.jira_workspace.lower() != "enabled"
                else "Not configured"
            ),
            "support_email": sw.support_email or "Not configured",
        }
        for sw in candidates
    ]

    crew = JiraRoutingCrew(event_summary, candidates_data)

    # Run synchronous crew in thread executor with timeout
    loop = asyncio.get_event_loop()
    try:
        crew_result = await asyncio.wait_for(
            loop.run_in_executor(None, crew.run),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("jira_routing_crew_timeout")
        return None

    matched_ids = crew_result.get("matched_software_ids", [])
    confidence = crew_result.get("confidence", 0.0)

    if confidence < ROUTING_CONFIDENCE_THRESHOLD:
        logger.info(
            "jira_routing_crew_low_confidence",
            confidence=confidence,
            reasoning=crew_result.get("reasoning", ""),
        )
        return None

    # Map back to webhooks
    matched_webhooks = []
    for sid_str in matched_ids:
        try:
            sid = uuid.UUID(sid_str)
            if sid in webhook_by_sw:
                matched_webhooks.append(webhook_by_sw[sid])
        except ValueError:
            continue

    if not matched_webhooks:
        logger.info("jira_routing_crew_no_valid_match", raw_ids=matched_ids)
        return None

    logger.info(
        "jira_routing_tier2_match",
        matched_count=len(matched_webhooks),
        confidence=confidence,
        reasoning=crew_result.get("reasoning", ""),
    )
    return matched_webhooks
