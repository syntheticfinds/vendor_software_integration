import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class SignalEvent(TimestampMixin, Base):
    __tablename__ = "signal_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    software_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("software_registrations.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # jira, email
    source_id: Mapped[str | None] = mapped_column(String(500))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))  # low, medium, high, critical
    title: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class HealthScore(TimestampMixin, Base):
    __tablename__ = "health_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    software_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("software_registrations.id"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    category_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)
    signal_summary: Mapped[str | None] = mapped_column(Text)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="preliminary")  # preliminary, developing, solid
    scoring_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scoring_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summaries: Mapped[dict | None] = mapped_column(JSON, default=None)
    trajectory_data: Mapped[dict | None] = mapped_column(JSON, default=None)


class ReviewDraft(TimestampMixin, Base):
    __tablename__ = "review_drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    software_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("software_registrations.id"), nullable=False)
    health_score_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("health_scores.id"))
    draft_subject: Mapped[str | None] = mapped_column(String(500))
    draft_body: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="preliminary")  # preliminary, developing, solid
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, edited, approved, declined
    edited_body: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
