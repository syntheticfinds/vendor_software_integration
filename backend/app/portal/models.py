import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class PublicSoftwareIndex(TimestampMixin, Base):
    __tablename__ = "public_software_index"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    software_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    avg_health_score: Mapped[float | None] = mapped_column(Integer)
    company_count: Mapped[int] = mapped_column(Integer, default=0)
    category_scores: Mapped[dict | None] = mapped_column(JSON)
    common_issues: Mapped[str | None] = mapped_column(Text)
    sentiment_summary: Mapped[str | None] = mapped_column(Text)


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[dict | None] = mapped_column(JSON)
