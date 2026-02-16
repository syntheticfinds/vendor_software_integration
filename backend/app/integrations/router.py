from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, decode_token
from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.integrations.schemas import (
    DriveStatusResponse,
    GmailAuthUrl,
    GmailDisconnectResponse,
    GmailStatusResponse,
    JiraPollingEnableRequest,
    JiraPollingStatusResponse,
    JiraWebhookDisconnectResponse,
    JiraWebhookInfo,
    JiraWebhookListResponse,
    JiraWebhookSetupRequest,
    JiraWebhookSetupResponse,
)
from app.config import settings
from app.integrations.service import (
    create_jira_webhook,
    delete_integration,
    delete_jira_webhook,
    disable_jira_polling,
    enable_jira_polling,
    exchange_code_for_tokens,
    generate_authorization_url,
    get_google_email,
    get_integration,
    get_jira_polling_config,
    get_jira_webhooks_by_secret,
    get_jira_webhooks_for_company,
    record_jira_event,
    save_integration,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/integrations", tags=["integrations"])

# TODO: move to config for production
FRONTEND_URL = "http://localhost:5173"


@router.get("/gmail/authorize", response_model=GmailAuthUrl)
async def gmail_authorize(
    company: Company = Depends(get_current_company),
):
    """Generate Google OAuth authorization URL.

    Uses the company's JWT access token as the state parameter for CSRF
    protection. The callback will decode it to identify the company.
    """
    state = create_access_token(str(company.id))
    authorization_url = generate_authorization_url(state)
    return GmailAuthUrl(authorization_url=authorization_url)


@router.get("/gmail/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback.

    Called by Google's redirect — the browser has no Authorization header.
    Authentication is verified via the JWT embedded in the state parameter.
    """
    # Verify state (decode the JWT to get company_id)
    payload = decode_token(state)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    company_id = payload.get("sub")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    # Exchange code for tokens
    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        logger.error("gmail_token_exchange_failed", error=str(e))
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?gmail=error")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    scopes = token_data.get("scope", "")

    if not refresh_token:
        logger.error("gmail_no_refresh_token", company_id=company_id)
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?gmail=error&reason=no_refresh_token")

    # Get the Google account email
    try:
        email_address = await get_google_email(access_token)
    except Exception as e:
        logger.error("gmail_userinfo_failed", error=str(e))
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?gmail=error")

    # Save integration
    await save_integration(
        db=db,
        company_id=UUID(company_id),
        email_address=email_address,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scopes=scopes,
    )

    logger.info("gmail_connected", company_id=company_id, email=email_address)
    return RedirectResponse(url=f"{FRONTEND_URL}/settings?gmail=success")


@router.get("/gmail/status", response_model=GmailStatusResponse)
async def gmail_status(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Get Gmail connection status for the current company."""
    integration = await get_integration(db, company.id)

    if not integration:
        return GmailStatusResponse(connected=False)

    return GmailStatusResponse(
        connected=True,
        email_address=integration.email_address,
        is_active=integration.is_active,
        scopes=integration.scopes,
        last_sync_at=integration.last_sync_at,
        connected_at=integration.created_at,
    )


@router.delete("/gmail", response_model=GmailDisconnectResponse)
async def gmail_disconnect(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Gmail integration (revoke token and delete record)."""
    deleted = await delete_integration(db, company.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail integration found",
        )
    return GmailDisconnectResponse(status="disconnected", message="Gmail integration removed successfully")


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------


@router.get("/drive/status", response_model=DriveStatusResponse)
async def drive_status(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Get Google Drive connection status.

    Drive is available when Gmail is connected with the drive.readonly scope.
    """
    integration = await get_integration(db, company.id)
    if not integration:
        return DriveStatusResponse(available=False, enabled=False)

    has_drive_scope = "drive.readonly" in (integration.scopes or "")
    return DriveStatusResponse(
        available=has_drive_scope,
        enabled=integration.drive_sync_enabled,
        last_sync_at=integration.drive_last_sync_at,
        needs_reauth=not has_drive_scope and integration.is_active,
    )


@router.post("/drive/enable")
async def drive_enable(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Enable Drive sync (requires drive.readonly scope)."""
    integration = await get_integration(db, company.id)
    if not integration or "drive.readonly" not in (integration.scopes or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail must be connected with Drive scope first. Re-connect Gmail to grant access.",
        )
    integration.drive_sync_enabled = True
    await db.commit()
    return {"status": "enabled"}


@router.post("/drive/disable")
async def drive_disable(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Disable Drive sync."""
    integration = await get_integration(db, company.id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No integration found",
        )
    integration.drive_sync_enabled = False
    await db.commit()
    return {"status": "disabled"}


# ---------------------------------------------------------------------------
# Jira Webhook
# ---------------------------------------------------------------------------


def _webhook_base_url(request: Request) -> str:
    """Return the base URL for constructing webhook URLs."""
    if settings.WEBHOOK_BASE_URL:
        return settings.WEBHOOK_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.post("/jira/setup", response_model=JiraWebhookSetupResponse)
async def jira_setup(
    body: JiraWebhookSetupRequest,
    request: Request,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Generate or reuse a Jira webhook URL for a specific software.

    If *reuse_webhook_secret* is provided, the software shares the same
    webhook URL as other software already using that secret.
    """
    webhook, is_new_url = await create_jira_webhook(
        db, company.id, body.software_id, reuse_secret=body.reuse_webhook_secret,
    )

    base = _webhook_base_url(request)
    webhook_url = f"{base}/api/v1/integrations/jira/webhook/{webhook.webhook_secret}"

    logger.info(
        "jira_webhook_setup",
        company_id=str(company.id),
        software_id=str(body.software_id),
        reused=not is_new_url,
    )
    return JiraWebhookSetupResponse(
        webhook_url=webhook_url,
        webhook_secret=webhook.webhook_secret,
        software_id=body.software_id,
        is_new_url=is_new_url,
        instructions=(
            "Add this URL as a webhook in your Jira project settings:\n"
            "1. Go to Jira Settings > System > WebHooks\n"
            "2. Click 'Create a WebHook'\n"
            "3. Paste the webhook URL\n"
            "4. Select events: Issue created, updated, deleted; Comment created, updated\n"
            "5. Optionally filter by project (JQL): project = YOUR_PROJECT_KEY"
        ),
    )


@router.get("/jira/webhooks", response_model=JiraWebhookListResponse)
async def jira_list_webhooks(
    request: Request,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """List all Jira webhooks for the current company."""
    rows = await get_jira_webhooks_for_company(db, company.id)
    base = _webhook_base_url(request)

    return JiraWebhookListResponse(
        webhooks=[
            JiraWebhookInfo(
                software_id=wh.software_id,
                software_name=sw_name,
                vendor_name=v_name,
                webhook_url=f"{base}/api/v1/integrations/jira/webhook/{wh.webhook_secret}",
                webhook_secret=wh.webhook_secret,
                is_active=wh.is_active,
                events_received=wh.events_received,
                last_event_at=wh.last_event_at,
                connected_at=wh.created_at,
            )
            for wh, sw_name, v_name in rows
        ]
    )


@router.delete("/jira/{software_id}", response_model=JiraWebhookDisconnectResponse)
async def jira_disconnect(
    software_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Remove Jira webhook for a specific software."""
    deleted = await delete_jira_webhook(db, software_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jira integration found for this software",
        )
    return JiraWebhookDisconnectResponse(
        status="disconnected",
        message="Jira webhook removed. Remember to delete the webhook in Jira settings.",
    )


@router.post("/jira/webhook/{webhook_secret}")
async def jira_webhook_receiver(
    webhook_secret: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Receive Jira Cloud webhook events.

    Unauthenticated — validated by the secret token in the URL.
    Routes events to the appropriate software using 2-tier intelligent routing.
    """
    from app.demo.router import _find_or_merge_signal, _run_signal_analysis_background
    from app.integrations.jira_handler import parse_jira_webhook
    from app.integrations.jira_routing import route_jira_event

    # Validate webhook token — may match multiple software
    webhooks = await get_jira_webhooks_by_secret(db, webhook_secret)
    if not webhooks:
        raise HTTPException(status_code=404, detail="Not found")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Parse Jira event
    parsed = parse_jira_webhook(payload)
    if parsed is None:
        for wh in webhooks:
            await record_jira_event(db, wh)
        return {"status": "ignored", "reason": "untracked event type"}

    # Intelligent routing: determine which software this event belongs to
    routed_webhooks = await route_jira_event(db, webhooks, parsed)

    if not routed_webhooks:
        # No match — drop the event but record telemetry
        for wh in webhooks:
            await record_jira_event(db, wh)
        logger.info(
            "jira_webhook_dropped",
            issue_key=parsed["source_id"],
            event_type=parsed["event_type"],
            total_webhooks=len(webhooks),
        )
        return {
            "status": "dropped",
            "reason": "no matching software",
            "event_type": parsed["event_type"],
            "issue_key": parsed["source_id"],
        }

    # Create or merge signal for each routed software
    results = []
    for webhook in routed_webhooks:
        signal, is_new = await _find_or_merge_signal(
            db,
            company_id=webhook.company_id,
            software_id=webhook.software_id,
            source_type="jira",
            source_id=parsed["source_id"],
            event_type=parsed["event_type"],
            severity=parsed["severity"],
            title=parsed["title"],
            body=parsed["body"],
            occurred_at=parsed["occurred_at"],
            event_metadata=parsed["event_metadata"],
        )

        logger.info(
            "jira_webhook_processed",
            company_id=str(webhook.company_id),
            software_id=str(webhook.software_id),
            event_type=parsed["event_type"],
            issue_key=parsed["source_id"],
            signal_new=is_new,
        )

        await record_jira_event(db, webhook)

        background_tasks.add_task(
            _run_signal_analysis_background, webhook.company_id, webhook.software_id,
        )

        results.append({
            "signal_id": str(signal.id),
            "software_id": str(webhook.software_id),
            "merged": not is_new,
        })

    return {
        "status": "processed",
        "event_type": parsed["event_type"],
        "software_count": len(results),
        "total_webhooks": len(webhooks),
        "routed_webhooks": len(routed_webhooks),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Jira Polling (Pull)
# ---------------------------------------------------------------------------


@router.get("/jira-polling/status", response_model=JiraPollingStatusResponse)
async def jira_polling_status(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Get Jira polling status for the current company."""
    available = bool(settings.JIRA_SITE_URL and settings.JIRA_API_TOKEN)
    config = await get_jira_polling_config(db, company.id)

    if not config:
        return JiraPollingStatusResponse(available=available, enabled=False)

    return JiraPollingStatusResponse(
        available=available,
        enabled=config.is_enabled,
        last_sync_at=config.last_sync_at,
        issues_synced=config.issues_synced or 0,
        jql_filter=config.jql_filter,
    )


@router.post("/jira-polling/enable")
async def jira_polling_enable(
    body: JiraPollingEnableRequest | None = None,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Enable Jira polling for the current company."""
    if not settings.JIRA_SITE_URL or not settings.JIRA_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jira API credentials are not configured. Set JIRA_SITE_URL, JIRA_USER_EMAIL, and JIRA_API_TOKEN in .env.",
        )
    jql = body.jql_filter if body else None
    await enable_jira_polling(db, company.id, jql_filter=jql)
    return {"status": "enabled"}


@router.post("/jira-polling/disable")
async def jira_polling_disable(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Disable Jira polling for the current company."""
    config = await disable_jira_polling(db, company.id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jira polling config found",
        )
    return {"status": "disabled"}
