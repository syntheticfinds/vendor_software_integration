from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    software_id: UUID
    source_type: str | None = None  # if None, ingest from all connectors


class IngestResponse(BaseModel):
    ingested_count: int
    software_id: UUID


class AnalyzeRequest(BaseModel):
    software_id: UUID
    window_days: int = Field(30, ge=1, le=365)


class AnalyzeResponse(BaseModel):
    status: str
    software_id: UUID


class SignalEventResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    source_type: str
    source_id: str | None
    event_type: str
    severity: str | None
    title: str | None
    body: str | None
    event_metadata: dict | None
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalEventListResponse(BaseModel):
    items: list[SignalEventResponse]
    total: int


class HealthScoreResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    score: int
    category_breakdown: dict
    signal_summary: str | None
    signal_count: int
    confidence_tier: str
    scoring_window_start: datetime
    scoring_window_end: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDraftResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    health_score_id: UUID | None
    draft_subject: str | None
    draft_body: str
    confidence_tier: str
    status: str
    edited_body: str | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDraftUpdate(BaseModel):
    status: str = Field(pattern="^(approved|declined|edited)$")
    edited_body: str | None = None
