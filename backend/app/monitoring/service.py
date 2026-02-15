import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.email_watcher import MockEmailSource, get_unprocessed_emails_query
from app.monitoring.models import DetectedSoftware, MonitoredEmail

logger = structlog.get_logger()


async def trigger_scan(db: AsyncSession, company_id: uuid.UUID, source: str = "mock") -> dict:
    """Load mock emails and return scan info. Detection runs separately."""
    if source == "mock":
        email_source = MockEmailSource()
        emails = await email_source.fetch_emails(db, company_id)
    else:
        # Gmail source will be implemented later
        emails = []

    logger.info("scan_triggered", company_id=str(company_id), source=source, email_count=len(emails))

    return {
        "scan_id": str(uuid.uuid4()),
        "status": "emails_loaded",
        "queued_emails": len(emails),
    }


async def get_unprocessed_emails(db: AsyncSession, company_id: uuid.UUID) -> list[MonitoredEmail]:
    result = await db.execute(get_unprocessed_emails_query(company_id))
    return list(result.scalars().all())


async def get_detections(
    db: AsyncSession,
    company_id: uuid.UUID,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[DetectedSoftware], int]:
    query = select(DetectedSoftware).where(DetectedSoftware.company_id == company_id)
    count_query = select(func.count()).select_from(DetectedSoftware).where(DetectedSoftware.company_id == company_id)

    if status:
        query = query.where(DetectedSoftware.status == status)
        count_query = count_query.where(DetectedSoftware.status == status)

    query = query.order_by(DetectedSoftware.detected_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    count_result = await db.execute(count_query)

    return list(result.scalars().all()), count_result.scalar_one()


async def get_detection_by_id(db: AsyncSession, detection_id: uuid.UUID) -> DetectedSoftware | None:
    result = await db.execute(
        select(DetectedSoftware).where(DetectedSoftware.id == detection_id)
    )
    return result.scalar_one_or_none()


async def update_detection_status(db: AsyncSession, detection: DetectedSoftware, status: str) -> DetectedSoftware:
    detection.status = status
    await db.commit()
    await db.refresh(detection)
    return detection
