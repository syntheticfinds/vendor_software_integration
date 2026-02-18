import re
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.demo.schemas import (
    ComposeEmailRequest,
    ComposeEmailResponse,
    ComposeSignalRequest,
    ComposeSignalResponse,
    DemoCompany,
)
from app.monitoring.models import MonitoredEmail
from app.signals.models import SignalEvent
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()
router = APIRouter(prefix="/demo", tags=["demo"])

# ---------------------------------------------------------------------------
# Thread deduplication helpers
# ---------------------------------------------------------------------------

_REPLY_PREFIX = re.compile(r"^(Re:\s*|Fwd:\s*|FW:\s*|RE:\s*)+", re.IGNORECASE)
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _normalize_title(title: str | None) -> str:
    """Strip reply/forward prefixes so thread messages match."""
    if not title:
        return ""
    return _REPLY_PREFIX.sub("", title).strip()


def _max_severity(a: str | None, b: str | None) -> str:
    ra = _SEVERITY_RANK.get(a or "medium", 1)
    rb = _SEVERITY_RANK.get(b or "medium", 1)
    return (a or "medium") if ra >= rb else (b or "medium")


async def _find_or_merge_signal(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    source_type: str,
    source_id: str | None,
    event_type: str,
    severity: str,
    title: str | None,
    body: str | None,
    occurred_at: datetime,
    event_metadata: dict,
) -> tuple[SignalEvent, bool]:
    """Find an existing signal with the same thread title and merge, or create new.

    Returns (signal, is_new).
    """
    normalized = _normalize_title(title)

    if normalized:
        result = await db.execute(
            select(SignalEvent).where(
                SignalEvent.company_id == company_id,
                SignalEvent.software_id == software_id,
                SignalEvent.source_type == source_type,
            ).order_by(SignalEvent.occurred_at.desc()).limit(50)
        )
        for sig in result.scalars().all():
            if _normalize_title(sig.title) == normalized:
                # Lifecycle transitions must NOT merge — they need separate
                # signals for trajectory tracking:
                #  - ticket_resolved: pairs with ticket_created for resolution metrics
                #  - ticket_reopened: counts as recurrence + invalidates prior resolution
                # Instead, skip the merge and fall through to create a new signal,
                # inheriting the original stage_topic.
                _LIFECYCLE_SKIP = {
                    ("ticket_resolved", "ticket_created"),
                    ("ticket_resolved", "ticket_reopened"),
                    ("ticket_reopened", "ticket_resolved"),
                    ("ticket_reopened", "ticket_created"),
                }
                if (event_type, sig.event_type) in _LIFECYCLE_SKIP:
                    sig_meta = sig.event_metadata if isinstance(sig.event_metadata, dict) else {}
                    inherited_stage = sig_meta.get("stage_topic")
                    if inherited_stage:
                        event_metadata = {**event_metadata, "_inherit_stage": inherited_stage}
                    logger.info(
                        "lifecycle_transition_skip_merge",
                        event_type=event_type,
                        existing_type=sig.event_type,
                        signal_id=str(sig.id),
                        inherited_stage=inherited_stage,
                    )
                    break

                # Append body as a thread update
                if body:
                    date_label = occurred_at.strftime("%b %d, %Y %H:%M")
                    sig.body = (sig.body or "") + f"\n\n--- Update ({date_label}) ---\n{body}"

                # Escalate severity to the highest seen
                sig.severity = _max_severity(sig.severity, severity)

                # Keep the latest timestamp (strip tz for safe comparison with SQLite-stored naive datetimes)
                occ_naive = occurred_at.replace(tzinfo=None) if occurred_at.tzinfo else occurred_at
                sig_naive = sig.occurred_at.replace(tzinfo=None) if sig.occurred_at.tzinfo else sig.occurred_at
                if occ_naive > sig_naive:
                    sig.occurred_at = occurred_at

                # Clean up the title (strip Re:/Fwd:)
                sig.title = normalized

                # Merge reporters into a list
                meta = sig.event_metadata if isinstance(sig.event_metadata, dict) else {}
                new_reporter = event_metadata.get("reporter")
                if new_reporter:
                    reporters = meta.get("reporters", [])
                    old_single = meta.get("reporter")
                    if old_single and old_single not in reporters:
                        reporters.append(old_single)
                    if new_reporter not in reporters:
                        reporters.append(new_reporter)
                    meta["reporters"] = reporters
                    meta["reporter"] = new_reporter

                # Re-classify merged signal (but preserve original stage_topic —
                # updates to the same work item belong to the same lifecycle stage)
                original_stage = meta.get("stage_topic")
                tags = await _classify_for_software(
                    db, software_id, source_type, event_type,
                    sig.severity, sig.title, sig.body,
                )
                meta.update(tags)
                if original_stage and tags.get("stage_topic") != original_stage:
                    logger.info(
                        "merge_stage_preserved",
                        signal_id=str(sig.id),
                        original_stage=original_stage,
                        classifier_stage=tags.get("stage_topic"),
                    )
                    meta["stage_topic"] = original_stage
                sig.event_metadata = meta

                await db.commit()
                await db.refresh(sig)
                return sig, False

    # Classify new signal
    tags = await _classify_for_software(
        db, software_id, source_type, event_type,
        severity, title, body,
    )
    # If this signal was created because a lifecycle transition skipped the
    # merge (e.g. ticket_resolved for an existing ticket_created), inherit
    # the original signal's stage_topic so the pair stays in the same stage.
    inherited_stage = event_metadata.pop("_inherit_stage", None)
    enriched_metadata = {**event_metadata, **tags}
    if inherited_stage:
        enriched_metadata["stage_topic"] = inherited_stage

    signal = SignalEvent(
        company_id=company_id,
        software_id=software_id,
        source_type=source_type,
        source_id=source_id,
        event_type=event_type,
        severity=severity,
        title=normalized or title,
        body=body,
        occurred_at=occurred_at,
        event_metadata=enriched_metadata,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal, True


# ---------------------------------------------------------------------------
# Classification helper
# ---------------------------------------------------------------------------

async def _classify_for_software(
    db: AsyncSession,
    software_id: uuid.UUID,
    source_type: str,
    event_type: str,
    severity: str | None,
    title: str | None,
    body: str | None,
) -> dict[str, str]:
    """Look up the software registration and classify the signal."""
    from app.signals.classification import classify_signal

    result = await db.execute(
        select(SoftwareRegistration).where(SoftwareRegistration.id == software_id)
    )
    sw = result.scalar_one_or_none()
    if not sw:
        return {}
    return classify_signal(
        source_type, event_type, severity,
        title, body,
        sw.software_name, sw.created_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    """Look up a company by ID, raise 404 if not found."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return company


async def _infer_software(
    db: AsyncSession,
    company_id: uuid.UUID,
    text: str,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
    sender_email: str | None = None,
) -> SoftwareRegistration | None:
    """Match against registered software to infer which product is referenced.

    Scores each registration by combining name matches with integration identifier
    matches. Integration IDs (jira workspace, email domain) act
    as confirmation signals to disambiguate when multiple software names match,
    since the same ID could belong to multiple registrations.
    """
    text_lower = text.lower()
    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.company_id == company_id,
            SoftwareRegistration.status == "active",
        )
    )
    all_sw = result.scalars().all()

    best: SoftwareRegistration | None = None
    best_score = 0

    for sw in all_sw:
        score = 0

        # Name match (base requirement — at least one name must appear)
        name_match = (
            sw.software_name.lower() in text_lower
            or sw.vendor_name.lower() in text_lower
        )
        if not name_match:
            continue
        # Longer software name = more specific match
        score = len(sw.software_name)

        # Integration ID confirmation bonuses
        if source_type == "jira" and source_id and sw.jira_workspace:
            if source_id.upper().startswith(sw.jira_workspace.upper()):
                score += 1000
        if sender_email and sw.support_email:
            try:
                sender_domain = sender_email.split("@")[1].lower()
                support_domain = sw.support_email.split("@")[1].lower()
                if sender_domain == support_domain:
                    score += 1000
            except (IndexError, AttributeError):
                pass

        if score > best_score:
            best = sw
            best_score = score

    return best


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _run_single_detection_background(
    company_id: uuid.UUID, email_id: uuid.UUID
):
    """Background task to run detection on a single composed email."""
    from app.agents.integration_detector.crew import load_registered_software, run_single_email_detection
    from app.database import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(
            select(MonitoredEmail).where(MonitoredEmail.id == email_id)
        )
        email = result.scalar_one_or_none()
        if not email or email.processed:
            return

        registered_data = await load_registered_software(db, company_id)
        detection = await run_single_email_detection(db, company_id, email, registered_data)

        logger.info(
            "demo_detection_complete",
            company_id=str(company_id),
            email_id=str(email_id),
            detected=detection is not None,
        )


async def _run_signal_analysis_background(
    company_id: uuid.UUID, software_id: uuid.UUID
):
    """Background task to run signal analysis after a new signal is ingested."""
    from app.database import async_session_factory
    from app.signals.service import run_analysis

    async with async_session_factory() as db:
        result = await run_analysis(db, company_id, software_id)
        logger.info(
            "demo_signal_analysis_complete",
            company_id=str(company_id),
            software_id=str(software_id),
            result_status=result.get("status"),
        )


# ---------------------------------------------------------------------------
# List endpoints (no auth)
# ---------------------------------------------------------------------------

@router.get("/companies", response_model=list[DemoCompany])
async def list_companies(db: AsyncSession = Depends(get_db)):
    """List all companies for the demo panel company selector."""
    result = await db.execute(
        select(Company).order_by(Company.company_name)
    )
    return [
        DemoCompany(
            id=str(c.id),
            company_name=c.company_name,
            industry=c.industry,
            company_size=c.company_size,
        )
        for c in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Compose endpoints (no auth — company_id in request body)
# ---------------------------------------------------------------------------

@router.post("/compose-email", response_model=ComposeEmailResponse)
async def compose_email(
    data: ComposeEmailRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create a single email from user input and route by category.

    - integration: run Software Integration Detector (detect new software)
    - feature_request / issue_debug: create a SignalEvent for the specified
      registered software and run signal analysis (health scoring pipeline)
    """
    company = await _get_company(db, data.company_id)

    formatted_sender = (
        f"{data.sender_name} <{data.sender}>" if data.sender_name else data.sender
    )

    email = MonitoredEmail(
        company_id=company.id,
        source="demo",
        message_id=f"demo-{uuid.uuid4()}",
        sender=formatted_sender,
        subject=data.subject,
        body_snippet=data.body,
        received_at=data.occurred_at or datetime.now(timezone.utc),
        processed=False,
        category=data.category,
        direction=data.direction,
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    detection_queued = False
    signal_created = False
    analysis_queued = False

    if data.category == "integration":
        # Route to Software Integration Detector
        if data.auto_detect:
            background_tasks.add_task(
                _run_single_detection_background, company.id, email.id
            )
            detection_queued = True
        # Mark as processed since detector will handle it
    else:
        # feature_request / issue_debug → create SignalEvent for existing software
        email.processed = True
        await db.commit()

        # Resolve software: explicit ID or infer from message content
        software = None
        if data.software_id:
            result = await db.execute(
                select(SoftwareRegistration).where(
                    SoftwareRegistration.id == data.software_id,
                    SoftwareRegistration.company_id == company.id,
                )
            )
            software = result.scalar_one_or_none()
        else:
            # For inbound emails, the sender is the vendor; for outbound, the recipient is
            vendor_email = data.sender if data.direction == "inbound" else data.recipient
            software = await _infer_software(
                db, company.id, f"{data.subject} {data.body}",
                source_type="email", sender_email=vendor_email,
            )

        if software:
            _signal, is_new = await _find_or_merge_signal(
                db,
                company_id=company.id,
                software_id=software.id,
                source_type="email",
                source_id=str(email.id),
                event_type=data.category,
                severity=data.severity or "medium",
                title=data.subject,
                body=data.body,
                occurred_at=data.occurred_at or datetime.now(timezone.utc),
                event_metadata={
                    "direction": data.direction,
                    "sender": formatted_sender,
                    **({"reporter": data.sender_name} if data.sender_name else {}),
                },
            )
            signal_created = is_new

            background_tasks.add_task(
                _run_signal_analysis_background, company.id, software.id
            )
            analysis_queued = True

    logger.info(
        "demo_email_composed",
        company_id=str(company.id),
        email_id=str(email.id),
        category=data.category,
        direction=data.direction,
        signal_created=signal_created,
    )

    return ComposeEmailResponse(
        email_id=str(email.id),
        sender=data.sender,
        subject=data.subject,
        category=data.category,
        direction=data.direction,
        detection_queued=detection_queued,
        signal_created=signal_created,
        analysis_queued=analysis_queued,
    )


@router.post("/compose-signal", response_model=ComposeSignalResponse)
async def compose_signal(
    data: ComposeSignalRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create a signal event for a registered software and run analysis in background."""
    company = await _get_company(db, data.company_id)

    # Resolve software: explicit ID or infer from message content
    software = None
    if data.software_id:
        result = await db.execute(
            select(SoftwareRegistration).where(
                SoftwareRegistration.id == data.software_id,
                SoftwareRegistration.company_id == company.id,
            )
        )
        software = result.scalar_one_or_none()
    else:
        software = await _infer_software(
            db, company.id, f"{data.title} {data.body}",
            source_type=data.source_type, source_id=data.source_id,
        )

    if not software:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not determine software from message content. Mention a registered vendor or software name in the title or body.",
        )

    source_id = data.source_id
    if not source_id:
        source_id = f"JIRA-{uuid.uuid4().hex[:6].upper()}"

    signal, is_new = await _find_or_merge_signal(
        db,
        company_id=company.id,
        software_id=software.id,
        source_type=data.source_type,
        source_id=source_id,
        event_type=data.event_type,
        severity=data.severity,
        title=data.title,
        body=data.body,
        occurred_at=data.occurred_at or datetime.now(timezone.utc),
        event_metadata={"reporter": data.reporter} if data.reporter else {},
    )

    background_tasks.add_task(
        _run_signal_analysis_background, company.id, software.id
    )

    logger.info(
        "demo_signal_composed",
        company_id=str(company.id),
        signal_id=str(signal.id),
        source_type=data.source_type,
        event_type=data.event_type,
        software_id=str(software.id),
        merged=not is_new,
    )

    return ComposeSignalResponse(
        signal_id=str(signal.id),
        software_id=str(software.id),
        source_type=data.source_type,
        event_type=data.event_type,
        severity=data.severity,
        title=data.title,
    )
