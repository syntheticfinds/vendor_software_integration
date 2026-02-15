import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def software_id(client: AsyncClient, auth_headers: dict):
    """Create a software registration and return its ID."""
    response = await client.post(
        "/api/v1/software",
        json={
            "vendor_name": "Acme Corp",
            "software_name": "Acme Platform",
            "intended_use": "project management",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_ingest_signals(client: AsyncClient, auth_headers: dict, software_id: str):
    response = await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ingested_count"] > 0
    assert data["software_id"] == software_id


@pytest.mark.asyncio
async def test_ingest_signals_by_source_type(client: AsyncClient, auth_headers: dict, software_id: str):
    response = await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id, "source_type": "jira"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["ingested_count"] > 0


@pytest.mark.asyncio
async def test_ingest_no_auth(client: AsyncClient, software_id: str):
    response = await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_events_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/signals/events", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_events_after_ingest(client: AsyncClient, auth_headers: dict, software_id: str):
    # Ingest first
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/signals/events", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert len(data["items"]) > 0
    # Check event structure
    event = data["items"][0]
    assert "source_type" in event
    assert "severity" in event
    assert "title" in event


@pytest.mark.asyncio
async def test_list_events_filter_by_severity(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    response = await client.get(
        "/api/v1/signals/events",
        params={"severity": "critical"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["severity"] == "critical"


@pytest.mark.asyncio
async def test_analyze_signals(client: AsyncClient, auth_headers: dict, software_id: str):
    # Ingest signals first
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    # Run analysis (uses deterministic fallback since no API key)
    response = await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id, "window_days": 30},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_analyze_no_events(client: AsyncClient, auth_headers: dict, software_id: str):
    response = await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id, "window_days": 30},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_events"


@pytest.mark.asyncio
async def test_health_scores_after_analysis(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/signals/health-scores", headers=auth_headers)
    assert response.status_code == 200
    scores = response.json()
    assert len(scores) > 0
    assert 0 <= scores[0]["score"] <= 100
    assert "category_breakdown" in scores[0]


@pytest.mark.asyncio
async def test_review_drafts_after_analysis(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/signals/review-drafts", headers=auth_headers)
    assert response.status_code == 200
    drafts = response.json()
    assert len(drafts) > 0
    assert drafts[0]["status"] == "pending"
    assert drafts[0]["draft_body"] != ""


@pytest.mark.asyncio
async def test_update_review_draft_approve(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    drafts = (await client.get("/api/v1/signals/review-drafts", headers=auth_headers)).json()
    draft_id = drafts[0]["id"]

    response = await client.patch(
        f"/api/v1/signals/review-drafts/{draft_id}",
        json={"status": "approved"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["reviewed_at"] is not None


@pytest.mark.asyncio
async def test_update_review_draft_edit(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    drafts = (await client.get("/api/v1/signals/review-drafts", headers=auth_headers)).json()
    draft_id = drafts[0]["id"]

    response = await client.patch(
        f"/api/v1/signals/review-drafts/{draft_id}",
        json={"status": "edited", "edited_body": "Revised content here."},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "edited"
    assert response.json()["edited_body"] == "Revised content here."


@pytest.mark.asyncio
async def test_send_draft_requires_approval(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    drafts = (await client.get("/api/v1/signals/review-drafts", headers=auth_headers)).json()
    draft_id = drafts[0]["id"]

    # Try to send without approving first
    response = await client.post(
        f"/api/v1/signals/review-drafts/{draft_id}/send",
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_send_approved_draft(client: AsyncClient, auth_headers: dict, software_id: str):
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": software_id},
        headers=auth_headers,
    )
    drafts = (await client.get("/api/v1/signals/review-drafts", headers=auth_headers)).json()
    draft_id = drafts[0]["id"]

    # Approve first
    await client.patch(
        f"/api/v1/signals/review-drafts/{draft_id}",
        json={"status": "approved"},
        headers=auth_headers,
    )

    # Send
    response = await client.post(
        f"/api/v1/signals/review-drafts/{draft_id}/send",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_review_draft_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/signals/review-drafts/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404
