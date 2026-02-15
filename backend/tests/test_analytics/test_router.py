import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def seeded_data(client: AsyncClient, auth_headers: dict):
    """Create software, ingest signals, and run analysis."""
    # Create software
    sw_res = await client.post(
        "/api/v1/software",
        json={"vendor_name": "Acme", "software_name": "Acme Platform", "intended_use": "testing"},
        headers=auth_headers,
    )
    sw_id = sw_res.json()["id"]

    # Ingest signals
    await client.post(
        "/api/v1/signals/ingest",
        json={"software_id": sw_id},
        headers=auth_headers,
    )

    # Run analysis
    await client.post(
        "/api/v1/signals/analyze",
        json={"software_id": sw_id},
        headers=auth_headers,
    )

    return sw_id


@pytest.mark.asyncio
async def test_overview_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_software"] == 0
    assert data["total_signals"] == 0


@pytest.mark.asyncio
async def test_overview_with_data(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_software"] == 1
    assert data["active_software"] == 1
    assert data["total_signals"] > 0
    assert data["avg_health_score"] is not None
    assert 0 <= data["avg_health_score"] <= 100


@pytest.mark.asyncio
async def test_software_summary(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/software-summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["software_name"] == "Acme Platform"
    assert data[0]["latest_score"] is not None


@pytest.mark.asyncio
async def test_health_trends(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/health-trends", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "date" in data[0]
    assert "score" in data[0]


@pytest.mark.asyncio
async def test_issue_categories(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/issue-categories", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "category" in data[0]
    assert "percentage" in data[0]
    # Percentages should sum to ~100
    total_pct = sum(d["percentage"] for d in data)
    assert 99 <= total_pct <= 101


@pytest.mark.asyncio
async def test_support_burden(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/support-burden", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["total_signals"] > 0
    assert "burden_score" in data[0]


@pytest.mark.asyncio
async def test_event_types(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/event-types", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "event_type" in data[0]


@pytest.mark.asyncio
async def test_source_distribution(client: AsyncClient, auth_headers: dict, seeded_data: str):
    response = await client.get("/api/v1/analytics/source-distribution", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    source_types = [d["source_type"] for d in data]
    assert "jira" in source_types


@pytest.mark.asyncio
async def test_analytics_no_auth(client: AsyncClient):
    response = await client.get("/api/v1/analytics/overview")
    assert response.status_code in (401, 403)
