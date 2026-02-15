from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CampaignCreate(BaseModel):
    vendor_name: str
    software_name: str
    target_criteria: dict | None = None
    message_template: str


class CampaignResponse(BaseModel):
    id: UUID
    vendor_name: str
    software_name: str
    target_criteria: dict | None
    message_template: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OutreachMessageResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    target_company_id: UUID
    message_body: str
    status: str
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendResult(BaseModel):
    campaign_id: str
    messages_sent: int
    status: str
