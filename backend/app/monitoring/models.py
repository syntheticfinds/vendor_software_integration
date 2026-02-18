import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class MonitoredEmail(TimestampMixin, Base):
    __tablename__ = "monitored_emails"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 'mock' or 'gmail'
    message_id: Mapped[str | None] = mapped_column(String(500))
    sender: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(Text)
    body_snippet: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50))  # integration, feature_request, issue_debug
    direction: Mapped[str | None] = mapped_column(String(20))  # inbound, outbound


class MonitoredDriveFile(TimestampMixin, Base):
    __tablename__ = "monitored_drive_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_snippet: Mapped[str | None] = mapped_column(Text)
    modified_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    web_view_link: Mapped[str | None] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50))


class MonitoredJiraIssue(TimestampMixin, Base):
    __tablename__ = "monitored_jira_issues"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    issue_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    description_snippet: Mapped[str | None] = mapped_column(Text)
    issue_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(50))
    reporter: Mapped[str | None] = mapped_column(String(255))
    issue_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issue_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    web_url: Mapped[str | None] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50))


class DetectedSoftware(TimestampMixin, Base):
    __tablename__ = "detected_software"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=generate_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    source_email_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("monitored_emails.id"))
    source_drive_file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("monitored_drive_files.id"), nullable=True)
    source_jira_issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("monitored_jira_issues.id"), nullable=True)
    detected_vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_software: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, confirmed, dismissed
    agent_reasoning: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
