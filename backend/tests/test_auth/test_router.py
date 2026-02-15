import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Acme Inc",
            "industry": "Technology",
            "company_size": "smb",
            "primary_email": "hello@acme.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["company"]["company_name"] == "Acme Inc"
    assert data["company"]["primary_email"] == "hello@acme.com"
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "company_name": "Dup Corp",
        "primary_email": "dup@test.com",
        "password": "password123",
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_password_too_short(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "company_name": "Short Pass Corp",
            "primary_email": "short@test.com",
            "password": "abc",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, registered_company: dict):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@testcorp.com", "password": "securepass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["company_name"] == "Test Corp"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, registered_company: dict):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@testcorp.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "password123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Test Corp"


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, registered_company: dict):
    refresh_token = registered_company["refresh_token"]
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    assert response.status_code == 401
