import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class IntelligenceCache(TimestampMixin, Base):
    __tablename__ = "intelligence_cache"
    __table_args__ = (UniqueConstraint("vendor_name", "software_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    software_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    auto_category: Mapped[str | None] = mapped_column(String(100))
    avg_health_score: Mapped[int | None] = mapped_column(Integer)
    company_count: Mapped[int] = mapped_column(Integer, default=0)
    industry_distribution: Mapped[dict | None] = mapped_column(JSON)
    size_distribution: Mapped[dict | None] = mapped_column(JSON)
    cuj_data: Mapped[dict | None] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
