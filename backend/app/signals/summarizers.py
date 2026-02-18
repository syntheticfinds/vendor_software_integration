"""Hierarchical summarizers for the analysis pipeline.

Each summarizer is a focused LLM call with a specialized system prompt.
Sub-category summaries feed into category summaries, which feed into overall
summaries, which feed into the review drafter.
"""

import asyncio
from datetime import datetime

import structlog

from app.signals.llm import summarize
from app.signals.models import SignalEvent

logger = structlog.get_logger()


def _format_signals(signals: list[SignalEvent], max_signals: int = 30) -> str:
    """Format signals into a concise text block for LLM consumption."""
    lines: list[str] = []
    for sig in signals[:max_signals]:
        sev = sig.severity or "medium"
        meta = sig.event_metadata or {}
        valence = meta.get("valence", "unknown")
        date_str = ""
        if sig.occurred_at:
            dt = sig.occurred_at if isinstance(sig.occurred_at, datetime) else sig.occurred_at
            date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
        line = f"- [{date_str}] [{sev}] [{valence}] {sig.title or sig.event_type}"
        if sig.body:
            body_preview = sig.body[:200].replace("\n", " ")
            line += f" — {body_preview}"
        lines.append(line)
    if len(signals) > max_signals:
        lines.append(f"  ... and {len(signals) - max_signals} more signals")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health sub-category summarizers
# ---------------------------------------------------------------------------

_FORMAT_RULES = (
    "FORMATTING RULES (mandatory):\n"
    "- Do NOT use any markdown: no bold (**), no headings (#), no bullet lists.\n"
    "- Write plain prose sentences and paragraphs only.\n"
    "- Do NOT mention any numeric scores, percentages, or ratings.\n"
    "- Quote or closely paraphrase the exact words from signal titles and bodies. "
    "Use the same terminology the events use — do not rephrase into abstract language.\n"
    "- Reference specific event titles, dates, and severity levels from the signals."
)

_RELIABILITY_SYSTEM = (
    "You are an integration reliability analyst. Summarize the reliability "
    "signals for a software integration concisely (2-4 sentences). Focus on "
    "incident patterns, outage frequency, downtime impact, recovery time, "
    "and availability trends. Be factual. Quote the exact wording from "
    "signal titles and bodies rather than paraphrasing abstractly.\n\n"
    + _FORMAT_RULES
)

_PERFORMANCE_SYSTEM = (
    "You are an integration performance analyst. Summarize the performance "
    "signals for a software integration concisely (2-4 sentences). Focus on "
    "latency issues, rate-limiting occurrences, throughput constraints, and "
    "response time trends. Be factual. Quote the exact wording from "
    "signal titles and bodies rather than paraphrasing abstractly.\n\n"
    + _FORMAT_RULES
)

_FITNESS_SYSTEM = (
    "You are a product-market fit analyst. Summarize the fitness-for-purpose "
    "signals for a software integration concisely (2-4 sentences). Focus on "
    "feature request patterns, capability gaps, fulfillment rate of past "
    "requests, and how well the software serves its intended use. Be factual. "
    "Quote the exact wording from signal titles and bodies.\n\n"
    + _FORMAT_RULES
)


def _signal_count_summary(signals: list[SignalEvent], category: str) -> str:
    """Generate a short deterministic summary from signal counts when LLM is unavailable."""
    n = len(signals)
    neg = sum(1 for s in signals if (s.event_metadata or {}).get("valence") == "negative")
    pos = sum(1 for s in signals if (s.event_metadata or {}).get("valence") == "positive")
    label = category.replace("_", " ")
    parts = [f"{n} {label}-related signal{'s' if n != 1 else ''} recorded"]
    if neg:
        parts.append(f"{neg} negative")
    if pos:
        parts.append(f"{pos} positive")
    return f"{', '.join(parts)}."


async def summarize_reliability(
    signals: list[SignalEvent], score: int, software_name: str,
) -> str:
    if not signals:
        return f"No reliability-specific signals were recorded for {software_name}."
    try:
        user = (
            f"Software: {software_name}\n"
            f"Signal count: {len(signals)}\n\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_RELIABILITY_SYSTEM, user)
    except Exception:
        return _signal_count_summary(signals, "reliability")


async def summarize_performance(
    signals: list[SignalEvent], score: int, software_name: str,
) -> str:
    if not signals:
        return f"No performance-specific signals were recorded for {software_name}."
    try:
        user = (
            f"Software: {software_name}\n"
            f"Signal count: {len(signals)}\n\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_PERFORMANCE_SYSTEM, user)
    except Exception:
        return _signal_count_summary(signals, "performance")


async def summarize_fitness(
    signals: list[SignalEvent], score: int, software_name: str,
) -> str:
    if not signals:
        return f"No fitness-for-purpose signals were recorded for {software_name}."
    try:
        user = (
            f"Software: {software_name}\n"
            f"Signal count: {len(signals)}\n\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_FITNESS_SYSTEM, user)
    except Exception:
        return _signal_count_summary(signals, "fitness for purpose")


_HEALTH_OVERALL_SYSTEM = (
    "You are a senior integration health analyst. Combine the reliability, "
    "performance, and fitness-for-purpose summaries into a cohesive overall "
    "health assessment (3-5 sentences). Spend more words on whichever areas "
    "are listed first — they are ordered by concern level (most concerning "
    "first). Write in third person about the software. Quote specific event "
    "details from the sub-summaries rather than using generic language. "
    "Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)


async def summarize_health_overall(
    sub_summaries: dict[str, str],
    scores: dict[str, int],
    overall_score: int,
    software_name: str,
) -> str:
    # Order sub-summaries by score ascending (worst first = most emphasis)
    ordered_cats = sorted(
        [c for c in ("reliability", "performance", "fitness_for_purpose") if sub_summaries.get(c)],
        key=lambda c: scores.get(c, 100),
    )
    parts: list[str] = []
    for cat in ordered_cats:
        label = cat.replace("_", " ").title()
        parts.append(f"{label}: {sub_summaries[cat]}")
    if not parts:
        return f"Insufficient data to produce an overall health summary for {software_name}."

    try:
        user = (
            f"Software: {software_name}\n\n"
            f"Sub-category summaries (ordered by concern level, most concerning first):\n\n"
            + "\n\n".join(parts)
        )
        return await summarize(_HEALTH_OVERALL_SYSTEM, user)
    except Exception:
        fallback_parts = [sub_summaries[c] for c in ordered_cats if sub_summaries.get(c)]
        return " ".join(fallback_parts)


# ---------------------------------------------------------------------------
# Trajectory sub-metric summarizers (per stage)
# ---------------------------------------------------------------------------

_FRICTION_SYSTEM = (
    "You are an integration friction analyst. Summarize the issue friction "
    "for a specific integration lifecycle stage in 2-3 sentences. Focus on "
    "the most impactful issues by severity, and whether positive outcomes "
    "offset the friction. Quote the exact event titles and wording from the "
    "signals. Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)

_RECURRENCE_SYSTEM = (
    "You are an issue recurrence analyst. Summarize recurring issue patterns "
    "for a specific integration lifecycle stage in 2-3 sentences. The signals "
    "you receive are from threads that had multiple incidents (the same issue "
    "re-surfacing after a gap). Focus on which issues keep coming back, how "
    "often, and what this suggests about unresolved root causes. Quote exact "
    "event titles. Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)

_ESCALATION_SYSTEM = (
    "You are a severity escalation analyst. Summarize severity escalation "
    "patterns for a specific integration lifecycle stage in 2-3 sentences. "
    "The signals you receive are from issue threads where severity increased "
    "over time (e.g. medium -> high). Focus on which issues escalated and "
    "what that implies about the integration health. Quote exact event "
    "titles. Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)

_RESOLUTION_SYSTEM = (
    "You are a resolution velocity analyst. Summarize ticket resolution "
    "patterns for a specific integration lifecycle stage in 2-3 sentences. "
    "Focus on which issues got resolved vs. remain open, and how quickly "
    "resolution happened. Quote exact event titles and dates. "
    "Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)

_EFFORT_SYSTEM = (
    "You are an integration effort analyst. Summarize the overall effort "
    "required during a specific integration lifecycle stage in 2-3 sentences. "
    "Classify each signal as either core product work (data engineering, "
    "queries, pipelines) or peripheral friction (SSO, billing, access "
    "control, compliance). Focus on the balance between productive core "
    "work vs. peripheral overhead. Quote exact event titles. "
    "Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)


def _metric_fallback(signals: list[SignalEvent], metric: str, stage_name: str) -> str:
    """Deterministic fallback for trajectory sub-metric summarizers."""
    n = len(signals)
    neg = sum(1 for s in signals if (s.event_metadata or {}).get("valence") == "negative")
    return f"{n} {metric}-related signal{'s' if n != 1 else ''} in {stage_name} stage ({neg} negative)."


async def summarize_friction(
    signals: list[SignalEvent], score: float, stage_name: str, software_name: str,
) -> str:
    if not signals:
        return f"No friction signals in the {stage_name} stage."
    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_FRICTION_SYSTEM, user)
    except Exception:
        return _metric_fallback(signals, "friction", stage_name)


async def summarize_recurrence(
    signals: list[SignalEvent], score: float, stage_name: str, software_name: str,
) -> str:
    if not signals:
        return f"No recurring issues detected in the {stage_name} stage."
    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_RECURRENCE_SYSTEM, user)
    except Exception:
        return _metric_fallback(signals, "recurrence", stage_name)


async def summarize_escalation(
    signals: list[SignalEvent], score: float, stage_name: str, software_name: str,
) -> str:
    if not signals:
        return f"No escalation patterns in the {stage_name} stage."
    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_ESCALATION_SYSTEM, user)
    except Exception:
        return _metric_fallback(signals, "escalation", stage_name)


async def summarize_resolution(
    signals: list[SignalEvent], score: float, stage_name: str, software_name: str,
) -> str:
    if not signals:
        return f"No resolution data in the {stage_name} stage."
    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_RESOLUTION_SYSTEM, user)
    except Exception:
        return _metric_fallback(signals, "resolution", stage_name)


async def summarize_effort(
    signals: list[SignalEvent], score: float, stage_name: str, software_name: str,
) -> str:
    if not signals:
        return f"No signals in the {stage_name} stage to assess effort."
    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n"
            f"Signals:\n{_format_signals(signals)}"
        )
        return await summarize(_EFFORT_SYSTEM, user)
    except Exception:
        return _metric_fallback(signals, "effort", stage_name)


# ---------------------------------------------------------------------------
# Stage summarizer
# ---------------------------------------------------------------------------

_STAGE_SYSTEM = (
    "You are an integration lifecycle analyst. Combine the sub-metric "
    "summaries (friction, recurrence, escalation, resolution, effort) into a "
    "cohesive stage-level assessment in 3-4 sentences. Spend more words on "
    "whichever sub-metrics are listed first — they are ordered by concern "
    "level (most concerning first). Preserve the specific event details and "
    "exact terminology from the sub-summaries rather than abstracting them. "
    "Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)


async def summarize_stage(
    stage_name: str,
    sub_summaries: dict[str, str],
    smoothness_score: float,
    software_name: str,
) -> str:
    # Order sub-metrics by score ascending (worst first = most emphasis)
    # We don't have individual scores here, so preserve the order they come in
    # but still filter to non-empty ones
    metrics_order = ("friction", "recurrence", "escalation", "resolution", "effort")
    parts: list[str] = []
    for metric in metrics_order:
        if metric in sub_summaries and sub_summaries[metric]:
            parts.append(f"{metric.title()}: {sub_summaries[metric]}")
    if not parts:
        return f"Insufficient data for the {stage_name} stage of {software_name}."

    try:
        user = (
            f"Software: {software_name} | Stage: {stage_name}\n\n"
            f"Sub-metric summaries (ordered by concern level, most concerning first):\n\n"
            + "\n\n".join(parts)
        )
        return await summarize(_STAGE_SYSTEM, user)
    except Exception:
        plain = [sub_summaries[m] for m in metrics_order if sub_summaries.get(m)]
        return " ".join(plain)


# ---------------------------------------------------------------------------
# Overall trajectory summarizer
# ---------------------------------------------------------------------------

_TRAJECTORY_OVERALL_SYSTEM = (
    "You are a senior integration maturity analyst. Combine per-stage "
    "summaries into an overall trajectory assessment in 3-5 sentences. "
    "Note the current lifecycle stage, any regression, and the biggest "
    "cross-stage patterns. Preserve specific event details from the stage "
    "summaries. Do NOT mention any numeric scores.\n\n"
    + _FORMAT_RULES
)


async def summarize_trajectory_overall(
    stage_summaries: dict[str, str],
    overall_score: float,
    current_stage: str,
    regression_detected: bool,
    regression_detail: str | None,
    software_name: str,
) -> str:
    parts: list[str] = []
    for stage_name, summary in stage_summaries.items():
        if summary:
            parts.append(f"{stage_name.title()}: {summary}")
    if not parts:
        return f"Insufficient trajectory data for {software_name}."

    try:
        regression_note = ""
        if regression_detected and regression_detail:
            regression_note = f"\nREGRESSION DETECTED: {regression_detail}\n"

        user = (
            f"Software: {software_name}\n"
            f"Current stage: {current_stage}\n"
            f"{regression_note}\n"
            f"Stage summaries:\n\n" + "\n\n".join(parts)
        )
        return await summarize(_TRAJECTORY_OVERALL_SYSTEM, user)
    except Exception:
        regression_text = f" Regression detected: {regression_detail}" if regression_detected and regression_detail else ""
        plain = [s for s in stage_summaries.values() if s]
        return f"{software_name} is in the {current_stage} stage.{regression_text} " + " ".join(plain)


# ---------------------------------------------------------------------------
# Review drafter
# ---------------------------------------------------------------------------

_REVIEW_DRAFTER_SYSTEM = (
    "You write evidence-based customer reviews of vendor software. Every "
    "statement must trace back to signal data provided. Write in first-person "
    "plural ('we', 'our team'). Be candid and helpful.\n\n"
    "CRITICAL RULES:\n"
    "- NEVER fabricate experiences not in the data\n"
    "- Scale the review to the data: 1-4 signals = 1-2 paragraphs; "
    "5-10 = moderate review; 11+ = detailed review\n"
    "- Include 'What went well' only if there are positive signals\n"
    "- Include 'What didn't go well' only if there are negative signals\n"
    "- Acknowledge limited data when signal count is low\n"
    "- Reference actual events (titles, dates) when possible\n"
    "- Quote the exact wording from event titles rather than paraphrasing\n"
    "- Do NOT mention any numeric scores, percentages, or ratings\n\n"
    + _FORMAT_RULES
)


async def draft_review(
    software_name: str,
    vendor_name: str,
    intended_use: str | None,
    health_summary: str,
    trajectory_summary: str,
    all_summaries: dict,
    all_scores: dict,
    signal_count: int,
    confidence_tier: str,
) -> dict[str, str]:
    """Draft a customer review using hierarchical summaries as structured input.

    Returns ``{"subject": "...", "body": "..."}``.
    """
    use_line = f'Intended use: "{intended_use}"\n' if intended_use else ""

    # Collect all sub-summaries for context
    detail_sections: list[str] = []

    # Health sub-summaries
    health_subs = all_summaries.get("health", {})
    for cat in ("reliability", "performance", "fitness_for_purpose"):
        if cat in health_subs and health_subs[cat]:
            detail_sections.append(f"  {cat.replace('_', ' ').title()}: {health_subs[cat]}")

    # Trajectory sub-summaries
    traj = all_summaries.get("trajectory", {})
    stages = traj.get("stages", {})
    for stage_name, stage_subs in stages.items():
        if isinstance(stage_subs, dict):
            stage_overall = stage_subs.get("overall", "")
            if stage_overall:
                detail_sections.append(f"  {stage_name.title()} stage: {stage_overall}")

    details = "\n".join(detail_sections) if detail_sections else "No detailed sub-summaries available."

    user = (
        f"Software: {software_name} by {vendor_name}\n"
        f"{use_line}"
        f"Signal count: {signal_count} | Confidence: {confidence_tier}\n\n"
        f"HEALTH ASSESSMENT:\n{health_summary}\n\n"
        f"TRAJECTORY ASSESSMENT:\n{trajectory_summary}\n\n"
        f"DETAILED BREAKDOWNS:\n{details}\n\n"
        f"Write a review with a title and body. Return as:\n"
        f"TITLE: <review title>\n"
        f"BODY:\n<review body>"
    )

    try:
        raw = await summarize(_REVIEW_DRAFTER_SYSTEM, user, temperature=0.4, max_tokens=2048)

        # Parse TITLE: / BODY: format
        subject = f"Review: {software_name} by {vendor_name}"
        body = raw

        if "TITLE:" in raw:
            parts = raw.split("BODY:", 1)
            title_part = parts[0]
            subject = title_part.replace("TITLE:", "").strip()
            if len(parts) > 1:
                body = parts[1].strip()

        return {"subject": subject, "body": body}
    except Exception:
        # Deterministic fallback review
        subject = f"Review: {software_name} by {vendor_name}"
        body_parts = [
            f"Integration review for {software_name} by {vendor_name}.",
            f"Based on {signal_count} signals (confidence: {confidence_tier}).",
        ]
        if health_summary:
            body_parts.append(f"\nHealth: {health_summary}")
        if trajectory_summary:
            body_parts.append(f"\nTrajectory: {trajectory_summary}")
        return {"subject": subject, "body": "\n".join(body_parts)}


# ---------------------------------------------------------------------------
# Orchestrator — runs the full hierarchy
# ---------------------------------------------------------------------------


async def run_hierarchical_summarizers(
    health_breakdown: dict[str, int],
    health_overall_score: int,
    stage_groups: dict[str, list[SignalEvent]],
    stage_metrics: dict[str, dict[str, float]],
    stage_smoothness: dict[str, float],
    overall_smoothness: float,
    current_stage: str,
    regression_detected: bool,
    regression_detail: str | None,
    software_name: str,
    all_signals: list[SignalEvent] | None = None,
    health_signals: list[SignalEvent] | None = None,
) -> dict:
    """Run the full hierarchical summarization pipeline.

    Returns the summary tree:
    {
        "health": {"reliability": ..., "performance": ..., "fitness_for_purpose": ..., "overall": ...},
        "trajectory": {
            "stages": {
                "onboarding": {"friction": ..., ..., "overall": ...},
                ...
            },
            "overall": ...
        }
    }
    """
    from app.signals.trajectory import (
        detect_effort,
        detect_escalation,
        detect_fitness_signals,
        detect_friction_signals,
        detect_performance_signals,
        detect_recurrence,
        detect_reliability_signals,
        detect_resolution,
    )

    all_sigs = all_signals or []
    hs_sigs = health_signals or all_sigs

    # ── Level 0: All sub-category summarizers in parallel ──
    level0_tasks: list[asyncio.Task] = []
    level0_keys: list[tuple[str, str]] = []  # (domain, key) for tracking

    # Health sub-categories — use shared detect functions (same as timeline endpoints)
    health_detect = {
        "reliability": detect_reliability_signals(hs_sigs),
        "performance": detect_performance_signals(hs_sigs),
        "fitness_for_purpose": detect_fitness_signals(hs_sigs),
    }
    health_summarizer = {
        "reliability": summarize_reliability,
        "performance": summarize_performance,
        "fitness_for_purpose": summarize_fitness,
    }
    for cat in ("reliability", "performance", "fitness_for_purpose"):
        signals = health_detect[cat]
        score = health_breakdown.get(cat, 75)
        task = asyncio.ensure_future(health_summarizer[cat](signals, score, software_name))
        level0_tasks.append(task)
        level0_keys.append(("health", cat))

    # Trajectory sub-metrics per stage — use shared detect_* functions
    # (same source of truth as timeline endpoints + scoring)
    active_stages = {s: sigs for s, sigs in stage_groups.items() if sigs}
    for stage_name, sigs in active_stages.items():
        metrics = stage_metrics.get(stage_name, {})

        # Detect signal subsets using the same functions as the timeline endpoints
        friction_sigs = detect_friction_signals(sigs)
        recurrence_sigs = [sig for sig, *_ in detect_recurrence(all_sigs, stage_name)]
        escalation_sigs = [sig for sig, *_ in detect_escalation(all_sigs, stage_name)]
        resolution_pairs = detect_resolution(all_sigs, stage_name)
        resolution_sigs: list[SignalEvent] = []
        seen_ids: set[int] = set()
        for resolved, created, _cat, _hours in resolution_pairs:
            for s in (created, resolved):
                if id(s) not in seen_ids:
                    seen_ids.add(id(s))
                    resolution_sigs.append(s)
        effort_sigs = [sig for sig, *_ in detect_effort(sigs)]

        sub_metric_signals = {
            "friction": friction_sigs,
            "recurrence": recurrence_sigs,
            "escalation": escalation_sigs,
            "resolution": resolution_sigs,
            "effort": effort_sigs,
        }

        summarizer_map = {
            "friction": summarize_friction,
            "recurrence": summarize_recurrence,
            "escalation": summarize_escalation,
            "resolution": summarize_resolution,
            "effort": summarize_effort,
        }
        for metric_name, fn in summarizer_map.items():
            metric_signals = sub_metric_signals[metric_name]
            metric_score = metrics.get(metric_name, 50.0)
            task = asyncio.ensure_future(fn(metric_signals, metric_score, stage_name, software_name))
            level0_tasks.append(task)
            level0_keys.append(("trajectory", f"{stage_name}.{metric_name}"))

    # Run all level 0 in parallel
    try:
        level0_results = await asyncio.gather(*level0_tasks, return_exceptions=True)
    except Exception:
        logger.warning("level0_summarizers_failed")
        level0_results = [None] * len(level0_tasks)

    # Unpack results
    health_sub_summaries: dict[str, str] = {}
    traj_sub_summaries: dict[str, dict[str, str]] = {}

    for (domain, key), result in zip(level0_keys, level0_results):
        text = result if isinstance(result, str) else ""
        if domain == "health":
            health_sub_summaries[key] = text
        else:
            stage_name, metric_name = key.split(".", 1)
            if stage_name not in traj_sub_summaries:
                traj_sub_summaries[stage_name] = {}
            traj_sub_summaries[stage_name][metric_name] = text

    # ── Level 1: Category summarizers in parallel ──
    level1_tasks: list[asyncio.Task] = []
    level1_keys: list[tuple[str, str]] = []

    # Health overall
    level1_tasks.append(asyncio.ensure_future(
        summarize_health_overall(
            health_sub_summaries, health_breakdown, health_overall_score, software_name,
        )
    ))
    level1_keys.append(("health", "overall"))

    # Per-stage summarizers — order sub-metrics by score (worst first)
    for stage_name in active_stages:
        sub_sums = traj_sub_summaries.get(stage_name, {})
        score = stage_smoothness.get(stage_name, 50.0)
        metrics = stage_metrics.get(stage_name, {})

        # Reorder sub-summaries by metric score ascending (worst first)
        ordered_subs: dict[str, str] = {}
        ordered_metrics = sorted(
            [m for m in ("friction", "recurrence", "escalation", "resolution", "effort") if sub_sums.get(m)],
            key=lambda m: metrics.get(m, 100.0),
        )
        for m in ordered_metrics:
            ordered_subs[m] = sub_sums[m]

        level1_tasks.append(asyncio.ensure_future(
            summarize_stage(stage_name, ordered_subs, score, software_name)
        ))
        level1_keys.append(("trajectory_stage", stage_name))

    try:
        level1_results = await asyncio.gather(*level1_tasks, return_exceptions=True)
    except Exception:
        logger.warning("level1_summarizers_failed")
        level1_results = [None] * len(level1_tasks)

    health_overall_summary = ""
    stage_summaries: dict[str, str] = {}

    for (domain, key), result in zip(level1_keys, level1_results):
        text = result if isinstance(result, str) else ""
        if domain == "health":
            health_overall_summary = text
        else:
            stage_summaries[key] = text

    # Store stage overall summaries alongside sub-metric summaries
    for stage_name, overall_text in stage_summaries.items():
        if stage_name not in traj_sub_summaries:
            traj_sub_summaries[stage_name] = {}
        traj_sub_summaries[stage_name]["overall"] = overall_text

    # ── Level 2: Overall trajectory summarizer ──
    try:
        trajectory_overall_summary = await summarize_trajectory_overall(
            stage_summaries, overall_smoothness, current_stage,
            regression_detected, regression_detail, software_name,
        )
    except Exception:
        logger.warning("trajectory_overall_summarizer_failed")
        trajectory_overall_summary = ""

    # ── Build summary tree ──
    return {
        "health": {
            **health_sub_summaries,
            "overall": health_overall_summary,
        },
        "trajectory": {
            "stages": traj_sub_summaries,
            "overall": trajectory_overall_summary,
        },
    }
