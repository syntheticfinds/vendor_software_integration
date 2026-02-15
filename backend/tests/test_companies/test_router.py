import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_company(client: AsyncClient, registered_company: dict, auth_headers: dict):
    company_id = registered_company["company"]["id"]
    response = await client.get(f"/api/v1/companies/{company_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["company_name"] == "Test Corp"


@pytest.mark.asyncio
async def test_get_company_forbidden(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/companies/{fake_id}", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_company(client: AsyncClient, registered_company: dict, auth_headers: dict):
    company_id = registered_company["company"]["id"]
    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        headers=auth_headers,
        json={"company_name": "Updated Corp", "industry": "Finance"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Updated Corp"
    assert data["industry"] == "Finance"


@pytest.mark.asyncio
async def test_update_company_partial(client: AsyncClient, registered_company: dict, auth_headers: dict):
    company_id = registered_company["company"]["id"]
    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        headers=auth_headers,
        json={"company_size": "enterprise"},
    )
    assert response.status_code == 200
    assert response.json()["company_size"] == "enterprise"


@pytest.mark.asyncio
async def test_update_company_forbidden(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"/api/v1/companies/{fake_id}",
        headers=auth_headers,
        json={"company_name": "Hacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_auth_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/companies/00000000-0000-0000-0000-000000000000")
    assert response.status_code in (401, 403)
