from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PublicSoftwareResponse(BaseModel):
    id: UUID
    vendor_name: str
    software_name: str
    avg_health_score: float | None
    company_count: int
    category_scores: dict | None
    common_issues: str | None
    sentiment_summary: str | None

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str
    session_token: str | None = None


class ChatResponse(BaseModel):
    reply: str
    citations: list[dict] | None = None
    session_token: str


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    citations: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
