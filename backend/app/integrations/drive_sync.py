"""Fetch files from Google Drive REST API using httpx."""

from datetime import datetime, timezone

import httpx
import structlog

logger = structlog.get_logger()

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
MAX_FILES_PER_CYCLE = 50
CONTENT_SNIPPET_MAX_CHARS = 500

# Google Workspace MIME types that can be exported as text
_EXPORTABLE_MIME_TYPES: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


async def get_start_page_token(access_token: str) -> str:
    """Get the initial page token for the Drive changes API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API_BASE}/changes/startPageToken",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()["startPageToken"]


async def fetch_changed_files(
    access_token: str,
    page_token: str | None = None,
    since: datetime | None = None,
) -> tuple[list[dict], str | None]:
    """Fetch files changed since last sync.

    If *page_token* is provided, uses changes.list for incremental sync.
    Otherwise (first sync), uses files.list with a modifiedTime filter.

    Returns (list_of_file_dicts, new_page_token).
    Each file dict has keys: file_id, name, mime_type, modified_time, web_view_link.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    files: list[dict] = []

    async with httpx.AsyncClient() as client:
        if page_token:
            # Incremental sync via changes API
            new_page_token = page_token
            while len(files) < MAX_FILES_PER_CYCLE:
                resp = await client.get(
                    f"{DRIVE_API_BASE}/changes",
                    headers=headers,
                    params={
                        "pageToken": new_page_token,
                        "pageSize": 50,
                        "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,webViewLink,trashed))",
                        "includeRemoved": "false",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                for change in data.get("changes", []):
                    if change.get("removed"):
                        continue
                    f = change.get("file")
                    if not f or f.get("trashed"):
                        continue
                    files.append(_normalize_file(f))
                    if len(files) >= MAX_FILES_PER_CYCLE:
                        break

                new_page_token = data.get("newStartPageToken") or data.get("nextPageToken")
                if not data.get("nextPageToken"):
                    break

            return files, new_page_token
        else:
            # First sync: list files modified since the given timestamp
            query_parts = ["trashed = false"]
            if since:
                since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
                query_parts.append(f"modifiedTime > '{since_str}'")

            next_page_token: str | None = None
            while len(files) < MAX_FILES_PER_CYCLE:
                params: dict = {
                    "q": " and ".join(query_parts),
                    "pageSize": 50,
                    "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)",
                    "orderBy": "modifiedTime desc",
                }
                if next_page_token:
                    params["pageToken"] = next_page_token

                resp = await client.get(
                    f"{DRIVE_API_BASE}/files",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for f in data.get("files", []):
                    files.append(_normalize_file(f))
                    if len(files) >= MAX_FILES_PER_CYCLE:
                        break

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break

            # Get a start page token for future incremental syncs
            new_start_token = await get_start_page_token(access_token)
            return files, new_start_token


def _normalize_file(f: dict) -> dict:
    """Normalize a Drive API file resource to a standard dict."""
    modified_time = None
    mt_str = f.get("modifiedTime")
    if mt_str:
        try:
            modified_time = datetime.fromisoformat(mt_str.replace("Z", "+00:00"))
        except ValueError:
            modified_time = datetime.now(timezone.utc)

    return {
        "file_id": f.get("id", ""),
        "name": f.get("name", ""),
        "mime_type": f.get("mimeType", ""),
        "modified_time": modified_time or datetime.now(timezone.utc),
        "web_view_link": f.get("webViewLink"),
    }


async def export_file_content(
    access_token: str,
    file_id: str,
    mime_type: str,
) -> str | None:
    """Extract text content from a Drive file.

    Handles Google Workspace formats (Docs, Sheets, Slides) and plain text.
    Returns the first ~500 chars as a snippet, or None if unsupported.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        if mime_type in _EXPORTABLE_MIME_TYPES:
            export_mime = _EXPORTABLE_MIME_TYPES[mime_type]
            resp = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}/export",
                headers=headers,
                params={"mimeType": export_mime},
            )
            resp.raise_for_status()
            text = resp.text
        elif mime_type.startswith("text/"):
            resp = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                headers=headers,
                params={"alt": "media"},
            )
            resp.raise_for_status()
            text = resp.text
        else:
            return None

    return text[:CONTENT_SNIPPET_MAX_CHARS] if text else None
