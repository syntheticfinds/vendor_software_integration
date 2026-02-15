from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    source: str = Field(default="mock", pattern="^(mock|gmail)$")


class ScanResponse(BaseModel):
    scan_id: str
    status: str
    queued_emails: int


class DetectionResponse(BaseModel):
    id: UUID
    company_id: UUID
    source_email_id: UUID | None
    detected_vendor_name: str
    detected_software: str
    confidence_score: float
    status: str
    agent_reasoning: str | None
    detected_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class DetectionUpdate(BaseModel):
    status: str = Field(pattern="^(confirmed|dismissed)$")


class DetectionListResponse(BaseModel):
    items: list[DetectionResponse]
    total: int


class EmailResponse(BaseModel):
    id: UUID
    sender: str | None
    subject: str | None
    body_snippet: str | None
    received_at: datetime | None
    source: str
    category: str | None = None
    direction: str | None = None

    model_config = {"from_attributes": True}
