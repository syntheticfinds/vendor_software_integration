from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GmailAuthUrl(BaseModel):
    authorization_url: str


class GmailStatusResponse(BaseModel):
    connected: bool
    email_address: str | None = None
    is_active: bool = False
    scopes: str | None = None
    last_sync_at: datetime | None = None
    connected_at: datetime | None = None


class GmailDisconnectResponse(BaseModel):
    status: str
    message: str


# --- Jira Webhook ---


class JiraWebhookSetupRequest(BaseModel):
    software_id: UUID
    reuse_webhook_secret: str | None = None


class JiraWebhookSetupResponse(BaseModel):
    webhook_url: str
    webhook_secret: str
    software_id: UUID
    is_new_url: bool
    instructions: str


class JiraWebhookInfo(BaseModel):
    software_id: UUID
    software_name: str | None = None
    vendor_name: str | None = None
    webhook_url: str
    webhook_secret: str
    is_active: bool = False
    events_received: int = 0
    last_event_at: datetime | None = None
    connected_at: datetime | None = None


class JiraWebhookListResponse(BaseModel):
    webhooks: list[JiraWebhookInfo]


class JiraWebhookDisconnectResponse(BaseModel):
    status: str
    message: str


# --- Google Drive ---


class DriveStatusResponse(BaseModel):
    available: bool
    enabled: bool
    last_sync_at: datetime | None = None
    needs_reauth: bool = False


# --- Jira Polling ---


class JiraPollingStatusResponse(BaseModel):
    available: bool
    enabled: bool
    last_sync_at: datetime | None = None
    issues_synced: int = 0
    jql_filter: str | None = None


class JiraPollingEnableRequest(BaseModel):
    jql_filter: str | None = None
