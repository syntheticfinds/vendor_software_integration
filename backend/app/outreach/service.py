import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.outreach.models import OutreachCampaign, OutreachMessage
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()


async def create_campaign(
    db: AsyncSession,
    vendor_name: str,
    software_name: str,
    message_template: str,
    target_criteria: dict | None = None,
) -> OutreachCampaign:
    campaign = OutreachCampaign(
        vendor_name=vendor_name,
        software_name=software_name,
        message_template=message_template,
        target_criteria=target_criteria,
        status="draft",
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def get_campaigns(db: AsyncSession) -> list[OutreachCampaign]:
    result = await db.execute(
        select(OutreachCampaign).order_by(OutreachCampaign.created_at.desc())
    )
    return list(result.scalars().all())


async def get_campaign_by_id(db: AsyncSession, campaign_id: uuid.UUID) -> OutreachCampaign | None:
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
    )
    return result.scalar_one_or_none()


async def send_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> dict:
    """Find target companies and send outreach messages."""
    campaign = await get_campaign_by_id(db, campaign_id)
    if not campaign:
        return {"status": "not_found", "messages_sent": 0}

    # Find companies using this software
    result = await db.execute(
        select(SoftwareRegistration)
        .where(
            SoftwareRegistration.vendor_name == campaign.vendor_name,
            SoftwareRegistration.software_name == campaign.software_name,
            SoftwareRegistration.status == "active",
        )
    )
    registrations = list(result.scalars().all())

    sent = 0
    for reg in registrations:
        # Personalize message
        body = campaign.message_template.replace("{vendor}", campaign.vendor_name)
        body = body.replace("{software}", campaign.software_name)

        msg = OutreachMessage(
            campaign_id=campaign.id,
            target_company_id=reg.company_id,
            message_body=body,
            status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        db.add(msg)
        sent += 1

    campaign.status = "active"
    await db.commit()

    logger.info("outreach_campaign_sent", campaign_id=str(campaign_id), messages=sent)
    return {
        "campaign_id": str(campaign_id),
        "messages_sent": sent,
        "status": "sent",
    }


async def get_campaign_messages(
    db: AsyncSession, campaign_id: uuid.UUID
) -> list[OutreachMessage]:
    result = await db.execute(
        select(OutreachMessage)
        .where(OutreachMessage.campaign_id == campaign_id)
        .order_by(OutreachMessage.created_at.desc())
    )
    return list(result.scalars().all())
