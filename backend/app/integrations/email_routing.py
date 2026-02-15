"""Intelligent routing of emails to the correct software when multiple
registrations share the same support email address.

Implements multi-tier routing:
  Tier 0: Thread continuity -- if a previous email in the same thread
          was already routed to Software X, follow it.
  Tier 1: Deterministic matching via software name / vendor name / intended_use
          keyword scoring against subject + body.
  Tier 2: CrewAI LLM-based classification.
  No match: return None (caller skips signal creation; email flows to
            integration detection as usual).
"""

import asyncio
import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.models import MonitoredEmail
from app.signals.models import SignalEvent
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

ROUTING_CONFIDENCE_THRESHOLD = 0.6

_REPLY_PREFIX = re.compile(r"^(Re:\s*|Fwd:\s*|FW:\s*|RE:\s*)+", re.IGNORECASE)
_STOPWORDS = {"the", "and", "for", "with", "this", "that", "from", "are", "was", "our", "has", "not"}


def _normalize_subject(subject: str | None) -> str:
    """Strip reply/forward prefixes so thread messages match."""
    if not subject:
        return ""
    return _REPLY_PREFIX.sub("", subject).strip()


async def route_email_to_software(
    db: AsyncSession,
    email: MonitoredEmail,
    raw: dict | None,
    candidates: list[SoftwareRegistration],
) -> SoftwareRegistration | None:
    """Route an email to one software when multiple candidates share the same support email.

    Returns the matched SoftwareRegistration, or None if no confident match.
    """
    if len(candidates) == 1:
        return candidates[0]

    candidate_names = [sw.software_name for sw in candidates]

    # --- Tier 0: Thread continuity ---
    matched = await _thread_continuity_match(db, email, candidates)
    if matched:
        logger.info(
            "email_routing_tier0_match",
            software_name=matched.software_name,
            email_subject=email.subject,
        )
        return matched

    # --- Tier 1: Deterministic scoring ---
    matched = _deterministic_match(email, candidates)
    if matched:
        logger.info(
            "email_routing_tier1_match",
            software_name=matched.software_name,
            email_subject=email.subject,
        )
        return matched

    # --- Tier 2: CrewAI classification ---
    try:
        matched = await _crew_route(email, candidates)
        if matched:
            return matched
    except Exception as e:
        logger.error("email_routing_tier2_error", error=str(e))

    # --- No match ---
    logger.info(
        "email_routing_no_match",
        email_subject=email.subject,
        candidates=candidate_names,
    )
    return None


async def _thread_continuity_match(
    db: AsyncSession,
    email: MonitoredEmail,
    candidates: list[SoftwareRegistration],
) -> SoftwareRegistration | None:
    """Tier 0: Check if a previous email in the same thread was already routed.

    Uses subject normalization to find existing signals with the same
    base subject for any of the candidate software.
    """
    normalized = _normalize_subject(email.subject)
    if not normalized:
        return None

    candidate_ids = [sw.id for sw in candidates]
    candidate_by_id = {sw.id: sw for sw in candidates}

    # Find recent email signals for any candidate software
    result = await db.execute(
        select(SignalEvent).where(
            SignalEvent.company_id == email.company_id,
            SignalEvent.source_type == "email",
            SignalEvent.software_id.in_(candidate_ids),
        ).order_by(SignalEvent.occurred_at.desc()).limit(50)
    )
    recent_signals = result.scalars().all()

    normalized_lower = normalized.lower()
    for signal in recent_signals:
        signal_normalized = _normalize_subject(signal.title).lower()
        if signal_normalized and signal_normalized == normalized_lower:
            sw = candidate_by_id.get(signal.software_id)
            if sw:
                return sw

    return None


def _deterministic_match(
    email: MonitoredEmail,
    candidates: list[SoftwareRegistration],
) -> SoftwareRegistration | None:
    """Tier 1: Score-based deterministic matching against email content.

    Returns the best candidate if its score exceeds 0 and it wins by a margin
    of >= 2x over the runner-up. Otherwise returns None (ambiguous).
    """
    text = f"{email.subject or ''} {email.body_snippet or ''}"
    text_lower = text.lower()
    subject_lower = (email.subject or "").lower()

    scores: list[tuple[SoftwareRegistration, int]] = []

    for sw in candidates:
        score = 0
        sw_name_lower = sw.software_name.lower()
        vendor_lower = sw.vendor_name.lower()

        # Software name in combined text
        if sw_name_lower in text_lower:
            score += len(sw.software_name)
            # Bonus: software name in subject (short, high-signal text)
            if sw_name_lower in subject_lower:
                score += 500

        # Vendor name in combined text (only if distinct from software name)
        if vendor_lower != sw_name_lower and vendor_lower in text_lower:
            score += len(sw.vendor_name)

        # Intended use keyword overlap
        if sw.intended_use:
            use_words = {
                w.lower()
                for w in sw.intended_use.split()
                if len(w) >= 3
            }
            use_words -= _STOPWORDS
            text_words = set(text_lower.split())
            if use_words & text_words:
                score += 200

        scores.append((sw, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores or scores[0][1] == 0:
        return None

    best_sw, best_score = scores[0]

    # Require clear winner: best must beat runner-up by 2x margin
    if len(scores) >= 2:
        runner_up_score = scores[1][1]
        if runner_up_score > 0 and best_score < runner_up_score * 2:
            logger.info(
                "email_routing_tier1_ambiguous",
                best=best_sw.software_name,
                best_score=best_score,
                runner_up=scores[1][0].software_name,
                runner_up_score=runner_up_score,
            )
            return None

    return best_sw


async def _crew_route(
    email: MonitoredEmail,
    candidates: list[SoftwareRegistration],
) -> SoftwareRegistration | None:
    """Tier 2: LLM-based routing via CrewAI.

    Runs the synchronous crew in a thread executor with a 15-second timeout.
    Returns the matched SoftwareRegistration, or None.
    """
    from app.agents.email_router.crew import EmailRoutingCrew

    email_summary = (
        f"Subject: {email.subject or 'N/A'}\n"
        f"Sender: {email.sender or 'N/A'}\n"
        f"Body Snippet: {(email.body_snippet or 'N/A')[:1500]}\n"
    )

    candidates_data = [
        {
            "software_id": str(sw.id),
            "software_name": sw.software_name,
            "vendor_name": sw.vendor_name,
            "intended_use": sw.intended_use or "Not specified",
            "support_email": sw.support_email or "Not configured",
        }
        for sw in candidates
    ]

    crew = EmailRoutingCrew(email_summary, candidates_data)

    loop = asyncio.get_event_loop()
    try:
        crew_result = await asyncio.wait_for(
            loop.run_in_executor(None, crew.run),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("email_routing_crew_timeout")
        return None

    matched_id = crew_result.get("matched_software_id")
    confidence = crew_result.get("confidence", 0.0)

    if confidence < ROUTING_CONFIDENCE_THRESHOLD:
        logger.info(
            "email_routing_crew_low_confidence",
            confidence=confidence,
            reasoning=crew_result.get("reasoning", ""),
        )
        return None

    if not matched_id:
        return None

    try:
        target_id = uuid.UUID(matched_id)
    except ValueError:
        return None

    for sw in candidates:
        if sw.id == target_id:
            logger.info(
                "email_routing_tier2_match",
                software_id=str(sw.id),
                software_name=sw.software_name,
                confidence=confidence,
                reasoning=crew_result.get("reasoning", ""),
            )
            return sw

    return None
