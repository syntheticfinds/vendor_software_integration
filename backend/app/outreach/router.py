import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_company
from app.outreach.schemas import CampaignCreate, CampaignResponse, OutreachMessageResponse, SendResult
from app.outreach.service import create_campaign, get_campaign_by_id, get_campaign_messages, get_campaigns, send_campaign

router = APIRouter(prefix="/outreach", tags=["outreach"])


@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create(
    data: CampaignCreate,
    _=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    campaign = await create_campaign(
        db, data.vendor_name, data.software_name, data.message_template, data.target_criteria
    )
    return CampaignResponse.model_validate(campaign)


@router.get("/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(
    _=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    campaigns = await get_campaigns(db)
    return [CampaignResponse.model_validate(c) for c in campaigns]


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get(
    campaign_id: uuid.UUID,
    _=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_campaign_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign)


@router.post("/campaigns/{campaign_id}/send", response_model=SendResult)
async def send(
    campaign_id: uuid.UUID,
    _=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await send_campaign(db, campaign_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return SendResult(**result)


@router.get("/campaigns/{campaign_id}/messages", response_model=list[OutreachMessageResponse])
async def list_messages(
    campaign_id: uuid.UUID,
    _=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    messages = await get_campaign_messages(db, campaign_id)
    return [OutreachMessageResponse.model_validate(m) for m in messages]
