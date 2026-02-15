import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, case, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.signals.models import HealthScore, ReviewDraft, SignalEvent
from app.software.models import SoftwareRegistration


async def get_overview(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Get high-level dashboard statistics."""
    # Total and active software
    sw_total_stmt = (
        select(func.count()).select_from(SoftwareRegistration)
        .where(SoftwareRegistration.company_id == company_id)
    )
    sw_active_stmt = (
        select(func.count()).select_from(SoftwareRegistration)
        .where(SoftwareRegistration.company_id == company_id, SoftwareRegistration.status == "active")
    )
    if software_ids:
        sw_total_stmt = sw_total_stmt.where(SoftwareRegistration.id.in_(software_ids))
        sw_active_stmt = sw_active_stmt.where(SoftwareRegistration.id.in_(software_ids))
    sw_total = await db.execute(sw_total_stmt)
    sw_active = await db.execute(sw_active_stmt)

    # Total signals
    sig_total_stmt = (
        select(func.count()).select_from(SignalEvent)
        .where(SignalEvent.company_id == company_id)
    )
    if software_ids:
        sig_total_stmt = sig_total_stmt.where(SignalEvent.software_id.in_(software_ids))
    sig_total = await db.execute(sig_total_stmt)

    # Critical signals
    sig_critical_stmt = (
        select(func.count()).select_from(SignalEvent)
        .where(SignalEvent.company_id == company_id, SignalEvent.severity == "critical")
    )
    if software_ids:
        sig_critical_stmt = sig_critical_stmt.where(SignalEvent.software_id.in_(software_ids))
    sig_critical = await db.execute(sig_critical_stmt)

    # Average health score (latest per software)
    hs_where = HealthScore.company_id == company_id
    latest_scores_stmt = (
        select(
            HealthScore.software_id,
            func.max(HealthScore.created_at).label("latest"),
        )
        .where(hs_where)
        .group_by(HealthScore.software_id)
    )
    if software_ids:
        latest_scores_stmt = latest_scores_stmt.where(HealthScore.software_id.in_(software_ids))
    latest_scores_subq = latest_scores_stmt.subquery()

    avg_score_result = await db.execute(
        select(func.avg(HealthScore.score))
        .join(
            latest_scores_subq,
            (HealthScore.software_id == latest_scores_subq.c.software_id)
            & (HealthScore.created_at == latest_scores_subq.c.latest),
        )
    )
    avg_score = avg_score_result.scalar_one_or_none()

    # Pending reviews
    pending_stmt = (
        select(func.count()).select_from(ReviewDraft)
        .where(ReviewDraft.company_id == company_id, ReviewDraft.status == "pending")
    )
    if software_ids:
        pending_stmt = pending_stmt.where(ReviewDraft.software_id.in_(software_ids))
    pending_reviews = await db.execute(pending_stmt)

    return {
        "total_software": sw_total.scalar_one(),
        "active_software": sw_active.scalar_one(),
        "total_signals": sig_total.scalar_one(),
        "avg_health_score": round(avg_score, 1) if avg_score is not None else None,
        "pending_reviews": pending_reviews.scalar_one(),
        "critical_signals": sig_critical.scalar_one(),
    }


async def get_software_health_summary(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Get per-software health summary for dashboard table."""
    software_result = await db.execute(
        select(SoftwareRegistration)
        .where(SoftwareRegistration.company_id == company_id)
        .order_by(SoftwareRegistration.software_name)
    )
    software_list = list(software_result.scalars().all())

    summaries = []
    for sw in software_list:
        # Latest health score
        score_result = await db.execute(
            select(HealthScore.score)
            .where(HealthScore.software_id == sw.id)
            .order_by(HealthScore.created_at.desc())
            .limit(1)
        )
        latest_score = score_result.scalar_one_or_none()

        # Signal counts
        sig_count = await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.software_id == sw.id)
        )
        crit_count = await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.software_id == sw.id, SignalEvent.severity == "critical")
        )

        summaries.append({
            "software_id": str(sw.id),
            "software_name": sw.software_name,
            "vendor_name": sw.vendor_name,
            "latest_score": latest_score,
            "signal_count": sig_count.scalar_one(),
            "critical_count": crit_count.scalar_one(),
            "status": sw.status,
        })

    return summaries


async def get_health_trends(
    db: AsyncSession,
    company_id: uuid.UUID,
    days: int = 30,
) -> list[dict]:
    """Get health score trend data for charting."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(HealthScore)
        .join(SoftwareRegistration, HealthScore.software_id == SoftwareRegistration.id)
        .where(HealthScore.company_id == company_id, HealthScore.created_at >= since)
        .order_by(HealthScore.created_at.asc())
    )
    scores = list(result.scalars().all())

    # Get software names
    sw_names: dict[str, str] = {}
    if scores:
        sw_ids = list({str(s.software_id) for s in scores})
        sw_result = await db.execute(
            select(SoftwareRegistration).where(SoftwareRegistration.company_id == company_id)
        )
        for sw in sw_result.scalars().all():
            sw_names[str(sw.id)] = sw.software_name

    return [
        {
            "date": s.created_at.strftime("%Y-%m-%d"),
            "score": s.score,
            "software_id": str(s.software_id),
            "software_name": sw_names.get(str(s.software_id), "Unknown"),
        }
        for s in scores
    ]


async def get_issue_categories(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """Get signal severity distribution."""
    stmt = (
        select(SignalEvent.severity, func.count().label("count"))
        .where(SignalEvent.company_id == company_id)
        .group_by(SignalEvent.severity)
    )
    if software_ids:
        stmt = stmt.where(SignalEvent.software_id.in_(software_ids))
    result = await db.execute(stmt)
    rows = result.all()
    total = sum(r.count for r in rows) or 1

    return [
        {
            "category": r.severity or "unknown",
            "count": r.count,
            "percentage": round((r.count / total) * 100, 1),
        }
        for r in rows
    ]


async def get_support_burden(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Get per-software support burden metrics."""
    software_result = await db.execute(
        select(SoftwareRegistration)
        .where(SoftwareRegistration.company_id == company_id, SoftwareRegistration.status == "active")
    )
    software_list = list(software_result.scalars().all())

    burdens = []
    for sw in software_list:
        total = await db.execute(
            select(func.count()).select_from(SignalEvent).where(SignalEvent.software_id == sw.id)
        )
        critical = await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.software_id == sw.id, SignalEvent.severity == "critical")
        )
        high = await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.software_id == sw.id, SignalEvent.severity == "high")
        )

        total_val = total.scalar_one()
        crit_val = critical.scalar_one()
        high_val = high.scalar_one()

        # Burden score: weighted sum of signals
        burden = (crit_val * 4) + (high_val * 2) + (total_val - crit_val - high_val)

        burdens.append({
            "software_id": str(sw.id),
            "software_name": sw.software_name,
            "vendor_name": sw.vendor_name,
            "total_signals": total_val,
            "critical_signals": crit_val,
            "high_signals": high_val,
            "open_tickets": crit_val + high_val,
            "burden_score": round(burden, 1),
        })

    return sorted(burdens, key=lambda x: x["burden_score"], reverse=True)


async def get_event_type_distribution(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Get distribution of signal event types."""
    result = await db.execute(
        select(SignalEvent.event_type, func.count().label("count"))
        .where(SignalEvent.company_id == company_id)
        .group_by(SignalEvent.event_type)
        .order_by(func.count().desc())
    )
    return [{"event_type": r.event_type, "count": r.count} for r in result.all()]


async def get_source_distribution(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """Get distribution of signal sources."""
    stmt = (
        select(SignalEvent.source_type, func.count().label("count"))
        .where(SignalEvent.company_id == company_id)
        .group_by(SignalEvent.source_type)
    )
    if software_ids:
        stmt = stmt.where(SignalEvent.software_id.in_(software_ids))
    result = await db.execute(stmt)
    return [{"source_type": r.source_type, "count": r.count} for r in result.all()]
