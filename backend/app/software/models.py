import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class SoftwareRegistration(TimestampMixin, Base):
    __tablename__ = "software_registrations"
    __table_args__ = (UniqueConstraint("company_id", "vendor_name", "software_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    software_name: Mapped[str] = mapped_column(String(255), nullable=False)
    intended_use: Mapped[str | None] = mapped_column(Text)
    jira_workspace: Mapped[str | None] = mapped_column(String(255))
    support_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")
    detection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("detected_software.id"))
