from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CompanyBase(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    industry: str | None = Field(None, max_length=100)
    company_size: str | None = Field(None, pattern="^(startup|smb|enterprise)$")
    primary_email: EmailStr


class CompanyCreate(CompanyBase):
    password: str = Field(min_length=8, max_length=128)


class CompanyUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    industry: str | None = Field(None, max_length=100)
    company_size: str | None = Field(None, pattern="^(startup|smb|enterprise)$")


class CompanyResponse(BaseModel):
    id: UUID
    company_name: str
    industry: str | None
    company_size: str | None
    primary_email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
