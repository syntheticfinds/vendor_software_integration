import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.models import MonitoredEmail

# Realistic mock email templates that simulate vendor software adoption signals
MOCK_EMAIL_TEMPLATES = [
    {
        "sender": "noreply@slack.com",
        "subject": "Welcome to Slack! Your workspace is ready",
        "body_snippet": "Hi there! Your Slack workspace has been created successfully. You can now invite your team members and start collaborating. Get started by downloading the Slack app.",
    },
    {
        "sender": "support@atlassian.com",
        "subject": "Your Jira Software Cloud trial has started",
        "body_snippet": "Welcome to Jira Software Cloud! Your 14-day free trial is now active. Start by creating your first project and adding your team members.",
    },
    {
        "sender": "team@datadog.com",
        "subject": "Your Datadog account is ready",
        "body_snippet": "Welcome to Datadog! Your account has been provisioned. Install the Datadog Agent on your infrastructure to start collecting metrics, traces, and logs.",
    },
    {
        "sender": "hello@notion.so",
        "subject": "Welcome to Notion - Your workspace awaits",
        "body_snippet": "Welcome to Notion! We're excited to have you on board. Your workspace is ready for you to start organizing your team's knowledge.",
    },
    {
        "sender": "noreply@github.com",
        "subject": "Your GitHub Enterprise subscription is now active",
        "body_snippet": "Congratulations! Your GitHub Enterprise Cloud subscription is now active. You can start adding organization members and configuring your settings.",
    },
    {
        "sender": "billing@pagerduty.com",
        "subject": "PagerDuty account setup complete",
        "body_snippet": "Your PagerDuty account is set up and ready to go. Configure your first service and escalation policy to start receiving incident alerts.",
    },
    {
        "sender": "newsletter@techcrunch.com",
        "subject": "This week in tech: AI funding surges",
        "body_snippet": "Top stories this week: Major AI companies raise billions in new funding rounds. Plus, the latest product launches and startup news.",
    },
    {
        "sender": "marketing@salesforce.com",
        "subject": "Discover the power of Salesforce CRM",
        "body_snippet": "See how Salesforce can transform your business. Join our upcoming webinar to learn about our latest features and success stories from customers like you.",
    },
    {
        "sender": "noreply@aws.amazon.com",
        "subject": "Your AWS account is ready to use",
        "body_snippet": "Welcome to Amazon Web Services. Your account has been activated. Start building with our free tier offerings including EC2, S3, and Lambda.",
    },
    {
        "sender": "support@linear.app",
        "subject": "Welcome to Linear - Project setup complete",
        "body_snippet": "Your Linear workspace is set up. Import your existing issues or create your first project. Linear helps your team build software faster.",
    },
    {
        "sender": "no-reply@zoom.us",
        "subject": "Your Zoom Business license is activated",
        "body_snippet": "Your Zoom Business license is now active. You can host meetings with up to 300 participants and access advanced admin controls.",
    },
    {
        "sender": "team@sentry.io",
        "subject": "Sentry project created successfully",
        "body_snippet": "Your Sentry project has been created. Install our SDK in your application to start capturing errors and performance data in real-time.",
    },
]


class EmailSource(ABC):
    @abstractmethod
    async def fetch_emails(self, db: AsyncSession, company_id: uuid.UUID) -> list[MonitoredEmail]:
        pass


class MockEmailSource(EmailSource):
    async def fetch_emails(self, db: AsyncSession, company_id: uuid.UUID) -> list[MonitoredEmail]:
        emails = []
        for template in MOCK_EMAIL_TEMPLATES:
            email = MonitoredEmail(
                company_id=company_id,
                source="mock",
                message_id=f"mock-{uuid.uuid4()}",
                sender=template["sender"],
                subject=template["subject"],
                body_snippet=template["body_snippet"],
                received_at=datetime.now(timezone.utc),
                processed=False,
            )
            db.add(email)
            emails.append(email)
        await db.commit()
        for email in emails:
            await db.refresh(email)
        return emails


def get_unprocessed_emails_query(company_id: uuid.UUID):
    return (
        select(MonitoredEmail)
        .where(MonitoredEmail.company_id == company_id, MonitoredEmail.processed == False)  # noqa: E712
        .order_by(MonitoredEmail.received_at.desc())
    )
