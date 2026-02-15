import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_scan_trigger(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/monitoring/scan",
        headers=auth_headers,
        json={"source": "mock"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "emails_loaded"
    assert data["queued_emails"] > 0


@pytest.mark.asyncio
async def test_scan_without_auth(client: AsyncClient):
    response = await client.post("/api/v1/monitoring/scan", json={"source": "mock"})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_detections_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/monitoring/detections", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_detections_with_filter(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/monitoring/detections?status=pending",
        headers=auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_detection_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/monitoring/detections/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_detection_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"/api/v1/monitoring/detections/{fake_id}",
        headers=auth_headers,
        json={"status": "confirmed"},
    )
    assert response.status_code == 404
