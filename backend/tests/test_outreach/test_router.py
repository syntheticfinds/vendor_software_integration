import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_campaign(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "vendor_name": "Acme",
            "software_name": "Acme Platform",
            "message_template": "Hi, we'd like to discuss {software} by {vendor}.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["vendor_name"] == "Acme"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_list_campaigns(client: AsyncClient, auth_headers: dict):
    # Create one
    await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "vendor_name": "Acme",
            "software_name": "Acme Platform",
            "message_template": "Test message",
        },
        headers=auth_headers,
    )
    response = await client.get("/api/v1/outreach/campaigns", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_get_campaign(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "vendor_name": "Acme",
            "software_name": "Acme Platform",
            "message_template": "Test",
        },
        headers=auth_headers,
    )
    campaign_id = create_res.json()["id"]

    response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == campaign_id


@pytest.mark.asyncio
async def test_campaign_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/outreach/campaigns/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_campaign(client: AsyncClient, auth_headers: dict):
    # Create software registration
    await client.post(
        "/api/v1/software",
        json={"vendor_name": "Acme", "software_name": "Acme Platform", "intended_use": "test"},
        headers=auth_headers,
    )

    # Create campaign
    create_res = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "vendor_name": "Acme",
            "software_name": "Acme Platform",
            "message_template": "Hello about {software} by {vendor}",
        },
        headers=auth_headers,
    )
    campaign_id = create_res.json()["id"]

    # Send
    response = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/send",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["messages_sent"] >= 1


@pytest.mark.asyncio
async def test_campaign_messages(client: AsyncClient, auth_headers: dict):
    # Create software + campaign + send
    await client.post(
        "/api/v1/software",
        json={"vendor_name": "TestVendor", "software_name": "TestApp", "intended_use": "test"},
        headers=auth_headers,
    )
    create_res = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "vendor_name": "TestVendor",
            "software_name": "TestApp",
            "message_template": "Test outreach for {software}",
        },
        headers=auth_headers,
    )
    campaign_id = create_res.json()["id"]
    await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/send", headers=auth_headers)

    response = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/messages",
        headers=auth_headers,
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) >= 1
    assert messages[0]["status"] == "sent"


@pytest.mark.asyncio
async def test_outreach_no_auth(client: AsyncClient):
    response = await client.get("/api/v1/outreach/campaigns")
    assert response.status_code in (401, 403)
