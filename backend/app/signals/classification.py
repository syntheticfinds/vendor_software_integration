"""Signal classification — tags each signal with valence, subject, stage_topic, and health_categories."""

from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

VALID_VALENCES = {"positive", "negative", "neutral"}
VALID_SUBJECTS = {"internal_impl", "vendor_issue", "vendor_request", "vendor_comm"}
VALID_STAGE_TOPICS = {"onboarding", "integration", "stabilization", "productive", "optimization"}
VALID_HEALTH_CATEGORIES = {"reliability", "performance", "fitness_for_purpose"}


def classify_signal(
    source_type: str,
    event_type: str,
    severity: str | None,
    title: str | None,
    body: str | None,
    software_name: str,
    software_registered_at: datetime,
) -> dict[str, str]:
    """Classify a signal with valence, subject, stage_topic, and health_categories.

    Tries LLM classification first, falls back to deterministic keyword matching.
    Returns {"valence": ..., "subject": ..., "stage_topic": ..., "health_categories": [...]}.
    """
    reg_at = software_registered_at
    if reg_at.tzinfo is None:
        reg_at = reg_at.replace(tzinfo=timezone.utc)
    days = max(0, (datetime.now(timezone.utc) - reg_at).days)

    # Try LLM classification
    try:
        from app.agents.signal_classifier.crew import SignalClassifierCrew

        crew = SignalClassifierCrew(
            source_type=source_type,
            event_type=event_type,
            severity=severity or "medium",
            title=title or "",
            body=body or "",
            software_name=software_name,
            days_since_registration=days,
        )
        result = crew.run()
        if result:
            return result
    except Exception as e:
        logger.warning("signal_classification_llm_failed", error=str(e))

    # Deterministic fallback
    return _deterministic_classify(source_type, event_type, severity, title, body, days)


def _deterministic_classify(
    source_type: str,
    event_type: str,
    severity: str | None,
    title: str | None,
    body: str | None,
    days_since_reg: int,
) -> dict[str, str]:
    """Keyword-based fallback classification."""
    text = f"{title or ''} {body or ''}".lower()

    valence = _classify_valence(event_type, severity, text)
    subject = _classify_subject(source_type, event_type, text)
    stage_topic = _classify_stage_topic(text, days_since_reg)
    health_categories = _classify_health_categories(event_type, subject, text)

    return {
        "valence": valence,
        "subject": subject,
        "stage_topic": stage_topic,
        "health_categories": health_categories,
    }


def _classify_valence(event_type: str, severity: str | None, text: str) -> str:
    """Determine if signal is positive, negative, or neutral."""
    if event_type == "ticket_resolved":
        return "positive"
    if event_type == "ticket_created":
        return "negative"

    positive_kw = [
        "resolved", "fixed", "completed", "passed", "success",
        "working", "recovered", "restored", "upgraded",
    ]
    negative_kw = [
        "error", "outage", "fail", "broken", "timeout", "crash",
        "down", "incident", "blocker", "degraded", "502", "503",
        "500", "bug", "regression", "breaking change",
    ]

    if any(kw in text for kw in positive_kw):
        return "positive"
    if any(kw in text for kw in negative_kw):
        return "negative"
    return "neutral"


def _classify_subject(source_type: str, event_type: str, text: str) -> str:
    """Determine the signal subject category."""
    internal_kw = [
        "setup", "configure", "install", "migration", "deploy",
        "implement", "training", "onboard", "provision", "roll out",
    ]
    vendor_issue_kw = [
        "bug", "outage", "error", "defect", "regression", "downtime",
        "broken", "incident", "crash", "503", "502", "500",
    ]
    vendor_request_kw = [
        "request", "feature", "enhancement", "suggestion", "would like",
        "please add", "need support for", "capability",
    ]

    if any(kw in text for kw in internal_kw):
        return "internal_impl"
    if any(kw in text for kw in vendor_issue_kw):
        return "vendor_issue"
    if any(kw in text for kw in vendor_request_kw):
        return "vendor_request"
    if event_type in ("feature_request",):
        return "vendor_request"
    if source_type == "email" and event_type in ("vendor_email", "support_email_received"):
        return "vendor_comm"
    return "vendor_comm"


def _classify_stage_topic(text: str, days_since_reg: int) -> str:
    """Infer lifecycle stage from content keywords + time prior."""
    stage_keywords: dict[str, list[str]] = {
        "onboarding": [
            "onboarding", "account setup", "initial config", "first login",
            "welcome", "getting started", "provision", "invite", "team access",
            "create account", "sign up",
        ],
        "integration": [
            "api connect", "webhook", "data migration", "sync setup",
            "pipeline", "integration test", "sso", "oauth", "endpoint",
            "api key", "sdk", "data sync",
        ],
        "stabilization": [
            "bug fix", "patch", "hotfix", "edge case", "intermittent",
            "flaky", "tuning", "performance issue", "workaround",
            "stability", "reliability", "outage", "incident", "crash",
            "downtime", "degraded", "503", "502", "500", "regression",
            "breaking change", "investigate",
        ],
        "optimization": [
            "scale", "automat", "cost optim", "advanced feature",
            "rate limit", "batch processing", "caching", "throughput",
            "bulk export", "workflow",
        ],
        "productive": [
            "routine", "regular usage", "monthly report", "status update",
            "renewal", "quarterly review", "usage report",
        ],
    }

    scores: dict[str, float] = {stage: 0.0 for stage in stage_keywords}

    for stage, keywords in stage_keywords.items():
        for kw in keywords:
            if kw in text:
                scores[stage] += 1.0

    # Time-based prior (mild boost, does not override keyword matches)
    if days_since_reg < 14:
        scores["onboarding"] += 0.5
    elif days_since_reg < 45:
        scores["integration"] += 0.5
    elif days_since_reg < 90:
        scores["stabilization"] += 0.5
    elif days_since_reg < 180:
        scores["productive"] += 0.5
    else:
        scores["optimization"] += 0.3
        scores["productive"] += 0.3

    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0:
        # No keywords matched; use pure time-based fallback
        if days_since_reg < 14:
            return "onboarding"
        if days_since_reg < 45:
            return "integration"
        if days_since_reg < 90:
            return "stabilization"
        if days_since_reg < 180:
            return "productive"
        return "optimization"

    return best


def _classify_health_categories(event_type: str, subject: str, text: str) -> list[str]:
    """Determine which health score categories a signal is relevant to.

    A signal can belong to multiple categories (multi-label).
    """
    text = text.lower()
    categories: list[str] = []

    reliability_kw = [
        "outage", "incident", "downtime", "uptime", "availability",
        "crash", "failure", "failing", "recovery", "failover", "sla",
        "service disruption", "503", "502", "500", "error rate",
        "service restored", "maintenance window",
        "error", "broken", "bug", "regression", "not responding",
        "connection lost", "dropped", "unreachable", "flaky",
    ]
    performance_kw = [
        "latency", "slow", "timeout", "rate limit", "throttl",
        "throughput", "response time", "performance", "speed",
        "lag", "bottleneck", "load", "capacity",
        "degradation", "delay", "queue", "backlog",
    ]
    fitness_kw = [
        "feature request", "enhancement", "capability", "suggestion",
        "would like", "please add", "need support for", "missing feature",
        "workaround", "roadmap", "planned for",
        "wish list", "not supported", "limitation",
    ]

    if any(kw in text for kw in reliability_kw):
        categories.append("reliability")

    if any(kw in text for kw in performance_kw):
        categories.append("performance")

    if any(kw in text for kw in fitness_kw) or subject == "vendor_request":
        categories.append("fitness_for_purpose")

    # Heuristic fallback when no keywords matched
    if not categories:
        if subject == "vendor_request" or event_type == "feature_request":
            categories.append("fitness_for_purpose")
        elif subject == "vendor_issue":
            # Vendor issues default to reliability
            categories.append("reliability")
        elif event_type in ("ticket_created", "ticket_resolved"):
            categories.append("reliability")

    return categories
