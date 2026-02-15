from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ComposeEmailRequest(BaseModel):
    company_id: UUID
    sender: str = Field(min_length=1, max_length=255)
    sender_name: str | None = Field(None, max_length=255)
    recipient: str | None = Field(None, max_length=255)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    category: str = Field(pattern="^(integration|feature_request|issue_debug)$")
    direction: str = Field(pattern="^(inbound|outbound)$")
    auto_detect: bool = Field(default=True)
    software_id: UUID | None = Field(None)
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    occurred_at: datetime | None = Field(None)


class ComposeEmailResponse(BaseModel):
    email_id: str
    sender: str
    subject: str
    category: str
    direction: str
    detection_queued: bool
    signal_created: bool = False
    analysis_queued: bool = False


class ComposeSignalRequest(BaseModel):
    company_id: UUID
    software_id: UUID | None = Field(None)
    source_type: str = Field(pattern="^(jira)$")
    event_type: str = Field(min_length=1, max_length=100)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    source_id: str | None = Field(None, max_length=500)
    reporter: str | None = Field(None, max_length=255)
    occurred_at: datetime | None = Field(None)


class ComposeSignalResponse(BaseModel):
    signal_id: str
    software_id: str
    source_type: str
    event_type: str
    severity: str
    title: str


class DemoCompany(BaseModel):
    id: str
    company_name: str
    industry: str | None
    company_size: str | None


class DemoSoftware(BaseModel):
    id: str
    vendor_name: str
    software_name: str
    status: str
