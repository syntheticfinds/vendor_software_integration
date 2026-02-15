from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SoftwareCreate(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=255)
    software_name: str = Field(min_length=1, max_length=255)
    intended_use: str | None = None
    jira_workspace: str | None = Field(None, max_length=255)
    support_email: EmailStr | None = None
    detection_id: UUID | None = None


class SoftwareUpdate(BaseModel):
    vendor_name: str | None = Field(None, min_length=1, max_length=255)
    software_name: str | None = Field(None, min_length=1, max_length=255)
    intended_use: str | None = None
    jira_workspace: str | None = Field(None, max_length=255)
    support_email: EmailStr | None = None


class SoftwareResponse(BaseModel):
    id: UUID
    company_id: UUID
    vendor_name: str
    software_name: str
    intended_use: str | None
    jira_workspace: str | None
    support_email: str | None
    status: str
    detection_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SoftwareListResponse(BaseModel):
    items: list[SoftwareResponse]
    total: int
