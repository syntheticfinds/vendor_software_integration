import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_software(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={
            "vendor_name": "Slack",
            "software_name": "Slack Messaging",
            "intended_use": "Team communication",
            "jira_workspace": "acme.atlassian.net",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["vendor_name"] == "Slack"
    assert data["software_name"] == "Slack Messaging"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_create_duplicate_software(client: AsyncClient, auth_headers: dict):
    payload = {
        "vendor_name": "DupVendor",
        "software_name": "DupSoftware",
    }
    await client.post("/api/v1/software", headers=auth_headers, json=payload)
    response = await client.post("/api/v1/software", headers=auth_headers, json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_software(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={"vendor_name": "Vendor1", "software_name": "Soft1"},
    )
    response = await client.get("/api/v1/software", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_list_software_with_search(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={"vendor_name": "SearchVendor", "software_name": "SearchSoft"},
    )
    response = await client.get("/api/v1/software?search=SearchVendor", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_software_by_id(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={"vendor_name": "GetVendor", "software_name": "GetSoft"},
    )
    software_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/software/{software_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["vendor_name"] == "GetVendor"


@pytest.mark.asyncio
async def test_update_software(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={"vendor_name": "UpdateVendor", "software_name": "UpdateSoft"},
    )
    software_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/software/{software_id}",
        headers=auth_headers,
        json={"intended_use": "CI/CD pipeline"},
    )
    assert response.status_code == 200
    assert response.json()["intended_use"] == "CI/CD pipeline"


@pytest.mark.asyncio
async def test_delete_software(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/software",
        headers=auth_headers,
        json={"vendor_name": "DeleteVendor", "software_name": "DeleteSoft"},
    )
    software_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/software/{software_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's archived
    get_resp = await client.get(f"/api/v1/software/{software_id}", headers=auth_headers)
    assert get_resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_software_tenant_isolation(client: AsyncClient):
    # Register company A
    resp_a = await client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Company A",
            "primary_email": "a@company-a.com",
            "password": "password123",
        },
    )
    headers_a = {"Authorization": f"Bearer {resp_a.json()['access_token']}"}

    # Register company B
    resp_b = await client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Company B",
            "primary_email": "b@company-b.com",
            "password": "password123",
        },
    )
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    # Company A creates software
    create_resp = await client.post(
        "/api/v1/software",
        headers=headers_a,
        json={"vendor_name": "SecretVendor", "software_name": "SecretSoft"},
    )
    software_id = create_resp.json()["id"]

    # Company B cannot see Company A's software
    get_resp = await client.get(f"/api/v1/software/{software_id}", headers=headers_b)
    assert get_resp.status_code == 404

    # Company B's list doesn't include Company A's software
    list_resp = await client.get("/api/v1/software", headers=headers_b)
    assert list_resp.json()["total"] == 0
