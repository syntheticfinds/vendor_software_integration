import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_public_index_empty(client: AsyncClient):
    """Public endpoint — no auth needed."""
    response = await client.get("/api/v1/portal/software-index")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_rebuild_index(client: AsyncClient):
    response = await client.post("/api/v1/portal/rebuild-index")
    assert response.status_code == 200
    assert response.json()["status"] == "rebuilt"


@pytest.mark.asyncio
async def test_software_not_in_index(client: AsyncClient):
    response = await client.get("/api/v1/portal/software/Acme/Platform")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_no_data(client: AsyncClient):
    response = await client.post(
        "/api/v1/portal/chat",
        json={"message": "Tell me about Jira"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "session_token" in data
    assert len(data["session_token"]) > 0


@pytest.mark.asyncio
async def test_chat_session_continuity(client: AsyncClient):
    # First message
    r1 = await client.post(
        "/api/v1/portal/chat",
        json={"message": "Hello"},
    )
    token = r1.json()["session_token"]

    # Second message with same session
    r2 = await client.post(
        "/api/v1/portal/chat",
        json={"message": "What software is popular?", "session_token": token},
    )
    assert r2.json()["session_token"] == token
