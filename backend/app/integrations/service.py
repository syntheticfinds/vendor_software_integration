import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.models import EmailIntegration, JiraWebhook

logger = structlog.get_logger()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email"


def generate_authorization_url(state: str) -> str:
    """Build the Google OAuth2 authorization URL."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "state": state,
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_google_email(access_token: str) -> str:
    """Fetch the authenticated user's email address from Google."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()["email"]


async def save_integration(
    db: AsyncSession,
    company_id: uuid.UUID,
    email_address: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    scopes: str,
) -> EmailIntegration:
    """Create or update the Gmail integration for a company."""
    result = await db.execute(
        select(EmailIntegration).where(EmailIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if integration:
        integration.email_address = email_address
        integration.access_token = access_token
        integration.refresh_token = refresh_token
        integration.token_expires_at = expires_at
        integration.scopes = scopes
        integration.is_active = True
    else:
        integration = EmailIntegration(
            company_id=company_id,
            email_address=email_address,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            scopes=scopes,
            is_active=True,
        )
        db.add(integration)

    await db.commit()
    await db.refresh(integration)
    return integration


async def get_integration(db: AsyncSession, company_id: uuid.UUID) -> EmailIntegration | None:
    """Get the Gmail integration for a company."""
    result = await db.execute(
        select(EmailIntegration).where(EmailIntegration.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def delete_integration(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """Revoke Google token and delete the integration record."""
    integration = await get_integration(db, company_id)
    if not integration:
        return False

    # Best-effort revoke with Google
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                GOOGLE_REVOKE_URL,
                params={"token": integration.access_token},
            )
    except httpx.HTTPError:
        logger.warning("google_token_revoke_failed", company_id=str(company_id))

    await db.delete(integration)
    await db.commit()
    return True


async def refresh_access_token(db: AsyncSession, integration: EmailIntegration) -> str:
    """Refresh an expired access token. Returns the new access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": integration.refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            },
        )
        response.raise_for_status()
        token_data = response.json()

    integration.access_token = token_data["access_token"]
    integration.token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_data["expires_in"]
    )
    await db.commit()
    await db.refresh(integration)
    return integration.access_token


async def ensure_valid_token(db: AsyncSession, integration: EmailIntegration) -> str:
    """Return a valid access token, refreshing if necessary."""
    now = datetime.now(timezone.utc)
    expires = integration.token_expires_at
    # Normalize for comparison (SQLite may return naive datetimes)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return await refresh_access_token(db, integration)
    return integration.access_token


# ---------------------------------------------------------------------------
# Jira webhook service functions
# ---------------------------------------------------------------------------


async def create_jira_webhook(
    db: AsyncSession,
    company_id: uuid.UUID,
    software_id: uuid.UUID,
    reuse_secret: str | None = None,
) -> tuple[JiraWebhook, bool]:
    """Create or update the Jira webhook for a specific software.

    If *reuse_secret* is provided, links this software to the same webhook URL
    (shared secret). Otherwise, generates a fresh secret.

    Returns (webhook, is_new_url) — is_new_url is True when a brand-new secret
    was generated (meaning the user needs to add a new webhook in Jira).
    """
    result = await db.execute(
        select(JiraWebhook).where(JiraWebhook.software_id == software_id)
    )
    webhook = result.scalar_one_or_none()

    is_new_url = reuse_secret is None
    secret = reuse_secret if reuse_secret else secrets.token_hex(32)

    if webhook:
        webhook.webhook_secret = secret
        webhook.is_active = True
        webhook.events_received = 0
        webhook.last_event_at = None
    else:
        webhook = JiraWebhook(
            company_id=company_id,
            software_id=software_id,
            webhook_secret=secret,
            is_active=True,
        )
        db.add(webhook)

    await db.commit()
    await db.refresh(webhook)
    return webhook, is_new_url


async def get_jira_webhook_for_software(
    db: AsyncSession, software_id: uuid.UUID,
) -> JiraWebhook | None:
    """Get the Jira webhook for a specific software."""
    result = await db.execute(
        select(JiraWebhook).where(JiraWebhook.software_id == software_id)
    )
    return result.scalar_one_or_none()


async def get_jira_webhooks_for_company(
    db: AsyncSession, company_id: uuid.UUID,
) -> list[tuple[JiraWebhook, str, str]]:
    """Get all Jira webhooks for a company, with software names.

    Returns list of (JiraWebhook, software_name, vendor_name) tuples.
    """
    from app.software.models import SoftwareRegistration

    result = await db.execute(
        select(
            JiraWebhook,
            SoftwareRegistration.software_name,
            SoftwareRegistration.vendor_name,
        )
        .join(SoftwareRegistration, JiraWebhook.software_id == SoftwareRegistration.id)
        .where(JiraWebhook.company_id == company_id)
    )
    return list(result.all())


async def get_jira_webhooks_by_secret(
    db: AsyncSession, secret: str,
) -> list[JiraWebhook]:
    """Look up all active Jira webhooks sharing this secret token.

    Multiple software can share the same webhook URL/secret.
    """
    result = await db.execute(
        select(JiraWebhook).where(
            JiraWebhook.webhook_secret == secret,
            JiraWebhook.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def delete_jira_webhook(
    db: AsyncSession, software_id: uuid.UUID,
) -> bool:
    """Delete the Jira webhook for a specific software."""
    webhook = await get_jira_webhook_for_software(db, software_id)
    if not webhook:
        return False
    await db.delete(webhook)
    await db.commit()
    return True


async def record_jira_event(db: AsyncSession, webhook: JiraWebhook) -> None:
    """Increment event counter and update last_event_at timestamp."""
    webhook.events_received = (webhook.events_received or 0) + 1
    webhook.last_event_at = datetime.now(timezone.utc)
    await db.commit()
