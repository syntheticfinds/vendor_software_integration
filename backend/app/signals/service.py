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

    # Look up software for classification
    from app.signals.classification import classify_signal
    from app.software.models import SoftwareRegistration

    sw_result = await db.execute(
        select(SoftwareRegistration).where(SoftwareRegistration.id == software_id)
    )
    sw = sw_result.scalar_one_or_none()

    for connector in connectors:
        events = await connector.fetch_events(company_id, software_id)
        for event in events:
            if sw:
                tags = classify_signal(
                    event.source_type, event.event_type, event.severity,
                    event.title, event.body,
                    sw.software_name, sw.created_at,
                )
                meta = event.event_metadata if isinstance(event.event_metadata, dict) else {}
                meta.update(tags)
                event.event_metadata = meta
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
    scores = list(result.scalars().all())

    # Bootstrap: if no score exists yet but signals do, generate a quick
    # deterministic score so the UI isn't empty on first load.  Once the
    # background analysis (triggered by ingest or manual Analyze) completes,
    # it will overwrite this with a full LLM-powered result.
    if software_id and not scores:
        signal_count_result = await db.execute(
            select(func.count()).select_from(SignalEvent).where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
        )
        current_signal_count = signal_count_result.scalar_one()

        if current_signal_count > 0:
            new_score = await _auto_compute_health_score(
                db, company_id, software_id,
            )
            if new_score:
                return [new_score]

    return scores


async def _auto_compute_health_score(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> HealthScore | None:
    """Bootstrap a deterministic health score when none exists yet.

    Used only on first page load before any ingest/analyze has run.
    The background analysis (triggered after ingest) will overwrite this
    with a full LLM-powered result including a rich summary.
    """
    from app.software.models import SoftwareRegistration

    result = await db.execute(
        select(SignalEvent).where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        ).order_by(SignalEvent.occurred_at.desc())
    )
    events = list(result.scalars().all())
    if not events:
        return None

    sw_result = await db.execute(
        select(SoftwareRegistration).where(SoftwareRegistration.id == software_id)
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return None

    analysis = _deterministic_analysis(
        events, software.software_name, software.vendor_name, software.intended_use,
    )

    score_data = analysis.get("score", {})
    score_val = score_data.get("score", 70) if isinstance(score_data, dict) else 70
    breakdown = score_data.get("category_breakdown", {}) if isinstance(score_data, dict) else {}
    cat_confidence = score_data.get("category_confidence", {}) if isinstance(score_data, dict) else {}
    if cat_confidence:
        breakdown["category_confidence"] = cat_confidence
    summary_text = analysis.get("summary", {})
    if isinstance(summary_text, dict):
        summary_text = summary_text.get("summary", "")
    summary_text = str(summary_text)

    return await save_health_score(
        db, company_id, software_id,
        score=int(score_val),
        category_breakdown=breakdown,
        signal_summary=summary_text,
        signal_count=len(events),
        window_days=30,
    )


async def save_health_score(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    score: int,
    category_breakdown: dict,
    signal_summary: str,
    signal_count: int,
    window_days: int,
    summaries: dict | None = None,
    trajectory_data: dict | None = None,
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
        summaries=summaries,
        trajectory_data=trajectory_data,
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


async def get_latest_health_score(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> HealthScore | None:
    """Return the most recent HealthScore for a company/software pair."""
    result = await db.execute(
        select(HealthScore)
        .where(
            HealthScore.company_id == company_id,
            HealthScore.software_id == software_id,
        )
        .order_by(HealthScore.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
    """Run the hierarchical signal analysis pipeline.

    1. Fetch and window-filter signals
    2. Group signals by health category and stage
    3. Deterministic scoring (health + trajectory)
    4. Hierarchical LLM summarization (parallel)
    5. LLM review drafting
    6. Save HealthScore (with summaries + trajectory_data) + ReviewDraft
    """
    # ── 1. Fetch signals ──
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_events = list(result.scalars().all())

    if not all_events:
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

    # Window filter
    since_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)

    def _to_naive(dt) -> datetime | None:
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
    if not events:
        events = all_events

    # Get software details
    from app.software.models import SoftwareRegistration
    sw_result = await db.execute(
        select(SoftwareRegistration).where(SoftwareRegistration.id == software_id)
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"status": "software_not_found"}

    # ── 2. Backfill classification metadata ──
    from app.signals.classification import _deterministic_classify, _classify_health_categories
    from app.signals.trajectory import (
        STAGES,
        _build_stage_timeline,
        _combine_smoothness_score,
        _compute_smoothness,
        _generate_explanation,
        _tz_fix,
    )

    # all_tz_events = every signal (full lifecycle), used for trajectory
    # tz_events = windowed subset (recent), used for health scoring
    all_tz_events = _tz_fix(list(all_events))
    tz_events = _tz_fix(list(events))

    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    # Backfill ALL signals so metadata is consistent across both sets
    for sig in all_tz_events:
        meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}

        # Backfill valence/subject/stage_topic if missing
        if "valence" not in meta:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0
            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta.update(tags)

        # Backfill health_categories if missing
        if "health_categories" not in meta:
            text = f"{sig.title or ''} {sig.body or ''}".strip()
            cats = _classify_health_categories(
                sig.event_type or "", meta.get("subject", ""), text,
            )
            meta["health_categories"] = cats

        sig.event_metadata = meta

    # ── 3. Deterministic scoring — HEALTH (windowed) ──
    det_result = _deterministic_analysis(
        tz_events, software.software_name, software.vendor_name, software.intended_use,
    )
    score_data = det_result.get("score", {})
    health_score_val = score_data.get("score", 70) if isinstance(score_data, dict) else 70
    health_breakdown = score_data.get("category_breakdown", {}) if isinstance(score_data, dict) else {}
    health_cat_confidence = score_data.get("category_confidence", {}) if isinstance(score_data, dict) else {}
    if health_cat_confidence:
        health_breakdown["category_confidence"] = health_cat_confidence

    # ── 5. Deterministic scoring — TRAJECTORY (full lifecycle) ──
    timeline = _build_stage_timeline(all_tz_events)
    current_stage = timeline["current_stage"]

    stages_output = []
    stage_metrics: dict[str, dict[str, float]] = {}
    stage_smoothness: dict[str, float] = {}

    for stage_name in STAGES:
        stage_signals = timeline["stage_signals"].get(stage_name, [])
        date_range = timeline["stage_ranges"].get(stage_name)

        if not stage_signals:
            from app.signals.trajectory import STAGE_ORDER
            if stage_name == current_stage:
                status = "current"
            elif STAGE_ORDER[stage_name] < STAGE_ORDER[current_stage]:
                status = "completed"
            else:
                status = "upcoming"
            stages_output.append({
                "name": stage_name, "status": status, "signal_count": 0,
                "smoothness_score": None, "date_range": None,
                "explanation": f"No signals classified as {stage_name}.",
                "metrics": None,
            })
            continue

        metrics, metric_details, metric_confidence = _compute_smoothness(stage_signals, all_signals=all_tz_events, stage_topic=stage_name)
        smoothness = _combine_smoothness_score(metrics, stage_name)

        stage_metrics[stage_name] = metrics
        stage_smoothness[stage_name] = round(smoothness, 1)

        from app.signals.trajectory import STAGE_ORDER
        if stage_name == current_stage:
            status = "current"
        elif STAGE_ORDER[stage_name] < STAGE_ORDER[current_stage]:
            status = "completed"
        else:
            status = "upcoming"

        explanation = _generate_explanation(stage_name, metrics, smoothness, len(stage_signals))

        stages_output.append({
            "name": stage_name, "status": status,
            "signal_count": len(stage_signals),
            "smoothness_score": round(smoothness, 1),
            "date_range": date_range,
            "explanation": explanation,
            "metrics": metrics,
            "metric_details": metric_details,
            "metric_confidence": metric_confidence,
        })

    scored = [s for s in stages_output if s["smoothness_score"] is not None]
    overall_smoothness = sum(s["smoothness_score"] for s in scored) / len(scored) if scored else 50.0
    overall_smoothness = round(overall_smoothness, 1)

    total_signals = len(all_tz_events)
    if total_signals >= 15:
        confidence = "solid"
    elif total_signals >= 5:
        confidence = "developing"
    else:
        confidence = "preliminary"

    trajectory_data = {
        "current_stage": current_stage,
        "stages": stages_output,
        "regression_detected": timeline["regression_detected"],
        "regression_detail": timeline["regression_detail"],
        "overall_smoothness": overall_smoothness,
        "confidence": confidence,
    }

    # ── 6. Hierarchical LLM summarization ──
    summaries = None
    draft_data = None

    try:
        from app.signals.summarizers import draft_review, run_hierarchical_summarizers

        summaries = await run_hierarchical_summarizers(
            health_breakdown=health_breakdown,
            health_overall_score=int(health_score_val),
            stage_groups=timeline["stage_signals"],
            stage_metrics=stage_metrics,
            stage_smoothness=stage_smoothness,
            overall_smoothness=overall_smoothness,
            current_stage=current_stage,
            regression_detected=timeline["regression_detected"],
            regression_detail=timeline["regression_detail"],
            software_name=software.software_name,
            all_signals=all_tz_events,
            health_signals=tz_events,
        )

        # ── 7. Review draft ──
        health_overall = summaries.get("health", {}).get("overall", "") if summaries else ""
        traj_overall = summaries.get("trajectory", {}).get("overall", "") if summaries else ""

        draft_data = await draft_review(
            software_name=software.software_name,
            vendor_name=software.vendor_name,
            intended_use=software.intended_use,
            health_summary=health_overall,
            trajectory_summary=traj_overall,
            all_summaries=summaries or {},
            all_scores={
                "health_score": int(health_score_val),
                "overall_smoothness": overall_smoothness,
                **health_breakdown,
            },
            signal_count=total_signals,
            confidence_tier=confidence,
        )
    except Exception as e:
        logger.warning("hierarchical_summarizers_failed_using_deterministic", error=str(e))

    # Deterministic fallback for summary text + review draft
    det_summary = det_result.get("summary", {})
    summary_text = det_summary.get("summary", "") if isinstance(det_summary, dict) else str(det_summary)
    health_overall_text = summaries.get("health", {}).get("overall", "") if summaries else ""
    signal_summary = health_overall_text or summary_text

    if not draft_data:
        det_draft = det_result.get("draft", {})
        draft_data = {
            "subject": det_draft.get("subject", f"Review: {software.software_name} by {software.vendor_name}"),
            "body": det_draft.get("body", summary_text),
        }

    # ── 8. Save ──
    hs = await save_health_score(
        db, company_id, software_id,
        score=int(health_score_val),
        category_breakdown=health_breakdown,
        signal_summary=signal_summary,
        signal_count=total_signals,
        window_days=window_days,
        summaries=summaries,
        trajectory_data=trajectory_data,
    )

    await save_review_draft(
        db, company_id, software_id, hs.id,
        draft_data["subject"], str(draft_data["body"]), hs.confidence_tier,
    )

    return {
        "status": "completed",
        "signal_count": total_signals,
        "health_score": int(health_score_val),
        "confidence_tier": hs.confidence_tier,
    }


# ---------------------------------------------------------------------------
# Health scoring — classifier-tag-based structural detection
# ---------------------------------------------------------------------------
# Aligned with trajectory scoring: uses classifier metadata (valence,
# health_categories) and structural pattern detection (severity-weighted
# impact, ticket resolution, trend direction) instead of hardcoded
# event-type profiles.
# ---------------------------------------------------------------------------

# Reuse trajectory's severity weights for consistency
_HEALTH_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 4.0, "high": 2.5, "medium": 1.0, "low": 0.3,
}


def _score_health_category(
    category_signals: list[SignalEvent],
    all_events: list[SignalEvent],
) -> tuple[float, dict[str, float]]:
    """Score a single health category using structural detection.

    Returns (score_0_100, sub_metrics) where sub_metrics has:
      - impact:     severity-weighted friction (like trajectory's friction)
      - resolution: ticket resolution rate (like trajectory's resolution)
      - trend:      recent-half vs earlier-half severity direction

    Score 0-100, higher = healthier.  Default 75 when no signals.
    """
    from app.signals.trajectory import _pair_tickets

    if not category_signals:
        return 75.0, {"impact": 75.0, "resolution": 75.0, "trend": 75.0}

    # --- Impact (like friction): severity-weighted negative minus positive offset ---
    negative = [
        s for s in category_signals
        if (s.event_metadata or {}).get("valence") == "negative"
    ]
    positive = [
        s for s in category_signals
        if (s.event_metadata or {}).get("valence") == "positive"
    ]

    neg_weight = sum(_HEALTH_SEVERITY_WEIGHT.get(s.severity or "medium", 1.0) for s in negative)
    pos_offset = sum(_HEALTH_SEVERITY_WEIGHT.get(s.severity or "medium", 1.0) * 0.5 for s in positive)
    raw_impact = neg_weight - pos_offset
    impact_score = max(0.0, min(100.0, 100.0 - raw_impact * 5))

    # --- Resolution: ticket pairs within this category's signals ---
    # Use all_events for cross-stage pairing, then filter to category signals
    all_pairs = _pair_tickets(all_events)
    cat_signal_ids = {id(s) for s in category_signals}
    cat_created = [s for s in category_signals if s.event_type == "ticket_created"]

    if cat_created:
        paired_created_ids = {id(c) for c, _r in all_pairs}
        matched = sum(1 for s in cat_created if id(s) in paired_created_ids)
        resolution_score = (matched / len(cat_created)) * 100
    else:
        resolution_score = 75.0  # neutral default when no tickets

    # --- Trend: compare severity burden in recent half vs earlier half ---
    sorted_sigs = sorted(
        category_signals,
        key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc),
    )
    mid = len(sorted_sigs) // 2
    if mid >= 1 and len(sorted_sigs) >= 4:
        earlier = sorted_sigs[:mid]
        recent = sorted_sigs[mid:]
        earlier_burden = sum(
            _HEALTH_SEVERITY_WEIGHT.get(s.severity or "medium", 1.0)
            for s in earlier if (s.event_metadata or {}).get("valence") == "negative"
        ) / max(len(earlier), 1)
        recent_burden = sum(
            _HEALTH_SEVERITY_WEIGHT.get(s.severity or "medium", 1.0)
            for s in recent if (s.event_metadata or {}).get("valence") == "negative"
        ) / max(len(recent), 1)
        # Improving = recent burden lower → score above 75
        # Worsening = recent burden higher → score below 75
        if earlier_burden == 0 and recent_burden == 0:
            trend_score = 75.0
        elif earlier_burden == 0:
            trend_score = max(0.0, 75.0 - recent_burden * 10)
        else:
            ratio = recent_burden / earlier_burden
            # ratio < 1 = improving, ratio > 1 = worsening
            trend_score = max(0.0, min(100.0, 75.0 + (1 - ratio) * 25))
    else:
        trend_score = 75.0  # not enough data to measure trend

    # Combine sub-metrics: impact is most important, then resolution, then trend
    combined = impact_score * 0.50 + resolution_score * 0.30 + trend_score * 0.20
    score = max(0.0, min(100.0, combined))

    sub_metrics = {
        "impact": round(impact_score, 1),
        "resolution": round(resolution_score, 1),
        "trend": round(trend_score, 1),
    }
    return round(score, 1), sub_metrics


def _deterministic_analysis(
    events: list[SignalEvent],
    software_name: str,
    vendor_name: str,
    intended_use: str | None = None,
) -> dict:
    """Deterministic health scoring using classifier tags and structural detection.

    Groups signals by health_categories classifier metadata, then scores each
    category using severity-weighted impact, ticket resolution rate, and trend
    analysis — the same structural approach as trajectory smoothness scoring.
    """
    total = len(events)

    # --- Group signals by health_categories classifier tags ---
    health_groups: dict[str, list[SignalEvent]] = {
        "reliability": [],
        "performance": [],
        "fitness_for_purpose": [],
    }
    for e in events:
        cats = (e.event_metadata or {}).get("health_categories", [])
        if isinstance(cats, list):
            for cat in cats:
                if cat in health_groups:
                    health_groups[cat].append(e)

    # --- Score each category ---
    reliability_score, reliability_sub = _score_health_category(
        health_groups["reliability"], events,
    )
    performance_score, performance_sub = _score_health_category(
        health_groups["performance"], events,
    )

    breakdown: dict = {
        "reliability": int(reliability_score),
        "performance": int(performance_score),
    }

    # Confidence: "high" when >=2 relevant signals, "low" = default baseline
    category_confidence: dict[str, str] = {
        "reliability": "high" if len(health_groups["reliability"]) >= 2 else "low",
        "performance": "high" if len(health_groups["performance"]) >= 2 else "low",
    }

    if intended_use:
        fitness_score, fitness_sub = _score_health_category(
            health_groups["fitness_for_purpose"], events,
        )
        breakdown["fitness_for_purpose"] = int(fitness_score)
        category_confidence["fitness_for_purpose"] = (
            "high" if len(health_groups["fitness_for_purpose"]) >= 2 else "low"
        )
        overall = int(
            reliability_score * 0.35 + performance_score * 0.35 + fitness_score * 0.30
        )
    else:
        overall = int(reliability_score * 0.50 + performance_score * 0.50)

    # --- Collect what-works / what-doesnt from classifier valence ---
    what_works: list[str] = []
    what_doesnt: list[str] = []
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for e in events:
        sev = e.severity or "medium"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        valence = (e.event_metadata or {}).get("valence")
        label = e.title or e.event_type or "event"
        if valence == "positive":
            what_works.append(label)
        elif valence == "negative" and sev in ("critical", "high", "medium"):
            what_doesnt.append(label)

    summary = (
        f"Over the analysis window, {total} signal events were recorded for {software_name}. "
        f"Severity breakdown: {severity_counts['critical']} critical, "
        f"{severity_counts['high']} high, {severity_counts['medium']} medium, "
        f"{severity_counts['low']} low."
    )

    # --- Build review body ---
    tier = compute_confidence_tier(total)
    use_line = f'We adopted {software_name} for: "{intended_use}".\n\n' if intended_use else ""

    if tier == "preliminary":
        data_note = f"Note: This is an early-stage review based on only {total} signal event(s). Scores may shift significantly as more data comes in.\n\n"
    else:
        data_note = ""

    body = f"{use_line}{data_note}Overall Health Score: {overall}/100\n\n"

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
        f"- Reliability: {breakdown['reliability']}/100\n"
        f"- Performance: {breakdown['performance']}/100\n"
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
        "score": {"score": overall, "category_breakdown": breakdown, "category_confidence": category_confidence},
        "draft": {
            "subject": f"Review: {software_name} by {vendor_name}",
            "body": body,
        },
    }
