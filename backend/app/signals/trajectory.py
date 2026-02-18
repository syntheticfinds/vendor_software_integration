"""Integration maturity trajectory — stage inference and smoothness scoring."""

import re
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.signals.models import SignalEvent
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

STAGES = ["onboarding", "integration", "stabilization", "productive", "optimization"]
STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}

SEVERITY_WEIGHT = {"critical": 4.0, "high": 2.5, "medium": 1.0, "low": 0.3}


def _tz_fix(signals: list[SignalEvent]) -> list[SignalEvent]:
    """Ensure every signal's occurred_at is timezone-aware (UTC)."""
    for sig in signals:
        if sig.occurred_at and sig.occurred_at.tzinfo is None:
            sig.occurred_at = sig.occurred_at.replace(tzinfo=timezone.utc)
    return signals

# Stage-dependent weights for combining smoothness sub-metrics
STAGE_SMOOTHNESS_WEIGHTS: dict[str, dict[str, float]] = {
    "onboarding": {"friction": 0.35, "recurrence": 0.10, "escalation": 0.15, "resolution": 0.30, "effort": 0.10},
    "integration": {"friction": 0.30, "recurrence": 0.15, "escalation": 0.15, "resolution": 0.25, "effort": 0.15},
    "stabilization": {"friction": 0.25, "recurrence": 0.20, "escalation": 0.20, "resolution": 0.20, "effort": 0.15},
    "productive": {"friction": 0.20, "recurrence": 0.25, "escalation": 0.15, "resolution": 0.15, "effort": 0.25},
    "optimization": {"friction": 0.20, "recurrence": 0.25, "escalation": 0.15, "resolution": 0.15, "effort": 0.25},
}

_REPLY_PREFIX = re.compile(r"^(Re:\s*|Fwd:\s*|FW:\s*|RE:\s*)+", re.IGNORECASE)
_TICKET_PREFIX = re.compile(r"^\[[A-Za-z]+-\d+\]\s*")


def _normalize_title(title: str | None) -> str:
    if not title:
        return ""
    cleaned = _REPLY_PREFIX.sub("", title).strip()
    cleaned = _TICKET_PREFIX.sub("", cleaned).strip()
    return cleaned.lower()


async def compute_trajectory(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> dict:
    """Compute the full maturity trajectory for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    if not signals:
        return _empty_trajectory()

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()
        # Re-fetch to get updated metadata
        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        signals = _tz_fix(list(result.scalars().all()))

    # Build timeline
    timeline = _build_stage_timeline(signals)
    current_stage = timeline["current_stage"]

    # Build output stages
    stages_output = []
    for stage_name in STAGES:
        stage_signals = timeline["stage_signals"].get(stage_name, [])
        date_range = timeline["stage_ranges"].get(stage_name)

        if not stage_signals:
            if stage_name == current_stage:
                status = "current"
            elif STAGE_ORDER[stage_name] < STAGE_ORDER[current_stage]:
                status = "completed"
            else:
                status = "upcoming"
            stages_output.append({
                "name": stage_name,
                "status": status,
                "signal_count": 0,
                "smoothness_score": None,
                "date_range": None,
                "explanation": f"No signals classified as {stage_name}.",
                "metrics": None,
            })
            continue

        metrics, metric_details, metric_confidence = _compute_smoothness(stage_signals, all_signals=signals, stage_topic=stage_name)
        smoothness = _combine_smoothness_score(metrics, stage_name)

        if stage_name == current_stage:
            status = "current"
        elif STAGE_ORDER[stage_name] < STAGE_ORDER[current_stage]:
            status = "completed"
        else:
            status = "upcoming"

        explanation = _generate_explanation(stage_name, metrics, smoothness, len(stage_signals))

        stages_output.append({
            "name": stage_name,
            "status": status,
            "signal_count": len(stage_signals),
            "smoothness_score": round(smoothness, 1),
            "date_range": date_range,
            "explanation": explanation,
            "metrics": metrics,
            "metric_details": metric_details,
            "metric_confidence": metric_confidence,
        })

    # Overall smoothness: average of stages that have scores
    scored = [s for s in stages_output if s["smoothness_score"] is not None]
    overall = sum(s["smoothness_score"] for s in scored) / len(scored) if scored else 50.0

    total_signals = len(signals)
    if total_signals >= 15:
        confidence = "solid"
    elif total_signals >= 5:
        confidence = "developing"
    else:
        confidence = "preliminary"

    benchmarks = await _compute_benchmarks(
        db, software_id, software.vendor_name, software.software_name,
        stages_output, round(overall, 1),
    )

    return {
        "current_stage": current_stage,
        "stages": stages_output,
        "regression_detected": timeline["regression_detected"],
        "regression_detail": timeline["regression_detail"],
        "overall_smoothness": round(overall, 1),
        "confidence": confidence,
        "benchmarks": benchmarks,
    }


def _build_stage_timeline(signals: list[SignalEvent]) -> dict:
    """Segment signals by stage_topic, determine current stage, detect regression."""
    stage_signals: dict[str, list[SignalEvent]] = defaultdict(list)
    stage_ranges: dict[str, dict[str, str]] = {}

    for sig in signals:
        meta = sig.event_metadata or {}
        stage_topic = meta.get("stage_topic", "productive")
        stage_signals[stage_topic].append(sig)

    # Compute date ranges per stage
    for stage, sigs in stage_signals.items():
        dates = [s.occurred_at for s in sigs if s.occurred_at]
        if dates:
            stage_ranges[stage] = {
                "start": min(dates).isoformat(),
                "end": max(dates).isoformat(),
            }

    # Determine current stage via weighted vote from recent signals
    recent_count = min(10, len(signals))
    recent = signals[-recent_count:]
    stage_votes: dict[str, float] = defaultdict(float)

    for i, sig in enumerate(recent):
        meta = sig.event_metadata or {}
        stage_topic = meta.get("stage_topic", "productive")
        subject = meta.get("subject", "vendor_comm")

        # internal_impl signals are strongest stage indicators
        weight = 2.0 if subject == "internal_impl" else 1.0
        # Recency boost: later items in the list are more recent
        weight *= 1 + i * 0.1
        stage_votes[stage_topic] += weight

    current_stage = max(stage_votes, key=lambda k: stage_votes[k]) if stage_votes else "onboarding"

    # Regression detection
    if stage_signals:
        peak_stage = max(
            stage_signals.keys(),
            key=lambda s: STAGE_ORDER.get(s, 0),
        )
    else:
        peak_stage = "onboarding"

    regression = STAGE_ORDER.get(current_stage, 0) < STAGE_ORDER.get(peak_stage, 0)
    regression_detail = None
    if regression:
        regression_detail = (
            f"Integration appears to have regressed from {peak_stage} to {current_stage}. "
            f"Recent signals show {current_stage}-type activity."
        )

    return {
        "current_stage": current_stage,
        "stage_signals": dict(stage_signals),
        "stage_ranges": stage_ranges,
        "regression_detected": regression,
        "regression_detail": regression_detail,
    }


def _truncate(text: str, max_len: int = 45) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "\u2026"


def _label(s: SignalEvent) -> str:
    return _truncate(s.title or s.event_type or "signal")


_FRICTION_IMPACT = {"critical": "major", "high": "significant", "medium": "moderate", "low": "minor"}


def _compute_smoothness(
    signals: list[SignalEvent],
    all_signals: list[SignalEvent] | None = None,
    stage_topic: str | None = None,
) -> tuple[dict[str, float], dict[str, str], dict[str, str]]:
    """Compute 5 smoothness sub-metrics + natural-language narrative per metric.

    Uses the shared ``detect_*`` functions so that scoring, summarisation,
    and the UI timeline endpoints all operate on identical signal sets.

    Parameters
    ----------
    signals:
        Stage-filtered signals.
    all_signals:
        ALL signals across every stage (needed by recurrence / escalation /
        resolution which detect patterns cross-stage).  Falls back to
        *signals* when not provided.
    stage_topic:
        Name of the current stage (e.g. ``"onboarding"``).  Used to filter
        cross-stage detection results back to this stage.

    Returns (scores, details, confidence) where scores and details are dicts
    keyed by metric name, and confidence maps metric name to "high" or "low".
    Scores are 0-100, higher = smoother.  Confidence is "low" when a default
    was used due to insufficient data.
    """
    all_sigs = all_signals or signals
    details: dict[str, str] = {}

    # 1. Net friction -------------------------------------------------------
    friction_sigs = detect_friction_signals(signals)
    negative = [s for s in friction_sigs if (s.event_metadata or {}).get("valence") == "negative"]
    positive = [s for s in friction_sigs if (s.event_metadata or {}).get("valence") == "positive"]

    neg_friction = sum(SEVERITY_WEIGHT.get(s.severity or "medium", 1.0) for s in negative)
    pos_benefit = sum(SEVERITY_WEIGHT.get(s.severity or "medium", 1.0) * 0.5 for s in positive)
    raw_friction = neg_friction - pos_benefit
    friction_score = max(0.0, min(100.0, 100.0 - raw_friction * 5))

    if negative or positive:
        parts: list[str] = []
        top_neg = sorted(negative, key=lambda s: SEVERITY_WEIGHT.get(s.severity or "medium", 1.0), reverse=True)
        for s in top_neg[:3]:
            impact = _FRICTION_IMPACT.get(s.severity or "medium", "moderate")
            parts.append(f"'{_label(s)}' ({s.severity or 'medium'}) added {impact} friction")
        if positive:
            pos_labels = " and ".join(f"'{_label(s)}'" for s in positive[:2])
            parts.append(f"{pos_labels} partially offset this as positive outcome{'s' if len(positive) > 1 else ''}")
        if len(negative) > 3:
            parts.append(f"{len(negative) - 3} more negative signal{'s' if len(negative) - 3 > 1 else ''} also contributed")
        details["friction"] = ". ".join(parts) + "."
    else:
        details["friction"] = "No positive or negative signals occurred in this stage, so friction is neutral."

    # 2. Issue recurrence (aligned: detect_recurrence + _split_into_incidents)
    recurrence_results = detect_recurrence(all_sigs, stage_topic)

    stage_threads: set[str] = set()
    for s in signals:
        norm = _normalize_title(s.title)
        if norm:
            stage_threads.add(norm)

    recurring_thread_topics = {topic for _, topic, _, _, _ in recurrence_results}
    total_threads = max(len(stage_threads), 1)
    recurring_count = len(recurring_thread_topics)
    recurrence_score = max(0.0, min(100.0, 100.0 - (recurring_count / total_threads) * 100))

    if stage_threads:
        if recurring_thread_topics:
            parts = []
            # Show top recurring topics with incident counts
            topic_incidents: dict[str, int] = {}
            for _, topic, _, total_inc, _ in recurrence_results:
                topic_incidents[topic] = max(topic_incidents.get(topic, 0), total_inc)
            for topic, inc_count in sorted(topic_incidents.items(), key=lambda x: x[1], reverse=True)[:3]:
                parts.append(f"'{_truncate(topic)}' recurred across {inc_count} incidents, suggesting an unresolved root cause")
            rest = len(stage_threads) - len(recurring_thread_topics)
            if rest > 0:
                parts.append(f"{rest} other thread{'s' if rest > 1 else ''} appeared only once")
            details["recurrence"] = ". ".join(parts) + "."
        else:
            details["recurrence"] = f"Each of the {len(stage_threads)} issue threads appeared only once \u2014 no recurring problems detected."
    else:
        details["recurrence"] = "No signal threads to analyze for recurrence."

    # 3. Escalation rate (aligned: detect_escalation, within-thread severity)
    escalation_results = detect_escalation(all_sigs, stage_topic)

    stage_severity_signals = [s for s in signals if s.severity and s.severity in SEVERITY_ORDER]
    if len(stage_severity_signals) < 2:
        escalation_score = 75.0
        details["escalation"] = (
            f"Only {len(stage_severity_signals)} signal{'s' if len(stage_severity_signals) != 1 else ''} "
            f"with severity \u2014 not enough to measure whether issues escalated over time."
        )
    elif escalation_results:
        escalation_rate = len(escalation_results) / max(len(stage_severity_signals) - 1, 1)
        escalation_score = max(0.0, min(100.0, 100.0 - escalation_rate * 100))
        esc_parts: list[str] = []
        for sig, _thread, sev_from, sev_to in escalation_results[:2]:
            esc_parts.append(
                f"'{_label(sig)}' escalated from {sev_from} to {sev_to}, "
                f"indicating the situation worsened"
            )
        rest = len(escalation_results) - len(esc_parts)
        tail = f" {rest} more escalation{'s' if rest > 1 else ''} also detected." if rest > 0 else ""
        details["escalation"] = ". ".join(esc_parts) + "." + tail
    else:
        escalation_score = 100.0
        details["escalation"] = (
            f"Across {len(stage_severity_signals)} signals with severity, "
            f"no within-thread escalation occurred."
        )

    # 4. Resolution velocity (aligned: _pair_tickets cross-stage) -----------
    all_pairs = _pair_tickets(all_sigs)
    paired_created_ids = {id(c) for c, r in all_pairs}
    created_in_stage = [s for s in signals if s.event_type == "ticket_created"]

    if not created_in_stage:
        resolution_score = 75.0
        details["resolution"] = "No tickets were created in this stage, so resolution cannot be measured."
    else:
        matched = sum(1 for s in created_in_stage if id(s) in paired_created_ids)
        resolution_score = (matched / len(created_in_stage)) * 100

        resolved_titles: list[str] = [_label(s) for s in created_in_stage if id(s) in paired_created_ids]
        unresolved_titles: list[str] = [_label(s) for s in created_in_stage if id(s) not in paired_created_ids]

        parts = []
        if resolved_titles:
            labels = " and ".join(f"'{t}'" for t in resolved_titles[:2])
            more = f" (and {len(resolved_titles) - 2} more)" if len(resolved_titles) > 2 else ""
            parts.append(f"{labels}{more} {'were' if len(resolved_titles) > 1 else 'was'} resolved")
        if unresolved_titles:
            labels = " and ".join(f"'{t}'" for t in unresolved_titles[:2])
            more = f" (and {len(unresolved_titles) - 2} more)" if len(unresolved_titles) > 2 else ""
            parts.append(f"{labels}{more} {'remain' if len(unresolved_titles) > 1 else 'remains'} open")
        details["resolution"] = ". ".join(parts) + "." if parts else "No resolution data."

    # 5. Effort (aligned: core/peripheral classification) --------------------
    effort_results = detect_effort(signals)
    peripheral_count = sum(1 for _, cls, _ in effort_results if cls == "peripheral")
    core_count = sum(1 for _, cls, _ in effort_results if cls == "core")
    total = len(effort_results)

    if total == 0:
        effort_score = 75.0
        details["effort"] = "No signals in this stage, so effort distribution cannot be measured."
    else:
        peripheral_ratio = peripheral_count / total
        effort_score = max(0.0, min(100.0, 100.0 - peripheral_ratio * 100))

        if peripheral_ratio < 0.15:
            details["effort"] = (
                f"Nearly all signals ({core_count} of {total}) represent core product work, "
                f"suggesting productive effort."
            )
        elif peripheral_ratio > 0.5:
            cat_counter: dict[str, int] = defaultdict(int)
            for _, cls, cat in effort_results:
                if cls == "peripheral" and cat:
                    cat_counter[cat] += 1
            top = sorted(cat_counter.items(), key=lambda x: x[1], reverse=True)[:2]
            cat_desc = ", ".join(f"{c} ({n})" for c, n in top)
            details["effort"] = (
                f"{peripheral_count} of {total} signals are peripheral overhead "
                f"({cat_desc}), indicating significant non-core effort."
            )
        else:
            details["effort"] = (
                f"{core_count} core vs {peripheral_count} peripheral signals "
                f"\u2014 moderate overhead from non-core work."
            )

    scores = {
        "friction": round(friction_score, 1),
        "recurrence": round(recurrence_score, 1),
        "escalation": round(escalation_score, 1),
        "resolution": round(resolution_score, 1),
        "effort": round(effort_score, 1),
    }

    # Confidence: "high" when metric is computed from real data,
    # "low" when it fell back to a default due to insufficient data.
    confidence: dict[str, str] = {
        "friction": "high" if (negative or positive) else "low",
        "recurrence": "high" if stage_threads else "low",
        "escalation": "high" if len(stage_severity_signals) >= 2 else "low",
        "resolution": "high" if created_in_stage else "low",
        "effort": "high" if total > 0 else "low",
    }

    return scores, details, confidence


def _combine_smoothness_score(metrics: dict[str, float], stage_name: str) -> float:
    """Combine sub-metrics into a single 0-100 smoothness score."""
    weights = STAGE_SMOOTHNESS_WEIGHTS.get(stage_name, STAGE_SMOOTHNESS_WEIGHTS["productive"])
    return sum(metrics[k] * weights[k] for k in weights)


def _generate_explanation(
    stage_name: str, metrics: dict[str, float], smoothness: float, signal_count: int,
) -> str:
    """Generate a human-readable explanation for stage smoothness."""
    quality = "smooth" if smoothness >= 70 else "moderate" if smoothness >= 40 else "rough"

    worst_metric = min(metrics, key=lambda k: metrics[k])
    worst_labels = {
        "friction": "high issue friction",
        "recurrence": "recurring issues",
        "escalation": "escalating severity",
        "resolution": "slow resolution",
        "effort": "high communication effort",
    }

    explanation = f"{stage_name.title()} was {quality} ({signal_count} signal{'s' if signal_count != 1 else ''}). "
    if smoothness < 70:
        explanation += f"Main concern: {worst_labels.get(worst_metric, worst_metric)}."
    else:
        explanation += "No major concerns."

    return explanation


def _empty_trajectory() -> dict:
    """Return empty trajectory when no signals exist."""
    return {
        "current_stage": "onboarding",
        "stages": [
            {
                "name": stage,
                "status": "current" if stage == "onboarding" else "upcoming",
                "signal_count": 0,
                "smoothness_score": None,
                "date_range": None,
                "explanation": "No signals yet." if stage == "onboarding" else "Not reached yet.",
                "metrics": None,
            }
            for stage in STAGES
        ],
        "regression_detected": False,
        "regression_detail": None,
        "overall_smoothness": 50.0,
        "confidence": "preliminary",
    }


# ---------------------------------------------------------------------------
# Peer benchmarks
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "our", "the", "to", "we", "with",
})


def _tokenize_use(text: str | None) -> set[str]:
    if not text:
        return set()
    return {w for w in text.lower().split() if w not in _STOP_WORDS and len(w) > 2}


async def _find_peer_registrations(
    db: AsyncSession,
    vendor_name: str,
    software_name: str,
    intended_use: str | None,
) -> tuple[list[SoftwareRegistration], str | None]:
    """Find peer software registrations for benchmarking.

    Strategy:
    1. Match by auto_category from IntelligenceCache (strongest signal).
    2. Fallback: match by intended_use keyword overlap.

    Returns (peer_registrations, match_label).
    """
    from app.intelligence.models import IntelligenceCache

    # Strategy 1: IntelligenceCache auto_category
    result = await db.execute(
        select(IntelligenceCache.auto_category).where(
            IntelligenceCache.vendor_name == vendor_name,
            IntelligenceCache.software_name == software_name,
        )
    )
    category = result.scalar_one_or_none()

    if category:
        result = await db.execute(
            select(
                IntelligenceCache.vendor_name,
                IntelligenceCache.software_name,
            ).where(
                IntelligenceCache.auto_category == category,
                or_(
                    IntelligenceCache.vendor_name != vendor_name,
                    IntelligenceCache.software_name != software_name,
                ),
            ).limit(20)
        )
        peer_products = result.all()

        if peer_products:
            conditions = [
                and_(
                    SoftwareRegistration.vendor_name == vn,
                    SoftwareRegistration.software_name == sn,
                    SoftwareRegistration.status == "active",
                )
                for vn, sn in peer_products
            ]
            result = await db.execute(
                select(SoftwareRegistration).where(or_(*conditions))
            )
            peers = list(result.scalars().all())
            if peers:
                return peers, category

    # Strategy 2: intended_use keyword overlap
    if not intended_use:
        return [], None

    own_tokens = _tokenize_use(intended_use)
    if not own_tokens:
        return [], None

    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.status == "active",
            SoftwareRegistration.intended_use.isnot(None),
            or_(
                SoftwareRegistration.vendor_name != vendor_name,
                SoftwareRegistration.software_name != software_name,
            ),
        ).limit(100)
    )
    candidates = result.scalars().all()

    scored: list[tuple[SoftwareRegistration, float]] = []
    for reg in candidates:
        peer_tokens = _tokenize_use(reg.intended_use)
        if not peer_tokens:
            continue
        overlap = len(own_tokens & peer_tokens)
        similarity = overlap / min(len(own_tokens), len(peer_tokens))
        if similarity >= 0.4:
            scored.append((reg, similarity))

    scored.sort(key=lambda x: x[1], reverse=True)
    peers = [reg for reg, _ in scored[:20]]
    if peers:
        return peers, f"similar use case"

    return [], None


def _benchmark_stat(
    own_score: float | None, peer_scores: list[float],
) -> dict | None:
    if not peer_scores or own_score is None:
        return None
    avg = sum(peer_scores) / len(peer_scores)
    med = statistics.median(peer_scores)
    below = sum(1 for s in peer_scores if own_score > s)
    percentile = int((below / len(peer_scores)) * 100)
    return {
        "average": round(avg, 1),
        "median": round(med, 1),
        "percentile": percentile,
        "peer_count": len(peer_scores),
    }


async def _compute_benchmarks(
    db: AsyncSession,
    software_id: uuid.UUID,
    vendor_name: str,
    software_name: str,
    own_stages: list[dict],
    own_overall: float,
) -> dict | None:
    """Compute benchmark comparisons against alternative software across all companies."""
    from app.signals.models import HealthScore

    # Look up intended_use for fallback matching
    result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, vendor_name, software_name, intended_use,
    )
    if not peer_regs:
        return None

    peer_reg_ids = [r.id for r in peer_regs]
    reg_map = {r.id: r for r in peer_regs}

    # --- Strategy 1: Read stored trajectory data from latest HealthScore ---
    peer_overall_scores: list[float] = []
    peer_stage_scores: dict[str, list[float]] = defaultdict(list)
    peer_metric_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    regs_needing_fallback: list[uuid.UUID] = []

    # Fetch latest HealthScore with trajectory_data for each peer
    for reg_id in peer_reg_ids:
        hs_result = await db.execute(
            select(HealthScore.trajectory_data).where(
                HealthScore.software_id == reg_id,
                HealthScore.trajectory_data.isnot(None),
            ).order_by(HealthScore.created_at.desc()).limit(1)
        )
        td = hs_result.scalar_one_or_none()

        if td and isinstance(td, dict) and td.get("stages"):
            # Use stored trajectory scores
            stage_scores_for_peer: dict[str, float] = {}
            for stage_data in td["stages"]:
                sname = stage_data.get("name")
                sscore = stage_data.get("smoothness_score")
                smetrics = stage_data.get("metrics")
                if sname and sscore is not None:
                    peer_stage_scores[sname].append(round(sscore, 1))
                    stage_scores_for_peer[sname] = sscore
                    if smetrics:
                        for mk, mv in smetrics.items():
                            if mv is not None:
                                peer_metric_scores[sname][mk].append(round(mv, 1))
            scored = list(stage_scores_for_peer.values())
            if scored:
                peer_overall_scores.append(round(sum(scored) / len(scored), 1))
        else:
            regs_needing_fallback.append(reg_id)

    # --- Strategy 2: On-the-fly computation for peers without stored data ---
    if regs_needing_fallback:
        result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(regs_needing_fallback))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        signals_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            signals_by_sw[sig.software_id].append(sig)

        from app.signals.classification import _deterministic_classify

        for sw_id, sigs in signals_by_sw.items():
            if not sigs:
                continue
            reg = reg_map.get(sw_id)
            if not reg:
                continue

            reg_at = reg.created_at
            if reg_at and reg_at.tzinfo is None:
                reg_at = reg_at.replace(tzinfo=timezone.utc)

            for sig in sigs:
                if "valence" not in (sig.event_metadata or {}):
                    occ = sig.occurred_at
                    if occ and occ.tzinfo is None:
                        occ = occ.replace(tzinfo=timezone.utc)
                    days = max(0, (occ - reg_at).days) if reg_at and occ else 0
                    tags = _deterministic_classify(
                        sig.source_type, sig.event_type, sig.severity,
                        sig.title, sig.body, days,
                    )
                    meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                    meta.update(tags)
                    sig.event_metadata = meta

            timeline = _build_stage_timeline(sigs)
            stage_scores_for_peer = {}
            for stage_name in STAGES:
                stage_sigs = timeline["stage_signals"].get(stage_name, [])
                if stage_sigs:
                    metrics, _, _ = _compute_smoothness(stage_sigs, all_signals=sigs, stage_topic=stage_name)
                    score = _combine_smoothness_score(metrics, stage_name)
                    peer_stage_scores[stage_name].append(round(score, 1))
                    stage_scores_for_peer[stage_name] = score
                    for metric_name, metric_val in metrics.items():
                        peer_metric_scores[stage_name][metric_name].append(round(metric_val, 1))

            scored = list(stage_scores_for_peer.values())
            if scored:
                peer_overall_scores.append(round(sum(scored) / len(scored), 1))

    if not peer_overall_scores:
        return None

    # Build benchmark comparisons
    stage_benchmarks: dict[str, dict] = {}
    for stage_name in STAGES:
        own_stage = next((s for s in own_stages if s["name"] == stage_name), None)
        own_score = own_stage["smoothness_score"] if own_stage else None
        bm = _benchmark_stat(own_score, peer_stage_scores.get(stage_name, []))
        if bm:
            # Add per-metric benchmarks
            own_metrics = own_stage.get("metrics") if own_stage else None
            if own_metrics and stage_name in peer_metric_scores:
                metric_bms: dict[str, dict] = {}
                for mk in ("friction", "recurrence", "escalation", "resolution", "effort"):
                    own_mv = own_metrics.get(mk)
                    peer_vals = peer_metric_scores[stage_name].get(mk, [])
                    mbm = _benchmark_stat(own_mv, peer_vals)
                    if mbm:
                        metric_bms[mk] = mbm
                if metric_bms:
                    bm["metrics"] = metric_bms
            stage_benchmarks[stage_name] = bm

    overall_bm = _benchmark_stat(own_overall, peer_overall_scores)

    return {
        "category": match_label,
        "peer_count": len(peer_overall_scores),
        "overall": overall_bm,
        "stages": stage_benchmarks,
    }


async def compute_trajectory_benchmarks(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> dict | None:
    """Compute trajectory benchmarks for stored trajectory data.

    Fetches the software registration details and the latest stored
    trajectory data, then delegates to ``_compute_benchmarks``.
    """
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return None

    # Try stored trajectory first
    from app.signals.models import HealthScore

    hs_result = await db.execute(
        select(HealthScore)
        .where(
            HealthScore.company_id == company_id,
            HealthScore.software_id == software_id,
        )
        .order_by(HealthScore.created_at.desc())
        .limit(1)
    )
    latest_hs = hs_result.scalar_one_or_none()

    if latest_hs and latest_hs.trajectory_data:
        td = latest_hs.trajectory_data
        return await _compute_benchmarks(
            db, software_id, software.vendor_name, software.software_name,
            td.get("stages", []), td.get("overall_smoothness", 50.0),
        )

    # Fallback: compute trajectory from scratch for benchmark input
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))
    if not signals:
        return None

    timeline = _build_stage_timeline(signals)
    stages_output = []
    for stage_name in STAGES:
        stage_sigs = timeline["stage_signals"].get(stage_name, [])
        if not stage_sigs:
            stages_output.append({"name": stage_name, "smoothness_score": None, "metrics": None})
            continue
        metrics, _, _ = _compute_smoothness(stage_sigs, all_signals=signals, stage_topic=stage_name)
        smoothness = _combine_smoothness_score(metrics, stage_name)
        stages_output.append({"name": stage_name, "smoothness_score": round(smoothness, 1), "metrics": metrics})

    scored = [s for s in stages_output if s["smoothness_score"] is not None]
    overall = sum(s["smoothness_score"] for s in scored) / len(scored) if scored else 50.0

    return await _compute_benchmarks(
        db, software_id, software.vendor_name, software.software_name,
        stages_output, round(overall, 1),
    )


async def compute_health_score_benchmarks(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> dict | None:
    """Compute health score benchmarks against peer software registrations."""
    from app.signals.models import HealthScore

    # Get own latest health score
    result = await db.execute(
        select(HealthScore).where(
            HealthScore.company_id == company_id,
            HealthScore.software_id == software_id,
        ).order_by(HealthScore.created_at.desc()).limit(1)
    )
    own_hs = result.scalar_one_or_none()
    if not own_hs:
        return None

    # Get software for peer lookup
    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = result.scalar_one_or_none()
    if not software:
        return None

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, software.intended_use,
    )
    if not peer_regs:
        return None

    peer_reg_ids = [r.id for r in peer_regs]

    # Get latest health score per peer registration using a subquery
    from sqlalchemy import func as sa_func
    latest_hs_subq = (
        select(
            HealthScore.software_id,
            sa_func.max(HealthScore.created_at).label("max_created"),
        )
        .where(HealthScore.software_id.in_(peer_reg_ids))
        .group_by(HealthScore.software_id)
        .subquery()
    )
    result = await db.execute(
        select(HealthScore).join(
            latest_hs_subq,
            (HealthScore.software_id == latest_hs_subq.c.software_id)
            & (HealthScore.created_at == latest_hs_subq.c.max_created),
        )
    )
    peer_scores = list(result.scalars().all())

    if not peer_scores:
        return None

    # Overall score benchmark
    peer_overall = [hs.score for hs in peer_scores if hs.score is not None]
    overall_bm = _benchmark_stat(own_hs.score, peer_overall)

    # Per-category benchmarks
    own_breakdown = own_hs.category_breakdown or {}
    category_keys = list(own_breakdown.keys())
    category_bms: dict[str, dict] = {}
    for cat in category_keys:
        own_val = own_breakdown.get(cat)
        peer_vals = []
        for hs in peer_scores:
            bd = hs.category_breakdown or {}
            if cat in bd and bd[cat] is not None:
                peer_vals.append(bd[cat])
        bm = _benchmark_stat(own_val, peer_vals)
        if bm:
            category_bms[cat] = bm

    return {
        "category": match_label,
        "peer_count": len(peer_scores),
        "overall": overall_bm,
        "categories": category_bms,
    }


# ---------------------------------------------------------------------------
# Issue rate over time (rolling 7-day window)
# ---------------------------------------------------------------------------


def _rolling_7day_counts(
    signals: list[SignalEvent],
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Compute rolling 7-day issue count for each day in [start_date, end_date]."""
    daily: dict[date, int] = defaultdict(int)
    for sig in signals:
        if sig.occurred_at:
            d = sig.occurred_at.date() if isinstance(sig.occurred_at, datetime) else sig.occurred_at
            daily[d] += 1

    points: list[dict] = []
    current = start_date
    while current <= end_date:
        window_start = current - timedelta(days=6)
        count = sum(daily.get(window_start + timedelta(days=i), 0) for i in range(7))
        points.append({"date": current.isoformat(), "count": count})
        current += timedelta(days=1)
    return points


def _issue_rate_commentary(
    points: list[dict],
    days_since_reg: int,
    software_name: str,
) -> dict:
    """Generate trend commentary for the issue rate curve."""
    if len(points) < 7:
        return {
            "trend": "stable",
            "message": f"Not enough data yet to determine a trend for {software_name}.",
        }

    recent_7 = sum(p["count"] for p in points[-7:])
    prev_7 = sum(p["count"] for p in points[-14:-7]) if len(points) >= 14 else recent_7

    if prev_7 == 0 and recent_7 == 0:
        return {
            "trend": "stable",
            "message": f"No new issues in the last two weeks for {software_name}.",
        }

    if prev_7 == 0:
        change_pct = 100.0
    else:
        change_pct = ((recent_7 - prev_7) / prev_7) * 100

    if change_pct <= -20:
        trend = "declining"
        message = (
            f"Issue rate for {software_name} is declining "
            f"({prev_7} issues last week vs {recent_7} this week). "
            f"A declining curve means the integration is stabilizing."
        )
    elif change_pct >= 20:
        trend = "increasing"
        message = (
            f"Issue rate for {software_name} is increasing "
            f"({prev_7} issues last week vs {recent_7} this week). "
        )
        if days_since_reg > 45:
            message += (
                f"This is a red flag \u2014 {software_name} has been registered for "
                f"{days_since_reg} days and should be past the early teething phase."
            )
        else:
            message += (
                f"This may be expected since {software_name} was registered only "
                f"{days_since_reg} days ago and is likely still in early adoption."
            )
    else:
        trend = "stable"
        message = (
            f"Issue rate for {software_name} has been steady "
            f"(~{recent_7} issues per week)."
        )

    return {"trend": trend, "message": message}


async def compute_issue_rate(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Compute the rolling 7-day issue rate for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    # Fetch negative-valence signals (the "issues")
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    issues = [
        s for s in all_signals
        if (s.event_metadata or {}).get("valence") == "negative"
    ]

    # If no classification tags yet, fall back to ticket_created events
    if not issues:
        issues = [s for s in all_signals if s.event_type == "ticket_created"]

    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    today = datetime.now(timezone.utc).date()
    start_date = reg_at.date() if reg_at else today - timedelta(days=90)
    days_since_reg = max(0, (today - start_date).days)

    # Extend at least 7 days for the rolling window to make sense
    if (today - start_date).days < 7:
        start_date = today - timedelta(days=7)

    points = _rolling_7day_counts(issues, start_date, today)
    commentary = _issue_rate_commentary(points, days_since_reg, software.software_name)

    # Peer comparison
    intended_use_result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = intended_use_result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, intended_use,
    )

    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        # Detach so in-memory edits aren't flushed
        for sig in all_peer_signals:
            db.expunge(sig)

        if stage_topic:
            all_peer_signals = [
                s for s in all_peer_signals
                if (s.event_metadata or {}).get("stage_topic") == stage_topic
            ]

        # Filter to negative-valence, fall back to ticket_created
        peer_issues = [
            s for s in all_peer_signals
            if (s.event_metadata or {}).get("valence") == "negative"
        ]
        if not peer_issues:
            peer_issues = [s for s in all_peer_signals if s.event_type == "ticket_created"]

        if peer_issues:
            # Compute average rolling counts across peers
            peer_daily: dict[date, int] = defaultdict(int)
            for sig in peer_issues:
                if sig.occurred_at:
                    d = sig.occurred_at.date() if isinstance(sig.occurred_at, datetime) else sig.occurred_at
                    peer_daily[d] += 1

            # Average by number of peer registrations
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            current = start_date
            while current <= today:
                window_start = current - timedelta(days=6)
                raw = sum(peer_daily.get(window_start + timedelta(days=i), 0) for i in range(7))
                peer_points.append({
                    "date": current.isoformat(),
                    "count": round(raw / n_peers),
                })
                current += timedelta(days=1)

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "days_since_registration": days_since_reg,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Issue recurrence rate over time (rolling 30-day window, weekly samples)
# ---------------------------------------------------------------------------


def _recurrence_at_date(
    signals: list[SignalEvent],
    sample_date: date,
    window_days: int = 30,
) -> tuple[float, int, int, list[str]]:
    """Compute recurrence rate for a 30-day window ending on sample_date.

    Returns (rate_pct, recurring_count, total_threads, top_topics).
    """
    window_start = sample_date - timedelta(days=window_days - 1)

    window_signals = [
        s for s in signals
        if s.occurred_at
        and window_start <= (s.occurred_at.date() if isinstance(s.occurred_at, datetime) else s.occurred_at) <= sample_date
    ]

    threads: dict[str, int] = {}
    for s in window_signals:
        norm = _normalize_title(s.title)
        if norm:
            threads[norm] = threads.get(norm, 0) + 1

    total = len(threads)
    if total == 0:
        return 0.0, 0, 0, []

    recurring_items = [(name, count) for name, count in threads.items() if count > 1]
    recurring_count = len(recurring_items)
    rate = (recurring_count / total) * 100

    # Top recurring topics sorted by frequency
    recurring_items.sort(key=lambda x: x[1], reverse=True)
    top_topics = [_truncate(name, 50) for name, _ in recurring_items[:3]]

    return round(rate, 1), recurring_count, total, top_topics


def _recurrence_commentary(
    points: list[dict],
    software_name: str,
) -> dict:
    """Generate trend commentary for recurrence rate."""
    if len(points) < 3:
        return {
            "trend": "stable",
            "message": f"Not enough data yet to determine a recurrence trend for {software_name}.",
        }

    recent = points[-1]["rate"]
    earlier = points[0]["rate"]

    if len(points) >= 4:
        recent_avg = sum(p["rate"] for p in points[-2:]) / 2
        earlier_avg = sum(p["rate"] for p in points[:2]) / 2
    else:
        recent_avg = recent
        earlier_avg = earlier

    diff = recent_avg - earlier_avg

    if diff <= -10:
        trend = "improving"
        message = (
            f"Recurrence rate for {software_name} is improving "
            f"(from {earlier_avg:.0f}% to {recent_avg:.0f}%). "
            f"Recurring issues are being resolved at their root causes."
        )
    elif diff >= 10:
        trend = "worsening"
        message = (
            f"Recurrence rate for {software_name} is worsening "
            f"(from {earlier_avg:.0f}% to {recent_avg:.0f}%). "
            f"Persistent recurrence on the same topics signals the vendor "
            f"isn\u2019t fixing root causes."
        )
    else:
        trend = "stable"
        message = (
            f"Recurrence rate for {software_name} has been steady "
            f"(around {recent_avg:.0f}%)."
        )

    # Append the latest recurring topics if any
    top = points[-1].get("top_topics", [])
    if top:
        topic_str = ", ".join(f"\u201c{t}\u201d" for t in top[:3])
        message += f" Current recurring topics: {topic_str}."

    return {"trend": trend, "message": message}


async def compute_recurrence_rate(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Compute rolling recurrence rate for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    # Fetch negative-valence signals (the issues that can recur)
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    issues = [
        s for s in all_signals
        if (s.event_metadata or {}).get("valence") == "negative"
    ]
    if not issues:
        issues = [s for s in all_signals if s.event_type == "ticket_created"]

    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    today = datetime.now(timezone.utc).date()
    start_date = reg_at.date() if reg_at else today - timedelta(days=90)

    # Need at least 30 days of data for the window
    if (today - start_date).days < 30:
        start_date = today - timedelta(days=30)

    # Sample weekly: every 7 days from start+30 to today
    first_sample = start_date + timedelta(days=29)  # first full 30-day window
    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        rate, recurring, total, topics = _recurrence_at_date(issues, sample)
        points.append({
            "date": sample.isoformat(),
            "rate": rate,
            "recurring_count": recurring,
            "total_threads": total,
            "top_topics": topics,
        })
        sample += timedelta(days=7)

    # Always include today as final point if not already there
    if points and points[-1]["date"] != today.isoformat():
        rate, recurring, total, topics = _recurrence_at_date(issues, today)
        points.append({
            "date": today.isoformat(),
            "rate": rate,
            "recurring_count": recurring,
            "total_threads": total,
            "top_topics": topics,
        })

    if not points:
        rate, recurring, total, topics = _recurrence_at_date(issues, today)
        points.append({
            "date": today.isoformat(),
            "rate": rate,
            "recurring_count": recurring,
            "total_threads": total,
            "top_topics": topics,
        })

    commentary = _recurrence_commentary(points, software.software_name)

    # Peer comparison
    intended_use_result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = intended_use_result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, intended_use,
    )

    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        if stage_topic:
            all_peer_signals = [
                s for s in all_peer_signals
                if (s.event_metadata or {}).get("stage_topic") == stage_topic
            ]

        peer_issues = [
            s for s in all_peer_signals
            if (s.event_metadata or {}).get("valence") == "negative"
        ]
        if not peer_issues:
            peer_issues = [s for s in all_peer_signals if s.event_type == "ticket_created"]

        if peer_issues:
            n_peers = len(peer_regs)

            # Compute per-peer recurrence, then average
            peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
            for sig in peer_issues:
                peer_by_sw[sig.software_id].append(sig)

            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                rates: list[float] = []
                for sw_sigs in peer_by_sw.values():
                    rate_val, _, _, _ = _recurrence_at_date(sw_sigs, sample)
                    rates.append(rate_val)
                avg_rate = sum(rates) / len(rates) if rates else 0.0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_rate),  # rate as int for PeerRecurrenceRate
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                rates = []
                for sw_sigs in peer_by_sw.values():
                    rate_val, _, _, _ = _recurrence_at_date(sw_sigs, today)
                    rates.append(rate_val)
                avg_rate = sum(rates) / len(rates) if rates else 0.0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_rate),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Resolution time over time
# ---------------------------------------------------------------------------


def _pair_tickets(
    signals: list[SignalEvent],
) -> list[tuple[SignalEvent, SignalEvent]]:
    """Pair ticket_created/ticket_reopened with ticket_resolved events.

    Groups lifecycle signals by source_id (primary) or normalized title
    (fallback), sorts each group chronologically, and pairs each created/
    reopened with the next resolved that follows it.  This correctly handles
    multiple create→resolve→reopen→resolve cycles on the same ticket.

    Returns list of (created, resolved) tuples.
    """
    _CREATED_TYPES = {"ticket_created", "ticket_reopened"}
    _LIFECYCLE_TYPES = _CREATED_TYPES | {"ticket_resolved"}

    # Group lifecycle signals by source_id, with title as fallback key
    groups: dict[str, list[SignalEvent]] = {}
    for s in signals:
        if s.event_type not in _LIFECYCLE_TYPES:
            continue
        key = s.source_id or _normalize_title(s.title) or ""
        if key:
            groups.setdefault(key, []).append(s)

    pairs: list[tuple[SignalEvent, SignalEvent]] = []
    used: set[uuid.UUID] = set()

    for _key, group in groups.items():
        group.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))
        pending: SignalEvent | None = None
        for s in group:
            if s.event_type in _CREATED_TYPES:
                pending = s
            elif s.event_type == "ticket_resolved" and pending and pending.id not in used:
                pairs.append((pending, s))
                used.add(pending.id)
                used.add(s.id)
                pending = None

    return pairs


def _ticket_category(sig: SignalEvent) -> str:
    """Classify a created ticket as 'issue' or 'feature'."""
    meta = sig.event_metadata or {}
    subject = meta.get("subject")

    if subject == "vendor_issue":
        return "issue"
    if subject in ("internal_impl", "vendor_request"):
        return "feature"

    if meta.get("valence") == "negative":
        return "issue"

    if sig.event_type == "feature_request":
        return "feature"

    return "issue"


# ---------------------------------------------------------------------------
# Shared detection functions — single source of truth for signal selection.
# Used by _compute_smoothness (scoring), summarizer pipeline, and
# compute_*_events timeline endpoints.
# ---------------------------------------------------------------------------


def detect_friction_signals(
    stage_signals: list[SignalEvent],
) -> list[SignalEvent]:
    """Return negative + positive valence signals (same as compute_friction_events)."""
    return [
        s for s in stage_signals
        if (s.event_metadata or {}).get("valence") in ("negative", "positive")
    ]


def detect_recurrence(
    all_signals: list[SignalEvent],
    stage_topic: str | None = None,
) -> list[tuple[SignalEvent, str, int, int, str]]:
    """Detect recurring issue signals (2nd+ incidents in title threads).

    Returns ``[(signal, thread_topic, incident_number, total_incidents, first_seen), ...]``.
    Groups ALL signals by normalized title, splits into incidents via
    ``_split_into_incidents``, and collects signals from the 2nd+ incidents.
    Same logic as ``compute_recurrence_events``.
    """
    threads: dict[str, list[SignalEvent]] = {}
    for s in all_signals:
        norm = _normalize_title(s.title)
        if norm:
            threads.setdefault(norm, []).append(s)

    results: list[tuple[SignalEvent, str, int, int, str]] = []
    for thread_topic, sigs in threads.items():
        sigs.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))
        incidents = _split_into_incidents(sigs)
        if len(incidents) < 2:
            continue
        first_seen = ""
        if incidents[0] and incidents[0][0].occurred_at:
            first_seen = incidents[0][0].occurred_at.strftime("%b %d")
        for inc_idx, incident in enumerate(incidents[1:], start=2):
            for s in incident:
                results.append((s, thread_topic, inc_idx, len(incidents), first_seen))

    if stage_topic:
        results = [
            t for t in results
            if (t[0].event_metadata or {}).get("stage_topic") == stage_topic
        ]
    return results


def detect_escalation(
    all_signals: list[SignalEvent],
    stage_topic: str | None = None,
) -> list[tuple[SignalEvent, str, str, str]]:
    """Detect within-thread severity escalation signals.

    Returns ``[(signal, thread_topic, severity_from, severity_to), ...]``.
    Groups ALL signals with severity by normalized title, detects within-thread
    severity increases.  Same logic as ``compute_escalation_events``.
    """
    threads: dict[str, list[SignalEvent]] = defaultdict(list)
    for s in all_signals:
        if s.severity and s.severity in SEVERITY_ORDER:
            norm = _normalize_title(s.title)
            if norm:
                threads[norm].append(s)

    results: list[tuple[SignalEvent, str, str, str]] = []
    for thread_title, thread_sigs in threads.items():
        thread_sigs.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))
        current_sev = SEVERITY_ORDER.get(thread_sigs[0].severity or "", 0)
        current_sev_name = thread_sigs[0].severity or "low"
        for sig in thread_sigs[1:]:
            sev = SEVERITY_ORDER.get(sig.severity or "", 0)
            if sev > current_sev:
                results.append((sig, thread_title, current_sev_name, sig.severity or "unknown"))
                current_sev_name = sig.severity or "unknown"
            current_sev = max(current_sev, sev)

    if stage_topic:
        results = [
            t for t in results
            if (t[0].event_metadata or {}).get("stage_topic") == stage_topic
        ]
    return results


def detect_resolution(
    all_signals: list[SignalEvent],
    stage_topic: str | None = None,
) -> list[tuple[SignalEvent, SignalEvent, str, float]]:
    """Detect resolved ticket pairs.

    Returns ``[(resolved_signal, created_signal, category, hours), ...]``.
    Pairs across ALL signals via ``_pair_tickets``, optionally filters to
    pairs where the *resolved* signal's ``stage_topic`` matches.
    Same logic as ``compute_resolution_events``.
    """
    pairs = _pair_tickets(all_signals)
    results: list[tuple[SignalEvent, SignalEvent, str, float]] = []
    for created, resolved in pairs:
        hours = (resolved.occurred_at - created.occurred_at).total_seconds() / 3600
        cat = _ticket_category(created)
        results.append((resolved, created, cat, hours))

    if stage_topic:
        results = [
            t for t in results
            if (t[0].event_metadata or {}).get("stage_topic") == stage_topic
        ]
    return results


def detect_effort(
    stage_signals: list[SignalEvent],
) -> list[tuple[SignalEvent, str, str | None]]:
    """Classify signals as core or peripheral for effort analysis.

    Returns ``[(signal, classification, peripheral_category), ...]``.
    Same logic as ``compute_effort_events``.
    """
    return [(s, *_classify_core_peripheral(s)) for s in stage_signals]


# ---------------------------------------------------------------------------
# Health sub-category detect functions (shared by timeline + summarizer)
# ---------------------------------------------------------------------------

_PERFORMANCE_DETECT_KW: list[str] = [
    "latency", "slow", "timeout", "rate limit", "throttl",
    "throughput", "response time", "performance", "speed",
    "lag", "bottleneck", "load", "capacity",
    "degradation", "delay", "queue", "backlog",
]


def detect_reliability_signals(
    signals: list[SignalEvent],
) -> list[SignalEvent]:
    """Filter to incident-related signals (same as compute_reliability_events).

    Uses ``INCIDENT_KEYWORDS`` keyword matching on title+body.
    """
    return [s for s in signals if _is_incident_signal(s)]


def detect_performance_signals(
    signals: list[SignalEvent],
) -> list[SignalEvent]:
    """Filter to performance-related signals (same as compute_performance_events).

    Checks LLM-extracted ``performance_tags`` when available (set by the
    performance timeline endpoint).  Falls back to keyword matching for
    signals that haven't been through the extraction pipeline yet.
    """
    results: list[SignalEvent] = []
    for s in signals:
        tags = (s.event_metadata or {}).get("performance_tags")
        if tags is not None:
            if tags.get("has_latency") or tags.get("has_rate_limit"):
                results.append(s)
        else:
            text = " ".join(filter(None, [s.title, s.body])).lower()
            if any(kw in text for kw in _PERFORMANCE_DETECT_KW):
                results.append(s)
    return results


def detect_fitness_signals(
    signals: list[SignalEvent],
) -> list[SignalEvent]:
    """Filter to fitness/feature-request signals (same as compute_fitness_events).

    Returns vendor_request signals plus fulfillment signals (positive-valence
    signals in the same thread as a request).
    """
    request_titles: set[str] = set()
    for s in signals:
        if (s.event_metadata or {}).get("subject") == "vendor_request":
            title = _normalize_title(s.title or "")
            if title:
                request_titles.add(title)

    results: list[SignalEvent] = []
    for s in signals:
        meta = s.event_metadata or {}
        title = _normalize_title(s.title or "")
        if meta.get("subject") == "vendor_request":
            results.append(s)
        elif title in request_titles and meta.get("valence") == "positive":
            results.append(s)
    return results


def _resolution_time_at_date(
    pairs: list[tuple[SignalEvent, SignalEvent]],
    sample_date: date,
    window_days: int = 30,
) -> tuple[float | None, float | None, int]:
    """Compute median and P90 resolution hours for pairs resolved in window.

    Returns (median_hours, p90_hours, pair_count).
    """
    window_start = sample_date - timedelta(days=window_days - 1)

    durations: list[float] = []
    for created, resolved in pairs:
        rd = resolved.occurred_at.date() if isinstance(resolved.occurred_at, datetime) else resolved.occurred_at
        if window_start <= rd <= sample_date:
            hours = (resolved.occurred_at - created.occurred_at).total_seconds() / 3600
            durations.append(hours)

    if not durations:
        return None, None, 0

    durations.sort()
    med = statistics.median(durations)
    idx = min(int(len(durations) * 0.9), len(durations) - 1)
    p90 = durations[idx]

    return round(med, 1), round(p90, 1), len(durations)


def _resolution_time_commentary(
    points: list[dict],
    category: str,
    software_name: str,
) -> dict:
    """Generate trend commentary for resolution time."""
    label = "issue" if category == "issue" else "feature implementation"

    valid = [p for p in points if p["median_hours"] is not None]
    if len(valid) < 3:
        return {
            "trend": "stable",
            "message": f"Not enough resolved {label} tickets to determine a trend for {software_name}.",
        }

    mid = len(valid) // 2
    earlier_avg = sum(p["median_hours"] for p in valid[:mid]) / mid
    recent_avg = sum(p["median_hours"] for p in valid[mid:]) / (len(valid) - mid)

    if earlier_avg == 0:
        diff_pct = 0.0
    else:
        diff_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100

    if diff_pct <= -15:
        trend = "improving"
        message = (
            f"Resolution time for {label} tickets on {software_name} is improving "
            f"(median dropped from {earlier_avg:.0f}h to {recent_avg:.0f}h). "
            f"The vendor is resolving {label}s faster."
        )
    elif diff_pct >= 15:
        trend = "worsening"
        message = (
            f"Resolution time for {label} tickets on {software_name} is worsening "
            f"(median rose from {earlier_avg:.0f}h to {recent_avg:.0f}h). "
            f"Slow resolution erodes the value of the integration."
        )
    else:
        trend = "stable"
        message = (
            f"Resolution time for {label} tickets on {software_name} has been steady "
            f"(around {recent_avg:.0f}h median)."
        )

    return {"trend": trend, "message": message}


async def compute_resolution_time(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Compute rolling resolution time metrics for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    # Pair tickets
    all_pairs = _pair_tickets(all_signals)

    # Split by category
    category_pairs: dict[str, list[tuple[SignalEvent, SignalEvent]]] = defaultdict(list)
    for created, resolved in all_pairs:
        cat = _ticket_category(created)
        category_pairs[cat].append((created, resolved))

    # Count unmatched created tickets per category
    paired_ids = {c.id for c, _ in all_pairs}
    all_created = [s for s in all_signals if s.event_type == "ticket_created"]
    unmatched_by_cat: dict[str, list[SignalEvent]] = defaultdict(list)
    for c in all_created:
        if c.id not in paired_ids:
            unmatched_by_cat[_ticket_category(c)].append(c)

    # Date range
    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    today = datetime.now(timezone.utc).date()
    start_date = reg_at.date() if reg_at else today - timedelta(days=90)
    days_since_reg = max(0, (today - start_date).days)

    if (today - start_date).days < 30:
        start_date = today - timedelta(days=30)

    first_sample = start_date + timedelta(days=29)

    # Build per-category results
    categories_output: list[dict] = []
    for cat in ["issue", "feature"]:
        pairs = category_pairs.get(cat, [])
        unmatched = unmatched_by_cat.get(cat, [])

        points: list[dict] = []
        sample = first_sample
        while sample <= today:
            med, p90, pair_count = _resolution_time_at_date(pairs, sample)
            open_count = sum(
                1 for c in unmatched
                if (c.occurred_at.date() if isinstance(c.occurred_at, datetime) else c.occurred_at) <= sample
            )
            points.append({
                "date": sample.isoformat(),
                "median_hours": med,
                "p90_hours": p90,
                "pair_count": pair_count,
                "open_count": open_count,
            })
            sample += timedelta(days=7)

        if points and points[-1]["date"] != today.isoformat():
            med, p90, pair_count = _resolution_time_at_date(pairs, today)
            points.append({
                "date": today.isoformat(),
                "median_hours": med,
                "p90_hours": p90,
                "pair_count": pair_count,
                "open_count": len(unmatched),
            })

        if not points:
            med, p90, pair_count = _resolution_time_at_date(pairs, today)
            points.append({
                "date": today.isoformat(),
                "median_hours": med,
                "p90_hours": p90,
                "pair_count": pair_count,
                "open_count": len(unmatched),
            })

        commentary = _resolution_time_commentary(points, cat, software.software_name)

        categories_output.append({
            "category": cat,
            "points": points,
            "commentary": commentary,
            "peer": None,
        })

    # Peer comparison
    intended_use_result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = intended_use_result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, intended_use,
    )

    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        if stage_topic:
            all_peer_signals = [
                s for s in all_peer_signals
                if (s.event_metadata or {}).get("stage_topic") == stage_topic
            ]

        # Group by software_id and pre-compute pairs per peer
        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        peer_pairs_by_sw: dict[uuid.UUID, dict[str, list[tuple[SignalEvent, SignalEvent]]]] = {}
        for sw_id, sw_sigs in peer_by_sw.items():
            sw_pairs = _pair_tickets(sw_sigs)
            cats: dict[str, list[tuple[SignalEvent, SignalEvent]]] = defaultdict(list)
            for c, r in sw_pairs:
                cats[_ticket_category(c)].append((c, r))
            peer_pairs_by_sw[sw_id] = dict(cats)

        n_peers = len(peer_regs)

        for cat_output in categories_output:
            cat = cat_output["category"]
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                medians: list[float] = []
                p90s: list[float] = []
                for sw_id, cats in peer_pairs_by_sw.items():
                    cat_pairs = cats.get(cat, [])
                    med, p90, count = _resolution_time_at_date(cat_pairs, sample)
                    if med is not None:
                        medians.append(med)
                    if p90 is not None:
                        p90s.append(p90)
                peer_points.append({
                    "date": sample.isoformat(),
                    "median_hours": round(statistics.median(medians), 1) if medians else None,
                    "p90_hours": round(statistics.median(p90s), 1) if p90s else None,
                    "pair_count": len(medians),
                    "open_count": 0,
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                medians = []
                p90s = []
                for sw_id, cats in peer_pairs_by_sw.items():
                    cat_pairs = cats.get(cat, [])
                    med, p90, count = _resolution_time_at_date(cat_pairs, today)
                    if med is not None:
                        medians.append(med)
                    if p90 is not None:
                        p90s.append(p90)
                peer_points.append({
                    "date": today.isoformat(),
                    "median_hours": round(statistics.median(medians), 1) if medians else None,
                    "p90_hours": round(statistics.median(p90s), 1) if p90s else None,
                    "pair_count": len(medians),
                    "open_count": 0,
                })

            cat_output["peer"] = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "categories": categories_output,
        "days_since_registration": days_since_reg,
    }


# ---------------------------------------------------------------------------
# Vendor responsiveness over time (rolling 30-day window, weekly samples)
# ---------------------------------------------------------------------------


def _pair_email_threads(
    signals: list[SignalEvent],
) -> tuple[
    list[tuple[SignalEvent, SignalEvent, float]],  # response_pairs: (outbound, inbound, lag_hours)
    list[SignalEvent],                              # proactive_inbounds
    list[SignalEvent],                              # unanswered_outbounds
]:
    """Pair outbound→inbound emails within conversation threads.

    Thread grouping is by normalized title. Within each thread, outbound
    messages are queued (FIFO) and matched to the next inbound reply.
    Inbound messages with no pending outbound are classified as proactive.
    """
    emails = [
        s for s in signals
        if s.source_type == "email" and (s.event_metadata or {}).get("direction")
    ]

    # Group by normalized title → conversation threads
    threads: dict[str, list[SignalEvent]] = defaultdict(list)
    for s in emails:
        norm = _normalize_title(s.title)
        if norm:
            threads[norm].append(s)

    response_pairs: list[tuple[SignalEvent, SignalEvent, float]] = []
    proactive_inbounds: list[SignalEvent] = []
    all_unanswered: list[SignalEvent] = []

    for _thread_key, thread_signals in threads.items():
        thread_signals.sort(key=lambda s: s.occurred_at)
        pending_outbounds: list[SignalEvent] = []

        for sig in thread_signals:
            direction = (sig.event_metadata or {}).get("direction")
            if direction == "outbound":
                pending_outbounds.append(sig)
            elif direction == "inbound":
                if pending_outbounds:
                    outbound = pending_outbounds.pop(0)  # FIFO — oldest first
                    lag = (sig.occurred_at - outbound.occurred_at).total_seconds() / 3600
                    if lag >= 0:
                        response_pairs.append((outbound, sig, lag))
                    else:
                        # Negative lag shouldn't happen; treat inbound as proactive
                        proactive_inbounds.append(sig)
                else:
                    proactive_inbounds.append(sig)

        all_unanswered.extend(pending_outbounds)

    return response_pairs, proactive_inbounds, all_unanswered


def _responsiveness_at_date(
    signals: list[SignalEvent],
    sample_date: date,
    window_days: int = 30,
) -> tuple[float | None, float | None, int, int, int]:
    """Compute responsiveness metrics for a 30-day window ending on sample_date.

    Returns (median_lag_hours, p90_lag_hours, response_count, proactive_count, unanswered_count).
    """
    window_start = sample_date - timedelta(days=window_days - 1)

    response_pairs, proactive_inbounds, unanswered_outbounds = _pair_email_threads(signals)

    # Filter response pairs: inbound occurred in window
    window_pairs = [
        (out, inb, lag) for out, inb, lag in response_pairs
        if window_start <= (inb.occurred_at.date() if isinstance(inb.occurred_at, datetime) else inb.occurred_at) <= sample_date
    ]

    # Filter proactive inbounds in window
    proactive_in_window = [
        s for s in proactive_inbounds
        if window_start <= (s.occurred_at.date() if isinstance(s.occurred_at, datetime) else s.occurred_at) <= sample_date
    ]

    # Unanswered: outbounds sent on or before sample_date that still have no reply
    unanswered_in_window = [
        s for s in unanswered_outbounds
        if (s.occurred_at.date() if isinstance(s.occurred_at, datetime) else s.occurred_at) <= sample_date
    ]

    if not window_pairs:
        return None, None, 0, len(proactive_in_window), len(unanswered_in_window)

    lags = sorted([lag for _, _, lag in window_pairs])
    med = round(statistics.median(lags), 1)
    idx = min(int(len(lags) * 0.9), len(lags) - 1)
    p90 = round(lags[idx], 1)

    return med, p90, len(window_pairs), len(proactive_in_window), len(unanswered_in_window)


def _responsiveness_commentary(
    points: list[dict],
    software_name: str,
) -> dict:
    """Generate trend commentary for vendor responsiveness."""
    valid = [p for p in points if p["median_lag_hours"] is not None]
    if len(valid) < 3:
        return {
            "trend": "stable",
            "message": f"Not enough email data to determine a responsiveness trend for {software_name}.",
        }

    mid = len(valid) // 2
    earlier_avg = sum(p["median_lag_hours"] for p in valid[:mid]) / mid
    recent_avg = sum(p["median_lag_hours"] for p in valid[mid:]) / (len(valid) - mid)

    if earlier_avg == 0:
        diff_pct = 0.0
    else:
        diff_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100

    if diff_pct <= -15:
        trend = "improving"
        message = (
            f"Vendor response time for {software_name} is improving "
            f"(median dropped from {earlier_avg:.0f}h to {recent_avg:.0f}h). "
            f"The vendor is replying faster."
        )
    elif diff_pct >= 15:
        trend = "worsening"
        message = (
            f"Vendor response time for {software_name} is worsening "
            f"(median rose from {earlier_avg:.0f}h to {recent_avg:.0f}h). "
            f"You\u2019re spending more time chasing the vendor."
        )
    else:
        trend = "stable"
        message = (
            f"Vendor response time for {software_name} has been steady "
            f"(around {recent_avg:.0f}h median)."
        )

    # Mention proactive inbounds if present in latest point
    latest = points[-1]
    if latest.get("proactive_count", 0) > 0:
        message += (
            f" The vendor also sent {latest['proactive_count']} proactive "
            f"communication{'s' if latest['proactive_count'] != 1 else ''} "
            f"(maintenance notices, updates) in the latest window\u2009\u2014\u2009a positive sign."
        )

    return {"trend": trend, "message": message}


async def compute_vendor_responsiveness(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
) -> dict:
    """Compute rolling vendor responsiveness metrics for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    today = datetime.now(timezone.utc).date()
    start_date = reg_at.date() if reg_at else today - timedelta(days=90)
    days_since_reg = max(0, (today - start_date).days)

    if (today - start_date).days < 30:
        start_date = today - timedelta(days=30)

    first_sample = start_date + timedelta(days=29)

    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        med, p90, resp_count, proactive, unanswered = _responsiveness_at_date(
            all_signals, sample,
        )
        points.append({
            "date": sample.isoformat(),
            "median_lag_hours": med,
            "p90_lag_hours": p90,
            "response_count": resp_count,
            "proactive_count": proactive,
            "unanswered_count": unanswered,
        })
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        med, p90, resp_count, proactive, unanswered = _responsiveness_at_date(
            all_signals, today,
        )
        points.append({
            "date": today.isoformat(),
            "median_lag_hours": med,
            "p90_lag_hours": p90,
            "response_count": resp_count,
            "proactive_count": proactive,
            "unanswered_count": unanswered,
        })

    if not points:
        med, p90, resp_count, proactive, unanswered = _responsiveness_at_date(
            all_signals, today,
        )
        points.append({
            "date": today.isoformat(),
            "median_lag_hours": med,
            "p90_lag_hours": p90,
            "response_count": resp_count,
            "proactive_count": proactive,
            "unanswered_count": unanswered,
        })

    commentary = _responsiveness_commentary(points, software.software_name)

    # Peer comparison
    intended_use_result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = intended_use_result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, intended_use,
    )

    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        # Group by software_id for per-peer computation
        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        n_peers = len(peer_regs)
        peer_points: list[dict] = []
        sample = first_sample
        while sample <= today:
            medians: list[float] = []
            p90s: list[float] = []
            proactive_counts: list[int] = []
            for sw_sigs in peer_by_sw.values():
                med_p, p90_p, _, proactive_p, _ = _responsiveness_at_date(sw_sigs, sample)
                if med_p is not None:
                    medians.append(med_p)
                if p90_p is not None:
                    p90s.append(p90_p)
                proactive_counts.append(proactive_p)
            peer_points.append({
                "date": sample.isoformat(),
                "median_lag_hours": round(statistics.median(medians), 1) if medians else None,
                "p90_lag_hours": round(statistics.median(p90s), 1) if p90s else None,
                "response_count": len(medians),
                "proactive_count": round(sum(proactive_counts) / len(proactive_counts)) if proactive_counts else 0,
                "unanswered_count": 0,
            })
            sample += timedelta(days=7)

        if peer_points and peer_points[-1]["date"] != today.isoformat():
            medians = []
            p90s = []
            proactive_counts = []
            for sw_sigs in peer_by_sw.values():
                med_p, p90_p, _, proactive_p, _ = _responsiveness_at_date(sw_sigs, today)
                if med_p is not None:
                    medians.append(med_p)
                if p90_p is not None:
                    p90s.append(p90_p)
                proactive_counts.append(proactive_p)
            peer_points.append({
                "date": today.isoformat(),
                "median_lag_hours": round(statistics.median(medians), 1) if medians else None,
                "p90_lag_hours": round(statistics.median(p90s), 1) if p90s else None,
                "response_count": len(medians),
                "proactive_count": round(sum(proactive_counts) / len(proactive_counts)) if proactive_counts else 0,
                "unanswered_count": 0,
            })

        peer_data = {
            "category": match_label,
            "peer_count": n_peers,
            "points": peer_points,
        }

    return {
        "points": points,
        "commentary": commentary,
        "days_since_registration": days_since_reg,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Severity escalation rate over time (rolling 30-day window, weekly samples)
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _detect_escalations(
    signals: list[SignalEvent],
) -> list[tuple[str, datetime]]:
    """Detect severity escalation events within conversation threads.

    Groups signals by normalized title, walks each thread chronologically,
    and records an escalation whenever severity increases compared to the
    previous event in the same thread.

    Returns list of (thread_title, escalation_date) tuples.
    """
    threads: dict[str, list[SignalEvent]] = defaultdict(list)
    for s in signals:
        if s.severity and s.severity in SEVERITY_ORDER:
            norm = _normalize_title(s.title)
            if norm:
                threads[norm].append(s)

    escalations: list[tuple[str, datetime]] = []

    for thread_title, thread_signals in threads.items():
        thread_signals.sort(key=lambda s: s.occurred_at)
        current_sev = SEVERITY_ORDER.get(thread_signals[0].severity or "", 0)

        for sig in thread_signals[1:]:
            sev = SEVERITY_ORDER.get(sig.severity or "", 0)
            if sev > current_sev:
                escalations.append((thread_title, sig.occurred_at))
            current_sev = max(current_sev, sev)

    return escalations


def _escalation_at_date(
    signals: list[SignalEvent],
    sample_date: date,
    window_days: int = 30,
) -> tuple[float, int, int, list[str]]:
    """Compute escalation rate for a 30-day window ending on sample_date.

    Returns (rate_pct, escalation_count, total_threads, top_escalations).
    """
    window_start = sample_date - timedelta(days=window_days - 1)

    # Active threads in window
    window_signals = [
        s for s in signals
        if s.occurred_at
        and s.severity and s.severity in SEVERITY_ORDER
        and window_start <= (s.occurred_at.date() if isinstance(s.occurred_at, datetime) else s.occurred_at) <= sample_date
    ]

    active_threads: set[str] = set()
    for s in window_signals:
        norm = _normalize_title(s.title)
        if norm:
            active_threads.add(norm)

    total = len(active_threads)
    if total == 0:
        return 0.0, 0, 0, []

    # Detect escalations from ALL signals (need full history for context),
    # but only count those whose escalation_date falls in the window
    all_escalations = _detect_escalations(signals)
    window_escalations: dict[str, int] = {}
    for title, esc_date in all_escalations:
        d = esc_date.date() if isinstance(esc_date, datetime) else esc_date
        if window_start <= d <= sample_date and title in active_threads:
            window_escalations[title] = window_escalations.get(title, 0) + 1

    escalation_count = len(window_escalations)
    rate = (escalation_count / total) * 100

    # Top escalating threads sorted by frequency
    sorted_esc = sorted(window_escalations.items(), key=lambda x: x[1], reverse=True)
    top_escalations = [_truncate(name, 50) for name, _ in sorted_esc[:3]]

    return round(rate, 1), escalation_count, total, top_escalations


def _escalation_commentary(
    points: list[dict],
    software_name: str,
) -> dict:
    """Generate trend commentary for escalation rate."""
    if len(points) < 3:
        return {
            "trend": "stable",
            "message": f"Not enough data yet to determine an escalation trend for {software_name}.",
        }

    recent = points[-1]["rate"]
    earlier = points[0]["rate"]

    if len(points) >= 4:
        recent_avg = sum(p["rate"] for p in points[-2:]) / 2
        earlier_avg = sum(p["rate"] for p in points[:2]) / 2
    else:
        recent_avg = recent
        earlier_avg = earlier

    diff = recent_avg - earlier_avg

    if diff <= -10:
        trend = "improving"
        message = (
            f"Escalation rate for {software_name} is declining "
            f"(from {earlier_avg:.0f}% to {recent_avg:.0f}%). "
            f"Initial severity assessments are becoming more accurate."
        )
    elif diff >= 10:
        trend = "worsening"
        message = (
            f"Escalation rate for {software_name} is rising "
            f"(from {earlier_avg:.0f}% to {recent_avg:.0f}%). "
            f"Issues are compounding or initial severity assessments are too optimistic."
        )
    else:
        trend = "stable"
        message = (
            f"Escalation rate for {software_name} has been steady "
            f"(around {recent_avg:.0f}%)."
        )

    top = points[-1].get("top_escalations", [])
    if top:
        topic_str = ", ".join(f"\u201c{t}\u201d" for t in top[:3])
        message += f" Recently escalated topics: {topic_str}."

    return {"trend": trend, "message": message}


async def compute_escalation_rate(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Compute rolling severity escalation rate for a software integration."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    reg_at = software.created_at
    if reg_at and reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)

    today = datetime.now(timezone.utc).date()
    start_date = reg_at.date() if reg_at else today - timedelta(days=90)

    if (today - start_date).days < 30:
        start_date = today - timedelta(days=30)

    first_sample = start_date + timedelta(days=29)
    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        rate, esc_count, total, top = _escalation_at_date(all_signals, sample)
        points.append({
            "date": sample.isoformat(),
            "rate": rate,
            "escalation_count": esc_count,
            "total_threads": total,
            "top_escalations": top,
        })
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        rate, esc_count, total, top = _escalation_at_date(all_signals, today)
        points.append({
            "date": today.isoformat(),
            "rate": rate,
            "escalation_count": esc_count,
            "total_threads": total,
            "top_escalations": top,
        })

    if not points:
        rate, esc_count, total, top = _escalation_at_date(all_signals, today)
        points.append({
            "date": today.isoformat(),
            "rate": rate,
            "escalation_count": esc_count,
            "total_threads": total,
            "top_escalations": top,
        })

    commentary = _escalation_commentary(points, software.software_name)

    # Peer comparison
    intended_use_result = await db.execute(
        select(SoftwareRegistration.intended_use).where(
            SoftwareRegistration.id == software_id,
        )
    )
    intended_use = intended_use_result.scalar_one_or_none()

    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, intended_use,
    )

    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        if stage_topic:
            all_peer_signals = [
                s for s in all_peer_signals
                if (s.event_metadata or {}).get("stage_topic") == stage_topic
            ]

        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        if peer_by_sw:
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                rates: list[float] = []
                for sw_sigs in peer_by_sw.values():
                    rate_val, _, _, _ = _escalation_at_date(sw_sigs, sample)
                    rates.append(rate_val)
                avg_rate = sum(rates) / len(rates) if rates else 0.0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_rate),
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                rates = []
                for sw_sigs in peer_by_sw.values():
                    rate_val, _, _, _ = _escalation_at_date(sw_sigs, today)
                    rates.append(rate_val)
                avg_rate = sum(rates) / len(rates) if rates else 0.0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_rate),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Core vs Peripheral issue ratio
# ---------------------------------------------------------------------------

PERIPHERAL_CATEGORIES: dict[str, list[str]] = {
    "SSO / Auth": [
        "sso", "saml", "ldap", "oauth", "openid", "authentication",
        "login", "sign-in", "sign in", "mfa", "2fa", "two-factor",
        "password", "credential", "single sign",
    ],
    "Billing": [
        "billing", "invoice", "payment", "subscription", "license",
        "pricing", "renewal", "charge", "cost", "quota", "plan upgrade",
        "plan downgrade",
    ],
    "Access / Permissions": [
        "permission", "access control", "rbac", "role", "privilege",
        "authorization", "forbidden", "access denied", "user management",
        "provisioning", "scim", "directory sync", "user access",
    ],
    "Compliance": [
        "compliance", "audit", "gdpr", "soc2", "soc 2", "hipaa",
        "certification", "data retention", "privacy policy",
        "security review",
    ],
}


def _classify_core_peripheral(sig: "SignalEvent") -> tuple[str, str | None]:
    """Return ("core", None) or ("peripheral", category_name)."""
    text = " ".join(
        filter(None, [sig.title, sig.body])
    ).lower()
    if not text:
        return ("core", None)

    for cat_name, keywords in PERIPHERAL_CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                return ("peripheral", cat_name)

    return ("core", None)


def _core_peripheral_at_date(
    signals: list["SignalEvent"],
    sample_date: "date",
) -> tuple[float, int, int, int, list[str]]:
    """Compute core/peripheral stats for a 30-day window ending at sample_date.

    Returns (peripheral_ratio, core_count, peripheral_count, total, top_categories).
    """
    window_start = sample_date - timedelta(days=30)
    window_signals = [
        s for s in signals
        if window_start < s.occurred_at.date() <= sample_date
    ]

    if not window_signals:
        return (0.0, 0, 0, 0, [])

    core = 0
    peripheral = 0
    cat_counter: dict[str, int] = defaultdict(int)

    for sig in window_signals:
        classification, cat = _classify_core_peripheral(sig)
        if classification == "peripheral":
            peripheral += 1
            if cat:
                cat_counter[cat] += 1
        else:
            core += 1

    total = core + peripheral
    ratio = round(peripheral / total * 100, 1) if total else 0.0

    top_cats = sorted(cat_counter, key=lambda k: cat_counter[k], reverse=True)[:3]

    return (ratio, core, peripheral, total, top_cats)


def _core_peripheral_commentary(
    points: list[dict],
    sw_name: str,
) -> dict[str, str]:
    """Generate trend commentary for core/peripheral ratio."""
    valid = [p for p in points if p["total_count"] > 0]
    if not valid:
        return {"trend": "stable", "message": f"Not enough data to assess {sw_name}'s issue profile."}

    mid = len(valid) // 2
    first_half = valid[:mid] if mid else valid
    second_half = valid[mid:] if mid else valid

    avg_first = sum(p["peripheral_ratio"] for p in first_half) / len(first_half)
    avg_second = sum(p["peripheral_ratio"] for p in second_half) / len(second_half)
    diff = avg_second - avg_first

    latest = valid[-1]
    peri_ratio = latest["peripheral_ratio"]
    core_count = latest["core_count"]
    peri_count = latest["peripheral_count"]
    top_cats = latest["top_peripheral_categories"]

    if diff <= -5:
        trend = "improving"
        msg = (
            f"{sw_name}'s peripheral issue ratio is declining — "
            f"down to {peri_ratio:.0f}% ({peri_count} peripheral vs {core_count} core). "
            "The ecosystem friction around the integration is decreasing."
        )
    elif diff >= 5:
        trend = "worsening"
        msg = (
            f"{sw_name}'s peripheral issue ratio is rising — "
            f"now {peri_ratio:.0f}% ({peri_count} peripheral vs {core_count} core). "
            "Ecosystem concerns (not the product itself) are growing."
        )
    else:
        trend = "stable"
        msg = (
            f"{sw_name}'s issue profile is stable at "
            f"{peri_ratio:.0f}% peripheral ({peri_count} peripheral vs {core_count} core)."
        )

    if top_cats:
        msg += f" Top peripheral categories: {', '.join(top_cats)}."

    return {"trend": trend, "message": msg}


async def compute_core_peripheral(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
    stage_topic: str | None = None,
) -> dict:
    """Compute core vs peripheral issue ratio over time."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        signals = [
            s for s in signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    if not signals:
        return {
            "points": [],
            "commentary": {
                "trend": "stable",
                "message": "No signals yet.",
            },
            "peer": None,
        }

    reg_date = software.created_at.date()
    today = date.today()

    first_sample = reg_date + timedelta(days=29)
    if first_sample > today:
        first_sample = today

    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        ratio, core, peri, total, top_cats = _core_peripheral_at_date(signals, sample)
        points.append({
            "date": sample.isoformat(),
            "peripheral_ratio": ratio,
            "core_count": core,
            "peripheral_count": peri,
            "total_count": total,
            "top_peripheral_categories": top_cats,
        })
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        ratio, core, peri, total, top_cats = _core_peripheral_at_date(signals, today)
        points.append({
            "date": today.isoformat(),
            "peripheral_ratio": ratio,
            "core_count": core,
            "peripheral_count": peri,
            "total_count": total,
            "top_peripheral_categories": top_cats,
        })

    sw_name = _truncate(software.software_name, 30)
    commentary = _core_peripheral_commentary(points, sw_name)

    # Peer comparison
    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, software.intended_use,
    )
    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        if stage_topic:
            all_peer_signals = [
                s for s in all_peer_signals
                if (s.event_metadata or {}).get("stage_topic") == stage_topic
            ]

        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        if peer_by_sw:
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                ratios: list[float] = []
                for sw_sigs in peer_by_sw.values():
                    r, _, _, _, _ = _core_peripheral_at_date(sw_sigs, sample)
                    ratios.append(r)
                avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_ratio),
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                ratios = []
                for sw_sigs in peer_by_sw.values():
                    r, _, _, _, _ = _core_peripheral_at_date(sw_sigs, today)
                    ratios.append(r)
                avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_ratio),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Fitness for Purpose – feature request pressure
# ---------------------------------------------------------------------------


def _fitness_at_date(
    signals: list["SignalEvent"],
    sample_date: "date",
) -> dict:
    """Compute fitness-for-purpose metrics for a 30-day window.

    Returns dict with request_ratio, repeat info, fulfillment info.
    """
    window_start = sample_date - timedelta(days=30)
    window_signals = [
        s for s in signals
        if window_start < s.occurred_at.date() <= sample_date
    ]
    all_to_date = [
        s for s in signals
        if s.occurred_at.date() <= sample_date
    ]

    empty = {
        "request_ratio": 0.0,
        "request_count": 0,
        "total_signals": 0,
        "repeat_count": 0,
        "unique_request_topics": 0,
        "fulfilled_count": 0,
        "total_request_threads": 0,
        "fulfillment_rate": 0.0,
        "top_repeats": [],
    }

    if not window_signals:
        return empty

    # 1. Feature request ratio (within window)
    requests_in_window = [
        s for s in window_signals
        if (s.event_metadata or {}).get("subject") == "vendor_request"
    ]
    request_ratio = round(
        len(requests_in_window) / len(window_signals) * 100, 1
    ) if window_signals else 0.0

    # 2. Repeat requests (within window, by normalized title)
    title_counts: dict[str, int] = defaultdict(int)
    for s in requests_in_window:
        title = _normalize_title(s.title or "")
        if title:
            title_counts[title] += 1

    repeat_topics = {t: c for t, c in title_counts.items() if c > 1}
    repeat_count = len(repeat_topics)
    unique_request_topics = len(title_counts)
    top_repeats = sorted(
        repeat_topics, key=lambda t: repeat_topics[t], reverse=True
    )[:3]
    # Truncate topic names for display
    top_repeats = [_truncate(t, 40) for t in top_repeats]

    # 3. Fulfillment rate (cumulative to sample_date)
    # Group all signals to date by normalized title
    by_title: dict[str, list["SignalEvent"]] = defaultdict(list)
    for s in all_to_date:
        title = _normalize_title(s.title or "")
        if title:
            by_title[title].append(s)

    fulfilled = 0
    total_request_threads = 0

    for _title, thread in by_title.items():
        sorted_thread = sorted(thread, key=lambda s: s.occurred_at)
        first_request_at = None

        for sig in sorted_thread:
            meta = sig.event_metadata or {}
            if meta.get("subject") == "vendor_request" and first_request_at is None:
                first_request_at = sig.occurred_at

        if first_request_at is None:
            continue  # no vendor_request in this thread

        total_request_threads += 1

        # Check for positive signal after the first request
        for sig in sorted_thread:
            meta = sig.event_metadata or {}
            if sig.occurred_at > first_request_at and meta.get("valence") == "positive":
                fulfilled += 1
                break

    fulfillment_rate = round(
        fulfilled / total_request_threads * 100, 1
    ) if total_request_threads else 0.0

    return {
        "request_ratio": request_ratio,
        "request_count": len(requests_in_window),
        "total_signals": len(window_signals),
        "repeat_count": repeat_count,
        "unique_request_topics": unique_request_topics,
        "fulfilled_count": fulfilled,
        "total_request_threads": total_request_threads,
        "fulfillment_rate": fulfillment_rate,
        "top_repeats": top_repeats,
    }


def _fitness_commentary(
    points: list[dict],
    sw_name: str,
) -> dict[str, str]:
    """Generate trend commentary for fitness-for-purpose metrics."""
    valid = [p for p in points if p["total_signals"] > 0]
    if not valid:
        return {
            "trend": "stable",
            "message": f"Not enough data to assess {sw_name}'s fitness for purpose.",
        }

    mid = len(valid) // 2
    first_half = valid[:mid] if mid else valid
    second_half = valid[mid:] if mid else valid

    avg_first = sum(p["request_ratio"] for p in first_half) / len(first_half)
    avg_second = sum(p["request_ratio"] for p in second_half) / len(second_half)
    diff = avg_second - avg_first

    latest = valid[-1]
    ratio = latest["request_ratio"]
    req_count = latest["request_count"]
    fulfillment = latest["fulfillment_rate"]
    repeat = latest["repeat_count"]

    if diff <= -5:
        trend = "improving"
        msg = (
            f"{sw_name}'s feature request ratio is declining — "
            f"down to {ratio:.0f}% ({req_count} request"
            f"{'s' if req_count != 1 else ''} in the last 30 days). "
            "Fewer gaps between what you need and what the product offers."
        )
    elif diff >= 5:
        trend = "worsening"
        msg = (
            f"{sw_name}'s feature request ratio is rising — "
            f"now {ratio:.0f}% ({req_count} request"
            f"{'s' if req_count != 1 else ''} in the last 30 days). "
            "Growing gap between your needs and product capabilities."
        )
    else:
        trend = "stable"
        msg = (
            f"{sw_name}'s feature request ratio is stable at "
            f"{ratio:.0f}% ({req_count} request"
            f"{'s' if req_count != 1 else ''} in the last 30 days)."
        )

    parts: list[str] = []
    if repeat > 0:
        parts.append(
            f"{repeat} recurring request topic{'s' if repeat != 1 else ''}"
        )
    if latest["total_request_threads"] > 0:
        parts.append(f"{fulfillment:.0f}% fulfillment rate")
    if parts:
        msg += " " + "; ".join(parts) + "."

    return {"trend": trend, "message": msg}


async def compute_fitness_metrics(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Compute fitness-for-purpose metrics over time."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill classification tags for unclassified signals
    unclassified = [
        s for s in signals if "subject" not in (s.event_metadata or {})
    ]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        signals = _tz_fix(list(result.scalars().all()))

    if not signals:
        return {
            "points": [],
            "commentary": {
                "trend": "stable",
                "message": "No signals yet.",
            },
            "peer": None,
        }

    reg_date = software.created_at.date()
    today = date.today()

    first_sample = reg_date + timedelta(days=29)
    if first_sample > today:
        first_sample = today

    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        pt = _fitness_at_date(signals, sample)
        pt["date"] = sample.isoformat()
        points.append(pt)
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        pt = _fitness_at_date(signals, today)
        pt["date"] = today.isoformat()
        points.append(pt)

    sw_name = _truncate(software.software_name, 30)
    commentary = _fitness_commentary(points, sw_name)

    # Peer comparison (request ratio)
    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, software.intended_use,
    )
    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        if peer_by_sw:
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                ratios: list[float] = []
                for sw_sigs in peer_by_sw.values():
                    pt = _fitness_at_date(sw_sigs, sample)
                    ratios.append(pt["request_ratio"])
                avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_ratio),
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                ratios = []
                for sw_sigs in peer_by_sw.values():
                    pt = _fitness_at_date(sw_sigs, today)
                    ratios.append(pt["request_ratio"])
                avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_ratio),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Fitness Events (timeline)
# ---------------------------------------------------------------------------


async def _llm_generate_fitness_descriptions(
    events_for_llm: list[dict],
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + fitness implication for each feature-request event.

    Returns list of {"summary": ..., "fitness_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity={ev['severity']} valence={ev['valence']}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing fitness-for-purpose signals for a {software_name} "
        "integration — specifically feature requests, enhancement suggestions, "
        "and their fulfillment.\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what was requested or "
        "what capability gap is revealed (~8-15 words). Reference the specific "
        "content — don't be generic. Don't repeat the ticket ID.\n"
        "2. **fitness_implication**: 1-2 sentences explaining how this event "
        "impacts the product's fitness for the user's needs. For requests "
        "(valence=negative/neutral), explain what use case is unmet. For "
        "positive signals (valence=positive), explain what gap was closed.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "fitness_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "fitness_implication": str(r.get("fitness_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_fitness_description_failed", error=str(e))
        return None


async def compute_fitness_events(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Return individual feature-request events that contribute to fitness scoring."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill classification for untagged signals
    unclassified = [s for s in all_signals if "subject" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Filter to vendor_request signals + their fulfillment signals
    fitness_signals = detect_fitness_signals(all_signals)
    fitness_signals.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not fitness_signals:
        return {"events": []}

    # LLM description caching
    cache_field = "fitness_desc"

    needs_llm: list[tuple[int, dict]] = []
    for i, s in enumerate(fitness_signals):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity": s.severity or "medium",
                "valence": meta.get("valence", "neutral"),
            }))

    if needs_llm:
        llm_results = await _llm_generate_fitness_descriptions(
            [ev for _, ev in needs_llm],
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = fitness_signals[idx]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    # Build the set of request titles from fitness signals
    request_titles: set[str] = set()
    for s in fitness_signals:
        if (s.event_metadata or {}).get("subject") == "vendor_request":
            t = _normalize_title(s.title or "")
            if t:
                request_titles.add(t)

    # Check which request titles got fulfilled (positive signal later in thread)
    fulfilled_titles: set[str] = set()
    by_title: dict[str, list[SignalEvent]] = defaultdict(list)
    for s in all_signals:
        title = _normalize_title(s.title or "")
        if title:
            by_title[title].append(s)

    for title, thread in by_title.items():
        if title not in request_titles:
            continue
        sorted_thread = sorted(thread, key=lambda s: s.occurred_at)
        first_request_at = None
        for sig in sorted_thread:
            if (sig.event_metadata or {}).get("subject") == "vendor_request" and first_request_at is None:
                first_request_at = sig.occurred_at
        if first_request_at is None:
            continue
        for sig in sorted_thread:
            if sig.occurred_at > first_request_at and (sig.event_metadata or {}).get("valence") == "positive":
                fulfilled_titles.add(title)
                break

    # Build response
    events = []
    for s in fitness_signals:
        meta = s.event_metadata or {}
        valence = meta.get("valence", "neutral")
        is_request = meta.get("subject") == "vendor_request"
        title = _normalize_title(s.title or "")
        is_fulfilled = title in fulfilled_titles

        if is_request:
            if is_fulfilled:
                status = "fulfilled"
            else:
                status = "open"
        else:
            # This is a fulfillment signal
            status = "fulfillment"

        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("fitness_implication", "")
        else:
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "fitness_implication": implication,
            "severity": s.severity or "medium",
            "valence": valence,
            "status": status,
            "source_type": s.source_type,
            "event_type": s.event_type,
        })

    return {"events": events}


# ---------------------------------------------------------------------------
# Reliability metrics
# ---------------------------------------------------------------------------

INCIDENT_KEYWORDS: list[str] = [
    "outage", "downtime", "503", "502", "500", "unavailable",
    "incident", "service disruption", "system down", "unresponsive",
    "service degradation", "service interruption", "service unavailable",
]

_EMPTY_RELIABILITY_NUMS: dict[str, float | None] = {
    "downtime_hours": None,
    "uptime_pct": None,
}


async def _llm_extract_reliability_numbers(
    texts: list[tuple[int, str]],
) -> list[dict[str, float | None]] | None:
    """Use LLM to extract quantitative reliability data from signal texts.

    Args:
        texts: List of (index, text) pairs.

    Returns:
        List of dicts with downtime_hours and uptime_pct, or None on failure.
    """
    if not texts:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    entries = [f"[{idx}] {text[:500]}" for idx, text in texts]

    prompt = (
        "Extract quantitative reliability data from each text below.\n\n"
        "For each entry, look for:\n"
        "- downtime_hours: Any mention of downtime duration, outage length, "
        "service unavailability period, or time a system was down. Convert to "
        "hours. Examples: '45 minutes of downtime' → 0.75, 'down for 2 hours' "
        "→ 2.0, '3-day outage' → 72.0, 'service was unavailable for about "
        "half an hour' → 0.5, 'experienced intermittent issues over 90 min' "
        "→ 1.5.\n"
        "- uptime_pct: Any mention of uptime percentage, availability "
        "percentage, SLA achievement, or reliability percentage. Examples: "
        "'99.9% uptime' → 99.9, 'four nines availability' → 99.99, "
        "'SLA of 99.5%' → 99.5, 'availability has been hovering around "
        "ninety-eight percent' → 98.0.\n\n"
        "Return a JSON array with one object per entry, in the same order. "
        "Each object must have exactly two keys: "
        "\"downtime_hours\" (number or null) and \"uptime_pct\" (number or "
        "null). If neither metric is mentioned, return "
        "{\"downtime_hours\": null, \"uptime_pct\": null}.\n\n"
        "Texts:\n" + "\n".join(entries) + "\n\n"
        "Return ONLY the JSON array, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, float | None]] = []
        for r in results:
            dh = r.get("downtime_hours")
            up = r.get("uptime_pct")
            validated.append({
                "downtime_hours": round(float(dh), 2) if dh is not None else None,
                "uptime_pct": round(float(up), 2) if up is not None else None,
            })
        return validated
    except Exception as e:
        logger.warning("llm_reliability_extraction_failed", error=str(e))
        return None


async def _backfill_reliability_extractions(
    db: "AsyncSession",
    signals: list["SignalEvent"],
) -> None:
    """Extract and cache quantitative reliability data for unprocessed signals.

    Uses LLM-based extraction, stores results in event_metadata.reliability_numbers.
    """
    to_extract: list[tuple[int, "SignalEvent"]] = []
    dirty = False

    for i, sig in enumerate(signals):
        meta = sig.event_metadata or {}
        if "reliability_numbers" not in meta:
            text = " ".join(filter(None, [sig.title, sig.body])).strip()
            if text:
                to_extract.append((i, sig))
            else:
                # No text — cache empty result immediately
                meta = dict(sig.event_metadata or {})
                meta["reliability_numbers"] = dict(_EMPTY_RELIABILITY_NUMS)
                sig.event_metadata = meta
                dirty = True

    if not to_extract:
        if dirty:
            await db.commit()
        return

    BATCH_SIZE = 20
    for batch_start in range(0, len(to_extract), BATCH_SIZE):
        batch = to_extract[batch_start : batch_start + BATCH_SIZE]
        texts: list[tuple[int, str]] = [
            (j, " ".join(filter(None, [sig.title, sig.body])))
            for j, (_, sig) in enumerate(batch)
        ]

        results = await _llm_extract_reliability_numbers(texts)

        if results is None:
            # LLM failed — leave uncached so next request retries
            logger.info("reliability_extraction_skipped_batch", batch_size=len(batch))
            continue

        # Pad if LLM returned fewer results than expected
        while len(results) < len(batch):
            results.append(dict(_EMPTY_RELIABILITY_NUMS))

        for (_, sig), nums in zip(batch, results):
            meta = dict(sig.event_metadata or {})
            meta["reliability_numbers"] = nums
            sig.event_metadata = meta

    await db.commit()


def _is_incident_signal(sig: "SignalEvent") -> bool:
    """Check if signal matches incident keywords."""
    text = " ".join(filter(None, [sig.title, sig.body])).lower()
    return any(kw in text for kw in INCIDENT_KEYWORDS)


def _reliability_at_date(
    signals: list["SignalEvent"],
    sample_date: "date",
) -> dict:
    """Compute reliability metrics for a 30-day window ending at sample_date."""
    window_start = sample_date - timedelta(days=30)
    window_signals = [
        s for s in signals
        if window_start < s.occurred_at.date() <= sample_date
    ]

    empty: dict = {
        "incident_count": 0,
        "weighted_density": 0.0,
        "mtbf_hours": None,
        "extracted_downtime_hours": None,
        "extracted_uptime_pct": None,
        "extraction_count": 0,
        "top_incidents": [],
    }

    if not window_signals:
        return empty

    # 1. Incident detection + severity-weighted density
    incidents: list["SignalEvent"] = []
    weighted = 0.0
    for s in window_signals:
        if _is_incident_signal(s):
            incidents.append(s)
            sev = (s.severity or "medium").lower()
            weighted += SEVERITY_WEIGHT.get(sev, 1.0)

    # 2. MTBF: average gap between consecutive incidents in window
    mtbf: float | None = None
    if len(incidents) >= 2:
        sorted_inc = sorted(incidents, key=lambda s: s.occurred_at)
        gaps: list[float] = []
        for i in range(1, len(sorted_inc)):
            gap = (sorted_inc[i].occurred_at - sorted_inc[i - 1].occurred_at)
            gaps.append(gap.total_seconds() / 3600)
        mtbf = round(statistics.mean(gaps), 1) if gaps else None

    # 3. Quantitative data from cached LLM extraction
    total_downtime = 0.0
    has_downtime = False
    latest_uptime: float | None = None
    extraction_count = 0

    for s in window_signals:
        nums = (s.event_metadata or {}).get(
            "reliability_numbers", _EMPTY_RELIABILITY_NUMS,
        )
        extracted_any = False
        if nums.get("downtime_hours") is not None:
            total_downtime += nums["downtime_hours"]
            has_downtime = True
            extracted_any = True
        if nums.get("uptime_pct") is not None:
            # Keep the latest uptime mention
            latest_uptime = nums["uptime_pct"]
            extracted_any = True
        if extracted_any:
            extraction_count += 1

    # Top incident titles (deduplicated, truncated)
    seen_titles: set[str] = set()
    top_incidents: list[str] = []
    for s in sorted(incidents, key=lambda s: s.occurred_at, reverse=True):
        title = _truncate(s.title or "Untitled incident", 50)
        norm = _normalize_title(title)
        if norm not in seen_titles:
            seen_titles.add(norm)
            top_incidents.append(title)
        if len(top_incidents) >= 3:
            break

    return {
        "incident_count": len(incidents),
        "weighted_density": round(weighted, 1),
        "mtbf_hours": mtbf,
        "extracted_downtime_hours": round(total_downtime, 1) if has_downtime else None,
        "extracted_uptime_pct": latest_uptime,
        "extraction_count": extraction_count,
        "top_incidents": top_incidents,
    }


def _reliability_commentary(
    points: list[dict],
    sw_name: str,
) -> dict[str, str]:
    """Generate trend commentary for reliability metrics."""
    valid = [p for p in points if p["incident_count"] > 0]
    if not valid:
        non_empty = [p for p in points if True]  # all points sampled
        if non_empty:
            return {
                "trend": "stable",
                "message": (
                    f"No incident signals detected for {sw_name}. "
                    "Either the integration is running smoothly or "
                    "incidents aren't being captured in the signal feed."
                ),
            }
        return {
            "trend": "stable",
            "message": f"Not enough data to assess {sw_name}'s reliability.",
        }

    mid = len(points) // 2
    first_half = points[:mid] if mid else points
    second_half = points[mid:] if mid else points

    avg_first = sum(p["weighted_density"] for p in first_half) / len(first_half)
    avg_second = sum(p["weighted_density"] for p in second_half) / len(second_half)

    latest = points[-1]
    count = latest["incident_count"]
    density = latest["weighted_density"]
    mtbf = latest["mtbf_hours"]

    # >=30% change for improving/worsening (relative to avoid small-number noise)
    if avg_first > 0 and (avg_second - avg_first) / avg_first <= -0.30:
        trend = "improving"
        msg = (
            f"{sw_name}'s reliability is improving — incident density "
            f"dropped to {density:.1f} ({count} incident"
            f"{'s' if count != 1 else ''} in the last 30 days)."
        )
    elif avg_first > 0 and (avg_second - avg_first) / avg_first >= 0.30:
        trend = "worsening"
        msg = (
            f"{sw_name}'s reliability is deteriorating — incident density "
            f"rose to {density:.1f} ({count} incident"
            f"{'s' if count != 1 else ''} in the last 30 days)."
        )
    elif avg_second > avg_first and avg_first == 0:
        trend = "worsening"
        msg = (
            f"{sw_name} is experiencing new incidents — "
            f"density of {density:.1f} ({count} incident"
            f"{'s' if count != 1 else ''} in the last 30 days)."
        )
    else:
        trend = "stable"
        msg = (
            f"{sw_name}'s incident density is stable at {density:.1f} "
            f"({count} incident{'s' if count != 1 else ''} in the last 30 days)."
        )

    if mtbf is not None:
        if mtbf < 24:
            msg += f" MTBF: {mtbf:.0f}h."
        else:
            msg += f" MTBF: {mtbf / 24:.1f} days."

    extracted = latest.get("extracted_downtime_hours")
    if extracted is not None and extracted > 0:
        if extracted < 24:
            msg += f" Reported downtime: {extracted:.1f}h."
        else:
            msg += f" Reported downtime: {extracted / 24:.1f} days."

    uptime = latest.get("extracted_uptime_pct")
    if uptime is not None:
        msg += f" Latest reported uptime: {uptime}%."

    return {"trend": trend, "message": msg}


async def compute_reliability(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Compute reliability metrics over time."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    if not signals:
        return {
            "points": [],
            "commentary": {
                "trend": "stable",
                "message": "No signals yet.",
            },
            "peer": None,
        }

    # LLM-based extraction of quantitative reliability data (cached in metadata)
    await _backfill_reliability_extractions(db, signals)
    # Re-fetch to pick up committed metadata changes
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    reg_date = software.created_at.date()
    today = date.today()

    first_sample = reg_date + timedelta(days=29)
    if first_sample > today:
        first_sample = today

    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        pt = _reliability_at_date(signals, sample)
        pt["date"] = sample.isoformat()
        points.append(pt)
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        pt = _reliability_at_date(signals, today)
        pt["date"] = today.isoformat()
        points.append(pt)

    sw_name = _truncate(software.software_name, 30)
    commentary = _reliability_commentary(points, sw_name)

    # Peer comparison (weighted density)
    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, software.intended_use,
    )
    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        if peer_by_sw:
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                densities: list[float] = []
                for sw_sigs in peer_by_sw.values():
                    pt = _reliability_at_date(sw_sigs, sample)
                    densities.append(pt["weighted_density"])
                avg_density = sum(densities) / len(densities) if densities else 0.0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_density),
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                densities = []
                for sw_sigs in peer_by_sw.values():
                    pt = _reliability_at_date(sw_sigs, today)
                    densities.append(pt["weighted_density"])
                avg_density = sum(densities) / len(densities) if densities else 0.0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_density),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }


# ---------------------------------------------------------------------------
# Performance metrics – latency & rate-limiting complaints
# ---------------------------------------------------------------------------

_EMPTY_PERFORMANCE_TAGS: dict[str, bool] = {
    "has_latency": False,
    "has_rate_limit": False,
}


async def _llm_extract_performance_tags(
    texts: list[tuple[int, str]],
) -> list[dict[str, bool]] | None:
    """Use LLM to detect latency and rate-limit complaints in signal texts.

    Returns list of {"has_latency": bool, "has_rate_limit": bool}, or None on failure.
    """
    if not texts:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    entries = [f"[{idx}] {text[:500]}" for idx, text in texts]

    prompt = (
        "Classify each text below for performance-related complaints.\n\n"
        "For each entry, determine:\n"
        "- has_latency: Does the text mention slow response times, high "
        "latency, timeouts, sluggish performance, delays, slow loading, "
        "poor response times, lag, slow API responses, long wait times, "
        "or general slowness of the service? (true/false)\n"
        "- has_rate_limit: Does the text mention rate limiting, throttling, "
        "API quota exceeded, too many requests, 429 errors, request limits, "
        "API call limits, capacity constraints, or being blocked due to "
        "exceeding usage limits? (true/false)\n\n"
        "Return a JSON array with one object per entry, in the same order. "
        "Each object must have exactly two keys: "
        "\"has_latency\" (boolean) and \"has_rate_limit\" (boolean).\n\n"
        "Texts:\n" + "\n".join(entries) + "\n\n"
        "Return ONLY the JSON array, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, bool]] = []
        for r in results:
            validated.append({
                "has_latency": bool(r.get("has_latency", False)),
                "has_rate_limit": bool(r.get("has_rate_limit", False)),
            })
        return validated
    except Exception as e:
        logger.warning("llm_performance_extraction_failed", error=str(e))
        return None


async def _backfill_performance_extractions(
    db: "AsyncSession",
    signals: list["SignalEvent"],
) -> None:
    """Extract and cache performance complaint tags for unprocessed signals.

    Uses LLM-based classification, stores in event_metadata.performance_tags.
    """
    to_extract: list[tuple[int, "SignalEvent"]] = []
    dirty = False

    for i, sig in enumerate(signals):
        meta = sig.event_metadata or {}
        if "performance_tags" not in meta:
            text = " ".join(filter(None, [sig.title, sig.body])).strip()
            if text:
                to_extract.append((i, sig))
            else:
                meta = dict(sig.event_metadata or {})
                meta["performance_tags"] = dict(_EMPTY_PERFORMANCE_TAGS)
                sig.event_metadata = meta
                dirty = True

    if not to_extract:
        if dirty:
            await db.commit()
        return

    BATCH_SIZE = 20
    for batch_start in range(0, len(to_extract), BATCH_SIZE):
        batch = to_extract[batch_start : batch_start + BATCH_SIZE]
        texts: list[tuple[int, str]] = [
            (j, " ".join(filter(None, [sig.title, sig.body])))
            for j, (_, sig) in enumerate(batch)
        ]

        results = await _llm_extract_performance_tags(texts)

        if results is None:
            logger.info("performance_extraction_skipped_batch", batch_size=len(batch))
            continue

        while len(results) < len(batch):
            results.append(dict(_EMPTY_PERFORMANCE_TAGS))

        for (_, sig), tags in zip(batch, results):
            meta = dict(sig.event_metadata or {})
            meta["performance_tags"] = tags
            sig.event_metadata = meta

    await db.commit()


def _performance_at_date(
    signals: list["SignalEvent"],
    sample_date: "date",
) -> dict:
    """Compute performance complaint metrics for a 30-day window."""
    window_start = sample_date - timedelta(days=30)
    window_signals = [
        s for s in signals
        if window_start < s.occurred_at.date() <= sample_date
    ]

    empty: dict = {
        "latency_count": 0,
        "rate_limit_count": 0,
        "total_signals": 0,
        "top_latency_issues": [],
        "top_rate_limit_issues": [],
    }

    if not window_signals:
        return empty

    latency_sigs: list["SignalEvent"] = []
    rate_limit_sigs: list["SignalEvent"] = []

    for s in window_signals:
        tags = (s.event_metadata or {}).get(
            "performance_tags", _EMPTY_PERFORMANCE_TAGS,
        )
        if tags.get("has_latency"):
            latency_sigs.append(s)
        if tags.get("has_rate_limit"):
            rate_limit_sigs.append(s)

    # Top latency issues (deduplicated, truncated)
    seen: set[str] = set()
    top_latency: list[str] = []
    for s in sorted(latency_sigs, key=lambda s: s.occurred_at, reverse=True):
        title = _truncate(s.title or "Untitled", 50)
        norm = _normalize_title(title)
        if norm not in seen:
            seen.add(norm)
            top_latency.append(title)
        if len(top_latency) >= 3:
            break

    seen.clear()
    top_rate_limit: list[str] = []
    for s in sorted(rate_limit_sigs, key=lambda s: s.occurred_at, reverse=True):
        title = _truncate(s.title or "Untitled", 50)
        norm = _normalize_title(title)
        if norm not in seen:
            seen.add(norm)
            top_rate_limit.append(title)
        if len(top_rate_limit) >= 3:
            break

    return {
        "latency_count": len(latency_sigs),
        "rate_limit_count": len(rate_limit_sigs),
        "total_signals": len(window_signals),
        "top_latency_issues": top_latency,
        "top_rate_limit_issues": top_rate_limit,
    }


def _performance_commentary(
    points: list[dict],
    sw_name: str,
) -> dict[str, str]:
    """Generate trend commentary for performance complaints."""
    combined = [p["latency_count"] + p["rate_limit_count"] for p in points]

    if all(c == 0 for c in combined):
        return {
            "trend": "stable",
            "message": (
                f"No performance complaints detected for {sw_name}. "
                "Either the integration performs well or issues aren't "
                "being captured in the signal feed."
            ),
        }

    mid = len(points) // 2
    first_half = combined[:mid] if mid else combined
    second_half = combined[mid:] if mid else combined

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    latest = points[-1]
    lat_c = latest["latency_count"]
    rl_c = latest["rate_limit_count"]
    total_c = lat_c + rl_c

    if avg_first > 0 and (avg_second - avg_first) / avg_first <= -0.30:
        trend = "improving"
        msg = (
            f"Performance complaints for {sw_name} are declining — "
            f"{total_c} complaint{'s' if total_c != 1 else ''} in the last 30 days."
        )
    elif avg_first > 0 and (avg_second - avg_first) / avg_first >= 0.30:
        trend = "worsening"
        msg = (
            f"Performance complaints for {sw_name} are rising — "
            f"{total_c} complaint{'s' if total_c != 1 else ''} in the last 30 days."
        )
    elif avg_second > avg_first and avg_first == 0:
        trend = "worsening"
        msg = (
            f"{sw_name} is experiencing new performance issues — "
            f"{total_c} complaint{'s' if total_c != 1 else ''} in the last 30 days."
        )
    else:
        trend = "stable"
        msg = (
            f"Performance complaint volume for {sw_name} is steady — "
            f"{total_c} in the last 30 days."
        )

    if lat_c > 0 and rl_c > 0:
        msg += (
            f" {lat_c} latency/slowness and {rl_c} rate-limit/throttling."
        )
    elif lat_c > 0:
        msg += f" All {lat_c} relate to latency or slowness."
    elif rl_c > 0:
        msg += f" All {rl_c} relate to rate limiting or throttling."

    return {"trend": trend, "message": msg}


async def compute_performance(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Compute performance complaint metrics over time."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    if not signals:
        return {
            "points": [],
            "commentary": {
                "trend": "stable",
                "message": "No signals yet.",
            },
            "peer": None,
        }

    # LLM-based extraction of performance complaint tags (cached in metadata)
    await _backfill_performance_extractions(db, signals)
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = _tz_fix(list(result.scalars().all()))

    reg_date = software.created_at.date()
    today = date.today()

    first_sample = reg_date + timedelta(days=29)
    if first_sample > today:
        first_sample = today

    points: list[dict] = []
    sample = first_sample
    while sample <= today:
        pt = _performance_at_date(signals, sample)
        pt["date"] = sample.isoformat()
        points.append(pt)
        sample += timedelta(days=7)

    if points and points[-1]["date"] != today.isoformat():
        pt = _performance_at_date(signals, today)
        pt["date"] = today.isoformat()
        points.append(pt)

    sw_name = _truncate(software.software_name, 30)
    commentary = _performance_commentary(points, sw_name)

    # Peer comparison (combined latency + rate_limit count)
    peer_regs, match_label = await _find_peer_registrations(
        db, software.vendor_name, software.software_name, software.intended_use,
    )
    peer_data = None
    if peer_regs:
        peer_reg_ids = [r.id for r in peer_regs]

        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        # Backfill performance tags for peer signals too
        await _backfill_performance_extractions(db, all_peer_signals)
        peer_result = await db.execute(
            select(SignalEvent)
            .where(SignalEvent.software_id.in_(peer_reg_ids))
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_peer_signals = _tz_fix(list(peer_result.scalars().all()))

        for sig in all_peer_signals:
            db.expunge(sig)

        peer_by_sw: dict[uuid.UUID, list[SignalEvent]] = defaultdict(list)
        for sig in all_peer_signals:
            peer_by_sw[sig.software_id].append(sig)

        if peer_by_sw:
            n_peers = len(peer_regs)
            peer_points: list[dict] = []
            sample = first_sample
            while sample <= today:
                counts: list[int] = []
                for sw_sigs in peer_by_sw.values():
                    pt = _performance_at_date(sw_sigs, sample)
                    counts.append(pt["latency_count"] + pt["rate_limit_count"])
                avg_count = sum(counts) / len(counts) if counts else 0
                peer_points.append({
                    "date": sample.isoformat(),
                    "count": round(avg_count),
                })
                sample += timedelta(days=7)

            if peer_points and peer_points[-1]["date"] != today.isoformat():
                counts = []
                for sw_sigs in peer_by_sw.values():
                    pt = _performance_at_date(sw_sigs, today)
                    counts.append(pt["latency_count"] + pt["rate_limit_count"])
                avg_count = sum(counts) / len(counts) if counts else 0
                peer_points.append({
                    "date": today.isoformat(),
                    "count": round(avg_count),
                })

            peer_data = {
                "category": match_label,
                "peer_count": n_peers,
                "points": peer_points,
            }

    return {
        "points": points,
        "commentary": commentary,
        "peer": peer_data,
    }

# ---------------------------------------------------------------------------
# Performance Events (timeline)
# ---------------------------------------------------------------------------


async def _llm_generate_performance_descriptions(
    events_for_llm: list[dict],
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + performance implication for each event.

    Returns list of {"summary": ..., "performance_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity={ev['severity']} category={ev['category']}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing performance-related events for a {software_name} "
        "integration.\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of the performance issue "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **performance_implication**: 1-2 sentences explaining how this "
        "event specifically impacts the performance of the integration. "
        "Reference the actual problem — latency spikes, slow API calls, "
        "rate limiting, throttling, timeouts. How does it affect the user "
        "experience and integration throughput?\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "performance_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "performance_implication": str(r.get("performance_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_performance_description_failed", error=str(e))
        return None


async def compute_performance_events(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Return individual events that contribute to performance scoring (latency + rate-limit)."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill classification for untagged signals
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Backfill performance tags if needed
    await _backfill_performance_extractions(db, all_signals)
    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Filter to performance-related signals only
    perf_signals = detect_performance_signals(all_signals)
    perf_signals.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not perf_signals:
        return {"events": []}

    # LLM description caching
    cache_field = "performance_desc"

    needs_llm: list[tuple[int, dict]] = []
    for i, s in enumerate(perf_signals):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            tags = meta.get("performance_tags", _EMPTY_PERFORMANCE_TAGS)
            category = "latency" if tags.get("has_latency") else "rate-limit"
            if tags.get("has_latency") and tags.get("has_rate_limit"):
                category = "latency + rate-limit"
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity": s.severity or "medium",
                "category": category,
            }))

    if needs_llm:
        llm_results = await _llm_generate_performance_descriptions(
            [ev for _, ev in needs_llm],
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = perf_signals[idx]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    # Build response
    events = []
    for s in perf_signals:
        meta = s.event_metadata or {}
        tags = meta.get("performance_tags", _EMPTY_PERFORMANCE_TAGS)
        has_latency = bool(tags.get("has_latency"))
        has_rate_limit = bool(tags.get("has_rate_limit"))

        if has_latency and has_rate_limit:
            category = "latency + rate-limit"
        elif has_latency:
            category = "latency"
        else:
            category = "rate-limit"

        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("performance_implication", "")
        else:
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "performance_implication": implication,
            "severity": s.severity or "medium",
            "category": category,
            "source_type": s.source_type,
            "event_type": s.event_type,
        })

    return {"events": events}


# ---------------------------------------------------------------------------
# Friction timeline — individual events that drive the friction score
# ---------------------------------------------------------------------------

_FRICTION_NEGATIVE_IMPACT = {"critical": "major setback", "high": "significant setback", "medium": "moderate setback", "low": "minor setback"}
_FRICTION_POSITIVE_IMPACT = {"critical": "major improvement", "high": "significant improvement", "medium": "moderate improvement", "low": "minor improvement"}

_STAGE_DESCRIPTIONS = {
    "onboarding": "initial setup, account creation, first logins, and early orientation",
    "integration": "connecting systems, API setup, data pipelines, and technical wiring",
    "stabilization": "resolving bugs, tuning performance, and hardening the integration",
    "productive": "routine day-to-day usage and steady-state operations",
    "optimization": "scaling, cost optimization, advanced features, and workflow automation",
}


async def _llm_generate_friction_descriptions(
    events_for_llm: list[dict],
    stage_topic: str | None,
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + friction implication for each event.

    Returns list of {"summary": ..., "friction_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    stage_label = stage_topic or "the integration lifecycle"
    stage_desc = _STAGE_DESCRIPTIONS.get(stage_topic or "", "the overall integration process")

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity={ev['severity']} valence={ev['valence']}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing friction events for a {software_name} integration "
        f"during the **{stage_label}** stage ({stage_desc}).\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what happened "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **friction_implication**: 1-2 sentences explaining how this "
        f"event specifically impacts friction during {stage_label}. "
        "Reference the actual problem/resolution described in the event. "
        "For negative events, explain what friction it creates. "
        "For positive events (valence=positive), explain how it reduces "
        "friction.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "friction_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "friction_implication": str(r.get("friction_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_friction_description_failed", error=str(e))
        return None


def _fallback_friction_summary(
    title: str | None,
    event_type: str,
) -> str:
    """Deterministic summary when LLM is unavailable."""
    clean_title = (title or "").strip()
    if clean_title.startswith("[") and "] " in clean_title:
        clean_title = clean_title.split("] ", 1)[1]
    for pfx in ("re: ", "fwd: ", "fw: "):
        if clean_title.lower().startswith(pfx):
            clean_title = clean_title[len(pfx):]

    if event_type == "ticket_resolved":
        return f"Resolved: {clean_title}"
    if event_type == "ticket_created":
        return f"New issue: {clean_title}"
    if event_type == "comment_added":
        return f"Update on: {clean_title}"
    if event_type == "ticket_updated":
        return f"Progress on: {clean_title}"
    return clean_title or "(untitled event)"


async def compute_friction_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Return individual negative/positive events that contribute to friction."""
    # Load software for registration date (needed for auto-classify)
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    # Use shared detection function
    friction_signals = detect_friction_signals(all_signals)
    friction_signals.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not friction_signals:
        return {"events": []}

    # Build cache key that includes stage so descriptions are stage-aware
    cache_field = f"friction_desc_{stage_topic or 'all'}"

    # Find signals that need LLM descriptions
    needs_llm: list[tuple[int, dict]] = []
    for i, s in enumerate(friction_signals):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity": s.severity or "medium",
                "valence": meta.get("valence", "negative"),
            }))

    # Batch LLM call for uncached descriptions
    if needs_llm:
        llm_results = await _llm_generate_friction_descriptions(
            [ev for _, ev in needs_llm],
            stage_topic,
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = friction_signals[idx]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    # Build response
    events = []
    for s in friction_signals:
        meta = s.event_metadata or {}
        valence = meta.get("valence")
        sev = s.severity or "medium"
        if valence == "positive":
            impact = _FRICTION_POSITIVE_IMPACT.get(sev, "moderate improvement")
        else:
            impact = _FRICTION_NEGATIVE_IMPACT.get(sev, "moderate setback")

        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("friction_implication", "")
        else:
            # Fallback if LLM failed or no API key
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "friction_implication": implication,
            "severity": sev,
            "valence": valence,
            "source_type": s.source_type,
            "event_type": s.event_type,
            "impact": impact,
        })

    return {"events": events}

# ---------------------------------------------------------------------------
# Recurrence events timeline (individual recurring events)
# ---------------------------------------------------------------------------

_RECURRENCE_NEGATIVE_IMPACT = {"critical": "major setback", "high": "significant setback", "medium": "moderate setback", "low": "minor setback"}
_RECURRENCE_POSITIVE_IMPACT = {"critical": "major improvement", "high": "significant improvement", "medium": "moderate improvement", "low": "minor improvement"}


def _split_into_incidents(
    signals: list[SignalEvent],
    resolution_gap_days: int = 7,
    time_gap_days: int = 14,
) -> list[list[SignalEvent]]:
    """Split a list of signals (same normalized title) into distinct incidents.

    An incident boundary is created when:
    1. A ticket_resolved event is followed by a new ticket_created/email_received event.
    2. There is a time gap of >=time_gap_days between consecutive events.
    3. After a resolution, any new event arriving >=resolution_gap_days later starts a new incident.
    """
    if not signals:
        return []

    incidents: list[list[SignalEvent]] = []
    current: list[SignalEvent] = [signals[0]]
    resolved = signals[0].event_type == "ticket_resolved"

    for s in signals[1:]:
        prev = current[-1]
        prev_date = prev.occurred_at
        curr_date = s.occurred_at
        gap_days = (curr_date - prev_date).days if prev_date and curr_date else 0

        # Start a new incident if:
        # (a) ticket was explicitly re-opened (always a new incident)
        # (b) previous incident was resolved and a new issue/email arrives after gap
        # (c) large time gap between events
        new_incident = False
        if s.event_type == "ticket_reopened":
            new_incident = True
        elif resolved and s.event_type in ("ticket_created", "email_received") and gap_days >= resolution_gap_days:
            new_incident = True
        elif gap_days >= time_gap_days:
            new_incident = True

        if new_incident:
            incidents.append(current)
            current = [s]
            resolved = s.event_type == "ticket_resolved"
        else:
            current.append(s)
            if s.event_type == "ticket_resolved":
                resolved = True

    if current:
        incidents.append(current)

    return incidents


async def _llm_generate_recurrence_descriptions(
    events_for_llm: list[dict],
    stage_topic: str | None,
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + recurrence implication for each event.

    Returns list of {"summary": ..., "recurrence_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    stage_label = stage_topic or "the integration lifecycle"
    stage_desc = _STAGE_DESCRIPTIONS.get(stage_topic or "", "the overall integration process")

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        first_seen = ev.get("first_seen", "unknown")
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity={ev['severity']} valence={ev['valence']}\n"
            f"    thread_topic: {ev.get('thread_topic', '(unknown)')}\n"
            f"    recurrence: incident #{ev['incident_number']} of {ev['total_incidents']} "
            f"(first seen: {first_seen})\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing recurrence events for a {software_name} integration "
        f"during the **{stage_label}** stage ({stage_desc}).\n\n"
        "These events represent issues that were previously resolved or addressed "
        "but have resurfaced as new incidents. Each event shows which incident "
        "number it belongs to (e.g., incident #2 of 3 means this is the second "
        "time this issue has appeared).\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what happened "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **recurrence_implication**: 1-2 sentences explaining why this "
        f"issue resurfacing impacts the {stage_label} stage. "
        "Address whether this pattern suggests the root cause wasn't fixed, "
        "whether the vendor's solution was insufficient, or whether this is "
        "a systemic issue. For positive events (valence=positive), note "
        "whether the recurrence suggests the fix might not be durable.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "recurrence_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "recurrence_implication": str(r.get("recurrence_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_recurrence_description_failed", error=str(e))
        return None


async def compute_recurrence_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Return events from issues that resurfaced after being previously resolved.

    True recurrence = same issue topic appearing in a *new* incident after a
    prior incident was resolved or went dormant.  Multi-turn threads (replies,
    comments on the same ticket) are NOT recurrence.
    """
    # Load software for registration date (needed for auto-classify)
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Group ALL signals by normalized title (before stage filtering)
    # Use shared detection function (cross-stage, then stage-filtered)
    recurrence_events = detect_recurrence(all_signals, stage_topic)

    # Sort by date
    recurrence_events.sort(key=lambda x: x[0].occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not recurrence_events:
        return {"events": []}

    # Build cache key that includes stage so descriptions are stage-aware
    cache_field = f"recurrence_desc_{stage_topic or 'all'}"

    # Find signals that need LLM descriptions
    needs_llm: list[tuple[int, dict]] = []
    for i, (s, thread_topic, inc_num, total_inc, first_seen) in enumerate(recurrence_events):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity": s.severity or "medium",
                "valence": meta.get("valence", "negative"),
                "thread_topic": thread_topic,
                "incident_number": inc_num,
                "total_incidents": total_inc,
                "first_seen": first_seen,
            }))

    # Batch LLM call for uncached descriptions
    if needs_llm:
        llm_results = await _llm_generate_recurrence_descriptions(
            [ev for _, ev in needs_llm],
            stage_topic,
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = recurrence_events[idx][0]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    # Build response
    events = []
    for s, thread_topic, inc_num, total_inc, first_seen in recurrence_events:
        meta = s.event_metadata or {}
        valence = meta.get("valence")
        sev = s.severity or "medium"
        if valence == "positive":
            impact = _RECURRENCE_POSITIVE_IMPACT.get(sev, "moderate improvement")
        else:
            impact = _RECURRENCE_NEGATIVE_IMPACT.get(sev, "moderate setback")

        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("recurrence_implication", "")
        else:
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "recurrence_implication": implication,
            "severity": sev,
            "valence": valence or "negative",
            "source_type": s.source_type,
            "event_type": s.event_type,
            "impact": impact,
            "incident_number": inc_num,
            "total_incidents": total_inc,
            "first_seen": first_seen,
            "thread_topic": thread_topic,
        })

    return {"events": events}

# ---------------------------------------------------------------------------
# Escalation events timeline (individual severity-escalation events)
# ---------------------------------------------------------------------------

_ESCALATION_SEVERITY_LABEL = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}


async def _llm_generate_escalation_descriptions(
    events_for_llm: list[dict],
    stage_topic: str | None,
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + escalation implication for each event.

    Returns list of {"summary": ..., "escalation_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    stage_label = stage_topic or "the integration lifecycle"
    stage_desc = _STAGE_DESCRIPTIONS.get(stage_topic or "", "the overall integration process")

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity_from={ev['severity_from']} severity_to={ev['severity_to']}\n"
            f"    thread_topic: {ev.get('thread_topic', '(unknown)')}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing escalation events for a {software_name} integration "
        f"during the **{stage_label}** stage ({stage_desc}).\n\n"
        "These are events where an issue's severity was increased (e.g., medium→high "
        "or high→critical), indicating the problem is worse than initially assessed.\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what happened "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **escalation_implication**: 1-2 sentences explaining why this "
        f"severity escalation impacts the {stage_label} stage. "
        "Address what the escalation reveals about the issue's true severity, "
        "whether initial triage was inadequate, or if the problem is compounding.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "escalation_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "escalation_implication": str(r.get("escalation_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_escalation_description_failed", error=str(e))
        return None


async def compute_escalation_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Return individual events where severity escalated within a thread.

    An escalation event is the specific signal where severity increased
    compared to the previous event in the same thread (e.g., medium→high).
    """
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Use shared detection function (cross-stage, then stage-filtered)
    escalation_events = detect_escalation(all_signals, stage_topic)
    escalation_events.sort(key=lambda x: x[0].occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not escalation_events:
        return {"events": []}

    cache_field = f"escalation_desc_{stage_topic or 'all'}"

    needs_llm: list[tuple[int, dict]] = []
    for i, (s, thread_topic, sev_from, sev_to) in enumerate(escalation_events):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity_from": sev_from,
                "severity_to": sev_to,
                "thread_topic": thread_topic,
            }))

    if needs_llm:
        llm_results = await _llm_generate_escalation_descriptions(
            [ev for _, ev in needs_llm],
            stage_topic,
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = escalation_events[idx][0]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    events = []
    for s, thread_topic, sev_from, sev_to in escalation_events:
        meta = s.event_metadata or {}
        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("escalation_implication", "")
        else:
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        from_label = _ESCALATION_SEVERITY_LABEL.get(sev_from, sev_from)
        to_label = _ESCALATION_SEVERITY_LABEL.get(sev_to, sev_to)

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "escalation_implication": implication,
            "severity_from": sev_from,
            "severity_to": sev_to,
            "severity_label": f"{from_label} → {to_label}",
            "source_type": s.source_type,
            "event_type": s.event_type,
            "thread_topic": thread_topic,
        })

    return {"events": events}


# ---------------------------------------------------------------------------
# Resolution events timeline (individual resolved-ticket events)
# ---------------------------------------------------------------------------


def _format_duration(hours: float) -> str:
    """Human-readable duration string from hours."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 24:
        return f"{hours:.0f}h"
    days = hours / 24
    if days < 10:
        return f"{days:.1f}d"
    return f"{days:.0f}d"


def _resolution_speed_label(hours: float, category: str) -> str:
    """Classify resolution speed relative to category benchmarks.

    Returns a directional label like "fast", "typical", "slow", "very slow".
    """
    if category == "issue":
        if hours <= 4:
            return "very fast"
        if hours <= 24:
            return "fast"
        if hours <= 72:
            return "typical"
        if hours <= 168:
            return "slow"
        return "very slow"
    else:  # feature
        if hours <= 24:
            return "very fast"
        if hours <= 72:
            return "fast"
        if hours <= 168:
            return "typical"
        if hours <= 336:
            return "slow"
        return "very slow"


async def _llm_generate_resolution_descriptions(
    events_for_llm: list[dict],
    stage_topic: str | None,
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + resolution implication for each event.

    Returns list of {"summary": ..., "resolution_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    stage_label = stage_topic or "the integration lifecycle"
    stage_desc = _STAGE_DESCRIPTIONS.get(stage_topic or "", "the overall integration process")

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] category={ev['category']} source={ev['source_type']} "
            f"severity={ev['severity']} speed={ev['speed_label']}\n"
            f"    resolution_hours: {ev['resolution_hours']:.1f}h "
            f"({_format_duration(ev['resolution_hours'])})\n"
            f"    created_title: {ev.get('created_title', '(none)')}\n"
            f"    resolved_title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing resolution events for a {software_name} integration "
        f"during the **{stage_label}** stage ({stage_desc}).\n\n"
        "These are tickets that were created and then resolved. Each event shows "
        "how long resolution took and whether the speed was fast, typical, or slow.\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what was resolved "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **resolution_implication**: 1-2 sentences explaining what the "
        f"resolution time means for the {stage_label} stage. "
        "For fast resolutions, note the positive signal about vendor support. "
        "For slow resolutions, explain the cost of delay (blocked work, "
        "workarounds needed, lost productivity). "
        "For typical times, provide brief context.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "resolution_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "resolution_implication": str(r.get("resolution_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_resolution_description_failed", error=str(e))
        return None


async def compute_resolution_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Return individual resolved-ticket events for the timeline.

    Each event represents a ticket that was created and then resolved,
    showing the resolution duration and its implication.
    """
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Use shared detection function (cross-stage pairing, then stage-filtered)
    resolution_items = detect_resolution(all_signals, stage_topic)

    # Sort by resolved date
    resolution_items.sort(
        key=lambda x: x[0].occurred_at or datetime.min.replace(tzinfo=timezone.utc)
    )

    if not resolution_items:
        return {"events": []}

    cache_field = f"resolution_desc_{stage_topic or 'all'}"

    needs_llm: list[tuple[int, dict]] = []
    for i, (resolved, created, cat, hours) in enumerate(resolution_items):
        meta = resolved.event_metadata or {}
        speed = _resolution_speed_label(hours, cat)
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": resolved.title,
                "created_title": created.title,
                "body": resolved.body,
                "event_type": resolved.event_type,
                "source_type": resolved.source_type,
                "severity": resolved.severity or created.severity or "medium",
                "category": cat,
                "resolution_hours": hours,
                "speed_label": speed,
            }))

    if needs_llm:
        llm_results = await _llm_generate_resolution_descriptions(
            [ev for _, ev in needs_llm],
            stage_topic,
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = resolution_items[idx][0]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    events = []
    for resolved, created, cat, hours in resolution_items:
        meta = resolved.event_metadata or {}
        cached = meta.get(cache_field)
        speed = _resolution_speed_label(hours, cat)

        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("resolution_implication", "")
        else:
            summary = _fallback_friction_summary(resolved.title, resolved.event_type)
            implication = ""

        events.append({
            "date": resolved.occurred_at.isoformat() if resolved.occurred_at else None,
            "summary": summary,
            "resolution_implication": implication,
            "resolution_hours": round(hours, 1),
            "resolution_label": _format_duration(hours),
            "speed_label": speed,
            "category": cat,
            "severity": resolved.severity or created.severity or "medium",
            "source_type": resolved.source_type,
            "event_type": resolved.event_type,
        })

    return {"events": events}


# ---------------------------------------------------------------------------
# Effort events timeline (individual core vs peripheral events)
# ---------------------------------------------------------------------------


async def _llm_generate_effort_descriptions(
    events_for_llm: list[dict],
    stage_topic: str | None,
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + effort implication for each event.

    Returns list of {"summary": ..., "effort_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    stage_label = stage_topic or "the integration lifecycle"
    stage_desc = _STAGE_DESCRIPTIONS.get(stage_topic or "", "the overall integration process")

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        classification = ev["classification"]
        peripheral_cat = ev.get("peripheral_category") or "N/A"
        entries.append(
            f"[{i}] classification={classification} "
            f"peripheral_category={peripheral_cat} "
            f"source={ev['source_type']} severity={ev['severity']}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing effort events for a {software_name} integration "
        f"during the **{stage_label}** stage ({stage_desc}).\n\n"
        "Each event is classified as either 'core' (directly about the product's "
        "intended functionality) or 'peripheral' (ecosystem friction like SSO, "
        "billing, access/permissions, or compliance — not the product itself).\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of what happened "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **effort_implication**: 1-2 sentences explaining what this "
        f"event means for integration effort during {stage_label}. "
        "For peripheral events, explain how ecosystem friction (SSO setup, "
        "billing disputes, access provisioning) diverts effort away from "
        "core value. For core events, note whether this advances or "
        "blocks the integration's primary purpose.\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "effort_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "effort_implication": str(r.get("effort_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_effort_description_failed", error=str(e))
        return None


async def compute_effort_events(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    stage_topic: str | None = None,
) -> dict:
    """Return individual events classified as core vs peripheral for the timeline.

    Each event shows whether it represents core product work or peripheral
    ecosystem friction (SSO, billing, access, compliance).
    """
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill: classify untagged signals deterministically
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Apply stage filter
    if stage_topic:
        all_signals = [
            s for s in all_signals
            if (s.event_metadata or {}).get("stage_topic") == stage_topic
        ]

    if not all_signals:
        return {"events": []}

    # Use shared detection function
    classified = detect_effort(all_signals)

    # Sort by date
    classified.sort(
        key=lambda x: x[0].occurred_at or datetime.min.replace(tzinfo=timezone.utc)
    )

    cache_field = f"effort_desc_{stage_topic or 'all'}"

    needs_llm: list[tuple[int, dict]] = []
    for i, (sig, cls, cat) in enumerate(classified):
        meta = sig.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": sig.title,
                "body": sig.body,
                "event_type": sig.event_type,
                "source_type": sig.source_type,
                "severity": sig.severity or "medium",
                "classification": cls,
                "peripheral_category": cat,
            }))

    if needs_llm:
        llm_results = await _llm_generate_effort_descriptions(
            [ev for _, ev in needs_llm],
            stage_topic,
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = classified[idx][0]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    events = []
    for sig, cls, cat in classified:
        meta = sig.event_metadata or {}
        cached = meta.get(cache_field)

        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("effort_implication", "")
        else:
            summary = _fallback_friction_summary(sig.title, sig.event_type)
            implication = ""

        events.append({
            "date": sig.occurred_at.isoformat() if sig.occurred_at else None,
            "summary": summary,
            "effort_implication": implication,
            "classification": cls,
            "peripheral_category": cat,
            "severity": sig.severity or "medium",
            "source_type": sig.source_type,
            "event_type": sig.event_type,
        })

    return {"events": events}


# ---------------------------------------------------------------------------
# Reliability Events (timeline)
# ---------------------------------------------------------------------------

_RELIABILITY_SEVERITY_LABELS = {
    "critical": "critical incident",
    "high": "major incident",
    "medium": "moderate incident",
    "low": "minor incident",
}


async def _llm_generate_reliability_descriptions(
    events_for_llm: list[dict],
    software_name: str,
) -> list[dict[str, str]] | None:
    """Use LLM to generate summary + reliability implication for each incident event.

    Returns list of {"summary": ..., "reliability_implication": ...} or None on failure.
    """
    if not events_for_llm:
        return []

    import json as _json

    import anthropic

    from app.config import settings

    if not settings.ANTHROPIC_API_KEY:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    entries = []
    for i, ev in enumerate(events_for_llm):
        body_snippet = (ev.get("body") or "")[:400]
        entries.append(
            f"[{i}] type={ev['event_type']} source={ev['source_type']} "
            f"severity={ev['severity']}\n"
            f"    title: {ev.get('title', '(none)')}\n"
            f"    body: {body_snippet}"
        )

    prompt = (
        f"You are analyzing reliability-impacting incidents for a {software_name} "
        "integration.\n\n"
        "For each event below, generate:\n"
        "1. **summary**: A concise one-line description of the incident "
        "(~8-15 words). Reference the specific content — don't be generic. "
        "Don't repeat the ticket ID.\n"
        "2. **reliability_implication**: 1-2 sentences explaining how this "
        "incident specifically impacts the reliability of the integration. "
        "Reference the actual problem described — was there downtime, data loss, "
        "service degradation, latency spikes? How does it affect trust in the "
        "vendor's uptime and stability?\n\n"
        "Events:\n" + "\n\n".join(entries) + "\n\n"
        "Return ONLY a JSON array with one object per event, in order. "
        'Each object: {"summary": "...", "reliability_implication": "..."}\n'
        "No markdown fences, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            results = _json.loads(raw)
        except _json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                results = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response: {raw[:200]}")

        if not isinstance(results, list):
            raise ValueError("LLM response is not a list")

        validated: list[dict[str, str]] = []
        for r in results:
            validated.append({
                "summary": str(r.get("summary", "")),
                "reliability_implication": str(r.get("reliability_implication", "")),
            })
        return validated
    except Exception as e:
        logger.warning("llm_reliability_description_failed", error=str(e))
        return None


async def compute_reliability_events(
    db: "AsyncSession",
    company_id: "uuid.UUID",
    software_id: "uuid.UUID",
) -> dict:
    """Return individual incident events that contribute to reliability scoring."""
    sw_result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.id == software_id,
            SoftwareRegistration.company_id == company_id,
        )
    )
    software = sw_result.scalar_one_or_none()
    if not software:
        return {"error": "software_not_found"}

    result = await db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.company_id == company_id,
            SignalEvent.software_id == software_id,
        )
        .order_by(SignalEvent.occurred_at.asc())
    )
    all_signals = _tz_fix(list(result.scalars().all()))

    # Auto-backfill classification for untagged signals
    unclassified = [s for s in all_signals if "valence" not in (s.event_metadata or {})]
    if unclassified:
        from app.signals.classification import _deterministic_classify

        reg_at = software.created_at
        if reg_at and reg_at.tzinfo is None:
            reg_at = reg_at.replace(tzinfo=timezone.utc)

        for sig in unclassified:
            occ = sig.occurred_at
            if occ and occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            days = max(0, (occ - reg_at).days) if reg_at and occ else 0

            tags = _deterministic_classify(
                sig.source_type, sig.event_type, sig.severity,
                sig.title, sig.body, days,
            )
            meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
            meta.update(tags)
            sig.event_metadata = meta

        await db.commit()

        result = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
            )
            .order_by(SignalEvent.occurred_at.asc())
        )
        all_signals = _tz_fix(list(result.scalars().all()))

    # Filter to incident-related signals only
    incident_signals = detect_reliability_signals(all_signals)
    incident_signals.sort(key=lambda s: s.occurred_at or datetime.min.replace(tzinfo=timezone.utc))

    if not incident_signals:
        return {"events": []}

    # LLM description caching
    cache_field = "reliability_desc"

    needs_llm: list[tuple[int, dict]] = []
    for i, s in enumerate(incident_signals):
        meta = s.event_metadata or {}
        if cache_field not in meta:
            needs_llm.append((i, {
                "title": s.title,
                "body": s.body,
                "event_type": s.event_type,
                "source_type": s.source_type,
                "severity": s.severity or "medium",
            }))

    if needs_llm:
        llm_results = await _llm_generate_reliability_descriptions(
            [ev for _, ev in needs_llm],
            software.software_name,
        )

        if llm_results and len(llm_results) == len(needs_llm):
            dirty = False
            for (idx, _ev_data), desc in zip(needs_llm, llm_results):
                sig = incident_signals[idx]
                meta = dict(sig.event_metadata) if isinstance(sig.event_metadata, dict) else {}
                meta[cache_field] = desc
                sig.event_metadata = meta
                dirty = True
            if dirty:
                await db.commit()

    # Also run reliability number extractions for downtime/uptime data
    await _backfill_reliability_extractions(db, incident_signals)

    # Build response
    events = []
    for s in incident_signals:
        meta = s.event_metadata or {}
        sev = s.severity or "medium"
        severity_label = _RELIABILITY_SEVERITY_LABELS.get(sev, "incident")

        cached = meta.get(cache_field)
        if cached and isinstance(cached, dict):
            summary = cached.get("summary", "")
            implication = cached.get("reliability_implication", "")
        else:
            summary = _fallback_friction_summary(s.title, s.event_type)
            implication = ""

        # Extract downtime/uptime from reliability_numbers cache
        nums = meta.get("reliability_numbers", {})
        downtime_hours = nums.get("downtime_hours") if nums else None
        uptime_pct = nums.get("uptime_pct") if nums else None

        events.append({
            "date": s.occurred_at.isoformat() if s.occurred_at else None,
            "summary": summary,
            "reliability_implication": implication,
            "severity": sev,
            "severity_label": severity_label,
            "source_type": s.source_type,
            "event_type": s.event_type,
            "downtime_hours": downtime_hours,
            "uptime_pct": uptime_pct,
        })

    return {"events": events}
