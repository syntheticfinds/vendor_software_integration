"""Fetch emails from Gmail REST API using httpx."""

import html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
import structlog

logger = structlog.get_logger()

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_MESSAGES_PER_CYCLE = 100


async def fetch_new_gmail_messages(
    access_token: str,
    since: datetime | None = None,
) -> list[dict]:
    """Fetch messages from Gmail, looking back up to 24 hours.

    If *since* is provided (e.g. the integration's created_at), we never
    fetch messages older than that timestamp.  This prevents pulling in
    historical emails when a new account is first connected.

    Dedup in sync_scheduler still guards against storing duplicates.

    Returns a list of dicts with keys:
        message_id, sender, recipients, subject, body_snippet, received_at
    """
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    if since:
        # Ensure timezone-aware for comparison (SQLite stores naive datetimes)
        since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        earliest = max(since_aware, twenty_four_hours_ago)
    else:
        earliest = twenty_four_hours_ago

    # Gmail `after:` filter uses epoch seconds
    after_epoch = int(earliest.timestamp())

    messages: list[dict] = []
    page_token: str | None = None

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # --- Step 1: List message IDs ---
        message_ids: list[str] = []
        while len(message_ids) < MAX_MESSAGES_PER_CYCLE:
            params: dict = {
                "q": f"after:{after_epoch}",
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            for msg in data.get("messages", []):
                message_ids.append(msg["id"])
                if len(message_ids) >= MAX_MESSAGES_PER_CYCLE:
                    break

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # --- Step 2: Fetch details for each message ---
        for msg_id in message_ids:
            try:
                detail = await _fetch_message_detail(client, headers, msg_id)
                if detail:
                    messages.append(detail)
            except httpx.HTTPStatusError:
                logger.warning("gmail_message_fetch_failed", message_id=msg_id)
                continue

    return messages


async def _fetch_message_detail(
    client: httpx.AsyncClient,
    headers: dict,
    message_id: str,
) -> dict | None:
    """Fetch a single message's metadata + snippet."""
    resp = await client.get(
        f"{GMAIL_API_BASE}/messages/{message_id}",
        headers=headers,
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Subject", "Date"],
        },
    )
    resp.raise_for_status()
    data = resp.json()

    # Parse headers
    header_map: dict[str, str] = {}
    for h in data.get("payload", {}).get("headers", []):
        header_map[h["name"].lower()] = h["value"]

    sender = header_map.get("from", "")
    recipients = header_map.get("to", "")
    subject = header_map.get("subject", "")
    snippet = html.unescape(data.get("snippet", ""))

    # Parse received_at from Date header
    received_at = None
    date_str = header_map.get("date")
    if date_str:
        try:
            received_at = parsedate_to_datetime(date_str)
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except Exception:
            received_at = None

    if received_at is None:
        # Fallback: Gmail internalDate (millisecond epoch)
        internal_date = data.get("internalDate")
        if internal_date:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)

    return {
        "message_id": message_id,
        "sender": sender,
        "recipients": recipients,
        "subject": subject,
        "body_snippet": snippet,
        "received_at": received_at or datetime.now(timezone.utc),
    }
