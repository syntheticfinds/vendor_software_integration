import random
import uuid
from datetime import datetime, timedelta, timezone

from app.signals.connectors.base import DataConnector
from app.signals.models import SignalEvent

JIRA_EVENTS = [
    {"event_type": "ticket_created", "severity": "medium", "title": "API returns 500 on /users endpoint", "body": "Intermittent 500 errors when calling the vendor API. Started after their latest update."},
    {"event_type": "ticket_created", "severity": "high", "title": "Data sync failing since morning", "body": "Automated data sync has been failing with timeout errors. Manual retry works sometimes."},
    {"event_type": "ticket_created", "severity": "low", "title": "Dashboard loading slowly", "body": "The vendor dashboard takes 10+ seconds to load. May be related to increased data volume."},
    {"event_type": "ticket_resolved", "severity": "medium", "title": "SSO integration fixed", "body": "The SSO login issue has been resolved by the vendor. Users can now login normally."},
    {"event_type": "ticket_created", "severity": "critical", "title": "Complete outage - cannot access platform", "body": "The vendor platform is completely down. All API calls returning 503. Status page shows major incident."},
    {"event_type": "ticket_created", "severity": "low", "title": "Feature request: bulk export", "body": "Would like to have bulk export capability for reporting purposes."},
    {"event_type": "ticket_created", "severity": "medium", "title": "Webhook delivery delays", "body": "Webhooks from the vendor are arriving 15-30 minutes late instead of near real-time."},
]

EMAIL_EVENTS = [
    {"event_type": "support_email_received", "severity": "low", "title": "Re: Feature request follow-up", "body": "Hi, we wanted to follow up on your feature request. This is planned for Q2."},
    {"event_type": "support_email_received", "severity": "medium", "title": "Planned maintenance notification", "body": "We will be performing scheduled maintenance this Saturday from 2-6 AM UTC."},
    {"event_type": "support_email_received", "severity": "high", "title": "Action required: breaking API change", "body": "We're deprecating v1 API endpoints on March 1st. Please migrate to v2."},
]


class MockJiraConnector(DataConnector):
    source_type = "jira"

    async def fetch_events(self, company_id, software_id, since=None):
        events = []
        now = datetime.now(timezone.utc)
        selected = random.sample(JIRA_EVENTS, min(len(JIRA_EVENTS), random.randint(3, 6)))
        for i, template in enumerate(selected):
            events.append(SignalEvent(
                company_id=company_id,
                software_id=software_id,
                source_type=self.source_type,
                source_id=f"JIRA-{random.randint(1000, 9999)}",
                event_type=template["event_type"],
                severity=template["severity"],
                title=template["title"],
                body=template["body"],
                occurred_at=now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23)),
            ))
        return events


class MockEmailConnector(DataConnector):
    source_type = "email"

    async def fetch_events(self, company_id, software_id, since=None):
        events = []
        now = datetime.now(timezone.utc)
        selected = random.sample(EMAIL_EVENTS, min(len(EMAIL_EVENTS), random.randint(1, 3)))
        for template in selected:
            events.append(SignalEvent(
                company_id=company_id,
                software_id=software_id,
                source_type=self.source_type,
                source_id=f"EMAIL-{uuid.uuid4().hex[:8]}",
                event_type=template["event_type"],
                severity=template["severity"],
                title=template["title"],
                body=template["body"],
                occurred_at=now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23)),
            ))
        return events


def get_connectors() -> list[DataConnector]:
    return [MockJiraConnector(), MockEmailConnector()]
