import json
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.signals.connectors.mock_connector import get_connectors
from app.signals.models import HealthScore, ReviewDraft, SignalEvent

logger = structlog.get_logger()


def compute_confidence_tier(signal_count: int) -> str:
    """Derive quality tier from the number of signals backing the analysis.

    - preliminary: 1-4 signals — limited data, take with a grain of salt
    - developing:  5-14 signals — building a picture, moderate confidence
    - solid:       15+ signals — comprehensive data, high confidence
    """
    if signal_count >= 15:
        return "solid"
    if signal_count >= 5:
        return "developing"
    return "preliminary"


async def ingest_signals(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    source_type: str | None = None,
) -> int:
    """Run connectors and persist normalized signal events."""
    connectors = get_connectors()
    if source_type:
        connectors = [c for c in connectors if c.source_type == source_type]

    total = 0
    for connector in connectors:
        events = await connector.fetch_events(company_id, software_id)
        for event in events:
            db.add(event)
            total += 1

    await db.commit()
    logger.info("signals_ingested", company_id=str(company_id), software_id=str(software_id), count=total)
    return total


async def get_signal_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID | None = None,
    source_type: str | None = None,
    severity: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[SignalEvent], int]:
    query = select(SignalEvent).where(SignalEvent.company_id == company_id)
    count_q = select(func.count()).select_from(SignalEvent).where(SignalEvent.company_id == company_id)

    if software_id:
        query = query.where(SignalEvent.software_id == software_id)
        count_q = count_q.where(SignalEvent.software_id == software_id)
    if source_type:
        query = query.where(SignalEvent.source_type == source_type)
        count_q = count_q.where(SignalEvent.source_type == source_type)
    if severity:
        query = query.where(SignalEvent.severity == severity)
        count_q = count_q.where(SignalEvent.severity == severity)
    if from_date:
        query = query.where(SignalEvent.occurred_at >= from_date)
        count_q = count_q.where(SignalEvent.occurred_at >= from_date)
    if to_date:
        query = query.where(SignalEvent.occurred_at <= to_date)
        count_q = count_q.where(SignalEvent.occurred_at <= to_date)

    query = query.order_by(SignalEvent.occurred_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    count_result = await db.execute(count_q)
    return list(result.scalars().all()), count_result.scalar_one()


async def get_health_scores(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID | None = None,
) -> list[HealthScore]:
    query = select(HealthScore).where(HealthScore.company_id == company_id)
    if software_id:
        query = query.where(HealthScore.software_id == software_id)
    query = query.order_by(HealthScore.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def save_health_score(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    score: int,
    category_breakdown: dict,
    signal_summary: str,
    signal_count: int,
    window_days: int,
) -> HealthScore:
    now = datetime.now(timezone.utc)
    tier = compute_confidence_tier(signal_count)
    hs = HealthScore(
        company_id=company_id,
        software_id=software_id,
        score=max(0, min(100, score)),
        category_breakdown=category_breakdown,
        signal_summary=signal_summary,
        signal_count=signal_count,
        confidence_tier=tier,
        scoring_window_start=now - timedelta(days=window_days),
        scoring_window_end=now,
    )
    db.add(hs)
    await db.commit()
    await db.refresh(hs)
    return hs


async def save_review_draft(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    health_score_id: uuid.UUID,
    subject: str,
    body: str,
    confidence_tier: str = "preliminary",
) -> ReviewDraft:
    # Upsert: one review per software — reuse existing draft instead of creating duplicates
    existing = (await db.execute(
        select(ReviewDraft).where(
            ReviewDraft.company_id == company_id,
            ReviewDraft.software_id == software_id,
        ).order_by(ReviewDraft.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    if existing:
        existing.health_score_id = health_score_id
        existing.draft_subject = subject
        existing.draft_body = body
        existing.confidence_tier = confidence_tier
        existing.status = "pending"
        existing.edited_body = None
        existing.reviewed_at = None
        await db.commit()
        await db.refresh(existing)
        return existing

    draft = ReviewDraft(
        company_id=company_id,
        software_id=software_id,
        health_score_id=health_score_id,
        draft_subject=subject,
        draft_body=body,
        confidence_tier=confidence_tier,
        status="pending",
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    return draft


async def get_review_drafts(
    db: AsyncSession,
    company_id: uuid.UUID,
    status: str | None = None,
) -> list[ReviewDraft]:
    query = select(ReviewDraft).where(ReviewDraft.company_id == company_id)
    if status:
        query = query.where(ReviewDraft.status == status)
    query = query.order_by(ReviewDraft.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_review_draft_by_id(db: AsyncSession, draft_id: uuid.UUID) -> ReviewDraft | None:
    result = await db.execute(select(ReviewDraft).where(ReviewDraft.id == draft_id))
    return result.scalar_one_or_none()


async def update_review_draft(
    db: AsyncSession,
    draft: ReviewDraft,
    status: str,
    edited_body: str | None = None,
) -> ReviewDraft:
    draft.status = status
    if edited_body is not None:
        draft.edited_body = edited_body
    if status in ("approved", "declined", "edited"):
        draft.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(draft)
    return draft


async def run_analysis(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    window_days: int = 30,
) -> dict:
    """Run the signal analysis pipeline: gather events, score, draft review."""
    # Fetch all events for this software, then filter by window in Python.
    # (SQLite text-based datetime comparisons can be unreliable with timezone-aware values.)
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.desc())
    )
    all_events = list(result.scalars().all())

    if not all_events:
        # Debug: check if there are ANY signals for this company
        total_result = await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.company_id == company_id)
        )
        total = total_result.scalar_one()
        logger.warning(
            "run_analysis_no_events_debug",
            company_id=str(company_id),
            software_id=str(software_id),
            total_company_signals=total,
        )
        return {"status": "no_events", "signal_count": 0}

    # Use naive UTC for comparison (SQLite returns naive datetimes)
    since_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)

    def _to_naive(dt) -> datetime | None:
        """Coerce value to a naive datetime (handles str from SQLite)."""
        if dt is None:
            return None
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return None
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    events = [
        e for e in all_events
        if _to_naive(e.occurred_at) is not None and _to_naive(e.occurred_at) >= since_naive
    ]

    # Fall back to all events if the window filter removed everything.
    # This ensures analysis always runs when signals exist (e.g. demo data
    # with older dates, or race between merge-commit and background read).
    if not events:
        logger.info(
            "run_analysis_window_expanded",
            company_id=str(company_id),
            software_id=str(software_id),
            total_events=len(all_events),
            window_days=window_days,
        )
        events = all_events

    # Prepare events as JSON for the crew
    events_json = json.dumps([
        {
            "source_type": e.source_type,
            "event_type": e.event_type,
            "severity": e.severity,
            "title": e.title,
            "body": e.body,
            "occurred_at": e.occurred_at.isoformat() if isinstance(e.occurred_at, datetime) else str(e.occurred_at),
        }
        for e in events
    ])

    # Get software details
    from app.software.models import SoftwareRegistration
    sw_result = await db.execute(
        select(SoftwareRegistration).where(SoftwareRegistration.id == software_id)
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"status": "software_not_found"}

    # Try to run CrewAI analysis (full LLM-powered multi-agent pipeline)
    try:
        from app.agents.signal_analyzer.crew import SignalAnalysisCrew
        crew = SignalAnalysisCrew(software.software_name, software.vendor_name, events_json, software.intended_use)
        crew_result = crew.run()
    except Exception as e:
        logger.warning("crew_analysis_failed_using_deterministic", error=str(e))
        crew_result = None

    # Fallback: deterministic scoring if crew fails or isn't configured
    if not crew_result or not isinstance(crew_result, dict):
        crew_result = _deterministic_analysis(events, software.software_name, software.vendor_name, software.intended_use)

    # Save health score
    score_data = crew_result.get("score", {})
    if isinstance(score_data, dict):
        score_val = score_data.get("score", 70)
        breakdown = score_data.get("category_breakdown", {})
    else:
        score_val = score_data if isinstance(score_data, int) else 70
        breakdown = crew_result.get("category_breakdown", {})

    summary_text = crew_result.get("summary", "")
    if isinstance(summary_text, dict):
        summary_text = summary_text.get("summary", str(summary_text))

    hs = await save_health_score(
        db, company_id, software_id,
        score=int(score_val),
        category_breakdown=breakdown,
        signal_summary=str(summary_text),
        signal_count=len(events),
        window_days=window_days,
    )

    # Save review draft
    draft_data = crew_result.get("draft", {})
    subject = draft_data.get("subject", f"Review: {software.software_name} by {software.vendor_name}")
    body = draft_data.get("body", summary_text)

    await save_review_draft(db, company_id, software_id, hs.id, subject, str(body), hs.confidence_tier)

    return {"status": "completed", "signal_count": len(events), "health_score": int(score_val), "confidence_tier": hs.confidence_tier}


# ---------------------------------------------------------------------------
# Event impact profiles (used by deterministic fallback only)
# ---------------------------------------------------------------------------
# When CrewAI is available, it performs content-aware sentiment analysis
# directly.  These profiles are used as the static fallback when CrewAI
# fails.
#
# Each (source_type, event_type) has a MAGNITUDE for how much it CAN affect
# each scoring category, plus a DEFAULT sentiment that controls direction:
#   positive → magnitudes added (improve score)
#   negative → magnitudes subtracted (hurt score)
#   neutral  → magnitudes applied at 20% as a mild nudge
#
# `support_always_positive`: even negative events give a small support_quality
# boost (someone is at least tracking the issue).
# ---------------------------------------------------------------------------

_EVENT_PROFILES: dict[tuple[str, str], dict] = {
    # -- Jira ------------------------------------------------------------------
    ("jira", "ticket_created"): {
        "reliability": 1.0,
        "support_quality": 0.2,
        "performance": 0.5,
        "default_sentiment": "negative",
        "support_always_positive": True,  # filing a ticket = engaging support
    },
    ("jira", "ticket_resolved"): {
        "reliability": 0.8,
        "support_quality": 1.0,
        "performance": 0.5,
        "default_sentiment": "positive",
        "support_always_positive": True,
    },
    ("jira", "ticket_updated"): {
        "reliability": 0.3,
        "support_quality": 0.4,
        "performance": 0.2,
        "default_sentiment": "neutral",
        "support_always_positive": True,
    },
    ("jira", "comment_added"): {
        "reliability": 0.5,
        "support_quality": 0.5,
        "performance": 0.4,
        "default_sentiment": "neutral",  # content determines direction
        "support_always_positive": True,
    },
    # -- Email -----------------------------------------------------------------
    ("email", "support_email_received"): {
        "reliability": 0.3,
        "support_quality": 0.5,
        "performance": 0.2,
        "default_sentiment": "neutral",  # content determines direction
        "support_always_positive": True,
    },
    ("email", "feature_request"): {
        "reliability": 0.1,
        "support_quality": 0.2,
        "performance": 0.1,
        "default_sentiment": "neutral",
        "support_always_positive": True,
    },
    ("email", "issue_debug"): {
        "reliability": 0.5,
        "support_quality": 0.4,
        "performance": 0.3,
        "default_sentiment": "negative",
        "support_always_positive": True,
    },
}

# Severity multipliers — scale the magnitude values above
_SEVERITY_MULTIPLIER: dict[str, float] = {
    "critical": 3.0,
    "high": 2.0,
    "medium": 1.0,
    "low": 0.4,
}

# Default profile for unknown (source_type, event_type) combinations
_DEFAULT_PROFILE: dict = {
    "reliability": 0.3,
    "support_quality": 0.2,
    "performance": 0.2,
    "default_sentiment": "neutral",
    "support_always_positive": True,
}


def _deterministic_analysis(
    events: list[SignalEvent],
    software_name: str,
    vendor_name: str,
    intended_use: str | None = None,
) -> dict:
    """Fallback deterministic scoring when CrewAI is unavailable.

    Each (source_type, event_type) has magnitude values for how much it CAN
    affect each category.  The default_sentiment from the profile controls
    the DIRECTION:
      positive → magnitudes boost scores
      negative → magnitudes reduce scores
      neutral  → magnitudes applied at 20% (mild nudge)

    Support quality gets special treatment: even negative events give a small
    positive bump when the profile has support_always_positive=True (filing a
    ticket means someone is engaging the support process).
    """
    total = len(events)

    # Accumulate weighted impacts per category
    reliability_delta = 0.0
    support_delta = 0.0
    performance_delta = 0.0

    what_works: list[str] = []
    what_doesnt: list[str] = []
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for i, e in enumerate(events):
        sev = e.severity or "medium"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

        profile = _EVENT_PROFILES.get((e.source_type, e.event_type), _DEFAULT_PROFILE)
        multiplier = _SEVERITY_MULTIPLIER.get(sev, 1.0)

        sentiment = profile["default_sentiment"]

        # Direction factor: positive = +1, negative = -1, neutral = +0.2
        if sentiment == "positive":
            direction = 1.0
        elif sentiment == "negative":
            direction = -1.0
        else:
            direction = 0.2  # neutral nudge

        reliability_delta += profile["reliability"] * direction * multiplier
        performance_delta += profile["performance"] * direction * multiplier

        # Support quality: negative events still get a mild positive bump
        # when the profile says support_always_positive (someone is at least
        # engaging the support process by filing/tracking the issue)
        if sentiment == "negative" and profile.get("support_always_positive"):
            support_delta += profile["support_quality"] * 0.3 * multiplier
        else:
            support_delta += profile["support_quality"] * direction * multiplier

        # Classify for what-went-well / what-didn't-go-well
        label = e.title or e.event_type or "event"
        if sentiment == "positive":
            what_works.append(label)
        elif sentiment == "negative" and sev in ("critical", "high", "medium"):
            what_doesnt.append(label)

    # Convert deltas to 0-100 scores starting from a 75 baseline
    # (no signals = healthy default; deltas shift it)
    baseline = 75
    reliability = max(0, min(100, int(baseline + reliability_delta)))
    support = max(0, min(100, int(baseline + support_delta)))
    performance = max(0, min(100, int(baseline + performance_delta)))

    breakdown = {
        "reliability": reliability,
        "support_quality": support,
        "performance": performance,
    }

    if intended_use:
        # Fitness for purpose: weighted combination of reliability + performance
        # with a bonus for good support (resolved issues = vendor cares)
        fitness_raw = (reliability * 0.5) + (performance * 0.3) + (support * 0.2)
        fitness = max(0, min(100, int(fitness_raw)))
        breakdown["fitness_for_purpose"] = fitness
        overall = int(
            (reliability * 0.30) + (support * 0.25) + (performance * 0.25) + (fitness * 0.20)
        )
    else:
        overall = int((reliability * 0.4) + (support * 0.3) + (performance * 0.3))

    resolved = severity_counts.get("resolved", 0)
    for e in events:
        if "resolved" in (e.event_type or ""):
            resolved += 1

    summary = (
        f"Over the analysis window, {total} signal events were recorded for {software_name}. "
        f"Severity breakdown: {severity_counts['critical']} critical, "
        f"{severity_counts['high']} high, {severity_counts['medium']} medium, "
        f"{severity_counts['low']} low."
    )

    # Build review body — scale to available data
    tier = compute_confidence_tier(total)
    use_line = f'We adopted {software_name} for: "{intended_use}".\n\n' if intended_use else ""

    if tier == "preliminary":
        data_note = f"Note: This is an early-stage review based on only {total} signal event(s). Scores may shift significantly as more data comes in.\n\n"
    elif tier == "developing":
        data_note = ""
    else:
        data_note = ""

    body = f"{use_line}{data_note}Overall Health Score: {overall}/100\n\n"

    # Only include sections that have real data
    if what_works:
        well_section = "\n".join(f"- {w}" for w in what_works[:5])
        body += f"What went well:\n{well_section}\n\n"

    if what_doesnt:
        bad_section = "\n".join(f"- {w}" for w in what_doesnt[:5])
        body += f"What didn't go well:\n{bad_section}\n\n"

    if not what_works and not what_doesnt:
        body += "No clearly positive or negative signals in this window.\n\n"

    body += (
        f"Score breakdown:\n"
        f"- Reliability: {reliability}/100\n"
        f"- Support Quality: {support}/100\n"
        f"- Performance: {performance}/100\n"
    )
    if intended_use:
        body += f"- Fitness for Purpose: {breakdown['fitness_for_purpose']}/100\n"

    body += (
        f"\nThis review is based on {total} signal event(s). "
        f"Please review and approve or edit before sharing."
    )

    return {
        "summary": {
            "summary": summary,
            "categories": severity_counts,
            "trend": "stable",
            "what_works": what_works[:5],
            "what_doesnt": what_doesnt[:5],
        },
        "score": {"score": overall, "category_breakdown": breakdown},
        "draft": {
            "subject": f"Review: {software_name} by {vendor_name}",
            "body": body,
        },
    }
