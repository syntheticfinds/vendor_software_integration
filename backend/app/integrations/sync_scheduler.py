"""Periodic Gmail sync: fetch new emails, run detection, track correspondence."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.gmail_sync import fetch_new_gmail_messages
from app.integrations.models import EmailIntegration
from app.integrations.service import ensure_valid_token
from app.monitoring.models import MonitoredEmail
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

SYNC_INTERVAL_SECONDS = 60


def _extract_email_address(header_value: str) -> str:
    """Extract bare email from a header like 'Name <email@example.com>'."""
    _, addr = parseaddr(header_value)
    return addr.lower()


def _extract_all_email_addresses(header_value: str) -> list[str]:
    """Extract all email addresses from a To header (comma-separated)."""
    addresses = []
    for part in header_value.split(","):
        addr = _extract_email_address(part.strip())
        if addr:
            addresses.append(addr)
    return addresses


def _match_email_to_software(
    email: MonitoredEmail,
    raw: dict | None,
    support_email_map: dict[str, list["SoftwareRegistration"]],
) -> tuple[list["SoftwareRegistration"], str | None]:
    """Match an email against support emails. Returns (candidates, direction).

    Returns a list of candidate registrations (may be >1 when multiple software
    share the same support email) and the direction (inbound/outbound).
    """
    # Use sender from raw data if available, otherwise from the stored model
    sender_str = raw.get("sender", "") if raw else (email.sender or "")
    sender_addr = _extract_email_address(sender_str)

    # Check inbound: sender is the support email
    if sender_addr in support_email_map:
        return support_email_map[sender_addr], "inbound"

    # Check outbound: any recipient is a support email (only if we have raw data)
    if raw:
        recipient_addrs = _extract_all_email_addresses(raw.get("recipients", ""))
        for recip in recipient_addrs:
            if recip in support_email_map:
                return support_email_map[recip], "outbound"

    return [], None


async def _track_correspondence(
    db: AsyncSession,
    company_id: uuid.UUID,
    new_emails: list[MonitoredEmail],
    raw_messages: list[dict],
) -> set[uuid.UUID]:
    """Match emails against registered software support emails.

    Processes both newly-fetched emails (with full raw data including recipients)
    and previously-synced emails that haven't been categorized yet.
    Creates SignalEvents for correspondence and runs signal analysis.

    Returns the set of MonitoredEmail IDs that were matched (so callers can
    skip further processing like integration detection on those emails).
    """
    from app.demo.router import _find_or_merge_signal
    from app.signals.service import run_analysis

    # Load registered software with support emails
    result = await db.execute(
        select(SoftwareRegistration).where(
            SoftwareRegistration.company_id == company_id,
            SoftwareRegistration.status == "active",
            SoftwareRegistration.support_email.isnot(None),
            SoftwareRegistration.support_email != "",
        )
    )
    registrations = result.scalars().all()
    if not registrations:
        logger.info("track_correspondence_no_registrations", company_id=str(company_id))
        return set()

    # Build a lookup: support_email -> list of SoftwareRegistrations
    support_email_map: dict[str, list[SoftwareRegistration]] = {}
    for sw in registrations:
        if sw.support_email:
            support_email_map.setdefault(sw.support_email.lower(), []).append(sw)

    logger.info(
        "track_correspondence_support_emails",
        company_id=str(company_id),
        support_emails=list(support_email_map.keys()),
    )

    if not support_email_map:
        return set()

    # Build a lookup from message_id to raw message data (for recipients)
    raw_by_id: dict[str, dict] = {m["message_id"]: m for m in raw_messages}

    # Also load previously-synced Gmail emails that haven't been categorised yet
    new_email_ids = {e.id for e in new_emails}
    result = await db.execute(
        select(MonitoredEmail).where(
            MonitoredEmail.company_id == company_id,
            MonitoredEmail.source == "gmail",
            MonitoredEmail.category.is_(None),
        )
    )
    uncategorised = [e for e in result.scalars().all() if e.id not in new_email_ids]

    all_emails = list(new_emails) + uncategorised

    logger.info(
        "track_correspondence_candidates",
        company_id=str(company_id),
        new_count=len(new_emails),
        uncategorised_count=len(uncategorised),
        total=len(all_emails),
    )

    matched_email_ids: set[uuid.UUID] = set()
    software_ids_with_new_signals: set[uuid.UUID] = set()

    for email in all_emails:
        raw = raw_by_id.get(email.message_id)
        candidates, direction = _match_email_to_software(email, raw, support_email_map)

        sender_addr = _extract_email_address(
            (raw.get("sender", "") if raw else (email.sender or ""))
        )
        logger.info(
            "track_correspondence_check",
            email_subject=email.subject,
            sender_addr=sender_addr,
            has_raw=raw is not None,
            candidate_count=len(candidates),
            direction=direction,
        )

        if not candidates or not direction:
            continue

        # Single candidate: route directly. Multiple: run intelligent routing.
        if len(candidates) == 1:
            matched_sw = candidates[0]
        else:
            from app.integrations.email_routing import route_email_to_software
            matched_sw = await route_email_to_software(db, email, raw, candidates)

        if not matched_sw:
            logger.info(
                "email_routing_skipped",
                email_subject=email.subject,
                candidate_count=len(candidates),
            )
            continue

        matched_email_ids.add(email.id)

        # Update the MonitoredEmail with direction and category
        email.direction = direction
        email.category = "vendor_email"
        email.processed = True
        await db.commit()

        # Create or merge signal
        signal, is_new = await _find_or_merge_signal(
            db,
            company_id=company_id,
            software_id=matched_sw.id,
            source_type="email",
            source_id=str(email.id),
            event_type="vendor_email",
            severity="low",
            title=email.subject,
            body=email.body_snippet,
            occurred_at=email.received_at or datetime.now(timezone.utc),
            event_metadata={
                "direction": direction,
                "sender": email.sender or "",
                "gmail_message_id": email.message_id,
            },
        )

        logger.info(
            "gmail_correspondence_tracked",
            company_id=str(company_id),
            software=matched_sw.software_name,
            direction=direction,
            subject=email.subject,
            signal_new=is_new,
        )

        software_ids_with_new_signals.add(matched_sw.id)

    # Run signal analysis for each software that got new signals
    for sw_id in software_ids_with_new_signals:
        try:
            await run_analysis(db, company_id, sw_id)
        except Exception:
            logger.exception(
                "gmail_correspondence_analysis_failed",
                company_id=str(company_id),
                software_id=str(sw_id),
            )

    return matched_email_ids


async def sync_company_gmail(db: AsyncSession, integration: EmailIntegration) -> int:
    """Fetch new Gmail messages for one company and run detection.

    Returns the number of new emails stored.
    """
    access_token = await ensure_valid_token(db, integration)

    # Never fetch emails from before the integration was connected
    raw_messages = await fetch_new_gmail_messages(access_token, since=integration.created_at)

    logger.info(
        "gmail_fetch_result",
        company_id=str(integration.company_id),
        last_sync_at=str(integration.last_sync_at),
        raw_count=len(raw_messages) if raw_messages else 0,
        subjects=[m.get("subject", "")[:60] for m in (raw_messages or [])],
    )

    new_emails: list[MonitoredEmail] = []

    if raw_messages:
        # Dedup: check which message_ids already exist
        incoming_ids = [m["message_id"] for m in raw_messages]
        result = await db.execute(
            select(MonitoredEmail.message_id).where(
                MonitoredEmail.company_id == integration.company_id,
                MonitoredEmail.message_id.in_(incoming_ids),
            )
        )
        existing_ids = set(result.scalars().all())

        logger.info(
            "gmail_dedup",
            company_id=str(integration.company_id),
            incoming=len(incoming_ids),
            already_stored=len(existing_ids),
        )

        # Store new emails
        for msg in raw_messages:
            if msg["message_id"] in existing_ids:
                continue

            email = MonitoredEmail(
                company_id=integration.company_id,
                source="gmail",
                message_id=msg["message_id"],
                sender=msg["sender"],
                subject=msg["subject"],
                body_snippet=msg["body_snippet"],
                received_at=msg["received_at"],
                processed=False,
            )
            db.add(email)
            new_emails.append(email)

        if new_emails:
            await db.commit()
            for email in new_emails:
                await db.refresh(email)

    # Track correspondence with registered software support emails FIRST
    # (always runs — also picks up previously-synced uncategorised emails)
    matched_email_ids: set[uuid.UUID] = set()
    try:
        matched_email_ids = await _track_correspondence(
            db, integration.company_id, new_emails, raw_messages or [],
        )
    except Exception:
        logger.exception(
            "gmail_correspondence_tracking_failed",
            company_id=str(integration.company_id),
        )

    # Run detection only on new emails NOT already matched to registered software
    if new_emails:
        unmatched = [e for e in new_emails if e.id not in matched_email_ids]
        if unmatched:
            from app.agents.integration_detector.crew import (
                load_registered_software,
                run_single_email_detection,
            )

            registered_data = await load_registered_software(db, integration.company_id)
            for email in unmatched:
                try:
                    detection = await run_single_email_detection(
                        db, integration.company_id, email, registered_data,
                    )
                    logger.info(
                        "gmail_email_processed",
                        company_id=str(integration.company_id),
                        email_id=str(email.id),
                        detected=detection is not None,
                    )
                except Exception:
                    logger.exception(
                        "gmail_detection_failed",
                        company_id=str(integration.company_id),
                        email_id=str(email.id),
                    )

    # Only advance last_sync_at when we actually stored new emails,
    # so delayed emails aren't permanently skipped.
    if new_emails:
        integration.last_sync_at = datetime.now(timezone.utc)
        await db.commit()

    return len(new_emails)


async def run_gmail_sync_cycle() -> None:
    """Run one sync cycle across all active Gmail integrations."""
    from app.database import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(
            select(EmailIntegration).where(EmailIntegration.is_active == True)  # noqa: E712
        )
        integrations = result.scalars().all()

        if not integrations:
            return

        total_new = 0
        for integration in integrations:
            try:
                count = await sync_company_gmail(db, integration)
                total_new += count
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.warning(
                        "gmail_token_revoked",
                        company_id=str(integration.company_id),
                    )
                    integration.is_active = False
                    await db.commit()
                else:
                    logger.warning(
                        "gmail_sync_http_error",
                        company_id=str(integration.company_id),
                        status_code=exc.response.status_code,
                        detail=exc.response.text[:200],
                    )
            except Exception:
                logger.exception(
                    "gmail_sync_company_error",
                    company_id=str(integration.company_id),
                )

        logger.info(
            "gmail_sync_cycle_complete",
            integrations_checked=len(integrations),
            new_emails=total_new,
        )


async def gmail_sync_loop() -> None:
    """Run Gmail sync every SYNC_INTERVAL_SECONDS indefinitely."""
    logger.info("gmail_sync_loop_started", interval=SYNC_INTERVAL_SECONDS)
    while True:
        try:
            await run_gmail_sync_cycle()
        except Exception:
            logger.exception("gmail_sync_loop_error")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
